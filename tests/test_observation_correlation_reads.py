"""OBS12 public reads over real HTTP, SQLite, and durable receipt ingress."""
from contextlib import contextmanager
from collections import Counter
import json
import re

from nexus_connector_core import R4_PREVIEW_REVISION
import pytest

from okto_nexus.adapters.outbound.sqlite import observation_correlation_projection as batch
from okto_nexus.adapters.outbound.sqlite.execution_receipts import append_execution_receipt
from okto_nexus.adapters.outbound.sqlite.execution_tickets import VerifiedExecutionTicket
from okto_nexus.application.auth import AgentKeyAuthService
from test_observation_correlation_http import (
    correlation_http as correlation_fixture, canonical_rows, insert, IMAGE,
)

correlation_http = correlation_fixture
BASE = '/api/v1/observations'
ATTENTION = '/api/v1/attention'
PUBLISH = '/v1/observations/activity'


@pytest.fixture
def reads(request):
    env = request.getfixturevalue('correlation_http')
    env.deps.config.feature_attention = True
    env.sequence = 1
    return env


def data(response):
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    return response.json()['data']


def get(env, path, headers=None):
    return data(env.client.get(path, headers=env.headers if headers is None else headers))


def detail(env, headers=None):
    return get(env, BASE+'/instances/'+env.instance['observed_instance_id'], headers)['item']


def select(env):
    return data(env.client.post(env.path, headers=env.headers, json=env.body))['correlation']


def publish(env, state='blocked', **changes):
    env.sequence += 1
    body = dict(schema_version=1, source_id=env.source['source_id'],
        observed_instance_id=env.instance['observed_instance_id'], generation=env.instance['generation'],
        sequence=env.sequence, state=state, evidence='inferred', observed_at=env.deps.clock.now_iso(), **changes)
    return data(env.client.post(PUBLISH, headers={'Authorization':'Bearer '+env.publish_token}, json=body))


def native_receipt(env):
    scope = dict(env.scope, binding_revision=1)
    now = env.deps.clock.now_iso()
    namespace = {key: scope[key] for key in ('server_id', 'executor_id')}
    with env.deps.connection_factory.unit_of_work() as uow:
        insert(uow.connection, 'execution_leases', **namespace, session_id=scope['session_id'],
            lease_serial=1, lease_id='reads-lease', grant_id='reads-grant', allowed_actions_json='["turn.submit"]',
            authorization_revision=1, configuration_revision=1, owner_generation=3, connection_generation=7,
            credential_epoch=1, valid_until_server='2099-01-01T00:00:00Z', request_id='reads-request', status='ACTIVE',
            connection_id='correlation-owner', scope_json=json.dumps(scope), applied_at=now)
        insert(uow.connection, 'execution_operations', **namespace, operation_id='reads-turn',
            subject_agent_id='observed', actor_agent_id='observed',
            **{key: scope[key] for key in ('binding_id', 'workspace_id', 'workspace_binding_id', 'session_id')},
            action='turn.submit', intent_hash='sha256:'+'e'*64, semantic_payload='{}',
            expected_revisions_json=json.dumps(scope), admission_state='ACCEPTED', created_at=now)
        insert(uow.connection, 'execution_dispatch_outbox', **namespace, operation_id='reads-turn',
            dispatch_state='DISPATCHED', lease_id='reads-lease', lease_serial=1)
    principal = VerifiedExecutionTicket('reads-ticket', scope['server_id'], scope['executor_id'],
        scope['binding_id'], 'observed', frozenset({'receipt:publish'}), 1, 1)
    for revision, stage in enumerate(('RECEIVED_DURABLE', 'RUNNING', 'SUCCEEDED'), 1):
        frame = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='operation.receipt',
            **namespace, binding_id=scope['binding_id'], agent_id='observed', session_id=scope['session_id'],
            connection_id='correlation-owner', connection_generation=7, operation_id='reads-turn',
            intent_hash='sha256:'+'e'*64, receipt_revision=revision, stage=stage,
            possible_effect=revision > 1, retry_safe=revision == 1)
        append_execution_receipt(env.deps.connection_factory, principal=principal, frame=frame)


def assert_minimal(env, item):
    assert item['canonical_session_ref'] == {key: env.body['selection'][key] for key in (
        'server_id', 'executor_id', 'session_id', 'open_operation_id', 'session_owner_generation', 'stream_epoch')}
    value = item['canonical_observation']
    assert set(value) == {'correlation_revision', 'verified_at', 'provenance', 'session_lifecycle_state',
                          'last_received_receipt', 'precedence'}
    assert value['correlation_revision'] == 1 and value['session_lifecycle_state'] == 'READY'
    assert value['precedence'] == 'canonical_core_facts'
    meta = value['last_received_receipt']
    assert meta == dict(status='verified', operation_id='reads-turn', action='turn.submit', stage='SUCCEEDED',
        receipt_revision=3, received_at=meta['received_at'], provenance='core_committed')
    raw = json.dumps(item)
    assert IMAGE not in raw and env.publish_token not in raw
    assert not any('"'+key+'"' in raw for key in ('proof', 'pid', 'host_id', 'creation_filetime',
        'image_path_sha256', 'binding_hash', 'canonical_frame', 'frame_digest', 'source_connection_id',
        'publisher_token_id', 'api_key_hash'))


def test_http_detail_list_and_attention_publish_minimal_separate_canonical_facts(reads):
    env = reads
    select(env)
    native_receipt(env)
    publish(env)
    calls = env.birth_calls, env.os_calls
    own_headers = {'Authorization':'Bearer '+env.agent_key}
    exact = detail(env)
    assert_minimal(env, exact)
    assert_minimal(env, detail(env, own_headers))
    page = get(env, BASE+'?agent_id=observed&workspace_id=obs-workspace')['items']
    assert page == [exact]
    item, = get(env, ATTENTION+'?kind=external_blocked')['items']
    assert item['external_observation'] == exact
    assert item['allowed_actions'] == ['inspect_external_observation']
    assert item['session_id'] is item['operation_id'] is None
    assert exact['activity_state'] == 'blocked' and exact['observational_only'] is True
    assert (env.birth_calls, env.os_calls) == calls


def test_summary_remains_external_and_does_not_read_native_batch(reads, monkeypatch):
    env = reads
    publish(env)
    before = get(env, BASE+'/summary')
    select(env)
    native_receipt(env)
    monkeypatch.setattr(batch, 'load', lambda *a, **k: pytest.fail('summary read native batch'))
    after = get(env, BASE+'/summary')
    for key in ('version', 'filters', 'feature_enabled', 'total_instances', 'activity', 'freshness', 'agents'):
        assert after[key] == before[key]
    assert after['activity'] == dict(working=0, idle=0, blocked=1, unknown=0)
    assert 'canonical' not in json.dumps(after)


def test_later_external_reports_preserve_canonical_facts_and_all_canonical_rows(reads):
    env = reads
    select(env)
    native_receipt(env)
    canonical = detail(env)['canonical_observation']
    before = canonical_rows(env)
    for state in ('blocked', 'idle', 'working'):
        publish(env, state)
        item = detail(env)
        assert item['activity_state'] == state
        assert item['canonical_observation'] == canonical
    assert canonical_rows(env) == before


@pytest.mark.parametrize('change', ['clear', 'rotate', 'source_revision', 'owner', 'stream', 'endpoint', 'executor', 'feature'])
def test_clear_rotation_and_current_fences_remove_public_correlation(reads, change):
    env = reads
    select(env)
    publish(env)
    assert detail(env)['canonical_session_ref'] is not None
    if change == 'clear':
        data(env.client.request('DELETE', env.path, headers=env.headers, json={'expected_revision':1}))
    elif change == 'rotate':
        data(env.client.post(env.source_path+'/instances/'+env.instance['observed_instance_id']+'/rotate',
            headers=env.headers, json=dict(expected_revision=env.source['revision'], expected_generation=env.instance['generation'])))
    elif change == 'source_revision':
        data(env.client.patch(env.source_path, headers=env.headers,
            json=dict(expected_revision=env.source['revision'], enabled=False)))
    elif change == 'feature':
        env.deps.config.feature_observations = False
    else:
        statements = dict(owner='UPDATE execution_sessions SET owner_generation=owner_generation+1',
            stream="UPDATE execution_sessions SET stream_epoch='replacement-stream'",
            endpoint='UPDATE agent_endpoints SET enabled=0',
            executor="UPDATE execution_executors SET revoked_at='2026-01-01T00:00:00Z'")
        with env.deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute(statements[change])
    current = detail(env)
    assert current['canonical_session_ref'] is current['canonical_observation'] is None
    for item in get(env, ATTENTION+'?kind=external_blocked&state=all')['items']:
        view = item['external_observation']
        assert view['canonical_session_ref'] is view['canonical_observation'] is None


def test_historical_completion_never_inherits_a_later_selected_correlation(reads):
    env = reads
    publish(env, 'idle', current_completion_ref='reads-completion-before-selection')
    old, = get(env, ATTENTION+'?kind=external_completion_unseen&state=all')['items']
    assert old['external_observation']['canonical_session_ref'] is None
    select(env)
    native_receipt(env)
    publish(env)
    assert detail(env)['canonical_session_ref'] is not None
    all_items = get(env, ATTENTION+'?state=all')['items']
    completion, = [item for item in all_items if item['kind'] == 'external_completion_unseen']
    assert completion['attention_id'] == old['attention_id']
    assert completion['external_observation']['canonical_session_ref'] is None
    assert completion['external_observation']['canonical_observation'] is None
    blocked, = [item for item in all_items if item['kind'] == 'external_blocked']
    assert_minimal(env, blocked['external_observation'])


def foreign_instance(env):
    auth = AgentKeyAuthService(env.deps.repos.agents, env.deps.clock)
    with env.deps.connection_factory.unit_of_work() as uow:
        env.deps.repos.agents.upsert(uow, agent_id='reads-foreign')
        auth.issue_key(uow, agent_id='reads-foreign')
        env.deps.repos.agents.set_permissions(uow, agent_id='reads-foreign', preset_id=None,
            permissions={'observations':{'manage_self':True, 'publish':True}})
        env.deps.repos.workspaces.upsert(uow, workspace_id='reads-foreign-workspace')
    source = data(env.client.post(BASE+'/sources', headers=env.headers, json=dict(agent_id='reads-foreign',
        source_kind='custom', workspace_ids=['reads-foreign-workspace'], registration_ref='reads-foreign-source')))['source']
    instance = data(env.client.post(BASE+'/sources/'+source['source_id']+'/instances', headers=env.headers,
        json=dict(expected_revision=source['revision'], workspace_id='reads-foreign-workspace', external_instance_ref='reads-foreign')))['instance']
    with env.deps.connection_factory.unit_of_work() as uow:
        original = env.deps.repos.observation_correlations.get(uow, observed_instance_id=env.instance['observed_instance_id'])
        selected = dict(original['selection'], source_id=source['source_id'], source_revision=source['revision'],
            observed_instance_id=instance['observed_instance_id'], generation=instance['generation'])
        env.deps.repos.observation_correlations.replace_selection(uow, selection=selected, proof=original['proof'],
            verified_at=original['verified_at'], now=env.deps.clock.now_iso(), max_records=4096,
            agent_id='reads-foreign', workspace_id='reads-foreign-workspace')
        # Poison only foreign correlation metadata: loading it would fail loudly.
        uow.connection.execute('UPDATE observation_correlations SET correlation_digest=? WHERE observed_instance_id=?',
            ('sha256:'+'f'*64, instance['observed_instance_id']))
    return source, instance


def test_self_agent_and_workspace_filters_do_not_load_foreign_private_scope(reads, monkeypatch):
    env = reads
    select(env)
    publish(env)
    source, foreign = foreign_instance(env)
    calls = []
    original = batch.load
    def tracked(uow, **kwargs):
        assert foreign['observed_instance_id'] not in kwargs['observed_instance_ids']
        calls.append(tuple(kwargs['observed_instance_ids']))
        return original(uow, **kwargs)
    monkeypatch.setattr(batch, 'load', tracked)
    own = {'Authorization':'Bearer '+env.agent_key}
    assert len(get(env, BASE, own)['items']) == 1
    assert detail(env, own)['agent_id'] == 'observed'
    for query in ('agent_id=observed', 'workspace_id=obs-workspace'):
        assert len(get(env, BASE+'?'+query)['items']) == 1
        assert len(get(env, ATTENTION+'?kind=external_blocked&'+query)['items']) == 1
    assert env.client.get(BASE+'/instances/'+foreign['observed_instance_id'], headers=own).status_code == 404
    assert env.client.get(BASE+'?source_id='+source['source_id'], headers=own).status_code == 404
    assert env.client.get(BASE+'?agent_id=reads-foreign', headers=own).status_code == 403
    assert calls and all(set(ids) <= {env.instance['observed_instance_id']} for ids in calls)


@contextmanager
def trace_reads(env, monkeypatch):
    statements = []
    original = env.deps.connection_factory.unit_of_work
    @contextmanager
    def traced(*args, **kwargs):
        with original(*args, **kwargs) as uow:
            uow.connection.set_trace_callback(statements.append)
            try:
                yield uow
            finally:
                uow.connection.set_trace_callback(None)
    with monkeypatch.context() as scoped:
        scoped.setattr(env.deps.connection_factory, 'unit_of_work', traced)
        yield statements


def grow_same_session(env, count=6):
    now = env.deps.clock.now_iso()
    instances = []
    with env.deps.connection_factory.unit_of_work() as uow:
        old = env.deps.repos.observation_correlations.get(uow, observed_instance_id=env.instance['observed_instance_id'])
        for index in range(count):
            instance = env.deps.repos.observations.create_instance(uow, source_id=env.source['source_id'],
                expected_revision=env.source['revision'], workspace_id='obs-workspace', external_instance_ref='reads-extra-'+str(index), now=now)
            instances.append(instance)
            selected = dict(old['selection'], observed_instance_id=instance['observed_instance_id'], generation=instance['generation'])
            env.deps.repos.observation_correlations.replace_selection(uow, selection=selected, proof=old['proof'],
                verified_at=old['verified_at'], now=now, max_records=4096, agent_id='observed', workspace_id='obs-workspace')
    token = data(env.client.post(env.source_path+'/tokens', headers=env.headers, json=dict(
        expected_revision=env.source['revision'], instance_grants=[{key:item[key] for key in ('observed_instance_id','generation')} for item in instances])))['token']
    reports = [dict(schema_version=1, source_id=env.source['source_id'], observed_instance_id=item['observed_instance_id'],
        generation=item['generation'], sequence=1, state='blocked', evidence='inferred', observed_at=env.deps.clock.now_iso()) for item in instances]
    data(env.client.post(PUBLISH, headers={'Authorization':'Bearer '+token}, json={'reports':reports}))


def test_read_query_count_is_constant_without_native_os_or_artifact_io_per_item(reads, monkeypatch, request):
    env = reads
    select(env)
    native_receipt(env)
    publish(env)
    calls = env.birth_calls, env.os_calls
    from okto_nexus.adapters.outbound.file.artifacts import LocalArtifactStore
    for method in ('describe', 'read_text', 'read_bytes'):
        monkeypatch.setattr(LocalArtifactStore, method, lambda *a, **k: pytest.fail('artifact hydration'))
    monkeypatch.setattr(env.host, 'read_existing_process_birth', lambda **k: pytest.fail('native birth read'))
    routes = [BASE+'?limit=200', ATTENTION+'?kind=external_blocked&limit=100', BASE+'/summary']
    # Retain cold HTTP counts separately. The first attention request performs
    # an extra agents lookup by api_key_hash; it is not per-item projection SQL.
    cold = []
    for route in routes:
        with trace_reads(env, monkeypatch) as statements:
            result = get(env, route)
        assert (len(result['items']) if 'items' in result else result['total_instances']) == 1
        cold.append(sum(sql.lstrip().upper().startswith(('SELECT', 'WITH')) for sql in statements))
    request.node.user_properties.append(('cold_http_query_counts', json.dumps(cold)))
    counts, profiles = [], []
    for expected in (1, 7):
        current, profile = [], []
        for route in routes:
            with trace_reads(env, monkeypatch) as statements:
                result = get(env, route)
            assert (len(result['items']) if 'items' in result else result['total_instances']) == expected
            current.append(sum(sql.lstrip().upper().startswith(('SELECT', 'WITH')) for sql in statements))
            profile.append(Counter(re.sub(r"'(?:''|[^'])*'", '?', sql).strip()[:350]
                for sql in statements if sql.lstrip().upper().startswith(('SELECT', 'WITH'))))
        counts.append(current)
        profiles.append(profile)
        if expected == 1:
            grow_same_session(env)
    differences = [dict(first_only=dict(first-second), second_only=dict(second-first))
        for first, second in zip(profiles[0], profiles[1])]
    request.node.user_properties.append(('warm_query_counts_1_and_7', json.dumps(counts)))
    request.node.user_properties.append(('redacted_query_differences', json.dumps(differences)))
    assert counts[0] == counts[1], differences
    assert all(number > 0 for number in counts[0])
    assert (env.birth_calls, env.os_calls) == calls
