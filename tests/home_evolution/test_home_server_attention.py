"""Canonical-occurrence port contract for a separate Server lane.

There is no global producer in today's migrated source tables. ContractItems
injects domain-valid, pre-authorized occurrences at the canonical query port;
it never inserts impossible NULL-workspace database rows or fabricates a native
producer. Real Home SQL/HTTP, workspace facts, operator authorization and
preference projection remain in use.
"""
# ruff: noqa: F811 -- explicit pytest fixtures
import json
import sqlite3
from types import SimpleNamespace
from contextlib import contextmanager

import pytest

from okto_nexus.adapters.outbound.sqlite.attention import SqliteAttentionQueries
from okto_nexus.adapters.outbound.sqlite import attention as attention_module
from okto_nexus.application import attention_operations as operations_module
from okto_nexus.domain.attention import digest, occurrence, with_preferences
from okto_nexus.errors import ErrorCode, OktoNexusError
from .fixtures import home_scenario as home_scenario, OPERATOR, WORKSPACES
from .test_home_queries import service as service
from .test_home_http import http as http
from .test_home_native import (decision_state as decision_state, opening as opening,
    isolated_native_inventory as isolated_native_inventory)


class ContractItems(SqliteAttentionQueries):
    def __init__(self, items):
        super().__init__()
        self.items, self.calls = items, 0

    @contextmanager
    def _relation(self, uow, **kwargs):
        self.calls += 1
        assert kwargs['context'].trusted_local_operator
        filters = kwargs['filters']
        if kwargs.get('source_scope') is not None or kwargs.get('server_only'):
            assert 'workspace_id' not in filters and 'agent_id' not in filters
        with SqliteAttentionQueries._relation(self, uow, **kwargs) as (sql, params):
            clauses = []
            params = dict(params, contract_items=json.dumps(self.items))
            for name in ('workspace_id', 'agent_id', 'category', 'kind', 'priority'):
                if name in filters:
                    params['contract_filter_'+name] = filters[name]
                    clauses.append("json_extract(item,'$."+name+"')=:contract_filter_"+name)
            if filters['state'] == 'active':
                clauses.append("json_extract(item,'$.active')=1")
            elif filters['state'] != 'all':
                params['contract_filter_state'] = filters['state']
                clauses.append("json_extract(item,'$.resolution')=:contract_filter_state")
            if filters['seen'] in ('seen', 'unseen'):
                clauses.append("json_extract(item,'$.seen_state.seen')="+('1' if filters['seen'] == 'seen' else '0'))
            elif filters['seen'] == 'snoozed':
                clauses.append("json_extract(item,'$.seen_state.snoozed')=1")
            yield ('WITH canonical_existing AS MATERIALIZED ('+sql+' SELECT item FROM viewing), '
                   'viewing AS MATERIALIZED (SELECT item FROM canonical_existing UNION ALL '
                   'SELECT nexus_attention_preferences_v1(j.value,p.seen_at,p.snoozed_until,p.revision,:now) '
                   'FROM json_each(:contract_items) j LEFT JOIN attention_preferences p '
                   "ON p.principal='operator' AND p.attention_id=json_extract(j.value,'$.attention_id')), "
                   'filtered AS MATERIALIZED (SELECT item FROM viewing WHERE '+(' AND '.join(clauses) or '1')+') ', params)


def item(now, ident, workspace=None, *, category='watch', priority=20, resolution='open'):
    return with_preferences(occurrence(kind='runtime_recovery_attention',
        source_type='contract_probe_only', source_id=ident, episode='probe',
        source_revision=[ident], first_detected_at=now, last_changed_at=now,
        workspace_id=workspace, agent_id='A', category=category, priority=priority,
        resolution=resolution, allowed_actions=()), now=now)


@pytest.fixture
def contracted(service, home_scenario):
    now = home_scenario.clock.now_iso()
    values = [item(now, f'global-{n}', category='watch' if n % 2 else 'action_required',
                   priority=30 if n == 3 else 20) for n in range(5)]
    values += [item(now, 'global-resolved', resolution='resolved'),
               item(now, 'project-a', WORKSPACES[0], category='action_required'),
               item(now, 'project-b', WORKSPACES[1], category='action_required')]
    queries = ContractItems(values)
    service.attention.queries = queries
    return service, queries, values


def test_server_lane_separate_from_all_project_counters_and_filters(contracted, home_scenario):
    service, queries, values = contracted
    before = home_scenario.counts()
    all_scope = service.read(context=OPERATOR)
    assert queries.calls == 1  # shared statement-local canonical projection
    assert all_scope['server_attention']['total'] == 5
    assert len(all_scope['server_attention']['items']) == 3
    assert all_scope['server_attention']['has_more']
    assert any(x['category'] == 'watch' for x in all_scope['server_attention']['items'])
    assert all(x['workspace_id'] is not None for x in all_scope['attention']['items'])
    assert all_scope['summary']['needs_you']['value'] == all_scope['attention']['total']
    for scope in ({'workspace_id': WORKSPACES[0]}, {'workspace_id':WORKSPACES[1]},
                  {'workspace_id':WORKSPACES[1], 'agent_id':'not-A', 'state':'running'}):
        result = service.read(context=OPERATOR, filters=scope)
        assert result['server_attention']['items'] == all_scope['server_attention']['items']
        assert result['server_attention']['revision'] == all_scope['server_attention']['revision']
        assert all(x['workspace_id'] == scope['workspace_id'] for x in result['attention']['items'])
        assert all(x['workspace_id'] == scope['workspace_id'] for x in result['work']['items'])
        assert all(x['workspace_id'] == scope['workspace_id'] for x in result['results']['items'])
    expected = {x['attention_id']:x for x in values if x['workspace_id'] is None and x['active']}
    assert all(x == expected[x['attention_id']] for x in all_scope['server_attention']['items'])
    assert home_scenario.counts() == before


def test_both_attention_lanes_page_without_crossing_scope_server_or_revision(contracted, home_scenario):
    service, queries, _ = contracted
    first = service.read(context=OPERATOR, section='server_attention', limit=2)
    second = service.read(context=OPERATOR, section='server_attention', limit=2, cursor=first['next_cursor'])
    third = service.read(context=OPERATOR, section='server_attention', limit=2, cursor=second['next_cursor'])
    assert len({x['attention_id'] for p in (first,second,third) for x in p['items']}) == 5
    assert third['next_cursor'] is None and not third['has_more']
    with pytest.raises(OktoNexusError):
        service.read(context=OPERATOR, section='attention', cursor=first['next_cursor'])
    with pytest.raises(OktoNexusError):
        service.read(context=OPERATOR, section='server_attention', filters={'workspace_id':WORKSPACES[0]}, cursor=first['next_cursor'])
    project = service.read(context=OPERATOR, section='attention', limit=1)
    all_ids = []
    while True:
        assert all(x['workspace_id'] is not None for x in project['items'])
        all_ids += [x['attention_id'] for x in project['items']]
        if not project['has_more']:
            break
        project = service.read(context=OPERATOR, section='attention', limit=1, cursor=project['next_cursor'])
    assert len(set(all_ids)) == len(all_ids) == project['total']
    original_item = queries.items[0]
    queries.items[0] = dict(original_item, source_revision=digest(['changed']))
    with pytest.raises(OktoNexusError) as exc:
        service.read(context=OPERATOR, section='server_attention', cursor=first['next_cursor'])
    assert exc.value.code == ErrorCode.CONFLICT

    canonical = service.attention.read(context=OPERATOR,
        filters={'workspace_id':WORKSPACES[0]}, limit=200)
    summary = service.attention.summary(context=OPERATOR,
        filters={'workspace_id':WORKSPACES[0]})
    assert summary['total'] == canonical['total'] == len(canonical['items'])
    assert all(row['workspace_id'] == WORKSPACES[0] for row in canonical['items'])
    # Restore content before testing installation binding: a stale revision
    # must not mask a missing Server identity fence.
    queries.items[0] = original_item
    assert service.read(context=OPERATOR, section='server_attention')['revision'] == first['revision']
    with home_scenario.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_installation SET server_id='replacement-server'")
    with pytest.raises(OktoNexusError) as exc:
        service.read(context=OPERATOR, section='server_attention', cursor=second['next_cursor'])
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_http_server_lane_scope_echo_and_closed_read_only_routes(http, contracted):
    service, _, _ = contracted
    http.app.state.home = service
    params = {'workspace_id':WORKSPACES[0], 'agent_id':'not-A', 'state':'running', 'limit':2}
    response = http.client.get('/api/v1/home/server-attention', params=params)
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data['scope'] == {k:v for k,v in params.items() if k != 'limit'}
    assert data['total'] == 5 and len(data['items']) == 2
    assert response.headers['cache-control'] == 'no-store'
    assert http.client.post('/api/v1/home/server-attention', json={}).status_code == 405
    assert http.client.get('/api/v1/home/server-attention', params={'unexpected':'x'}).status_code == 422
    assert http.client.get('/api/v1/home/attention').status_code == 200
    with pytest.raises(OktoNexusError) as exc:
        service.read(context=None, section='server_attention')
    assert exc.value.code == ErrorCode.PERMISSION_DENIED


def test_disabled_or_failed_canonical_source_is_not_false_empty_server_lane(service, home_scenario, monkeypatch):
    service.config.feature_attention = False
    result = service.read(context=OPERATOR)
    for lane in ('attention','server_attention'):
        assert result[lane]['status'] == 'disabled'
        assert result[lane]['total'] is None and not result[lane]['total_is_exact']
    service.config.feature_attention = True
    @contextmanager
    def broken(*args, **kwargs):
        raise OktoNexusError(ErrorCode.DB_ERROR, 'Unavailable', {})
        yield  # pragma: no cover
    monkeypatch.setattr(service.attention.queries, '_relation', broken)
    result = service.read(context=OPERATOR)
    assert result['work']['status'] == 'partial'
    assert result['results']['status'] == 'partial'
    assert result['server_attention']['status'] == 'unavailable'
    assert result['server_attention']['total'] is None
    assert result['summary']['needs_you']['value'] is None


def test_existing_migrated_sources_have_no_fabricated_server_incident(service):
    result = service.read(context=OPERATOR)
    assert result['server_attention']['status'] == 'ready'
    assert result['server_attention']['items'] == []
    assert result['server_attention']['total'] == 0


def test_global_preference_reuses_canonical_cas_and_keeps_project_sources_unchanged(contracted, home_scenario):
    service, _, _ = contracted
    before = service.read(context=OPERATOR, filters={'workspace_id':WORKSPACES[0]})
    occurrence = before['server_attention']['items'][0]
    changed = service.attention.mark_seen(context=OPERATOR, attention_id=occurrence['attention_id'],
        source_revision=occurrence['source_revision'], preference_revision=0)
    assert changed['item']['seen_state']['seen'] is True
    assert changed['item']['seen_state']['revision'] == 1
    after = service.read(context=OPERATOR, filters={'workspace_id':WORKSPACES[0]})
    for section in ('work','results','attention'):
        assert after[section] == before[section]
    with pytest.raises(OktoNexusError) as exc:
        service.attention.mark_seen(context=OPERATOR, attention_id=occurrence['attention_id'],
            source_revision=occurrence['source_revision'], preference_revision=0)
    assert exc.value.code == ErrorCode.CONFLICT


def test_server_projection_failure_keeps_other_sections_honest_and_authorization_denial_fatal(contracted, monkeypatch):
    service, queries, _ = contracted
    def fail_overview(*args, **kwargs):
        raise sqlite3.OperationalError('Synthetic overview materialization failure')
    original = service.queries.attention_page
    def fail_server(*args, **kwargs):
        if kwargs.get('serverwide'):
            raise sqlite3.OperationalError('Synthetic Server lane source failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(service.queries, 'overview', fail_overview)
    monkeypatch.setattr(service.queries, 'attention_page', fail_server)
    result = service.read(context=OPERATOR)
    assert result['server_attention']['status'] == 'unavailable'
    assert result['server_attention']['total'] is None
    assert result['attention']['status'] == result['work']['status'] == result['results']['status'] == 'ready'
    @contextmanager
    def forbidden(*args, **kwargs):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Synthetic source authorization denial', {})
        yield  # pragma: no cover
    monkeypatch.setattr(queries, '_relation', forbidden)
    with pytest.raises(OktoNexusError) as exc:
        service.read(context=OPERATOR)
    assert exc.value.code == ErrorCode.PERMISSION_DENIED


@pytest.mark.parametrize('declaration', [None, False])
def test_home_hint_never_prunes_undeclared_or_unbound_canonical_global_source(service, home_scenario, monkeypatch, declaration):
    """Contract-only source family, not installed in the product registry."""
    global_item = item(home_scenario.clock.now_iso(), 'unbound-contract-global')
    adapter = SimpleNamespace(SOURCE_SQL='SELECT '+"'"+json.dumps(global_item).replace("'","''")+"'"+
        ' AS facts WHERE :workspace_id IS NULL AND :agent_id IS NULL',
        build_policy=lambda uow, **kwargs: {'authorized':kwargs['context'].trusted_local_operator})
    if declaration is not None:
        adapter.WORKSPACE_BOUND = declaration
    application = SimpleNamespace(project=lambda facts, now, policy: [facts] if policy['authorized'] else [])
    original_import = attention_module.importlib.import_module
    def importing(name, package=None):
        if name == '.attention_contract_global':
            return adapter
        if name == 'okto_nexus.application.attention_contract_global':
            return application
        return original_import(name, package)
    monkeypatch.setattr(attention_module.importlib, 'import_module', importing)
    monkeypatch.setattr(attention_module, '_FAMILIES', dict(attention_module._FAMILIES,
        contract_global={'runtime_recovery_attention'}))
    result = service.read(context=OPERATOR,
        filters={'workspace_id':WORKSPACES[0], 'agent_id':'not-A', 'state':'running'})
    assert result['server_attention']['items'] == [global_item]
    assert result['attention']['total'] == result['summary']['needs_you']['value'] == 0
    server_page = service.read(context=OPERATOR, section='server_attention',
        filters={'workspace_id':WORKSPACES[1], 'agent_id':'not-A'})
    assert server_page['items'] == [global_item]


def test_workspace_bound_sources_keep_pushdown_and_classic_attention_is_unchanged(service, home_scenario, monkeypatch):
    with home_scenario.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET status='VERIFYING',claimed_by='B',verify_by=? WHERE workspace_id=?",
            (json.dumps({'kind':'agent','agent_id':'operator'}),WORKSPACES[1]))
    projected = []
    original = operations_module.project
    def observe(facts, now, policy):
        projected.append(facts.get('workspace_id'))
        return original(facts, now, policy)
    monkeypatch.setattr(operations_module, 'project', observe)
    canonical_before = service.attention.read(context=OPERATOR)
    assert WORKSPACES[1] in projected
    projected.clear()
    result = service.read(context=OPERATOR, filters={'workspace_id':WORKSPACES[0]})
    assert result['work']['status'] == result['server_attention']['status'] == 'ready'
    assert WORKSPACES[1] not in projected
    assert all(x['workspace_id'] == WORKSPACES[0] for x in result['attention']['items'])
    projected.clear()
    canonical_after = service.attention.read(context=OPERATOR)
    assert canonical_after == canonical_before
    assert WORKSPACES[1] in projected


@pytest.mark.parametrize('decision_state', ['input'], indirect=True)
def test_logical_handoff_sender_filter_preserves_receivers_native_question(decision_state):
    """A=operator sends tracked work to B=subject; B asks the real operator.

    The request was admitted and ingested by the canonical native fixture;
    only logical-domain linking facts are synthetic migrated rows. No native
    question/option/recipient is fabricated for the Home relation.
    """
    deps, app, _ = decision_state
    service = app.state.home
    now = deps.clock.now_iso()
    with deps.connection_factory.unit_of_work() as uow:
        c = uow.connection
        op = c.execute("SELECT * FROM execution_operations WHERE action='turn.submit'").fetchone()
        endpoint = c.execute("SELECT * FROM agent_endpoints WHERE agent_id='subject'").fetchone()
        c.execute("INSERT INTO handoffs(handoff_id,workspace_id,from_agent_id,target,status,claimed_by,claim_epoch,created_at,updated_at) VALUES('sender-work',?,'operator',?,'CLAIMED','subject',1,?,?)",
            (op['workspace_id'],json.dumps({'strategy':'direct','agent_id':'subject'}),now,now))
        c.execute("INSERT INTO messages(message_id,workspace_id,from_agent_id,created_at) VALUES('sender-message',?,'operator',?)",(op['workspace_id'],now))
        c.execute("INSERT INTO message_deliveries(delivery_id,message_id,recipient_agent_id,status,created_at) VALUES('sender-delivery','sender-message','subject','unread',?)",(now,))
        c.execute("INSERT INTO delivery_outbox(operation_id,delivery_id,message_id,workspace_id,actor_agent_id,credential_binding,recipient_agent_id,endpoint_id,endpoint_revision,envelope,request_hash,authorization_revision,root_operation_id,status,created_at,updated_at) VALUES('sender-domain','sender-delivery','sender-message',?,'operator','fixture','subject',?,?,'{}','fixture','fixture','sender-domain','ACCEPTED',?,?)",
            (op['workspace_id'],endpoint['endpoint_id'],endpoint['revision'],now,now))
        c.execute("INSERT INTO runtime_execution_grants(grant_id,issuer_agent_id,actor_agent_id,credential_binding,represented_agent_id,workspace_id,endpoint_id,actions,expires_at,max_executions,created_at) VALUES('sender-grant','operator','operator','fixture','subject',?,?,'[\"open\",\"send\"]','2099-01-01T00:00:00Z',5,?)",
            (op['workspace_id'],endpoint['endpoint_id'],now))
        c.execute("INSERT INTO runtime_handoff_bindings(handoff_id,claim_epoch,operation_id,grant_id,grant_revision,actor_agent_id,idempotency_key,request_hash,created_at) VALUES('sender-work',1,'sender-domain','sender-grant',1,'operator','sender-link','fixture',?)",(now,))
        c.execute('INSERT INTO execution_domain_deliveries VALUES(?,?,?,?)',
            (op['server_id'],op['executor_id'],op['operation_id'],'sender-domain'))
    all_work = service.read(context=OPERATOR, section='work', filters={'workspace_id':op['workspace_id']})
    selected = service.read(context=OPERATOR, section='work',
        filters={'workspace_id':op['workspace_id'],'agent_id':'operator'})
    original = next(row for row in all_work['items'] if row['source_ref']['id']=='sender-work')
    filtered = next(row for row in selected['items'] if row['source_ref']['id']=='sender-work')
    assert original['display_state'] == filtered['display_state'] == 'awaiting_operator'
    assert original['attention_refs'] and filtered['attention_refs'] == original['attention_refs']
    assert filtered['runtime_refs'] == original['runtime_refs']
    assert set(filtered['agent_ids']) == {'operator','subject'}
    # List/count scope remains the selected agent; only work classification
    # consumes the receiver evidence instead of pruning it prematurely.
    projected = service.read(context=OPERATOR, filters={'workspace_id':op['workspace_id'],'agent_id':'operator'})
    assert all(row['agent_id']=='operator' for row in projected['attention']['items'])
