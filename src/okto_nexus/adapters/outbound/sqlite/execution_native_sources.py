"""Select the admitted turn that owns a canonical native request."""


def native_turn_source_predicate(*, generation, epoch):
    """SQL shared by the exact source lookup and the batched Attention read."""
    return f"""(
        turn.action = 'turn.submit'
        OR (turn.action = 'turn.steer' AND EXISTS (
            SELECT 1 FROM session_interaction_claude_steer_targets target
            JOIN session_interaction_controls control USING(server_id,executor_id,operation_id)
            WHERE target.server_id=turn.server_id AND target.executor_id=turn.executor_id
              AND target.operation_id=turn.operation_id AND control.session_id=turn.session_id
              AND control.owner_generation={generation} AND target.target_stream_epoch={epoch}
              AND control.confirmed_effect_revision IS NOT NULL AND control.target_ref=target.target_operation_id
        ))
    )"""


_SOURCE_GENERATION = "COALESCE(:generation, json_extract(turn.expected_revisions_json,'$.session_owner_generation'))"
_SELECT = f"""
    SELECT turn.* FROM execution_operations turn
    WHERE turn.server_id=:server AND turn.executor_id=:executor AND turn.session_id=:session
      AND turn.operation_id=:operation
      AND {native_turn_source_predicate(generation=_SOURCE_GENERATION, epoch=':epoch')}
"""


def read_native_turn_source(conn, *, server_id, executor_id, session_id, operation_id, stream_epoch, owner_generation=None):
    return conn.execute(_SELECT, {
        'server': server_id, 'executor': executor_id, 'session': session_id, 'operation': operation_id,
        'generation': owner_generation, 'epoch': stream_epoch,
    }).fetchone()
