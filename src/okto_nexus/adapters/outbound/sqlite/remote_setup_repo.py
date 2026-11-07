"""Transactional remote review/checkpoint storage and exact canonical child joins."""
import json

from ....errors import ErrorCode, OktoNexusError
from .execution_agent_revisions import current_agent_revisions


MAX_ROOTS_PER_ACTOR = 1024
MAX_REVIEWS_PER_ROOT = 32


def _capacity(reason, limit):
    raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED,
        'Retained remote setup capacity was reached; existing receipts remain recoverable.',
        {'reason': reason, 'limit': limit})


def conflict(reason):
    raise OktoNexusError(ErrorCode.CONFLICT,'Remote setup changed; review the current facts.',{'reason':reason})


class SqliteRemoteSetupRepo:
    def get(self, uow, *, actor, setup_run_id, revision=None):
        row = uow.connection.execute('SELECT r.*,v.review_json,v.request_hash,v.previous_review_revision FROM remote_setup_runs r '
            'JOIN remote_setup_reviews v ON v.actor_agent_id=r.actor_agent_id AND v.setup_run_id=r.setup_run_id '
            'AND v.review_revision=COALESCE(?,r.current_review_revision) '
            'WHERE r.actor_agent_id=? AND r.setup_run_id=?',(revision,actor,setup_run_id)).fetchone()
        if row is None:
            return None
        result=dict(row)
        result['review']=json.loads(result.pop('review_json'))
        result['bootstrap']=json.loads(result.pop('bootstrap_json')) if row['bootstrap_json'] else None
        result['bootstrap_baseline']=json.loads(result.pop('bootstrap_baseline_json')) if row['bootstrap_baseline_json'] else None
        result['final_binding']=json.loads(result.pop('final_binding_json')) if row['final_binding_json'] else None
        return result

    def for_subject(self, uow, *, setup_run_id, agent_id):
        rows = uow.connection.execute(
            "SELECT actor_agent_id FROM remote_setup_runs WHERE setup_run_id=? "
            "AND json_extract(bootstrap_json,'$.agent_id')=? LIMIT 2", (setup_run_id,agent_id)).fetchall()
        if len(rows) != 1:
            return None
        return self.get(uow, actor=rows[0][0], setup_run_id=setup_run_id)

    def save_review(self,uow,*,actor,review,request_hash,expected_revision,now):
        root,revision=review['draft']['setup_run_id'],review['review_revision']
        conn=uow.connection
        # These bounded reads share the caller's writer transaction with both
        # the revision and its current pointer. A failed capacity check never
        # advances that pointer, erases a receipt or makes a key available again.
        if expected_revision is None:
            count=conn.execute('SELECT COUNT(*) FROM (SELECT 1 FROM remote_setup_runs '
                'WHERE actor_agent_id=? LIMIT ?)', (actor,MAX_ROOTS_PER_ACTOR)).fetchone()[0]
            if count>=MAX_ROOTS_PER_ACTOR:
                _capacity('REMOTE_SETUP_ROOT_CAPACITY',MAX_ROOTS_PER_ACTOR)
        existing=conn.execute('SELECT 1 FROM remote_setup_reviews WHERE actor_agent_id=? '
            'AND setup_run_id=? AND review_revision=?',(actor,root,revision)).fetchone()
        if existing is None:
            count=conn.execute('SELECT COUNT(*) FROM (SELECT 1 FROM remote_setup_reviews '
                'WHERE actor_agent_id=? AND setup_run_id=? LIMIT ?)',
                (actor,root,MAX_REVIEWS_PER_ROOT)).fetchone()[0]
            if count>=MAX_REVIEWS_PER_ROOT:
                _capacity('REMOTE_SETUP_REVIEW_CAPACITY',MAX_REVIEWS_PER_ROOT)
        if expected_revision is None:
            conn.execute('INSERT INTO remote_setup_runs(actor_agent_id,setup_run_id,current_review_revision,created_at,updated_at) '
                'VALUES(?,?,?,?,?)',(actor,root,revision,now,now))
        else:
            changed=conn.execute('UPDATE remote_setup_runs SET current_review_revision=?,updated_at=? '
                'WHERE actor_agent_id=? AND setup_run_id=? AND current_review_revision=?',
                (revision,now,actor,root,expected_revision)).rowcount
            if changed!=1:
                conflict('REVIEW_CHANGED')
        encoded=json.dumps(review,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        conn.execute('INSERT INTO remote_setup_reviews VALUES(?,?,?,?,?,?,?) ON CONFLICT DO NOTHING',
            (actor,root,revision,request_hash,expected_revision,encoded,now))

    def save_bootstrap(self,uow,*,actor,setup_run_id,revision,receipt,baseline,now):
        changed=uow.connection.execute('UPDATE remote_setup_runs SET bootstrap_json=?,bootstrap_review_revision=?,bootstrap_baseline_json=?,updated_at=? '
            'WHERE actor_agent_id=? AND setup_run_id=? AND current_review_revision=? AND bootstrap_json IS NULL',
            (json.dumps(receipt,sort_keys=True,separators=(',',':')),revision,json.dumps(baseline),now,actor,setup_run_id,revision)).rowcount
        if changed!=1:
            conflict('BOOTSTRAP_CHANGED')

    def machine_review(self, uow, *, agent_id, connector_id):
        server_id = self.server_id(uow)
        selected = uow.connection.execute(
            "SELECT executor_id,registered_by_agent_id FROM execution_executors "
            "WHERE server_id=? AND connector_id=? AND kind='remote'", (server_id,connector_id)).fetchone()
        if selected is not None and selected['registered_by_agent_id'] != agent_id:
            conflict('CONNECTOR_ID_OCCUPIED')
        # Same canonical predicates/order as remote_machine_policy.other_machines,
        # with a sentinel limit and a metadata-only projection.
        rows = uow.connection.execute(
            'SELECT b.binding_id,b.executor_id,b.endpoint_id,b.binding_revision,'
            'ep.revision AS endpoint_revision,e.connector_id FROM execution_bindings b '
            'JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id '
            'JOIN execution_executors e ON e.server_id=b.server_id AND e.executor_id=b.executor_id '
            "WHERE b.server_id=? AND ep.agent_id=? AND b.executor_id<>? AND e.kind='remote' "
            "AND e.revoked_at IS NULL AND ep.enabled=1 AND ep.activation_state='approved' "
            'ORDER BY b.binding_id LIMIT 101',
            (server_id,agent_id,selected['executor_id'] if selected else '')).fetchall()
        if len(rows) > 100:
            conflict('REMOTE_SETUP_REVIEW_TOO_LARGE')
        return [dict(row) for row in rows]

    def server_id(self,uow):
        row=uow.connection.execute('SELECT server_id FROM execution_installation WHERE singleton=1').fetchone()
        if row is None:
            conflict('SERVER_UNAVAILABLE')
        return row[0]

    def baseline(self,uow,*,agent_id):
        from ....application.connection_setup import baseline
        return baseline(uow,agent_id)

    def occupied_agent(self,uow,*,agent_id):
        return uow.connection.execute('SELECT 1 FROM agents WHERE agent_id=?',(agent_id,)).fetchone() is not None

    def credential(self,uow,*,agent_id,persist):
        server,revisions,_=current_agent_revisions(None,agent_id=agent_id,uow=uow,persist=persist)
        stored=uow.connection.execute('SELECT credential_epoch FROM execution_agent_revisions WHERE server_id=? AND agent_id=?',
            (server,agent_id)).fetchone()
        return dict(server_id=server,credential_epoch=revisions.credential_epoch,
            anchored_epoch=stored[0] if stored else None)

    def materialization(self,uow,*,record,proposal_id=None):
        boot=record['bootstrap']
        if boot is None:
            return None
        review=record['review']
        conn=uow.connection
        rows=conn.execute('SELECT * FROM execution_proposals WHERE server_id=? AND subject_agent_id=? '
            'AND (? IS NULL OR proposal_id=?) AND client_intent_id=? LIMIT 2',
            (boot['server_id'],boot['agent_id'],proposal_id,proposal_id,review['child_requests']['prepare'])).fetchall()
        if len(rows)!=1:
            return None
        row=dict(rows[0])
        proposal=json.loads(row['proposal_json'])
        expected=json.loads(row['expected_revisions_json'])
        link=expected.get('remote_setup')
        if not isinstance(link,dict) or link.get('actor_agent_id')!=record['actor_agent_id'] or link.get('setup_run_id')!=record['setup_run_id'] or link.get('review_revision')!=review['review_revision']:
            return None
        realization=conn.execute('SELECT r.*,w.workspace_id FROM execution_realizations r JOIN execution_workspace_bindings w '
            'ON w.server_id=r.server_id AND w.executor_id=r.executor_id AND w.workspace_binding_id=r.workspace_binding_id '
            'WHERE r.server_id=? AND r.executor_id=? AND r.realization_ref=? AND r.subject_agent_id=?',
            (boot['server_id'],proposal['executor_id'],proposal['realization_ref'],boot['agent_id'])).fetchone()
        executor=conn.execute('SELECT connector_id,registered_by_agent_id FROM execution_executors WHERE server_id=? AND executor_id=?',
            (boot['server_id'],proposal['executor_id'])).fetchone()
        registration=conn.execute('SELECT resolved_json FROM execution_client_intents WHERE server_id=? AND actor_agent_id=? AND client_intent_id=?',
            (boot['server_id'],boot['agent_id'],review['child_requests']['register'])).fetchone()
        if realization is None or executor is None or registration is None:
            return None
        resolved=json.loads(registration[0])
        if (resolved.get('executor_id')!=proposal['executor_id'] or executor['registered_by_agent_id']!=boot['agent_id']
                or realization['client_intent_id']!=review['child_requests']['realize']
                or realization['workspace_id']!=boot['workspace_id']
                or realization['candidate_ref']!=proposal['candidate_ref']
                or realization['inventory_revision']!=proposal['inventory_revision']
                or realization['local_root_proof_digest']!=expected.get('root_proof_digest')
                or realization['configuration_digest']!=expected.get('configuration_digest')
                or resolved.get('server_id')!=boot['server_id']
                or resolved.get('connector_id')!=executor['connector_id']):
            return None
        final=None
        if row['status']=='APPLIED':
            proof=json.loads(row['operator_proof_json'] or '{}')
            finish_id=row['proposal_id']+'_setup'
            committed=conn.execute('SELECT result_json FROM connection_setup_commits WHERE actor_agent_id=? AND client_intent_id=?',
                (proof.get('operator_agent_id',record['actor_agent_id']),finish_id)).fetchone()
            if committed is not None:
                saved=json.loads(committed[0])
                binding=saved.get('binding') or {}
                if saved.get('agent_id')==proposal['agent_id'] and binding.get('binding_id')==proposal['binding_id'] and binding.get('agent_id')==proposal['agent_id']:
                    final={key:proposal[key] for key in ('server_id','agent_id','workspace_id','executor_id','binding_id','proposal_id')}
                    final['finish_id']=finish_id
        from ....application.execution_binding_approvals import public_review_facts
        return dict(proposal=proposal,expected=public_review_facts(expected),status=row['status'],expires_at=row['expires_at'],
            approval_id=expected.get('operator_approval_id'),connector_id=executor['connector_id'],
            local_consent_id=realization['local_consent_id'],root_proof_digest=realization['local_root_proof_digest'],
            configuration_digest=realization['configuration_digest'],final_binding=final)


def _require_bootstrap_credential(uow, record):
    boot = record['bootstrap']
    if boot is None:
        conflict('REMOTE_SETUP_ROOT_UNAVAILABLE')
    current = SqliteRemoteSetupRepo().credential(uow, agent_id=boot['agent_id'], persist=False)
    if (current['server_id'] != boot['server_id']
            or current['credential_epoch'] != boot['credential_epoch']
            or current['anchored_epoch'] != current['credential_epoch']):
        conflict('REMOTE_SETUP_CREDENTIAL_CHANGED')


def validate_proposal_root(uow,*,reference,request,server_id,subject_agent_id):
    """Bind a host's ordinary proposal to one reviewed root; never approve it."""
    from ....application.remote_setup_contract import reference as normalize_reference
    reference=normalize_reference(reference)
    rows=uow.connection.execute('SELECT v.actor_agent_id FROM remote_setup_reviews v JOIN remote_setup_runs r '
        'USING(actor_agent_id,setup_run_id) WHERE v.setup_run_id=? AND v.review_revision=? '
        'AND json_extract(r.bootstrap_json,\'$.agent_id\')=? AND json_extract(r.bootstrap_json,\'$.server_id\')=? LIMIT 2',
        (reference['setup_run_id'],reference['review_revision'],subject_agent_id,server_id)).fetchall()
    if len(rows)!=1:
        conflict('REMOTE_SETUP_ROOT_UNAVAILABLE')
    repo=SqliteRemoteSetupRepo()
    record=repo.get(uow,actor=rows[0][0],setup_run_id=reference['setup_run_id'],revision=reference['review_revision'])
    review,boot=record['review'],record['bootstrap']
    _require_bootstrap_credential(uow, record)
    if (record['current_review_revision'] != reference['review_revision']
            or request['client_intent_id']!=review['child_requests']['prepare'] or request['workspace_id']!=boot['workspace_id']):
        conflict('REMOTE_SETUP_CHILD_SCOPE_CHANGED')
    # This narrow setup intent may prepare a remote configuration before Finish
    # changes runtime/location. It creates no execution authority. Existing
    # policies and admission paths are untouched.
    from nexus_connector_core.connection_configuration import parse_portable_connection_configuration
    from nexus_connector_core import CoreError
    try:
        configuration = parse_portable_connection_configuration(request.get('connection_configuration'))
    except (CoreError, TypeError, ValueError):
        conflict('REMOTE_SETUP_CONFIGURATION_REQUIRED')
    draft = review['draft']
    if (configuration != draft['configuration'] or request.get('project_preset') != review['selection']['project_preset']
            or request.get('replace_binding_id') is not None or request.get('adopt_endpoint_id') is not None
            or request['adapter_id'] != draft['installation']['adapter_id']
            or request['candidate_ref'] != draft['installation']['candidate_ref']):
        conflict('REMOTE_SETUP_REVIEW_CHANGED')
    executor = uow.connection.execute(
        "SELECT connector_id,registered_by_agent_id,kind FROM execution_executors WHERE server_id=? AND executor_id=?",
        (server_id, request['executor_id'])).fetchone()
    realization = uow.connection.execute(
        'SELECT * FROM execution_realizations WHERE server_id=? AND executor_id=? AND realization_ref=? AND subject_agent_id=?',
        (server_id, request['executor_id'], request['realization_ref'], subject_agent_id)).fetchone()
    registration = uow.connection.execute(
        'SELECT resolved_json FROM execution_client_intents WHERE server_id=? AND actor_agent_id=? AND client_intent_id=?',
        (server_id, subject_agent_id, review['child_requests']['register'])).fetchone()
    if (executor is None or executor['kind'] != 'remote' or executor['connector_id'] != draft['connector_id']
            or executor['registered_by_agent_id'] != subject_agent_id
            or realization is None or realization['client_intent_id'] != review['child_requests']['realize']
            or realization['local_consent_id'] != draft['local_consent']['local_consent_id']
            or registration is None or json.loads(registration[0]).get('executor_id') != request['executor_id']):
        conflict('REMOTE_SETUP_CHILD_SCOPE_CHANGED')
    return dict(reference,actor_agent_id=record['actor_agent_id'])


def require_current_proposal_root(uow, *, row, expected, apply_intent_id=None):
    """Extra CAS for an explicitly linked root; canonical approval remains required."""
    link = expected.get('remote_setup')
    if link is None:
        return
    if not isinstance(link, dict) or set(link) != {'actor_agent_id', 'setup_run_id', 'review_revision'}:
        conflict('REMOTE_SETUP_ROOT_UNAVAILABLE')
    record = SqliteRemoteSetupRepo().get(uow, actor=link['actor_agent_id'], setup_run_id=link['setup_run_id'])
    if (record is None or record['current_review_revision'] != link['review_revision']
            or record['bootstrap'] is None
            or record['bootstrap']['agent_id'] != row['subject_agent_id']
            or record['bootstrap']['server_id'] != row['server_id']
            or record['review']['child_requests']['prepare'] != row['client_intent_id']
            or apply_intent_id is not None and apply_intent_id != record['review']['child_requests']['apply']):
        conflict('REMOTE_SETUP_REVIEW_CHANGED')
    _require_bootstrap_credential(uow, record)


def record_finished_root(uow, *, row, expected, proposal, result):
    """Checkpoint canonical Finish references in its existing write transaction."""
    if expected.get('remote_setup') is None:
        return
    require_current_proposal_root(uow, row=row, expected=expected)
    link = expected['remote_setup']
    if (result.get('saved') is not True or result.get('agent_id') != proposal['agent_id']
            or (result.get('binding') or {}).get('binding_id') != proposal['binding_id']):
        conflict('REMOTE_SETUP_FINISH_UNCONFIRMED')
    final = {key: proposal[key] for key in ('server_id', 'agent_id', 'workspace_id',
        'executor_id', 'binding_id', 'proposal_id')}
    final['finish_id'] = proposal['proposal_id'] + '_setup'
    changed = uow.connection.execute(
        'UPDATE remote_setup_runs SET final_binding_json=? WHERE actor_agent_id=? AND setup_run_id=? '
        'AND current_review_revision=? AND final_binding_json IS NULL',
        (json.dumps(final,sort_keys=True,separators=(',',':')), link['actor_agent_id'],
         link['setup_run_id'], link['review_revision'])).rowcount
    if changed != 1:
        conflict('REMOTE_SETUP_FINISH_CHANGED')
