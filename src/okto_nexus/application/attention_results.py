"""Canonical result references, independent of operator viewing preferences."""
from ..domain.attention import instant, occurrence


def project(facts, now, policy):
    if facts['source_type'] == 'execution_result':
        return [occurrence(kind='result_unseen', source_type='execution_result', source_id=facts['operation_id'],
            episode=[facts['server_id'], facts['executor_id'], facts['stream_epoch'], facts['terminal_sequence']],
            source_revision=[facts['stream_epoch'], facts['terminal_sequence'], facts['delivery_outcome']],
            first_detected_at=facts['captured_at'], last_changed_at=facts['captured_at'],
            agent_id=facts['agent_id'], workspace_id=facts['workspace_id'], session_id=facts['session_id'],
            operation_id=facts['operation_id'], resolution='resolved', active=True,
            executor_id=facts['executor_id'],
            allowed_actions=['inspect_result'])]
    native = sorted(facts['native_results'], key=lambda row: (
        instant(row['captured_at']), row['server_id'], row['executor_id'], row['operation_id']))
    latest = native[-1] if native else None
    # Completion may arrive before or after its native result. The handoff claim
    # is the productive identity in either order, never the currently visible row.
    revision = dict(claim_epoch=facts['claim_epoch'], terminal_status=facts['terminal_status'],
        terminal_at=facts['terminal_at'], native_results=native)
    return [occurrence(kind='result_unseen', source_type='handoff_result', source_id=facts['handoff_id'],
        episode=facts['claim_epoch'], source_revision=revision,
        first_detected_at=facts['first_detected_at'], last_changed_at=facts['last_changed_at'],
        agent_id=latest['agent_id'] if latest else facts['agent_id'], workspace_id=facts['workspace_id'],
        session_id=latest['session_id'] if latest else None,
        operation_id=latest['operation_id'] if latest else None,
        executor_id=latest['executor_id'] if latest else None,
        resolution='resolved', active=True,
        allowed_actions=['inspect_handoff'] + (['inspect_result'] if latest else []))]
