"""One owned, bounded outbox sender for an authenticated executor connection."""

from __future__ import annotations

import asyncio
import time
from functools import partial

from ..adapters.outbound.sqlite.execution_dispatch_ownership import (
    recover_fenced_reservations, reject_unsent_dispatch, release_dispatch_owner,
)
from ..errors import ErrorCode, OktoNexusError
from .execution_dispatch import (
    begin_execution_send, release_unsent_dispatch, reserve_execution_dispatch,
)


class ExecutionDispatchPump:
    """Keep database producers owned through cancellation and connection close.

    The transport supplies one shared writer lock for frames and replies.
    Reservation occurs before waiting for that lock; authority is revalidated
    after it. The reader remains independent. A socket write is never a durable
    executor ACK. SENDING is retained until receipt or reconciliation.
    """

    def __init__(self, *, factory, channel, access, fresh_publications,
                 send, send_lock, verify_link, close_link, poll_interval=0.1, resolve_native_input=None,
                 retained_operations=None, wake_deliveries=None, idle_interval=1.0):
        self.factory, self.channel, self.access = factory, channel, access
        self.fresh_publications = fresh_publications
        self.send, self.send_lock = send, send_lock
        self.verify_link, self.close_link = verify_link, close_link
        self.poll_interval = poll_interval
        # After an empty scan, the pump scans again only when the store
        # committed a change, or when this long has passed (time-based work).
        self.idle_interval = max(idle_interval, poll_interval)
        self._idle_version = self._idle_since = None
        self.resolve_native_input = resolve_native_input
        self.retained_operations = retained_operations or (lambda: ())
        self.wake_deliveries = wake_deliveries or (lambda: None)
        self._stopping = asyncio.Event()
        self.task = None
        self.error = None
        self.close_error = None

    def start(self):
        if self.task is not None:
            raise RuntimeError('The dispatch owner has already started.')
        self.task = asyncio.create_task(self._run(), name=f'r4-dispatch-{self.channel.connection_id}')

    async def stop(self):
        self._stopping.set()
        if self.task is not None:
            await asyncio.shield(self.task)

    async def _database(self, function, **kwargs):
        # A cancelled waiter must not leave an unobserved transaction that can
        # reserve or fence an operation after its connection has been released.
        delay = self.poll_interval
        while True:
            task = asyncio.create_task(asyncio.to_thread(partial(function, **kwargs)))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                await asyncio.shield(task)
                raise
            except OktoNexusError as error:
                # Admission/BEGIN contention has no committed effect. Retry
                # this database boundary, never the native send. Closing the
                # shared local executor here would strand every healthy agent.
                if error.code != ErrorCode.DB_ERROR or not error.retryable or self._stopping.is_set():
                    raise
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                delay = min(max(delay * 2, 0.01), 1.0)

    def _store_version(self):
        probe = getattr(self.factory, 'data_version', None)
        try:
            return probe() if probe is not None else None
        except Exception:
            return None

    def _scan_due(self):
        """False while the last scan was empty and nothing committed since."""
        if self._idle_version is None or time.monotonic() - self._idle_since >= self.idle_interval:
            return True
        return self._store_version() != self._idle_version

    async def _run(self):
        reservation = None
        try:
            await self._database(recover_fenced_reservations, factory=self.factory, channel=self.channel)
            while not self._stopping.is_set():
                if not self._scan_due():
                    try:
                        await asyncio.wait_for(self._stopping.wait(), timeout=self.poll_interval)
                    except asyncio.TimeoutError:
                        pass
                    continue
                version = self._store_version()
                await self._database(self.verify_link)
                reservation = await self._database(reserve_execution_dispatch,
                    factory=self.factory, server_id=self.channel.server_id,
                    executor_id=self.channel.executor_id, remote_ready=True, channel=self.channel,
                    retained_operations=tuple(self.retained_operations()))
                # An empty scan is idle only when a change probe exists. The
                # version was read before the scan, so a later commit shows.
                self._idle_version = version if reservation is None else None
                self._idle_since = time.monotonic()
                if reservation is None:
                    try:
                        await asyncio.wait_for(self._stopping.wait(), timeout=self.poll_interval)
                    except asyncio.TimeoutError:
                        pass
                    continue
                # After an embedded owner restart, queued work can be reserved
                # before the new inventory observation is published. Keep it
                # pending until that observation exists; rejecting it here
                # would turn a transient startup gap into a terminal failure.
                if self.fresh_publications.get((self.channel.server_id, self.channel.executor_id)) is None:
                    await self._database(release_unsent_dispatch, factory=self.factory, reservation=reservation)
                    reservation = None
                    try:
                        await asyncio.wait_for(self._stopping.wait(), timeout=self.poll_interval)
                    except asyncio.TimeoutError:
                        pass
                    continue
                async with self.send_lock:
                    if self._stopping.is_set():
                        break
                    # Link ticket and lane authority are separate gates. Check
                    # both after the potentially blocking writer-lock wait.
                    await self._database(self.verify_link)
                    try:
                        authorized = await self._database(begin_execution_send,
                            factory=self.factory, reservation=reservation, remote_ready=True,
                            fresh_publications=self.fresh_publications, access=self.access, channel=self.channel,
                            resolve_native_input=self.resolve_native_input)
                    except OktoNexusError as error:
                        if (error.code == ErrorCode.CONFLICT and
                                (error.details or {}).get('transient') == 'inventory_not_fresh'):
                            await self._database(release_unsent_dispatch, factory=self.factory,
                                                 reservation=reservation)
                            reservation = None
                            try:
                                await asyncio.wait_for(self._stopping.wait(), timeout=self.poll_interval)
                            except asyncio.TimeoutError:
                                pass
                            continue
                        if error.code not in {ErrorCode.CONFLICT, ErrorCode.PERMISSION_DENIED,
                                              ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR,
                                              "AUTHORIZED_INPUT_UNAVAILABLE", "APPROVAL_AUTHORITY_REQUIRED"}:
                            raise
                        await self._database(reject_unsent_dispatch, factory=self.factory,
                                             reservation=reservation, error=error)
                        # Rejection may settle a never-sent initial message.
                        # Its logical queue must see the committed proof and
                        # current authority without waiting for a recovery tick.
                        self.wake_deliveries()
                        reservation = None
                        continue
                    # No cancellation or disconnect path can put this attempt
                    # back in PENDING after begin_execution_send committed.
                    reservation = None
                    if self._stopping.is_set():
                        break
                    await self.send(authorized.frame)
        except Exception as error:
            self.error = error
            try:
                await self.close_link()
            except Exception as close_error:
                # The peer may already be gone. Retain the failure for the
                # owner, then finish durable cleanup instead of skipping it.
                self.close_error = close_error
        finally:
            # Storage errors may leave a durable fence; never fake cleanup or
            # a successful send when this transaction cannot be committed.
            if reservation is not None:
                try:
                    await self._database(release_unsent_dispatch, factory=self.factory, reservation=reservation)
                except OktoNexusError as error:
                    if error.code != ErrorCode.CONFLICT:
                        raise
            await self._database(release_dispatch_owner, factory=self.factory, channel=self.channel)
