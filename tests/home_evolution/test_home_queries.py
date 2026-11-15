"""Home contracts exercised against migrated SQLite, not mocked card lists."""
# ruff: noqa: F811 -- imported pytest fixture is injected by name
import json
import sqlite3
from contextlib import contextmanager

import pytest

from okto_nexus.application.home import HomeOverviewService
from okto_nexus.application.attention import AttentionService
from okto_nexus.application.runtime_access import RuntimeAccessService
from okto_nexus.adapters.outbound.sqlite.home import SqliteHomeQueries
from okto_nexus.adapters.outbound.sqlite.attention import SqliteAttentionQueries
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError
from .fixtures import home_scenario as home_scenario, OPERATOR, WORKSPACES


@pytest.fixture
def service(home_scenario):
    s = home_scenario
    s.config.feature_attention = True
    with s.factory.unit_of_work() as uow:
        uow.connection.execute('INSERT INTO execution_installation VALUES(1,?,?,1,?)',
            ('fixture-server', 'fixture-executor', s.clock.now_iso()))
    access = RuntimeAccessService(connection_factory=s.factory, agents=s.repos.agents,
        endpoints=None, grants=None, config=s.config, clock=s.clock)
    attention = AttentionService(factory=s.factory, access=access, queries=SqliteAttentionQueries(),
        config=s.config, clock=s.clock)
    return HomeOverviewService(factory=s.factory, access=access, queries=SqliteHomeQueries(),
        attention=attention, observations=s.observations, config=s.config, clock=s.clock)


def test_overview_real_fixture_is_read_only_and_scoped(service, home_scenario):
    before = home_scenario.counts()
    value = service.read(context=OPERATOR, filters={'workspace_id': WORKSPACES[0]})
    assert {k: value[k]['status'] for k in ('work', 'results', 'agents', 'attention', 'external_activity')} == dict.fromkeys(
        ('work', 'results', 'agents', 'attention', 'external_activity'), 'ready')
    assert value['summary']['running']['value'] == 0
    assert value['work']['total'] == 4  # three handoffs plus terminal work with pending cleanup
    assert value['results']['total'] == 1
    assert value['results']['items'][0]['cleanup_state'] == 'pending'
    assert 'global' not in {a['agent_id'] for a in value['agents']['items']}
    assert home_scenario.counts() == before
    assert all(w['workspace_id'] == WORKSPACES[0] for w in value['work']['items'])
    assert '_attention_id' not in json.dumps(value)


def test_workspace_pages_are_complete_and_cursor_bound(service, home_scenario):
    scope = {'workspace_id': WORKSPACES[0]}
    first = service.read(context=OPERATOR, filters=scope, section='work', limit=2)
    second = service.read(context=OPERATOR, filters=scope, section='work', limit=2, cursor=first['next_cursor'])
    assert first['total'] == second['total'] == 4
    assert len({i['id'] for i in first['items'] + second['items']}) == 4
    with pytest.raises(OktoNexusError):
        service.read(context=OPERATOR, filters={'workspace_id': WORKSPACES[1]}, section='work', cursor=first['next_cursor'])
    with home_scenario.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET status='CLAIMED',claimed_by='B' WHERE handoff_id='fixture-handoff-0000'")
    with pytest.raises(OktoNexusError) as exc:
        service.read(context=OPERATOR, filters=scope, section='work', cursor=first['next_cursor'])
    assert exc.value.code == 'CONFLICT'


def test_operator_authority_not_an_agent_name(service):
    with pytest.raises(OktoNexusError):
        service.read(context=RuntimeRequestContext(None, 'http_agent'))


def test_disabled_external_and_failed_work_are_not_empty_success(service, monkeypatch):
    service.config.feature_observations = False
    original = service.queries.page
    def failed(uow, **kwargs):
        if kwargs['section'] == 'work':
            raise sqlite3.OperationalError('synthetic unavailable')
        return original(uow, **kwargs)
    monkeypatch.setattr(service.queries, 'page', failed)
    monkeypatch.setattr(service.queries, 'overview', lambda *args, **kwargs: (_ for _ in ()).throw(sqlite3.OperationalError('synthetic unavailable')))
    value = service.read(context=OPERATOR)
    assert value['work']['status'] == 'unavailable' and value['work']['total'] is None
    assert value['summary']['running']['value'] is None
    assert value['external_activity']['status'] == 'disabled'
    assert value['results']['status'] == 'ready'


def test_exact_target_server_workspace_and_session(service):
    item = service.read(context=OPERATOR, section='results')['items'][0]
    target = item['detail_target']
    assert service.resolve(context=OPERATOR, target=target)['agent_id'] == 'B'
    for changed in (dict(target, server_id='other'), dict(target, workspace_id=WORKSPACES[1]), dict(target, session_id='other')):
        with pytest.raises(OktoNexusError):
            service.resolve(context=OPERATOR, target=changed)


def test_each_page_uses_one_read_uow(service, monkeypatch):
    calls = []
    original = service.factory.unit_of_work
    @contextmanager
    def traced(*args, **kwargs):
        calls.append(kwargs)
        with original(*args, **kwargs) as uow:
            yield uow
    monkeypatch.setattr(service.factory, 'unit_of_work', traced)
    service.read(context=OPERATOR)
    assert calls == [{'write': False}]


def test_overview_shares_one_attention_projection_statement(service, monkeypatch):
    monkeypatch.setattr(service.queries, 'page', lambda *args, **kwargs: pytest.fail('Unexpected isolated fallback'))
    monkeypatch.setattr(service.queries, 'attention_page', lambda *args, **kwargs: pytest.fail('Unexpected second Attention projection'))
    view = service.read(context=OPERATOR)
    assert view['work']['status'] == view['attention']['status'] == view['results']['status'] == 'ready'


def test_agent_and_external_pages_have_reachable_continuations(service):
    first = service.read(context=OPERATOR, section='agents', limit=2)
    second = service.read(context=OPERATOR, section='agents', limit=2, cursor=first['next_cursor'])
    assert len(first['items']) == len(second['items']) == 2
    assert not ({a['agent_id'] for a in first['items']} & {a['agent_id'] for a in second['items']})
    third = service.read(context=OPERATOR, section='agents', limit=2, cursor=second['next_cursor'])
    workers = first['items'] + second['items'] + third['items']
    assert first['total'] == second['total'] == third['total'] == 5
    assert {a['agent_id'] for a in workers} == {'global','A','B','C','revoked'}
    assert len(workers) == 5 and not third['has_more']
    external = service.read(context=OPERATOR, section='external')
    assert external['total'] == 1


def test_unclaimed_direct_recipient_is_workspace_member_without_presence(service, home_scenario):
    with home_scenario.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET target=? WHERE handoff_id='fixture-handoff-0000'", ('{"strategy":"direct","agent_id":"global"}',))
    value = service.read(context=OPERATOR, section='agents', filters={'workspace_id':WORKSPACES[0]})
    agent = next(a for a in value['items'] if a['agent_id']=='global')
    assert agent['activity']=='not_reported' and agent['presence']=='offline'


@pytest.mark.parametrize('params', [{'workspace_id':'all'}, {'state':'invented'}, {'other':'x'}])
def test_invalid_filter_contract(service, params):
    with pytest.raises(OktoNexusError):
        service.read(context=OPERATOR, filters=params)


def test_started_event_requires_current_owner_stream_and_nonterminal(service, home_scenario):
    def view():
        return service.read(context=OPERATOR, section='work', filters={'state':'running'})
    with home_scenario.factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("UPDATE execution_receipts SET stage='SUBMITTED'")
        c.execute("UPDATE execution_operations SET expected_revisions_json=? WHERE operation_id='fixture-success'", ('{"session_owner_generation":1}',))
        c.execute("UPDATE execution_sessions SET stream_epoch='current-stream'")
    assert view()['total'] == 0  # ACCEPTED/SUBMITTED is not running
    with home_scenario.factory.unit_of_work() as uow:
        c = uow.connection
        event = json.dumps({'operation_id':'fixture-success', 'payload':{'delivery_phase':'started'}})
        c.execute("INSERT INTO execution_event_ingress VALUES('fixture-server','fixture-executor','fixture-native-session','current-stream',1,'synthetic','turn_state',?,?)", (event, home_scenario.clock.now_iso()))
        c.execute("INSERT INTO execution_event_watermarks VALUES('fixture-server','fixture-executor','fixture-native-session','current-stream',1,1,'none')")
    assert view()['total'] == 1
    with home_scenario.factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE execution_sessions SET owner_generation=2')
    assert view()['total'] == 0
    with home_scenario.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET owner_generation=1,stream_epoch='another-stream'")
    assert view()['total'] == 0
    with home_scenario.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET stream_epoch='current-stream'")
        uow.connection.execute("UPDATE execution_receipts SET stage='SUCCEEDED'")
    assert view()['total'] == 0


def test_result_preview_seen_and_bounded_artifact_metadata(service, home_scenario):
    with home_scenario.factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("INSERT INTO execution_event_ingress VALUES('fixture-server','fixture-executor','fixture-native-session','current-stream',2,'synthetic','turn_state','{}',?)", (home_scenario.clock.now_iso(),))
        c.execute("INSERT INTO execution_results VALUES('fixture-server','fixture-executor','fixture-success','fixture-native-session','current-stream',2,?,0,1,'success',?)",
            ('x'*600, home_scenario.clock.now_iso()))
    value = service.read(context=OPERATOR, section='results')
    result = value['items'][0]
    assert result['preview'] == 'x'*400 and result['truncated'] is True
    assert result['view_state'] == 'unseen'
    occurrence = result['attention']
    service.attention.mark_seen(context=OPERATOR, attention_id=occurrence['attention_id'],
        source_revision=occurrence['source_revision'], preference_revision=occurrence['seen_state']['revision'])
    assert service.read(context=OPERATOR, section='results')['items'][0]['view_state'] == 'seen'


def test_business_feed_uses_real_events_not_unread_or_private_payload(service, home_scenario):
    with home_scenario.factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO events(workspace_id,stream,type,actor_agent_id,payload,visibility,created_at) VALUES(?,'message','message.created','A',?,'public',?)",
            (WORKSPACES[0], '{"body":"private-fixture-token"}', home_scenario.clock.now_iso()))
    feed = service.read(context=OPERATOR, section='activity')
    assert any(i['kind'] == 'message.created' for i in feed['items'])
    assert 'private-fixture-token' not in json.dumps(feed)
    assert all(i['kind'] != 'fixture.activity' for i in feed['items'])


def link_handoff(scenario):
    with scenario.factory.unit_of_work() as uow:
        c = uow.connection
        delivery = c.execute("SELECT d.delivery_id,m.message_id FROM message_deliveries d JOIN messages m USING(message_id) WHERE m.workspace_id=? AND d.recipient_agent_id='B' LIMIT 1", (WORKSPACES[0],)).fetchone()
        assert delivery
        c.execute("INSERT INTO delivery_outbox(operation_id,delivery_id,message_id,workspace_id,actor_agent_id,credential_binding,recipient_agent_id,endpoint_id,endpoint_revision,envelope,request_hash,authorization_revision,root_operation_id,created_at,updated_at) VALUES('domain-work',?,?,?,'A','fixture','B','fixture-endpoint',1,'{}','fixture','fixture','domain-work',?,?)",
            (*delivery, WORKSPACES[0], scenario.clock.now_iso(), scenario.clock.now_iso()))
        c.execute("INSERT INTO runtime_execution_grants(grant_id,issuer_agent_id,actor_agent_id,credential_binding,represented_agent_id,workspace_id,endpoint_id,actions,expires_at,max_executions,created_at) VALUES('fixture-grant','operator','A','fixture','B',?,'fixture-endpoint','[]',?,3,?)", (WORKSPACES[0],scenario.clock.now_iso(),scenario.clock.now_iso()))
        c.execute("INSERT INTO runtime_handoff_bindings(handoff_id,claim_epoch,operation_id,grant_id,grant_revision,actor_agent_id,idempotency_key,request_hash,created_at) VALUES('fixture-handoff-0000',1,'domain-work','fixture-grant',1,'A','fixture','fixture',?)", (scenario.clock.now_iso(),))
        c.execute("INSERT INTO execution_domain_deliveries VALUES('fixture-server','fixture-executor','fixture-success','domain-work')")
        c.execute("UPDATE handoffs SET status='CLAIMED',claimed_by='B',claim_epoch=1 WHERE handoff_id='fixture-handoff-0000'")


def test_native_delivery_and_handoff_are_one_activity_then_claim_change_separates_history(service, home_scenario):
    link_handoff(home_scenario)
    value = service.read(context=OPERATOR, section='work', filters={'workspace_id':WORKSPACES[0]})
    assert value['total'] == 3
    handoff = next(i for i in value['items'] if i['source_ref']['id']=='fixture-handoff-0000')
    assert handoff['attempt_count'] == 1 and len(handoff['runtime_refs']) == 1
    with home_scenario.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET claim_epoch=2,status='OPEN',claimed_by=NULL WHERE handoff_id='fixture-handoff-0000'")
    handoff = next(i for i in service.read(context=OPERATOR, section='work')['items'] if i['source_ref']['id']=='fixture-handoff-0000')
    assert handoff['runtime_refs'] == [] and handoff['display_state'] == 'awaiting_owner'
    result = service.read(context=OPERATOR, section='results')['items'][0]
    assert result['verification_state'] == 'historical_claim'


def test_direct_delegation_keeps_each_handoff_and_canonical_task_title(service, home_scenario):
    with home_scenario.factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("INSERT INTO tasks(task_id,workspace_id,title,description,status,created_at) VALUES('real-title',?,'Review the output','private description','open',?)", (WORKSPACES[0],home_scenario.clock.now_iso()))
        c.execute("UPDATE handoffs SET target=?,task_id='real-title' WHERE handoff_id='fixture-handoff-0000'", ('{"strategy":"direct","agent_id":"B"}',))
        c.execute("UPDATE handoffs SET from_agent_id='B',target=? WHERE handoff_id='fixture-handoff-0002'", ('{"strategy":"direct","agent_id":"C"}',))
    value = service.read(context=OPERATOR, section='work', filters={'workspace_id':WORKSPACES[0]})
    parent = next(i for i in value['items'] if i['source_ref']['id']=='fixture-handoff-0000')
    child = next(i for i in value['items'] if i['source_ref']['id']=='fixture-handoff-0002')
    assert parent['title'] == 'Review the output' and parent['title_origin']=='canonical_title'
    assert parent['agent_ids'] == ['A','B'] and child['agent_ids']==['B','C']
    assert parent['id'] != child['id'] and 'private description' not in json.dumps(value)


def test_result_artifact_reference_uses_exact_durable_operation_without_paths(service, home_scenario):
    link_handoff(home_scenario)
    with home_scenario.factory.unit_of_work() as uow:
        c = uow.connection
        now = home_scenario.clock.now_iso()
        c.execute("INSERT INTO execution_event_ingress VALUES('fixture-server','fixture-executor','fixture-native-session','current-stream',2,'synthetic','turn_state','{}',?)", (now,))
        c.execute("INSERT INTO execution_results VALUES('fixture-server','fixture-executor','fixture-success','fixture-native-session','current-stream',2,'Report complete',0,1,'success',?)", (now,))
        c.execute("INSERT INTO artifacts(artifact_id,workspace_id,artifact_type,name,path,content_type,created_at) VALUES('output-ref',?,'file','result.txt','private-path-marker','text/plain',?)", (WORKSPACES[0],now))
        c.execute("INSERT INTO runtime_results(result_id,payload,captured_at,operation_id,canonical_server_id,canonical_executor_id,canonical_operation_id,output_artifact_id) VALUES('output-result','{}',?,'domain-work','fixture-server','fixture-executor','fixture-success','output-ref')", (now,))
    result = service.read(context=OPERATOR, section='results')['items'][0]
    assert result['artifacts'] == [{'artifact_id':'output-ref','filename':'result.txt','media_type':'text/plain'}]
    assert result['preview']=='Report complete' and 'private-path-marker' not in json.dumps(result)


def test_retries_share_handoff_controls_do_not_become_work(service, home_scenario):
    link_handoff(home_scenario)
    with home_scenario.factory.unit_of_work() as uow:
        c = uow.connection
        original = dict(c.execute("SELECT * FROM execution_operations WHERE operation_id='fixture-success'").fetchone())
        for operation_id, action in (('second-turn','turn.submit'),('steer-control','turn.steer'),('close-control','runtime.close')):
            row = dict(original, operation_id=operation_id, action=action)
            c.execute('INSERT INTO execution_operations('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')', tuple(row.values()))
            c.execute("INSERT INTO execution_domain_deliveries VALUES('fixture-server','fixture-executor',?,'domain-work')", (operation_id,))
        # The same immutable link appearing in history is not another attempt.
        c.execute("INSERT INTO execution_delivery_attempt_history VALUES('fixture-server','fixture-executor','fixture-success','domain-work',1,'fixture-endpoint','fixture-success',1,?)", (home_scenario.clock.now_iso(),))
    value = service.read(context=OPERATOR, section='work', filters={'workspace_id':WORKSPACES[0]})
    assert value['total'] == 3
    handoff = next(i for i in value['items'] if i['source_ref']['id']=='fixture-handoff-0000')
    assert handoff['attempt_count']==2
    assert {r['operation_id'] for r in handoff['runtime_refs']} == {'fixture-success','second-turn'}


def test_expired_claim_is_unknown_not_a_current_native_activity(service, home_scenario):
    link_handoff(home_scenario)
    with home_scenario.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET lease_expires_at='2000-01-01T00:00:00Z' WHERE handoff_id='fixture-handoff-0000'")
        uow.connection.execute("UPDATE execution_receipts SET stage='SUBMITTED'")
    value = service.read(context=OPERATOR, section='work')
    item = next(i for i in value['items'] if i['source_ref']['id']=='fixture-handoff-0000')
    assert item['display_state']=='outcome_unknown' and item['running_count']==0
