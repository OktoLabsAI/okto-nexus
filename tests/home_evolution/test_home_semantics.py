"""Additional HOME-R1 semantic boundaries using existing synthetic stores.

Prepared outside the repository while package inputs are frozen. No provider,
service or native runtime is executed by these tests.
"""
# ruff: noqa: F811 -- imported pytest fixture dependency names
import json

import pytest

from okto_nexus.errors import OktoNexusError
from .fixtures import home_scenario as home_scenario, OPERATOR, WORKSPACES
from .test_home_queries import service as service, link_handoff
from .test_home_native import decision_state, opening, isolated_native_inventory  # noqa: F401
from .test_home_http import http as http


def copy_row(conn, table, original, **changes):
    row = dict(original, **changes)
    conn.execute('INSERT INTO '+table+'('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')', tuple(row.values()))


def started_fixture(scenario):
    with scenario.factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("UPDATE execution_receipts SET stage='SUBMITTED'")
        c.execute("UPDATE execution_operations SET expected_revisions_json=? WHERE operation_id='fixture-success'", ('{"session_owner_generation":1}',))
        c.execute("UPDATE execution_sessions SET stream_epoch='current-stream'")
        event = json.dumps({'operation_id':'fixture-success','payload':{'delivery_phase':'started'}})
        c.execute("INSERT INTO execution_event_ingress VALUES('fixture-server','fixture-executor','fixture-native-session','current-stream',1,'synthetic','turn_state',?,?)", (event,scenario.clock.now_iso()))
        c.execute("INSERT INTO execution_event_watermarks VALUES('fixture-server','fixture-executor','fixture-native-session','current-stream',1,1,'none')")


@pytest.mark.parametrize('decision_state', ['input'], indirect=True)
def test_same_agent_two_sessions_keep_running_and_operator_wait_separate(decision_state):
    deps, app, _ = decision_state
    with deps.connection_factory.unit_of_work() as uow:
        c = uow.connection
        old_session = dict(c.execute('SELECT * FROM execution_sessions').fetchone())
        old_open = dict(c.execute("SELECT * FROM execution_operations WHERE action='runtime.open'").fetchone())
        old_turn = dict(c.execute("SELECT * FROM execution_operations WHERE action='turn.submit'").fetchone())
        copy_row(c,'execution_operations',old_open,operation_id='second-open',session_id='second-session')
        copy_row(c,'execution_sessions',old_session,session_id='second-session',open_operation_id='second-open',
            lifecycle_state='READY',lease_state='ACTIVE',stream_epoch='second-stream')
        copy_row(c,'execution_operations',old_turn,operation_id='second-turn',session_id='second-session',
            expected_revisions_json=json.dumps({'session_owner_generation':old_session['owner_generation']}))
        key = (old_turn['server_id'],old_turn['executor_id'])
        c.execute('INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,stage,possible_effect,retry_safe,received_at) VALUES(?,?,?,1,?,\'SUBMITTED\',1,0,?)',
            (*key,'second-turn',old_turn['intent_hash'],deps.clock.now_iso()))
        event = json.dumps({'operation_id':'second-turn','payload':{'delivery_phase':'started'}})
        c.execute('INSERT INTO execution_event_ingress VALUES(?,?,\'second-session\',\'second-stream\',1,\'synthetic\',\'turn_state\',?,?)', (*key,event,deps.clock.now_iso()))
        c.execute('INSERT INTO execution_event_watermarks VALUES(?,?,\'second-session\',\'second-stream\',1,1,\'none\')', key)
    value = app.state.home.read(context=OPERATOR)
    running = [i for i in value['work']['items'] if i['display_state']=='running']
    waiting = [i for i in value['work']['items'] if i['display_state']=='awaiting_operator']
    assert len(running)==len(waiting)==1
    assert running[0]['detail_target']['session_id']=='second-session'
    assert waiting[0]['detail_target']['session_id']==old_session['session_id']
    assert running[0]['agent_ids']==waiting[0]['agent_ids']
    assert running[0]['id']!=waiting[0]['id']
    assert value['summary']['running']['value']==1


def test_information_broadcast_unread_does_not_create_productive_work(service,home_scenario):
    before = service.read(context=OPERATOR)
    with home_scenario.factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("INSERT INTO messages(message_id,workspace_id,from_agent_id,target,subject,body,created_at) VALUES('broadcast-info',?,'A',?,'FYI','Information only',?)",
            (WORKSPACES[0],'{"strategy":"broadcast"}',home_scenario.clock.now_iso()))
        for recipient in ('B','C'):
            c.execute("INSERT INTO message_deliveries(delivery_id,message_id,recipient_agent_id,status,created_at) VALUES(?,'broadcast-info',?,'unread',?)", ('info-'+recipient,recipient,home_scenario.clock.now_iso()))
    after = service.read(context=OPERATOR)
    assert after['work']['items']==before['work']['items']
    assert after['summary']['running']==before['summary']['running']
    assert after['summary']['waiting_start']==before['summary']['waiting_start']
    with home_scenario.factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM message_deliveries WHERE message_id='broadcast-info' AND status='unread'").fetchone()[0]==2


@pytest.mark.parametrize('handoff_state,display', [('CLAIMED','result_available_cleanup_pending'),('VERIFYING','awaiting_verification')])
def test_successful_turn_never_completes_or_verifies_handoff(service,home_scenario,handoff_state,display):
    link_handoff(home_scenario)
    with home_scenario.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET status=? WHERE handoff_id='fixture-handoff-0000'",(handoff_state,))
    view = service.read(context=OPERATOR)
    work = next(i for i in view['work']['items'] if i['source_ref']['id']=='fixture-handoff-0000')
    result = next(i for i in view['results']['items'] if i['source_ref']['id']=='fixture-handoff-0000')
    assert work['display_state']==display
    assert result['outcome']=='SUCCEEDED' and result['verification_state']==handoff_state
    with home_scenario.factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id='fixture-handoff-0000'").fetchone()[0]==handoff_state


def test_same_agent_native_and_external_are_distinct_evidence(service,home_scenario):
    started_fixture(home_scenario)
    with home_scenario.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET api_key_hash='fixture-only-B',permissions=? WHERE agent_id='B'", ('{"observations":{"manage_self":true,"publish":true}}',))
    observations = home_scenario.observations
    source = observations.create_source(context=OPERATOR,body=dict(agent_id='B',source_kind='custom',
        workspace_ids=[WORKSPACES[0]],registration_ref='synthetic-second-source'))['source']
    instance = observations.create_instance(context=OPERATOR,source_id=source['source_id'],body=dict(
        expected_revision=source['revision'],workspace_id=WORKSPACES[0],external_instance_ref='fixture-native-session'))['instance']
    token = observations.issue_token(context=OPERATOR,source_id=source['source_id'],body=dict(
        expected_revision=source['revision'],instance_grants=[dict(observed_instance_id=instance['observed_instance_id'],generation=instance['generation'])]))['token']
    observations.publish(token=token,payload=dict(schema_version=1,source_id=source['source_id'],
        observed_instance_id=instance['observed_instance_id'],generation=instance['generation'],sequence=1,
        state='working',evidence='reported',observed_at=home_scenario.clock.now_iso()))
    view = service.read(context=OPERATOR,filters={'agent_id':'B'})
    assert view['summary']['running']['value']==1
    assert view['external_activity']['total']==1
    assert instance['observed_instance_id'] not in {i['id'] for i in view['work']['items']}
    assert any(i['display_state']=='running' for i in view['work']['items'])


def test_external_without_canonical_workspace_is_refused_not_inferred(service,home_scenario):
    observations = home_scenario.observations
    before = service.read(context=OPERATOR,section='external',filters={'workspace_id':WORKSPACES[0]})
    with pytest.raises(OktoNexusError):
        observations.create_instance(context=OPERATOR,source_id=home_scenario.source_id,body=dict(
            expected_revision=1,workspace_id=None,external_instance_ref='unscoped'))
    after = service.read(context=OPERATOR,section='external',filters={'workspace_id':WORKSPACES[0]})
    assert after['items']==before['items'] and after['total']==before['total']


def test_overview_omits_credential_prompt_tool_args_and_private_paths(service,home_scenario):
    link_handoff(home_scenario)
    markers = dict(credential='credential-private-777',prompt='prompt-private-777',
        tool_arguments='tool-args-private-777',private_path='private-path-777')
    with home_scenario.factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("UPDATE delivery_outbox SET credential_binding=?,envelope=? WHERE operation_id='domain-work'", (markers['credential'],json.dumps(markers)))
        c.execute("UPDATE execution_operations SET semantic_payload=?",(json.dumps(markers),))
        c.execute("UPDATE messages SET body=?",(markers['prompt'],))
        c.execute("INSERT INTO execution_event_ingress VALUES('fixture-server','fixture-executor','fixture-native-session','private-stream',1,'synthetic','log',?,?)",(json.dumps({'payload':markers}),home_scenario.clock.now_iso()))
        c.execute("INSERT INTO artifacts(artifact_id,workspace_id,artifact_type,name,path,created_at) VALUES('unrelated-artifact',?,'file','Unrelated',?,?)",(WORKSPACES[0],markers['private_path'],home_scenario.clock.now_iso()))
    serialized = json.dumps(service.read(context=OPERATOR),ensure_ascii=False)
    assert all(marker not in serialized for marker in markers.values())
    assert 'semantic_payload' not in serialized and 'credential_binding' not in serialized


@pytest.mark.parametrize('origin', ['native','manual'])
def test_handoff_result_reuses_canonical_task_title_without_description(service,home_scenario,origin):
    if origin=='native':
        link_handoff(home_scenario)
    with home_scenario.factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO tasks(task_id,workspace_id,title,description,status,created_at) VALUES('result-title',?,'Review export','private-task-description','open',?)",(WORKSPACES[0],home_scenario.clock.now_iso()))
        uow.connection.execute("UPDATE handoffs SET task_id='result-title' WHERE handoff_id='fixture-handoff-0000'")
        if origin=='manual':
            uow.connection.execute("UPDATE handoffs SET status='COMPLETED' WHERE handoff_id='fixture-handoff-0000'")
    result = next(i for i in service.read(context=OPERATOR,section='results')['items'] if i['source_ref']['id']=='fixture-handoff-0000')
    assert result['title']=='Review export'
    assert 'private-task-description' not in json.dumps(result)


def test_empty_installation_has_no_home_workers_until_worker_registered(http):
    def home_agents():
        response = http.client.get('/api/v1/home/overview')
        assert response.status_code == 200
        return response.json()['data']['agents']

    global_before = http.client.get('/api/v1/agents').json()['data']['items']
    graph_before = http.client.get('/api/v1/graph').json()['data']['nodes']
    assert {a['agent_id'] for a in global_before} == {'operator'}
    empty = home_agents()
    assert empty['total'] == 0 and empty['items'] == []
    assert empty['total_is_exact'] and not empty['has_more']
    with http.deps.connection_factory.unit_of_work() as uow:
        http.deps.repos.agents.upsert(uow, agent_id='available-worker', role='agent')
    populated = home_agents()
    assert populated['total'] == 1
    assert [a['agent_id'] for a in populated['items']] == ['available-worker']
    assert populated['items'][0]['activity'] == 'not_reported'
    assert {a['agent_id'] for a in http.client.get('/api/v1/agents').json()['data']['items']} == {'operator','available-worker'}
    graph_after = http.client.get('/api/v1/graph').json()['data']['nodes']
    assert {a['agent_id'] for a in graph_after} == {a['agent_id'] for a in graph_before} | {'available-worker'}
    filtered = http.client.get('/api/v1/home/agents', params={'agent_id':'operator'}).json()['data']
    assert filtered['total'] == 0 and filtered['items'] == []


def test_manual_handoff_presentation_redacts_existing_policy_tokens(service,home_scenario):
    tokens = ['nxs_home_only_fixture_777','nxsept_home_fixture_777',
        'sk-homefixture777777','Bearer fixture-bearer-777']
    with home_scenario.factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("INSERT INTO tasks(task_id,workspace_id,title,status,created_at) VALUES('sensitive-title',?,?,'open',?)",
            (WORKSPACES[0],'Review '+tokens[0],home_scenario.clock.now_iso()))
        c.execute("UPDATE handoffs SET status='COMPLETED',task_id='sensitive-title',result=? WHERE handoff_id='fixture-handoff-0000'", ('Synthetic credential '+' '.join(tokens),))
        c.execute("UPDATE handoffs SET task_id='sensitive-title' WHERE handoff_id='fixture-handoff-0002'")
    view = service.read(context=OPERATOR)
    result = next(i for i in view['results']['items'] if i['source_ref']['id']=='fixture-handoff-0000')
    work = next(i for i in view['work']['items'] if i['source_ref']['id']=='fixture-handoff-0002')
    assert result['title'] == work['title'] == 'Review [REDACTED]'
    assert result['preview'] == 'Synthetic credential '+' '.join(['[REDACTED]']*4)
    assert not any(token in json.dumps(view) for token in tokens)
    assert result['detail_target']['handoff_id']=='fixture-handoff-0000'


def test_message_subject_and_result_filename_redact_without_rewriting_ids(service,home_scenario):
    link_handoff(home_scenario)
    artifact_id='nxs_opaque_artifact_identifier'
    with home_scenario.factory.unit_of_work() as uow:
        c=uow.connection
        now=home_scenario.clock.now_iso()
        c.execute("UPDATE messages SET subject='Subject sk-homefixture777777'")
        original=dict(c.execute("SELECT * FROM delivery_outbox WHERE operation_id='domain-work'").fetchone())
        message=dict(c.execute('SELECT * FROM messages WHERE message_id=?',(original['message_id'],)).fetchone())
        copy_row(c,'messages',message,message_id='message-only-source')
        delivery=dict(c.execute('SELECT * FROM message_deliveries WHERE delivery_id=?',(original['delivery_id'],)).fetchone())
        copy_row(c,'message_deliveries',delivery,delivery_id='message-only-delivery',message_id='message-only-source')
        copy_row(c,'delivery_outbox',original,operation_id='message-only-work',delivery_id='message-only-delivery',message_id='message-only-source')
        c.execute("INSERT INTO execution_event_ingress VALUES('fixture-server','fixture-executor','fixture-native-session','current-stream',2,'synthetic','turn_state','{}',?)",(now,))
        c.execute("INSERT INTO execution_results VALUES('fixture-server','fixture-executor','fixture-success','fixture-native-session','current-stream',2,'Report complete',0,1,'success',?)",(now,))
        c.execute("INSERT INTO artifacts(artifact_id,workspace_id,artifact_type,name,path,content_type,created_at) VALUES(?,?,'file','Report nxsept_home_fixture_777','unprojected','text/plain',?)",(artifact_id,WORKSPACES[0],now))
        c.execute("INSERT INTO runtime_results(result_id,payload,captured_at,operation_id,canonical_server_id,canonical_executor_id,canonical_operation_id,output_artifact_id) VALUES('redaction-result','{}',?,'domain-work','fixture-server','fixture-executor','fixture-success',?)",(now,artifact_id))
    view=service.read(context=OPERATOR)
    conversation=next(i for i in view['work']['items'] if i['source_ref']['id']=='message-only-work')
    result=next(i for i in view['results']['items'] if i['source_ref']['id']=='fixture-handoff-0000')
    assert conversation['title']=='Subject [REDACTED]'
    assert result['artifacts']==[dict(artifact_id=artifact_id,filename='Report [REDACTED]',media_type='text/plain')]
    assert result['detail_target']['operation_id']=='fixture-success'
