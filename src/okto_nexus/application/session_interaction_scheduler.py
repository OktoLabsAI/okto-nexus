"""Advance durable session inputs in bounded pages under the serve owner."""

import asyncio
import logging
import time

from nexus_connector_core import CoreError

from ..domain.execution.keys import SessionKey, SessionOwnerGeneration
from ..domain.session_interaction import InputScope
from ..errors import OktoNexusError
from .session_interaction_capacity import advance_input_capacity

_LOG = logging.getLogger(__name__)


class SessionInputScheduler:
    def __init__(self, *, factory, access, availability, authority_fence, current_capability_revision,
                 fresh_publications, execution_ready, acquisition_enabled, page_size=8, interval=1,
                 monotonic=time.monotonic):
        self.factory = factory
        self.availability = availability
        self.execution_ready = execution_ready
        self.options = {'factory': factory, 'access': access, 'availability': availability,
            'authority_fence': authority_fence, 'current_capability_revision': current_capability_revision,
            'fresh_publications': fresh_publications, 'acquisition_enabled': acquisition_enabled}
        self.page_size, self.interval, self.monotonic = page_size, interval, monotonic
        self._after = ('', '', '', 0)
        self._next_scan = 0
        self._task = None
        self._closed = False

    @property
    def pending_count(self):
        return int(self._task is not None and not self._task.done())

    def tick(self):
        if self._closed or self.pending_count or self.monotonic() < self._next_scan:
            return
        if not self.availability.enabled or not self.execution_ready:
            return
        self._task = asyncio.create_task(self._advance_page(), name='session-input-dispatch')

    def begin_shutdown(self):
        self._closed = True

    async def aclose(self, *, timeout=1):
        self.begin_shutdown()
        if self._task is not None:
            _, pending = await asyncio.wait((self._task,), timeout=timeout)
            return len(pending)
        return 0

    def _read_page(self):
        with self.factory.unit_of_work(write=False) as uow:
            return uow.connection.execute("""
                SELECT DISTINCT i.server_id,i.executor_id,i.session_id,i.owner_generation,
                       i.binding_id,i.workspace_id,i.workspace_binding_id,i.agent_id
                FROM session_interaction_inputs i
                JOIN execution_sessions s USING(server_id,executor_id,session_id)
                JOIN execution_executors e USING(server_id,executor_id)
                WHERE (i.server_id,i.executor_id,i.session_id,i.owner_generation)>(?,?,?,?)
                  AND e.control_state IN ('CONTROL_READY','RECOVERING') AND e.revoked_at IS NULL
                  AND (
                      (? AND i.status='QUEUED' AND i.owner_generation=s.owner_generation AND s.lifecycle_state='READY'
                       AND s.lease_state='ACTIVE' AND e.control_state='CONTROL_READY')
                      OR i.capacity_state IN ('WAITING_CONSUMPTION','NEEDS_RECONCILIATION')
                      OR (i.capacity_state='CONSUMED' AND i.status='REFUSED_BEFORE_SEND'
                          AND EXISTS (SELECT 1 FROM execution_unsent_dispatch_proofs p
                              WHERE p.server_id=i.server_id AND p.executor_id=i.executor_id
                                AND p.operation_id=i.operation_id))
                      OR EXISTS (SELECT 1 FROM session_interaction_capacity_attempts a
                          WHERE a.server_id=i.server_id AND a.executor_id=i.executor_id AND a.session_id=i.session_id
                            AND a.input_id=i.input_id AND a.state='PREPARED' AND a.resolved_at IS NULL)
                  )
                ORDER BY i.server_id,i.executor_id,i.session_id,i.owner_generation LIMIT ?
            """, (*self._after, self.options['acquisition_enabled'], self.page_size)).fetchall()

    async def _advance_page(self):
        try:
            page = await asyncio.to_thread(self._read_page)
            for row in page:
                if self._closed:
                    break
                self._after = tuple(row)[:4]
                scope = InputScope(SessionKey(*self._after[:3]), SessionOwnerGeneration(row['owner_generation']),
                    row['binding_id'], row['workspace_id'], row['workspace_binding_id'], row['agent_id'])
                try:
                    await advance_input_capacity(scope=scope, remote_ready=self.execution_ready, **self.options)
                except (CoreError, OktoNexusError) as error:
                    # A later pass observes the same attempt. A scheduling
                    # failure says nothing about possible native effects.
                    _LOG.debug('Session input advancement deferred: code=%s', error.code)
            if len(page) < self.page_size:
                self._after = ('', '', '', 0)
        except Exception as error:  # noqa: BLE001 - keep the serve owner after a failed scan
            _LOG.warning('Session input scan failed: type=%s', type(error).__name__)
        finally:
            self._next_scan = self.monotonic() + self.interval
