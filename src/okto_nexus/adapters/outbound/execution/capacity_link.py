"""Capacity port over the existing authenticated, single-reader executor link.

The inbound link routes results here after authenticating the frame. This
adapter owns only bounded wire requests; attempts/reservations remain durable
in the Server use case and Core ledger. A timeout never invents a new attempt.
"""
from __future__ import annotations

import asyncio
import math
import secrets
from dataclasses import asdict

from nexus_connector_core import (
    CAPACITY_CONTRACT_REVISION, CapacityRequest, CapacityAssessment,
    CapacityReservation, CapacityConsumption, CoreError,
    encode_capacity_frame, decode_capacity_frame,
)

from ....application.execution_leases import ExecutionChannel


class CapacityLinkClient:
    def __init__(self, *, channel: ExecutionChannel, send, verify, capabilities,
                 request_timeout=5.0, max_requests=8, max_recovery_requests=4):
        if isinstance(capabilities, (str, bytes)) or CAPACITY_CONTRACT_REVISION not in capabilities:
            raise CoreError('CAPACITY_PROTOCOL_UNSUPPORTED', 'capacity_link')
        if (not isinstance(channel, ExecutionChannel) or not callable(send) or not callable(verify)
                or type(request_timeout) not in (int, float) or not math.isfinite(request_timeout)
                or not 0 < request_timeout <= 60
                or any(type(n) is not int or not 1 <= n <= 4096 for n in (max_requests, max_recovery_requests))):
            raise ValueError('Invalid capacity link composition.')
        self.channel = channel
        self._send, self._verify, self._timeout = send, verify, request_timeout
        self._limits = {False: max_requests, True: max_recovery_requests}
        self._pending = {}
        self._producers = {}
        self._closed = False

    def disconnect(self):
        """Fence immediately; admitted sends remain owned until they finish."""
        self._closed = True
        for future, _ in self._pending.values():
            if not future.done():
                future.set_exception(CoreError('NEEDS_RECONCILIATION', 'capacity_disconnect', possible_effect=True))

    async def aclose(self):
        self.disconnect()
        if self._producers:
            await asyncio.shield(asyncio.gather(*tuple(self._producers), return_exceptions=True))

    def accept_result(self, frame) -> bool:
        frame = decode_capacity_frame(encode_capacity_frame(frame))
        if (frame['type'] != 'capacity.result'
                or any(frame[key] != value for key, value in asdict(self.channel).items())):
            raise CoreError('SCOPE_MISMATCH', 'capacity_result')
        if self._closed:
            return False
        pending = self._pending.get(frame['request_id'])
        if pending is None:
            # Late result after the bounded observer expired. Durable get of
            # the original attempt is authoritative, never a second reserve.
            return False
        future, request = pending
        if frame['request_hash'] != request.request_hash:
            raise CoreError('RESERVATION_CONFLICT', 'capacity_result')
        if future.done():
            return False
        future.set_result(frame)
        return True

    async def _call(self, action, request, **fields):
        if type(request) is not CapacityRequest:
            raise ValueError('Invalid capacity request.')
        if (request.scope.server_id, request.scope.executor_id) != (self.channel.server_id, self.channel.executor_id):
            raise CoreError('NOT_AUTHORIZED', 'capacity_link_scope')
        if self._closed:
            raise CoreError('RECOVERING', 'capacity_link')
        recovery = action in ('get', 'release')
        if sum(value == recovery for value in self._producers.values()) >= self._limits[recovery]:
            raise CoreError('STALE_OBSERVATION', 'capacity_link_budget')
        frame = dict(contract_revision=CAPACITY_CONTRACT_REVISION, **asdict(self.channel),
            type='capacity.' + action, request_id='cap_' + secrets.token_hex(16), request=request.to_dict(), **fields)
        raw = encode_capacity_frame(frame).decode('utf-8')
        future = asyncio.get_running_loop().create_future()
        self._pending[frame['request_id']] = (future, request)

        async def exchange():
            send_started = False
            try:
                await self._verify(request, action=action)
                if self._closed:
                    raise CoreError('RECOVERING', 'capacity_link')
                send_started = True
                await self._send(raw)
                response = await asyncio.wait_for(asyncio.shield(future), self._timeout)
                await self._verify(request, action=action)
                if self._closed:
                    raise CoreError('NEEDS_RECONCILIATION', 'capacity_disconnect', possible_effect=True)
                if response['result_type'] == 'reservation':
                    return CapacityReservation.from_dict(response['result'])
                if response['result_type'] == 'assessment':
                    return CapacityAssessment.from_dict(response['result'])
                if action != 'get':
                    raise CoreError('NEEDS_RECONCILIATION', 'capacity_missing_result', possible_effect=True)
                return None
            except Exception as error:
                if send_started:
                    raise CoreError('NEEDS_RECONCILIATION', 'capacity_response', possible_effect=True) from error
                raise
            finally:
                self._pending.pop(frame['request_id'], None)
                if not future.done():
                    future.cancel()
                elif not future.cancelled():
                    future.exception()

        task = asyncio.create_task(exchange(), name='capacity-link-request')
        self._producers[task] = recovery
        def done(completed):
            self._producers.pop(completed, None)
            if not completed.cancelled():
                completed.exception()
        task.add_done_callback(done)
        # asyncio.wait does not cancel a send/authority producer that is slow
        # or ignores cancellation. It stays charged until actually completed.
        completed, _ = await asyncio.wait({task}, timeout=self._timeout)
        if not completed:
            raise CoreError('NEEDS_RECONCILIATION', 'capacity_observation', possible_effect=True)
        return task.result()

    async def assess_capacity(self, request):
        return await self._call('assess', request)

    async def try_reserve_capacity(self, request):
        return await self._call('reserve', request)

    @staticmethod
    def _reservation(result):
        if isinstance(result, CapacityAssessment):
            reason = result.reason if result.reason != 'AVAILABLE' else 'NEEDS_RECONCILIATION'
            raise CoreError(reason, 'capacity_result', possible_effect=reason == 'NEEDS_RECONCILIATION')
        return result

    async def get_capacity_reservation(self, request):
        return self._reservation(await self._call('get', request))

    async def consume_capacity(self, request, reservation_id, admitted: CapacityConsumption):
        return self._reservation(await self._call('consume', request, reservation_id=reservation_id,
                                                   consumption=admitted.to_dict()))

    async def release_capacity(self, request, reservation_id, reason):
        return self._reservation(await self._call('release', request, reservation_id=reservation_id, reason=reason))
