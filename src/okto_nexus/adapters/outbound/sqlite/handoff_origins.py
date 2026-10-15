"""Immutable creator provenance shares the canonical handoff transaction."""
from ....domain.handoff_origin import HandoffOrigin
from ....errors import ErrorCode, OktoNexusError


class SqliteHandoffOriginRepo:
    @staticmethod
    def _require(uow, workspace_id, handoff_id):
        row = uow.connection.execute('SELECT from_agent_id FROM handoffs WHERE workspace_id=? AND handoff_id=?',
                                      (workspace_id, handoff_id)).fetchone()
        if row is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'The handoff origin was not found in this workspace.', {})
        return row

    def record(self, uow, *, workspace_id, handoff_id, origin, captured_at):
        self._require(uow, workspace_id, handoff_id)
        uow.connection.execute('INSERT INTO execution_handoff_origins VALUES(?,?,?,?,?)',
            (handoff_id, origin.schema_version, origin.kind, origin.source_session_key, captured_at))

    def get(self, uow, *, workspace_id, handoff_id):
        self._require(uow, workspace_id, handoff_id)
        row = uow.connection.execute('SELECT schema_version,source_session_key FROM execution_handoff_origins '
                                      'WHERE handoff_id=?', (handoff_id,)).fetchone()
        return HandoffOrigin(row['source_session_key'], row['schema_version']) if row else HandoffOrigin()

    def bind_message(self, uow, *, workspace_id, handoff_id, message_id):
        creator = self._require(uow, workspace_id, handoff_id)['from_agent_id']
        row = uow.connection.execute('SELECT from_agent_id FROM messages WHERE workspace_id=? AND message_id=?',
                                      (workspace_id, message_id)).fetchone()
        if row is None or row['from_agent_id'] != creator:
            raise OktoNexusError(ErrorCode.CONFLICT, 'The execution message does not match its handoff creator.', {})
        origin = self.get(uow, workspace_id=workspace_id, handoff_id=handoff_id)
        if origin.source_session_key:
            uow.connection.execute('INSERT INTO execution_message_origins(message_id,source_session_key) VALUES(?,?)',
                                   (message_id, origin.source_session_key))
