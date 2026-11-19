"""Identify an exact control target from the current canonical stream."""

import hashlib
import json
from dataclasses import dataclass

from nexus_connector_core import get_control_targeting
from nexus_connector_core.native.pi_steer_facts import valid_pi_run_id
from nexus_connector_core.pi_control_link import PI_RUN_CONTROL_REVISION

from ..adapters.outbound.sqlite.session_interaction import _scope_params
from ..domain.attention import digest
from ..domain.session_interaction import InputScope
from .execution_native_session_mapping import (
    read_managed_native_session,
    reviewed_pi_context,
)


@dataclass(frozen=True, slots=True)
class ExactNativeTurn:
    native_id: str
    operation_id: str
    revision: str
    stream_epoch: str


@dataclass(frozen=True, slots=True)
class ExactPiRun:
    run_ref: str
    operation_id: str
    revision: str
    stream_epoch: str


@dataclass(frozen=True, slots=True)
class ExactClaudeOperation:
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
    evidence = _active_start(uow, scope, mapping.adapter_id, 'turn/started', 'turn_state')
    if evidence is None:
        return None
    selected, start, payload = evidence
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


def active_pi_run(uow, scope: InputScope, *, current_next_turn_revision,
                  remote_control_host=None) -> ExactPiRun | None:
    """Prove the observed run on the current, reviewed Pi owner."""
    mapping = read_managed_native_session(uow, scope)
    if mapping is None or mapping.stream_epoch is None or not reviewed_pi_context(mapping):
        return None
    capability = current_next_turn_revision(uow, scope)
    if capability is None:
        return None
    host = remote_control_host(scope.session.server_id, scope.session.executor_id) if remote_control_host else None
    channel = host.channel if host is not None and PI_RUN_CONTROL_REVISION in host.channel.control_capabilities else None
    evidence = _active_start(uow, scope, 'pi_rpc', 'agent_start', 'tool_activity', remote_pi_channel=channel)
    if evidence is None:
        return None
    selected, start, payload = evidence
    run = payload.get('hosted_pi_run_id')
    if not valid_pi_run_id(run):
        return None
    revision = 'sha256:' + digest({'action': 'exact_hosted_pi_run.v1', 'capability': capability,
        'opening': mapping.opening_operation_id, 'operation_id': selected['operation_id'],
        'epoch': selected['stream_epoch'], 'start': start['event_hash']})
    return ExactPiRun(run, selected['operation_id'], revision, selected['stream_epoch'])


def active_claude_operation(uow, scope: InputScope, *, current_next_turn_revision) -> ExactClaudeOperation | None:
    mapping = read_managed_native_session(uow, scope)
    if mapping is None or mapping.adapter_id != 'claude_stream' or mapping.stream_epoch is None:
        return None
    capability = current_next_turn_revision(uow, scope)
    if capability is None:
        return None
    unknown = uow.connection.execute("""
        SELECT 1
        FROM session_interaction_inputs i
        JOIN session_interaction_claude_steer_targets p USING(server_id,executor_id,operation_id)
        WHERE i.server_id=:server_id AND i.executor_id=:executor_id AND i.session_id=:session_id
          AND i.owner_generation=:owner_generation AND p.target_stream_epoch=:stream_epoch
          AND i.status='DELIVERY_UNKNOWN'
        LIMIT 1
    """, _scope_params(scope) | {'stream_epoch': mapping.stream_epoch}).fetchone()
    if unknown is not None:
        return None
    evidence = _active_start(uow, scope, 'claude_stream', 'nexus_claude_generating', 'tool_activity', phase=None)
    if evidence is None:
        return None
    selected, start, payload = evidence
    if type(payload.get('schema_version')) is not int or payload['schema_version'] != 1:
        return None
    revision = 'sha256:' + digest({'action': 'exact_claude_operation.v1', 'capability': capability,
        'opening': mapping.opening_operation_id, 'operation_id': selected['operation_id'],
        'epoch': selected['stream_epoch'], 'generating': start['event_hash']})
    return ExactClaudeOperation(selected['operation_id'], revision, selected['stream_epoch'])


def _active_start(uow, scope, adapter_id, native_start, event_type, *, phase='started', remote_pi_channel=None):
    conn = uow.connection
    scope_params = _scope_params(scope) | {'adapter_id': adapter_id, 'native_start': native_start,
        'event_type': event_type, 'phase': phase,
        'pi_connection_id': remote_pi_channel.connection_id if remote_pi_channel is not None else None,
        'pi_connection_generation': remote_pi_channel.connection_generation if remote_pi_channel is not None else None}
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
          AND s.workspace_binding_id=:workspace_binding_id AND e.adapter_id=:adapter_id
          AND (:adapter_id NOT IN ('pi_rpc','claude_stream') OR x.kind='embedded'
               OR (:adapter_id='pi_rpc' AND x.kind='remote' AND x.owner_instance_id=:pi_connection_id
                   AND x.generation=:pi_connection_generation))
          AND w.gap_state='none'
          AND (o.action='turn.submit' OR (:adapter_id='claude_stream' AND o.action='turn.steer'))
          AND o.admission_state='DISPATCHED' AND o.binding_id=:binding_id
          AND o.workspace_id=:workspace_id AND o.workspace_binding_id=:workspace_binding_id
          AND o.subject_agent_id=:agent_id AND d.dispatch_state='DISPATCHED'
          AND r.stage IN ('SUBMITTED','ACCEPTED') AND r.source_connection_id=x.owner_instance_id
          AND r.source_connection_generation=x.generation AND result.terminal_sequence IS NULL
          AND json_extract(o.expected_revisions_json,'$.session_owner_generation')=:owner_generation
          AND (:adapter_id NOT IN ('pi_rpc','claude_stream') OR NOT EXISTS (
              SELECT 1 FROM execution_event_ingress finish
              WHERE finish.server_id=s.server_id AND finish.executor_id=s.executor_id
                AND finish.session_id=s.session_id AND finish.stream_epoch=s.stream_epoch
                AND finish.event_type='turn_state' AND finish.sequence<=w.committed_contiguous
                AND json_extract(finish.payload_json,'$.operation_id')=o.operation_id
                AND json_extract(finish.payload_json,'$.payload.delivery_phase')='terminal'
          ))
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
          AND stream_epoch=:stream_epoch AND sequence<=:committed_contiguous AND event_type=:event_type
          AND json_extract(payload_json,'$.operation_id')=:operation_id
          AND json_extract(payload_json,'$.native_type')=:native_start
          AND json_extract(payload_json,'$.payload.delivery_phase') IS :phase
        LIMIT 2
    """, {**scope_params, **dict(selected)}).fetchall()
    if len(started) != 1:
        return None
    start = started[0]
    raw = start['payload_json']
    if 'sha256:' + hashlib.sha256(raw.encode()).hexdigest() != start['event_hash']:
        return None
    return selected, start, json.loads(raw)['payload']


def active_interrupt_target(uow, scope: InputScope, *, current_next_turn_revision, remote_control_host=None):
    turn = active_native_turn(uow, scope, current_next_turn_revision=current_next_turn_revision)
    if turn is not None:
        return turn
    run = active_pi_run(uow, scope, current_next_turn_revision=current_next_turn_revision,
                        remote_control_host=remote_control_host)
    if run is not None:
        contract = get_control_targeting('pi_rpc', 'turn.interrupt')
        if contract.supported and contract.native_turn_id == 'forbidden' and contract.requires_active_run:
            return run
    return None


def control_target_ref(target: ExactNativeTurn | ExactPiRun) -> str:
    return target.run_ref if isinstance(target, ExactPiRun) else target.native_id


def interrupt_revision(uow, scope: InputScope, native_turn_id: str, *, current_next_turn_revision,
                       observed_run=False, remote_control_host=None) -> str | None:
    turn = active_interrupt_target(uow, scope, current_next_turn_revision=current_next_turn_revision,
                                   remote_control_host=remote_control_host)
    if turn is None or isinstance(turn, ExactPiRun) != observed_run or control_target_ref(turn) != native_turn_id:
        return None
    return turn.revision


def steer_effect_revisions(turn: ExactNativeTurn | ExactPiRun | ExactClaudeOperation) -> tuple[str, str] | None:
    """Describe the installed Core contract for the proven target."""
    if isinstance(turn, ExactPiRun):
        adapter, native_id, timing, effect_name = 'pi_rpc', 'forbidden', 'NEXT_TURN_BOUNDARY', 'next_boundary'
    elif isinstance(turn, ExactClaudeOperation):
        adapter, native_id, timing, effect_name = 'claude_stream', 'forbidden', 'IMMEDIATE', 'interrupt_then_send'
    else:
        adapter, native_id, timing, effect_name = 'codex_app_server', 'required', 'IMMEDIATE', 'same_turn'
    contract = get_control_targeting(adapter, 'turn.steer')
    if not (contract.supported and contract.requires_active_run and
            (contract.native_turn_id, contract.steer_timing) == (native_id, timing)):
        return None
    capability = 'sha256:' + digest({'target': turn.revision, 'contract': contract.to_dict()})
    effect = 'sha256:' + digest({'capability': capability, 'effect': effect_name})
    return capability, effect


def steer_revisions(uow, scope: InputScope, native_turn_id: str, *, current_next_turn_revision,
                    observed_run=False, claude_operation=False,
                    remote_control_host=None) -> tuple[str, str] | ExactPiRun | ExactClaudeOperation | None:
    if claude_operation:
        turn = active_claude_operation(uow, scope, current_next_turn_revision=current_next_turn_revision)
        return turn if turn is not None and turn.operation_id == native_turn_id else None
    if observed_run:
        run = active_pi_run(uow, scope, current_next_turn_revision=current_next_turn_revision,
                            remote_control_host=remote_control_host)
        return run if run is not None and run.run_ref == native_turn_id else None
    turn = active_native_turn(uow, scope, current_next_turn_revision=current_next_turn_revision)
    if turn is None or turn.native_id != native_turn_id:
        return None
    return steer_effect_revisions(turn)
