"""Durable native request identities in the canonical domain transaction."""

class SqliteNativeActionRepository:
    @staticmethod
    def key(scope):
        return tuple(scope[k] for k in ('server_id', 'executor_id', 'session_id'))

    def get(self, uow, scope, action_id):
        return uow.connection.execute(
            'SELECT * FROM execution_native_actions WHERE server_id=? AND executor_id=? '
            'AND session_id=? AND action_id=?', (*self.key(scope), action_id)).fetchone()

    def claim_key_owner(self, uow, scope, key):
        return uow.connection.execute(
            'SELECT action_id FROM execution_native_actions WHERE server_id=? AND executor_id=? '
            'AND session_id=? AND claim_key=?', (*self.key(scope), key)).fetchone()

    def record(self, uow, *, scope, action_id, action, scope_json, digest, claim_key,
               handoff_id, response_json, now):
        uow.connection.execute(
            'INSERT INTO execution_native_actions(server_id,executor_id,session_id,action_id,'
            'action,scope_json,request_digest,claim_key,handoff_id,claim_epoch,response_json,created_at) '
            'SELECT ?,?,?,?,?,?,?,?,?,claim_epoch,?,? FROM handoffs WHERE handoff_id=?',
            (*self.key(scope), action_id, action, scope_json, digest, claim_key,
             handoff_id, response_json, now, handoff_id))
