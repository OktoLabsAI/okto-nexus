"""Bind canonical work to its admitted session without transferring ownership."""
import json

from nexus_connector_core.protocol import canonical_json

from ....errors import ErrorCode, OktoNexusError


def denied():
    return OktoNexusError(ErrorCode.PERMISSION_DENIED,
                         'The admitted session does not own this handoff claim.', {})


class SqliteExecutionClaimRepository:
    def matches(self, uow, *, handoff_id, claim_epoch, scope):
        row = uow.connection.execute('SELECT scope_json FROM execution_tool_claims '
            'WHERE handoff_id=? AND claim_epoch=?', (handoff_id, claim_epoch)).fetchone()
        return row is not None and row['scope_json'] == canonical_json(scope).decode()

    def bind(self, uow, *, handoff_id, claim_epoch, scope):
        conn = uow.connection
        claim = conn.execute('SELECT workspace_id,claimed_by,claim_epoch,status FROM handoffs '
                             'WHERE handoff_id=?', (handoff_id,)).fetchone()
        if (claim is None or tuple(claim) != (scope['workspace_id'], scope['agent_id'], claim_epoch, 'CLAIMED')):
            raise denied()
        prior = conn.execute('SELECT scope_json FROM execution_tool_claims '
            'WHERE handoff_id=? AND claim_epoch=?', (handoff_id, claim_epoch)).fetchone()
        encoded = canonical_json(scope).decode()
        if prior:
            if prior['scope_json'] != encoded:
                raise denied()  # No implicit adoption from another session/generation.
            return
        conn.execute('INSERT INTO execution_tool_claims '
            '(handoff_id,claim_epoch,server_id,executor_id,session_id,scope_json) VALUES (?,?,?,?,?,?)',
            (handoff_id, claim_epoch, scope['server_id'], scope['executor_id'], scope['session_id'], encoded))

    def bind_delivery(self, uow, *, operation_id, scope):
        conn = uow.connection
        claim = conn.execute('SELECT handoff_id,claim_epoch FROM runtime_handoff_bindings '
                             'WHERE operation_id=?', (operation_id,)).fetchone()
        if claim is None:
            return  # Ordinary messages never create claim authority.
        turns = conn.execute('SELECT p.expected_revisions_json FROM execution_domain_deliveries d '
            'JOIN execution_operations p USING(server_id,executor_id,operation_id) '
            "WHERE d.domain_operation_id=? AND p.action='turn.submit'", (operation_id,)).fetchall()
        if len(turns) != 1 or json.loads(turns[0][0]) != scope:
            raise denied()
        self.bind(uow, handoff_id=claim['handoff_id'], claim_epoch=claim['claim_epoch'], scope=scope)
