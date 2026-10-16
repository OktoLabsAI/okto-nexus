"""Private runtime payloads in the ArtifactStore, authorized by session scope.

Transport chunks are durable and idempotent. A reference becomes usable only
after the complete payload has been verified and persisted by the store port.
"""
import base64
import time
from datetime import datetime, timezone

from nexus_connector_core.event_artifacts import (
    SCOPE, event_reference, hydrate_event, artifact_ack, decode_event_artifact,
    encode_event_artifact,
)
from nexus_connector_core.protocol import canonical_json
from ..errors import OktoNexusError, ErrorCode
from .execution_leases import require_execution_lane


class ExecutionEventArtifacts:
    def __init__(self, factory, store):
        self.factory, self.store = factory, store

    def _authorize(self, uow, scope, channel, embedded_owner):
        from ..adapters.outbound.sqlite.execution_leases import SqliteExecutionLeaseRepository
        if any(scope[k] != getattr(channel,k) for k in
               ('server_id','executor_id','connection_id','connection_generation')):
            raise ValueError('Artifact connection mismatch')
        if not SqliteExecutionLeaseRepository().current_channel(uow, channel):
            raise ValueError('Artifact owner is no longer current')
        row = uow.connection.execute(
            'SELECT s.workspace_id,s.stream_epoch,e.agent_id FROM execution_sessions s '
            'JOIN execution_bindings b USING(server_id,executor_id,binding_id) '
            'JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id '
            'WHERE s.server_id=? AND s.executor_id=? AND s.session_id=? AND s.binding_id=?',
            tuple(scope[k] for k in ('server_id','executor_id','session_id','binding_id'))).fetchone()
        if row is None or row['agent_id'] != scope['agent_id'] or row['stream_epoch'] not in (None,scope['stream_epoch']):
            raise ValueError('Artifact has no authorized session')
        if embedded_owner is not None:
            embedded_owner.verify(uow=uow)
            if embedded_owner.channel != channel or not uow.connection.execute(
                'SELECT 1 FROM execution_local_streams WHERE server_id=? AND executor_id=? '
                'AND session_id=? AND stream_epoch=? AND agent_id=? AND binding_id=?',
                tuple(scope[k] for k in ('server_id','executor_id','session_id','stream_epoch','agent_id','binding_id'))).fetchone():
                raise ValueError('Artifact has no approved local stream')
        else:
            revisions = uow.connection.execute('SELECT * FROM execution_agent_revisions WHERE server_id=? AND agent_id=?',
                (scope['server_id'],scope['agent_id'])).fetchone()
            if revisions is None:
                raise ValueError('Artifact authority missing')
            require_execution_lane(uow, scope={**scope, **{k:revisions[k] for k in
                ('credential_epoch','authorization_revision','configuration_revision')}},
                channel=channel, now=datetime.now(timezone.utc))
        return row['workspace_id']

    def receive(self, frame, *, channel, embedded_owner=None):
        frame = decode_event_artifact(encode_event_artifact(frame))
        event = frame['event']
        ref = event_reference(event)
        scope = {**frame, **{k:event[k] for k in SCOPE}}
        raw = base64.b64decode(frame['data'], validate=True)
        reference_json = canonical_json(ref).decode()
        from ..adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
        current_agent_revisions(self.factory,agent_id=scope['agent_id'],require_active=embedded_owner is None)
        # Serialize reservations/chunks only; filesystem persistence must not
        # hold the shared database writer while other agents are publishing.
        content = None
        existing_path = None
        with self.factory.unit_of_work() as uow:
            workspace = self._authorize(uow, scope, channel, embedded_owner)
            db = uow.connection
            row = db.execute('SELECT * FROM execution_event_artifacts WHERE artifact_id=?', (ref['artifact_id'],)).fetchone()
            if row is None:
                # Discard abandoned incomplete uploads after a day; replay can
                # always reconstruct them from the unacknowledged Core journal.
                db.execute('DELETE FROM execution_event_artifacts WHERE storage_path IS NULL AND updated_at<?', (time.time()-86400,))
                usage = db.execute('SELECT (SELECT COALESCE(sum(size_bytes),0) FROM execution_event_artifacts) '
                                   '+ (SELECT COALESCE(sum(artifact_reserved_bytes),0) FROM runtime_results)').fetchone()[0]
                quota = db.execute('SELECT quota_bytes FROM runtime_artifact_settings WHERE singleton=1').fetchone()[0]
                if usage + ref['size_bytes'] > quota:
                    raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED, 'Runtime event artifact storage is full.', {})
                db.execute('INSERT INTO execution_event_artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (ref['artifact_id'],*[scope[k] for k in SCOPE], scope['binding_id'],scope['agent_id'],workspace,
                     reference_json,None,ref['size_bytes'],time.time()))
            elif row['reference_json'] != reference_json or any(row[k] != scope[k] for k in (*SCOPE,'binding_id','agent_id')):
                raise ValueError('Artifact identity conflict')
            if row is not None and row['storage_path']:
                existing_path = row['storage_path']
            previous = db.execute('SELECT content FROM execution_event_artifact_chunks WHERE artifact_id=? AND offset=?',
                                  (ref['artifact_id'],frame['offset'])).fetchone()
            if previous is not None and previous[0] != raw:
                raise ValueError('Artifact chunk conflict')
            if existing_path is None:
                db.execute('INSERT OR IGNORE INTO execution_event_artifact_chunks VALUES(?,?,?)',
                           (ref['artifact_id'],frame['offset'],raw))
            db.execute('UPDATE execution_event_artifacts SET updated_at=? WHERE artifact_id=?', (time.time(),ref['artifact_id']))
            chunks = db.execute('SELECT offset,content FROM execution_event_artifact_chunks WHERE artifact_id=? ORDER BY offset',
                                (ref['artifact_id'],)).fetchall()
            if sum(len(c['content']) for c in chunks) == ref['size_bytes']:
                content = b''.join(c['content'] for c in chunks)
        if existing_path:
            content = self.store.read_bytes(existing_path)
            hydrate_event(event,content)
            if content[frame['offset']:frame['offset']+len(raw)] != raw:
                raise ValueError('Artifact replay conflict')
        elif content is not None:
            hydrate_event(event, content)
            stored = self.store.put(workspace_id=workspace,agent_id=scope['agent_id'],artifact_id=ref['artifact_id'],
                artifact_type='json', storage_kind='path', name='runtime-event.json',content=content,
                source_path=None,metadata=ref,created_at=datetime.now(timezone.utc).isoformat())
            hydrate_event(event,self.store.read_bytes(stored.storage_path))
            with self.factory.unit_of_work() as uow:
                self._authorize(uow,scope,channel,embedded_owner)
                db = uow.connection
                changed = db.execute('UPDATE execution_event_artifacts SET storage_path=? WHERE artifact_id=? AND reference_json=?',
                                     (stored.storage_path,ref['artifact_id'],reference_json))
                if changed.rowcount != 1:
                    raise ValueError('Artifact reservation changed before persistence')
                db.execute('DELETE FROM execution_event_artifact_chunks WHERE artifact_id=?',(ref['artifact_id'],))
        return artifact_ack(frame)

    def resolve(self, conn, event):
        ref = event_reference(event)
        if ref is None:
            return event
        row = conn.execute('SELECT * FROM execution_event_artifacts WHERE artifact_id=?', (ref['artifact_id'],)).fetchone()
        if row is None or not row['storage_path'] or any(row[k] != event[k] for k in SCOPE):
            raise ValueError('Event artifact is not durably available in this session')
        return hydrate_event(event, self.store.read_bytes(row['storage_path']))


def resolve_event(factory, conn, event):
    if event_reference(event) is None:
        return event
    return factory.event_artifacts.resolve(conn,event)
