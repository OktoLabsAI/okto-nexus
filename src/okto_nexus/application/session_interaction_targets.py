"""Identify a controllable Codex turn from the current canonical stream."""

import hashlib
import json
from dataclasses import dataclass

from nexus_connector_core import get_control_targeting

from ..adapters.outbound.sqlite.session_interaction import _scope_params
from ..domain.attention import digest
from ..domain.session_interaction import InputScope
from .execution_native_session_mapping import read_managed_native_session


@dataclass(frozen=True, slots=True)
class ExactNativeTurn:
    native_id: str
    operation_id: str
    revision: str
    stream_epoch: str


def active_native_turn(uow, scope: InputScope, *, current_next_turn_revision) -> ExactNativeTurn | None:
    """A committed start must belong to one current, still-dispatched turn.

    The result is evidence for admission, with a separate check at the send
    cut. The Core adapter still fences the actual native turn before writing.
    """
    capability = current_next_turn_revision(uow, scope)
    if capability is None:
        return None
    mapping = read_managed_native_session(uow, scope)
    if mapping is None or mapping.codex_thread_id is None or mapping.stream_epoch is None:
        return None
    conn = uow.connection
    scope_params = _scope_params(scope)
    active = conn.execute("""
        SELECT o.operation_id, s.stream_epoch, w.committed_contiguous
        FROM execution_sessions s
        JOIN execution_executors x USING (server_id, executor_id)
        JOIN execution_bindings b ON b.server_id=s.server_id AND b.executor_id=s.executor_id
          AND b.binding_id=s.binding_id
        JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id
        JOIN execution_event_watermarks w ON w.server_id=s.server_id AND w.executor_id=s.executor_id
          AND w.session_id=s.session_id AND w.stream_epoch=s.stream_epoch
        JOIN execution_operations o ON o.server_id=s.server_id AND o.executor_id=s.executor_id
          AND o.session_id=s.session_id
        JOIN execution_dispatch_outbox d ON d.server_id=o.server_id AND d.executor_id=o.executor_id
          AND d.operation_id=o.operation_id
        JOIN execution_receipts r ON r.server_id=o.server_id AND r.executor_id=o.executor_id
          AND r.operation_id=o.operation_id AND r.receipt_revision=d.last_receipt_revision
        LEFT JOIN execution_results result ON result.server_id=o.server_id AND result.executor_id=o.executor_id
          AND result.operation_id=o.operation_id
        WHERE s.server_id=:server_id AND s.executor_id=:executor_id AND s.session_id=:session_id
          AND s.owner_generation=:owner_generation AND s.binding_id=:binding_id AND s.workspace_id=:workspace_id
          AND s.workspace_binding_id=:workspace_binding_id AND e.adapter_id='codex_app_server'
          AND w.gap_state='none'
          AND o.action='turn.submit' AND o.admission_state='DISPATCHED' AND o.binding_id=:binding_id
          AND o.workspace_id=:workspace_id AND o.workspace_binding_id=:workspace_binding_id
          AND o.subject_agent_id=:agent_id AND d.dispatch_state='DISPATCHED'
          AND r.stage IN ('SUBMITTED','ACCEPTED') AND r.source_connection_id=x.owner_instance_id
          AND r.source_connection_generation=x.generation AND result.terminal_sequence IS NULL
          AND json_extract(o.expected_revisions_json,'$.session_owner_generation')=:owner_generation
          AND NOT EXISTS (
              SELECT 1 FROM execution_event_ingress failure
              WHERE failure.server_id=s.server_id AND failure.executor_id=s.executor_id
                AND failure.session_id=s.session_id AND failure.stream_epoch=s.stream_epoch
                AND failure.event_type='error' AND failure.sequence<=w.committed_contiguous
                AND json_extract(failure.payload_json,'$.native_type')='core.event_pump_failed'
          )
        LIMIT 2
    """, scope_params).fetchall()
    if len(active) != 1:
        return None
    selected = active[0]
    started = conn.execute("""
        SELECT payload_json,event_hash,sequence
        FROM execution_event_ingress
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
          AND stream_epoch=:stream_epoch AND sequence<=:committed_contiguous AND event_type='turn_state'
          AND json_extract(payload_json,'$.operation_id')=:operation_id
          AND json_extract(payload_json,'$.native_type')='turn/started'
          AND json_extract(payload_json,'$.payload.delivery_phase')='started'
        LIMIT 2
    """, {**scope_params, **dict(selected)}).fetchall()
    if len(started) != 1:
        return None
    start = started[0]
    raw = start['payload_json']
    if 'sha256:' + hashlib.sha256(raw.encode()).hexdigest() != start['event_hash']:
        return None
    payload = json.loads(raw)['payload']
    turn = payload.get('turn_id')
    details = payload.get('turn')
    if (not isinstance(turn, str) or not 1 <= len(turn) <= 160 or not turn.isprintable()
            or 'REDACTED' in turn or payload.get('thread_id') != mapping.codex_thread_id
            or payload.get('threadId') != mapping.codex_thread_id
            or not isinstance(details, dict) or details.get('id') != turn):
        return None
    revision = 'sha256:' + digest({'action': 'exact_native_turn.v1', 'capability': capability,
        'operation_id': selected['operation_id'], 'epoch': selected['stream_epoch'], 'start': start['event_hash'],
        'thread_configuration': mapping.codex_configuration_hash})
    return ExactNativeTurn(turn, selected['operation_id'], revision, selected['stream_epoch'])


def interrupt_revision(uow, scope: InputScope, native_turn_id: str, *, current_next_turn_revision) -> str | None:
    turn = active_native_turn(uow, scope, current_next_turn_revision=current_next_turn_revision)
    if turn is None or turn.native_id != native_turn_id:
        return None
    return turn.revision


def steer_effect_revisions(turn: ExactNativeTurn) -> tuple[str, str] | None:
    """Describe the installed Core contract for this proven Codex turn."""
    contract = get_control_targeting('codex_app_server', 'turn.steer')
    if not (contract.supported and contract.native_turn_id == 'required' and contract.requires_active_run
            and contract.steer_timing == 'IMMEDIATE'):
        return None
    capability = 'sha256:' + digest({'target': turn.revision, 'contract': contract.to_dict()})
    effect = 'sha256:' + digest({'capability': capability, 'effect': 'same_turn'})
    return capability, effect


def steer_revisions(uow, scope: InputScope, native_turn_id: str, *, current_next_turn_revision) -> tuple[str, str] | None:
    turn = active_native_turn(uow, scope, current_next_turn_revision=current_next_turn_revision)
    if turn is None or turn.native_id != native_turn_id:
        return None
    return steer_effect_revisions(turn)
