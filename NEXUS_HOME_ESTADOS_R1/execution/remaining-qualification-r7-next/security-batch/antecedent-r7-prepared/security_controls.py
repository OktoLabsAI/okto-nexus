"""Prepared fixture controls. Imported only inside an approved own fixture.

No product import, SQL mutation, token persistence or native command here.
Management uses the fixture's canonical operator session; publication uses the
separate, narrowly issued observation token held in memory.
"""
import hashlib
import json
import base64


PRODUCTIVE_TABLES = (
    'connection_setup_commits', 'execution_bindings', 'agent_endpoints',
    'runtime_execution_grants', 'messages', 'message_deliveries', 'handoffs',
    'sessions', 'execution_sessions', 'execution_operations', 'execution_decisions',
    'execution_dispatch_outbox', 'delivery_outbox', 'runtime_handoff_bindings',
    'approvals', 'connection_authorization_receipts', 'execution_receipts',
    'runtime_native_approvals', 'runtime_relay_decisions', 'execution_results',
    'execution_event_ingress', 'execution_event_watermarks', 'runtime_results', 'events',
)
TABLES = PRODUCTIVE_TABLES + (
    'execution_leases', 'execution_session_capabilities', 'agents',
    'runtime_work_outcomes', 'one_shot_slots', 'execution_tool_claims',
)


class SecurityControls:
    def __init__(self, deps, controls, references, write):
        self.deps = deps
        self.controls = controls
        self.references = references
        self.write = write
        self.publisher = None
        self.private = controls.root / 'control/security-private'
        assert self.private.resolve().is_relative_to(controls.root.resolve())
        self.private.mkdir(mode=0o700)

    def snapshot(self, label):
        assert label in {'before', 'before-get', 'after-get', 'after-revoke', 'before-obs', 'after-idle', 'after-completion'}
        result, private = {}, {}
        with self.deps.connection_factory.unit_of_work(write=False) as uow:
            for table in TABLES:
                # Table names are constants, never browser/control input.
                cursor = uow.connection.execute('SELECT * FROM ' + table)
                columns = [column[0] for column in cursor.description]
                rows = [tuple(row) for row in cursor]
                cursor.close()
                def encode(value):
                    assert isinstance(value, bytes)
                    return {'sqlite_blob_base64': base64.b64encode(value).decode('ascii')}
                encoded = sorted(json.dumps(row, ensure_ascii=True, default=encode).encode() for row in rows)
                digest = hashlib.sha256()
                for row in encoded:
                    digest.update(len(row).to_bytes(8, 'big'))
                    digest.update(row)
                result[table] = {'rows': len(rows), 'sha256': digest.hexdigest()}
                primary = [row['name'] for row in sorted(
                    uow.connection.execute('PRAGMA table_info(' + table + ')').fetchall(),
                    key=lambda row: row['pk'],
                ) if row['pk']]
                private[table] = {'columns': columns, 'primary_key': primary,
                                  'rows': [json.loads(row) for row in encoded]}
        destination = self.private / (label + '.json')
        assert not destination.exists(), 'Snapshots are single-use, never overwrite antecedents'
        destination.write_text(json.dumps(private, ensure_ascii=True, indent=2) + '\n')
        destination.chmod(0o600)
        self.write('security-' + label + '.json', {'tables': result})
        return result

    def revoke_first_session_grant(self):
        """Discover the exact own grant read-only; DELETE is the only mutation."""
        ref = self.references[0]
        with self.deps.connection_factory.unit_of_work(write=False) as uow:
            rows = uow.connection.execute(
                'SELECT DISTINCT l.grant_id FROM execution_sessions s '
                'JOIN execution_leases l USING(server_id,executor_id,session_id) '
                'JOIN runtime_execution_grants g ON g.grant_id=l.grant_id '
                'WHERE s.server_id=? AND s.executor_id=? AND s.binding_id=? '
                'AND s.workspace_id=? AND s.workspace_binding_id=? '
                'AND g.endpoint_id=? AND g.workspace_id=? AND g.represented_agent_id=? '
                'AND g.revoked_at IS NULL',
                tuple(ref[key] for key in (
                    'server_id', 'executor_id', 'binding_id', 'workspace_id',
                    'workspace_binding_id', 'endpoint_id', 'workspace_id', 'agent_id',
                )),
            ).fetchall()
        assert len(rows) == 1, 'Require one exact session grant; never choose latest'
        grant_id = rows[0][0]
        answer = self.controls.revoke_grant(grant_id)
        assert answer['revoked'] is True
        with self.deps.connection_factory.unit_of_work(write=False) as uow:
            grant = uow.connection.execute(
                'SELECT revoked_at FROM runtime_execution_grants WHERE grant_id=?', (grant_id,),
            ).fetchone()
            affected = [dict(row) for row in uow.connection.execute(
                'SELECT DISTINCT s.server_id,s.executor_id,s.session_id,s.binding_id,'
                's.workspace_id,s.workspace_binding_id,s.owner_generation,s.lease_state '
                'FROM execution_sessions s JOIN execution_leases l '
                'USING(server_id,executor_id,session_id) WHERE l.grant_id=?', (grant_id,),
            )]
            assert grant and grant['revoked_at'] is not None and affected
            assert all(row['lease_state'] == 'REVOKED' for row in affected)
            assert not uow.connection.execute(
                "SELECT 1 FROM execution_leases WHERE grant_id=? AND status!='REVOKED'", (grant_id,),
            ).fetchone()
            assert not uow.connection.execute(
                'SELECT 1 FROM execution_session_capabilities c JOIN execution_leases l '
                'USING(server_id,executor_id,session_id) '
                'WHERE l.grant_id=? AND c.revoked_at IS NULL', (grant_id,),
            ).fetchone()
        self.write('security-revocation.json', {
            'method': 'DELETE', 'grant_id': grant_id, 'sessions': affected,
            'process_exit_claimed': False, 'reader_auth_revoked': False,
        })
        self.snapshot('after-revoke')

    def prepare_observation_owner(self):
        assert self.publisher is None
        ref = self.references[0]
        headers = self.controls.operator_headers()
        base = '/api/v1/observations/sources'
        source = self.controls.request('POST', base, {
            'agent_id': ref['agent_id'], 'source_kind': 'custom',
            'workspace_ids': [ref['workspace_id']], 'registration_ref': 'hst-security-owner',
        }, headers=headers)['source']
        source_id = source['source_id']
        instance = self.controls.request('POST', base + '/' + source_id + '/instances', {
            'expected_revision': source['revision'], 'workspace_id': ref['workspace_id'],
            'external_instance_ref': 'hst-security-instance',
        }, headers=headers)['instance']
        # Read back the current management revision; do not guess whether
        # instance creation increments the source revision.
        current = self.controls.request('GET', base + '/' + source_id, headers=headers)['source']
        issued = self.controls.request('POST', base + '/' + source_id + '/tokens', {
            'expected_revision': current['revision'], 'instance_grants': [{
                'observed_instance_id': instance['observed_instance_id'],
                'generation': instance['generation'],
            }],
        }, headers=headers)
        self.publisher = {'source_id': source_id, 'instance': instance, 'token': issued['token'], 'sequence': 0}
        self.write('security-observation-owner.json', {
            'source_id': source_id, 'observed_instance_id': instance['observed_instance_id'],
            'generation': instance['generation'], 'token_written': False,
        })
        self.snapshot('before-obs')

    def publish_observation(self, completion=False):
        owner = self.publisher
        assert owner is not None
        expected_sequence = 2 if completion else 1
        assert owner['sequence'] == expected_sequence - 1, 'No replay or silent reordering'
        body = {
            'schema_version': 1, 'source_id': owner['source_id'],
            'observed_instance_id': owner['instance']['observed_instance_id'],
            'generation': owner['instance']['generation'], 'sequence': expected_sequence,
            'state': 'idle', 'evidence': 'reported', 'observed_at': self.deps.clock.now_iso(),
            'valid_for_seconds': 120,
            'reason_code': 'external_completion' if completion else 'external_idle',
        }
        if completion:
            body['current_completion_ref'] = 'hst-security-reported-completion'
        self.controls.request('POST', '/v1/observations/activity', body, headers={
            'Authorization': 'Bearer ' + owner['token'], 'Cookie': '',
        })
        owner['sequence'] = expected_sequence
        # There is deliberately NO state='done': the canonical schema has
        # idle + reported completion evidence, not canonical task success.
        self.snapshot('after-completion' if completion else 'after-idle')
