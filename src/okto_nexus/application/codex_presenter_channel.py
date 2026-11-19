"""Serve bounded history reads on one authenticated Codex presentation."""

import asyncio
from contextlib import asynccontextmanager

from ..domain.runtime_context import RuntimeRequestContext
from ..domain.session_interaction import InputDeliveryState
from ..errors import ErrorCode, OktoNexusError
from .codex_presenter_history import (
    read_codex_history_snapshot,
    read_codex_history_updates,
    read_codex_input_start,
)
from .codex_presenter_requests import codex_history_page
from .codex_viewer_protocol import CodexViewerContext
from .session_interaction_controls import read_human_interrupt_receipt
from .session_interaction_receipts import read_session_input_receipt


class CodexPresenterHistoryChannel:
    """Keep one capture for the channel's cursor lifetime."""

    def __init__(self, *, broker, prove_owner, access, scope, author, attachment, audience, channel_id):
        self._broker = broker
        self._prove_owner = prove_owner
        self._access = access
        self._subject = {'scope': scope, 'author': author, 'attachment': attachment,
                         'audience': audience, 'channel_id': channel_id}
        self._snapshot_lock = asyncio.Lock()
        self._owner = None
        self._snapshot = None
        self._update_position = None

    async def _authorize(self):
        await asyncio.to_thread(self._broker.require_active, **self._subject)

    @asynccontextmanager
    async def _bound_owner(self):
        async with self._snapshot_lock:
            await self._authorize()
            current = await self._prove_owner(self._subject['scope'])
            if current[0].codex_thread_id is None:
                raise OktoNexusError(ErrorCode.CONFLICT, 'The exact Codex thread is unavailable.', {})
            if self._owner is not None and current != self._owner:
                raise OktoNexusError(ErrorCode.CONFLICT, 'The presentation owner changed.', {})
            yield current[0]
            if current != await self._prove_owner(self._subject['scope']):
                raise OktoNexusError(ErrorCode.CONFLICT, 'The presentation owner changed.', {})
            await self._authorize()
            self._owner = current

    async def page(self, *, method, params):
        async with self._bound_owner() as mapping:
            request = codex_history_page(method=method, params=params, native_thread_id=mapping.codex_thread_id)
            snapshot = self._snapshot if self._snapshot is not None else await self._capture(mapping)
            result = snapshot.page(request)
        self._snapshot = snapshot
        return result

    async def verify_input_thread(self, thread_id):
        async with self._bound_owner() as mapping:
            if thread_id != mapping.codex_thread_id:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The exact Codex thread is unavailable.', {})

    async def input_delivery(self, input_id):
        if self._subject['attachment'].access != 'write':
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The presentation cannot read input delivery.', {})

        def read(mapping):
            factory = self._broker.factory
            with self._broker.authority_fence() as human:
                receipt = read_session_input_receipt(factory, access=self._access, resolve_human=human,
                    scope=mapping.scope, author=self._subject['author'], input_id=input_id)
            start_can_be_observed = receipt.status in (InputDeliveryState.DISPATCHING, InputDeliveryState.ACCEPTED_NATIVE)
            turn = (read_codex_input_start(factory, mapping=mapping, operation_id=receipt.operation_id)
                    if start_can_be_observed and receipt.operation_id else None)
            return {'input_id': receipt.input_id, 'status': receipt.status, 'turn': turn}

        async with self._bound_owner() as mapping:
            return await asyncio.to_thread(read, mapping)

    async def interrupt_receipt(self, *, thread_id, intent, current_interrupt_target):
        if self._subject['attachment'].access != 'write':
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The presentation cannot read interrupt receipts.', {})

        def read(mapping):
            with self._broker.authority_fence() as human:
                operation = read_human_interrupt_receipt(self._broker.factory, access=self._access, resolve_human=human,
                    scope=mapping.scope, author=self._subject['author'], client_intent_id=intent,
                    current_interrupt_target=current_interrupt_target)
            return {'target_status': operation['interrupt']['target_status'],
                    'refused': bool(operation['error'] and not operation['possible_effect'])}

        async with self._bound_owner() as mapping:
            if thread_id != mapping.codex_thread_id:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The exact Codex thread is unavailable.', {})
            return await asyncio.to_thread(read, mapping)

    async def viewer_context(self, read_context, *, can_follow=False):
        async with self._bound_owner() as mapping:
            snapshot = self._snapshot
            context = await read_context(self._subject['scope'])
            if not isinstance(context, CodexViewerContext) or context.thread_id != mapping.codex_thread_id:
                raise OktoNexusError(ErrorCode.CONFLICT, 'The exact Codex viewer context is unavailable.', {})
            if context.status == 'active':
                if not can_follow:
                    raise OktoNexusError(ErrorCode.CONFLICT, 'The viewer cannot follow the active Codex turn.', {})
                if snapshot is None:
                    snapshot = await self._capture(mapping)
                if snapshot.active_turn is None:
                    raise OktoNexusError(ErrorCode.CONFLICT, 'The active Codex turn is not yet recorded.', {})
        self._snapshot = snapshot
        return context

    async def updates(self):
        async with self._bound_owner() as mapping:
            snapshot = self._snapshot
            if snapshot is None:
                raise OktoNexusError(ErrorCode.CONFLICT, 'Read the presentation history before following it.', {})
            position = self._update_position
            if position is None:
                position = snapshot.committed_through, snapshot.active_turn
            sequence, turn_id, result = await asyncio.to_thread(
                read_codex_history_updates, self._broker.factory, mapping=mapping, access=self._access,
                context=RuntimeRequestContext('operator', 'operator_session', trusted_local_operator=True),
                after_sequence=position[0], active_turn=position[1])
        self._update_position = sequence, turn_id
        return result

    async def _capture(self, mapping):
        context = RuntimeRequestContext('operator', 'operator_session', trusted_local_operator=True)
        return await asyncio.to_thread(read_codex_history_snapshot, self._broker.factory,
                                       mapping=mapping, access=self._access, context=context)
