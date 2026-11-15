"""SQLite outbox for exact, correlated session release publications."""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import sqlite3
import json

from nexus_connector_core import decode_r4_frame, encode_r4_frame
from nexus_connector_core.protocol import canonical_json
from nexus_connector_core.session_release import decode_session_release, encode_session_release

from ..errors import ConnectorError


class R4SessionReleaseStore:
    def __init__(self, path):
        self.path = Path(path)

    @classmethod
    def for_state(cls, store):
        return cls(store.path.with_suffix('.r4-session-releases.sqlite3'))

    @contextmanager
    def _transaction(self):
        conn = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA synchronous=FULL')
            conn.execute('PRAGMA max_page_count=32768')
            conn.execute('BEGIN IMMEDIATE')
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2, 3, 4, 5, 6):
                raise ConnectorError('VERSION_INCOMPATIBLE', 'session_release',
                                     'The release outbox requires a newer Connector.')
            conn.execute('CREATE TABLE IF NOT EXISTS releases ('
                'release_id TEXT PRIMARY KEY, identity TEXT NOT NULL, request BLOB NOT NULL,'
                'digest TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN (\'PENDING\',\'DEFERRED\',\'ACCEPTED\')),'
                'reply BLOB)')
            if version < 2:
                conn.execute('ALTER TABLE releases ADD COLUMN recovery BLOB')
                conn.execute('ALTER TABLE releases ADD COLUMN recovery_digest TEXT')
            if version < 3:
                conn.execute('ALTER TABLE releases ADD COLUMN event_retired INTEGER NOT NULL DEFAULT 0 '
                             'CHECK(event_retired IN (0,1))')
            if version < 4:
                conn.execute('ALTER TABLE releases ADD COLUMN claim_retired INTEGER NOT NULL DEFAULT 0 '
                             'CHECK(claim_retired IN (0,1))')
            if version < 5:
                conn.execute('DROP INDEX IF EXISTS release_event_retirement')
            conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS pending_release ON releases(identity) '
                         'WHERE state=\'PENDING\'')
            conn.execute('CREATE INDEX IF NOT EXISTS release_identity ON releases(identity)')
            conn.execute('CREATE INDEX IF NOT EXISTS release_recovery ON releases('
                         'json_extract(identity,\'$.scope.server_id\'),'
                         'json_extract(identity,\'$.scope.executor_id\'),'
                         'json_extract(identity,\'$.connection_generation\')) WHERE recovery IS NULL')
            conn.execute('CREATE INDEX IF NOT EXISTS release_event_retirement ON releases('
                         'json_extract(identity,\'$.scope.server_id\'),'
                         'json_extract(identity,\'$.scope.executor_id\')) '
                         'WHERE (state=\'ACCEPTED\' OR recovery IS NOT NULL) '
                         'AND (event_retired=0 OR claim_retired=0)')
            # An accepted reconciliation may precede any direct session.release.
            # Keep that proof as its own type; never manufacture a direct ACK.
            conn.execute('CREATE TABLE IF NOT EXISTS reconciliation_checkpoints ('
                         'identity TEXT PRIMARY KEY,server_id TEXT NOT NULL,executor_id TEXT NOT NULL,'
                         'proof BLOB NOT NULL,digest TEXT NOT NULL,retired INTEGER NOT NULL DEFAULT 0 '
                         'CHECK(retired IN (0,1)))')
            conn.execute('CREATE INDEX IF NOT EXISTS reconciliation_checkpoint_pending '
                         'ON reconciliation_checkpoints(server_id,executor_id) WHERE retired=0')
            conn.execute('PRAGMA user_version=6')
            yield conn
            conn.commit()
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as error:
            raise ConnectorError('JOURNAL_UNAVAILABLE', 'session_release',
                                 'The durable session release outbox is unavailable.') from error
        finally:
            if conn is not None:
                conn.close()

    @staticmethod
    def _identity(*, scope, connection_id, connection_generation):
        return canonical_json(dict(scope=scope, connection_id=connection_id,
                                   connection_generation=connection_generation)).decode()

    def _decode(self, row):
        if row is None or sha256(row['request']).hexdigest() != row['digest']:
            raise ConnectorError('JOURNAL_UNAVAILABLE', 'session_release',
                                 'The release outbox failed its integrity check.')
        request = decode_session_release(row['request'])
        if (request['type'] != 'session.release' or request['release_id'] != row['release_id']
                or self._identity(**{k: request[k] for k in
                    ('scope', 'connection_id', 'connection_generation')}) != row['identity']):
            raise ConnectorError('JOURNAL_UNAVAILABLE', 'session_release',
                                 'The release outbox identity is inconsistent.')
        reply = decode_session_release(row['reply']) if row['reply'] is not None else None
        expected = {'PENDING': None, 'DEFERRED': 'session.release.deferred',
                    'ACCEPTED': 'session.release.accepted'}[row['state']]
        if ((reply is None) != (expected is None) or reply is not None and (
                reply['type'] != expected or reply['request'] != request)):
            raise ConnectorError('JOURNAL_UNAVAILABLE', 'session_release',
                                 'The release acknowledgment is inconsistent.')
        if row['recovery'] is not None:
            if sha256(row['recovery']).hexdigest() != row['recovery_digest']:
                raise ConnectorError('JOURNAL_UNAVAILABLE', 'session_release', 'The recovery proof is corrupt.')
            proof = json.loads(row['recovery'])
            ack = decode_r4_frame(encode_r4_frame(proof['ack']))
            if not self._recovered(request, ack, proof['observation']):
                raise ConnectorError('JOURNAL_UNAVAILABLE', 'session_release', 'The recovery proof is inconsistent.')
        return request

    def pending(self, *, scope, connection_id, connection_generation):
        identity = self._identity(scope=scope, connection_id=connection_id,
                                  connection_generation=connection_generation)
        with self._transaction() as conn:
            row = conn.execute('SELECT * FROM releases WHERE identity=? AND state=\'PENDING\' AND recovery IS NULL',
                               (identity,)).fetchone()
            return None if row is None else self._decode(row)

    def prepare(self, request):
        encoded = encode_session_release(request)
        request = decode_session_release(encoded)
        if request['type'] != 'session.release':
            raise ValueError('A release request is required.')
        identity = self._identity(**{k: request[k] for k in
                                     ('scope', 'connection_id', 'connection_generation')})
        with self._transaction() as conn:
            scope = request['scope']
            checkpoints = conn.execute('SELECT * FROM reconciliation_checkpoints WHERE server_id=? '
                "AND executor_id=? AND json_extract(identity,'$.session_id')=?",
                (scope['server_id'],scope['executor_id'],scope['session_id'])).fetchall()
            if checkpoints:
                for checkpoint in checkpoints:
                    self._decode_checkpoint(checkpoint)
                raise ConnectorError('STALE_GENERATION','session_release',
                    'This opening already has an accepted reconciliation checkpoint.')
            row = conn.execute('SELECT * FROM releases WHERE release_id=?',
                               (request['release_id'],)).fetchone()
            if row is not None and self._decode(row) != request:
                raise ConnectorError('SCOPE_MISMATCH', 'session_release',
                                     'The release ID already belongs to another observation.')
            if row is not None and row['recovery'] is not None:
                raise ConnectorError('STALE_GENERATION', 'session_release',
                                     'This publication was resolved by a replacement connection.')
            recovered = conn.execute('SELECT * FROM releases WHERE identity=? AND recovery IS NOT NULL LIMIT 1',
                                     (identity,)).fetchone()
            if recovered is not None:
                self._decode(recovered)
                raise ConnectorError('STALE_GENERATION', 'session_release',
                                     'This original channel was already resolved by reconciliation.')
            pending = conn.execute('SELECT * FROM releases WHERE identity=? AND state=\'PENDING\'',
                                   (identity,)).fetchone()
            if pending is not None:
                # Unknown publication result always wins over a newer local
                # observation. No new proof is sent until its outcome is known.
                return self._decode(pending)
            accepted = conn.execute('SELECT * FROM releases WHERE identity=? AND state=\'ACCEPTED\'',
                                    (identity,)).fetchone()
            if accepted is not None:
                # Only exact replay is meaningful after canonical closure.
                return self._decode(accepted)
            if row is None:
                if conn.execute('SELECT count(*) FROM releases WHERE state=\'PENDING\' AND recovery IS NULL').fetchone()[0] >= 4096:
                    raise ConnectorError('CAPACITY_EXCEEDED', 'session_release',
                                         'The durable release outbox is full.')
                conn.execute('INSERT INTO releases(release_id,identity,request,digest,state,reply) '
                             'VALUES (?,?,?,?,\'PENDING\',NULL)',
                    (request['release_id'], identity, encoded, sha256(encoded).hexdigest()))
            else:
                conn.execute('UPDATE releases SET state=\'PENDING\',reply=NULL WHERE release_id=?',
                             (request['release_id'],))
            return request

    def acknowledge(self, reply):
        encoded = encode_session_release(reply)
        reply = decode_session_release(encoded)
        if reply['type'] not in ('session.release.accepted', 'session.release.deferred'):
            raise ValueError('A correlated release reply is required.')
        request = reply['request']
        with self._transaction() as conn:
            row = conn.execute('SELECT * FROM releases WHERE release_id=?',
                               (request['release_id'],)).fetchone()
            if row is None or self._decode(row) != request:
                raise ConnectorError('SCOPE_MISMATCH', 'session_release',
                                     'The reply does not match the durable release request.')
            if row['recovery'] is not None:
                raise ConnectorError('STALE_GENERATION', 'session_release',
                                     'The original channel was already reconciled.')
            state = 'ACCEPTED' if reply['type'] == 'session.release.accepted' else 'DEFERRED'
            if row['state'] == state:
                return
            if row['state'] != 'PENDING':
                raise ConnectorError('STALE_GENERATION', 'session_release',
                                     'The reply cannot supersede a completed publication attempt.')
            conn.execute('UPDATE releases SET state=?,reply=? WHERE release_id=?',
                         (state, encoded, request['release_id']))

    def accepted_event_page(self, server_id, executor_id, *, after=0, limit=128):
        if type(after) is not int or after<0 or type(limit) is not int or not 1<=limit<=128:
            raise ValueError('Invalid terminal event page.')
        with self._transaction() as conn:
            rows=conn.execute('SELECT rowid,* FROM releases WHERE rowid>? '
                'AND state=\'ACCEPTED\' AND (event_retired=0 OR claim_retired=0) '
                'AND json_extract(identity,\'$.scope.server_id\')=? '
                'AND json_extract(identity,\'$.scope.executor_id\')=? '
                'ORDER BY rowid LIMIT ?', (after,server_id,executor_id,limit)).fetchall()
            return [(row['rowid'],self._decode(row)) for row in rows]

    def resolved_checkpoint_page(self, server_id, executor_id, *, after=0, limit=128):
        """Page Server-accepted releases and exact accepted reconciliation proofs."""
        if type(after) is not int or after<0 or type(limit) is not int or not 1<=limit<=128:
            raise ValueError('Invalid resolved checkpoint page.')
        with self._transaction() as conn:
            rows=conn.execute('SELECT rowid,* FROM releases WHERE rowid>? '
                'AND (state=\'ACCEPTED\' OR recovery IS NOT NULL) '
                'AND (event_retired=0 OR claim_retired=0) '
                'AND json_extract(identity,\'$.scope.server_id\')=? '
                'AND json_extract(identity,\'$.scope.executor_id\')=? '
                'ORDER BY rowid LIMIT ?', (after,server_id,executor_id,limit)).fetchall()
            result=[]
            for row in rows:
                request=self._decode(row)
                if row['state']=='ACCEPTED':
                    sequence=request['sequence']
                    digest=sha256(row['request']).hexdigest()
                else:
                    proof=json.loads(row['recovery'])
                    sequence=proof['observation']['watermark']['sequence']
                    digest=row['recovery_digest']
                result.append((row['rowid'],request,sequence,digest))
            return result

    def mark_checkpoints_retired(self, request):
        request=decode_session_release(encode_session_release(request))
        with self._transaction() as conn:
            row=conn.execute('SELECT * FROM releases WHERE release_id=?',
                (request['release_id'],)).fetchone()
            if row is None or self._decode(row)!=request or (
                    row['state']!='ACCEPTED' and row['recovery'] is None):
                raise ConnectorError('RECONCILIATION_REQUIRED','session_release',
                                     'The release has no accepted Server proof.')
            conn.execute('UPDATE releases SET event_retired=1,claim_retired=1 WHERE release_id=?',
                         (request['release_id'],))

    @staticmethod
    def _recovered(request, ack, observation):
        """Compare the original opening with facts from the accepted cycle."""
        opening, claim, fact, watermark = (observation[k] for k in ('opening', 'claim', 'fact', 'watermark'))
        return (ack['type'] == 'reconcile.accepted' and not ack['recovery_remaining']
            and all(ack[k] == request[k] for k in ('server_id', 'executor_id'))
            and ack['connection_generation'] > request['connection_generation']
            and ack['connection_id'] != request['connection_id']
            and all(opening[k] == request[k] for k in ('server_id', 'executor_id', 'connection_id', 'connection_generation'))
            and all(opening[k] == request['scope'][k] for k in ('binding_id', 'agent_id', 'session_id', 'session_owner_generation'))
            and opening['operation_id'] == request['opening_operation_id']
            and opening['intent_hash'] == request['opening_intent_hash']
            and claim['session_id'] == fact['session_id'] == watermark['session_id'] == request['scope']['session_id']
            and claim['owner_generation'] == fact['owner_generation'] == request['scope']['session_owner_generation']
            and claim['state'] == 'RELEASED' and fact['process_state'] == 'EXITED'
            and type(fact.get('proof_digest')) is str and fact['proof_digest'].startswith('sha256:')
            and opening['stream_epoch'] == watermark['stream_epoch'] == request['stream_epoch']
            and watermark['sequence'] >= request['sequence'])

    def reconcile_page(self, ack, observations, *, after=0, limit=128):
        """Retire only exact old-channel observations; retain bytes and ACK proof.

        The application supplies facts it actually sent in the accepted cycle.
        A row outside those facts remains pending, even when control is ready.
        """
        ack = decode_r4_frame(encode_r4_frame(ack))
        if (ack['type'] != 'reconcile.accepted' or ack['recovery_remaining']
                or type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 128):
            raise ValueError('A completed reconciliation and bounded cursor are required.')
        with self._transaction() as conn:
            rows = conn.execute('SELECT rowid,* FROM releases WHERE rowid>? AND recovery IS NULL '
                'AND json_extract(identity,\'$.scope.server_id\')=? '
                'AND json_extract(identity,\'$.scope.executor_id\')=? '
                'AND json_extract(identity,\'$.connection_generation\')<? ORDER BY rowid LIMIT ?',
                (after, ack['server_id'], ack['executor_id'], ack['connection_generation'], limit)).fetchall()
            for row in rows:
                request = self._decode(row)
                scope = request['scope']
                observation = observations.get((scope['session_id'], scope['session_owner_generation']))
                if observation is None or not self._recovered(request, ack, observation):
                    continue
                raw = canonical_json(dict(ack=ack, observation=observation))
                conn.execute('UPDATE releases SET recovery=?,recovery_digest=? WHERE release_id=?',
                             (raw, sha256(raw).hexdigest(), request['release_id']))
            return rows[-1]['rowid'] if len(rows) == limit else None

    @staticmethod
    def _checkpoint_identity(ack, observation):
        """Validate internal facts from the exact completed authenticated cycle."""
        ack = decode_r4_frame(encode_r4_frame(ack))
        opening, claim, fact, watermark = (observation[k] for k in ('opening','claim','fact','watermark'))
        strings = ('server_id','executor_id','binding_id','agent_id','session_id',
                   'operation_id','intent_hash','connection_id','stream_epoch')
        if (ack['type'] != 'reconcile.accepted' or ack['recovery_remaining']
                or any(type(opening.get(k)) is not str or not 1 <= len(opening[k]) <= 160 for k in strings)
                or any(type(opening.get(k)) is not int or opening[k] < 1
                       for k in ('connection_generation','session_owner_generation'))
                or any(ack[k] != opening[k] for k in ('server_id','executor_id'))
                or ack['connection_generation'] <= opening['connection_generation']
                or ack['connection_id'] == opening['connection_id']
                or claim.get('session_id') != opening['session_id']
                or fact.get('session_id') != opening['session_id']
                or watermark.get('session_id') != opening['session_id']
                or type(claim.get('owner_generation')) is not int
                or type(fact.get('owner_generation')) is not int
                or claim['owner_generation'] != opening['session_owner_generation']
                or fact['owner_generation'] != opening['session_owner_generation']
                or claim.get('state') != 'RELEASED' or fact.get('process_state') != 'EXITED'
                or watermark.get('stream_epoch') != opening['stream_epoch']
                or type(watermark.get('sequence')) is not int or watermark['sequence'] < 0
                or type(fact.get('proof_digest')) is not str or len(fact['proof_digest']) != 71
                or not fact['proof_digest'].startswith('sha256:')
                or any(c not in '0123456789abcdef' for c in fact['proof_digest'][7:])):
            raise ValueError('Invalid accepted reconciliation checkpoint.')
        return canonical_json({k:opening[k] for k in (*strings,'connection_generation','session_owner_generation')}).decode()

    def record_reconciliation_checkpoints(self, ack, observations):
        """Persist only missing direct-release histories; caller authenticated ACK."""
        if type(observations) is not dict or len(observations) > 128:
            raise ValueError('Invalid reconciliation checkpoint page.')
        with self._transaction() as conn:
            for key, observation in observations.items():
                identity = self._checkpoint_identity(ack, observation)
                opening = observation['opening']
                if key != (opening['session_id'],opening['session_owner_generation']):
                    raise ValueError('The reconciliation observation key changed.')
                # Existing publications keep their exact old bytes/retirement ID.
                direct = conn.execute('SELECT * FROM releases WHERE '
                    "json_extract(identity,'$.scope.server_id')=? AND "
                    "json_extract(identity,'$.scope.executor_id')=? AND "
                    "json_extract(identity,'$.scope.session_id')=?",
                    (opening['server_id'],opening['executor_id'],opening['session_id'])).fetchall()
                if direct:
                    if not any(self._recovered(self._decode(row),ack,observation) for row in direct):
                        raise ValueError('The prior release scope changed.')
                    continue
                row = conn.execute('SELECT * FROM reconciliation_checkpoints WHERE identity=?',(identity,)).fetchone()
                raw = canonical_json(dict(ack=ack,observation=observation))
                if row is not None:
                    previous = self._decode_checkpoint(row)
                    if previous['observation'] != observation:
                        raise ValueError('The accepted reconciliation facts changed.')
                    continue  # Preserve the first accepted cycle on retries.
                conn.execute('INSERT INTO reconciliation_checkpoints(identity,server_id,executor_id,proof,digest) '
                    'VALUES (?,?,?,?,?)',(identity,opening['server_id'],opening['executor_id'],raw,sha256(raw).hexdigest()))

    def _decode_checkpoint(self, row):
        if sha256(row['proof']).hexdigest() != row['digest']:
            raise ValueError('Corrupt reconciliation checkpoint.')
        proof = json.loads(row['proof'])
        if (self._checkpoint_identity(proof['ack'],proof['observation']) != row['identity']
                or any(proof['observation']['opening'][k] != row[k] for k in ('server_id','executor_id'))):
            raise ValueError('The reconciliation checkpoint scope changed.')
        return proof

    def reconciliation_checkpoint_page(self, server_id, executor_id, *, after=0, limit=128):
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 128:
            raise ValueError('Invalid reconciliation checkpoint cursor.')
        with self._transaction() as conn:
            rows = conn.execute('SELECT rowid,* FROM reconciliation_checkpoints WHERE retired=0 AND rowid>? '
                'AND server_id=? AND executor_id=? ORDER BY rowid LIMIT ?',
                (after,server_id,executor_id,limit)).fetchall()
            return [(row['rowid'],self._decode_checkpoint(row),row['digest']) for row in rows]

    def mark_reconciliation_checkpoint_retired(self, proof, digest):
        identity = self._checkpoint_identity(proof['ack'],proof['observation'])
        with self._transaction() as conn:
            row = conn.execute('SELECT * FROM reconciliation_checkpoints WHERE identity=?',(identity,)).fetchone()
            if row is None or self._decode_checkpoint(row) != proof or row['digest'] != digest:
                raise ValueError('The original reconciliation checkpoint is required.')
            conn.execute('UPDATE reconciliation_checkpoints SET retired=1 WHERE identity=?',(identity,))
