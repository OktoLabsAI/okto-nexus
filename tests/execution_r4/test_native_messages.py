"""Public native messages commit once with session-owned sender identity."""
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import pytest

from test_mcp_session_capabilities import opening, activate


@pytest.mark.parametrize('opening', ['strict'], indirect=True)
def test_native_message_replay_and_scope(opening):
    cap=activate(opening, audience='nexus-native-session', actions=['message.create'])
    schema=json.loads((Path(__file__).parents[2]/'plans/contratos/http-target.schema.json').read_text())
    client=TestClient(opening[1],base_url='https://127.0.0.1:8202')
    request={'action_id':'pi-send','action':'message_create','scope':cap['scope'],
             'payload':{'message':{'subject':'Native sender','body':'Hello','target':{'strategy':'direct','agent_id':'other'}}}}
    Draft202012Validator(dict(schema,**{'$ref':'#/$defs/NativeActionRequest'})).validate(request)
    def send(body=request):
        return client.post('/v1/runtime/native-actions',headers={'Authorization':'Bearer '+cap['capability']},json=body)
    first=send()
    assert first.status_code==200,first.text
    Draft202012Validator(dict(schema,**{'$ref':'#/$defs/NativeActionResult'})).validate(first.json())
    assert send().json()==first.json()
    changed={**request,'payload':{'message':dict(request['payload']['message'],body='Changed')}}
    assert send(changed).status_code==409
    forged={**request,'action_id':'forged','payload':{'message':dict(request['payload']['message'],from_agent_id='operator')}}
    assert send(forged).status_code==422
    with opening[0].connection_factory.unit_of_work() as uow:
        assert uow.connection.execute('SELECT count(*) FROM messages').fetchone()[0]==1
        assert uow.connection.execute('SELECT from_agent_id FROM messages').fetchone()[0]=='subject'
        from okto_nexus.application.message_session_origin import runtime_key
        assert uow.connection.execute('SELECT source_session_key FROM execution_message_origins').fetchone()[0] == runtime_key(cap['scope'])
        assert uow.connection.execute('SELECT count(*) FROM execution_native_messages').fetchone()[0]==1
        assert uow.connection.execute('SELECT count(*) FROM sessions').fetchone()[0]==0
        uow.connection.execute('UPDATE execution_session_capabilities SET revoked_at=?',(opening[0].clock.now_iso(),))
    assert send().status_code==401


def test_native_message_approval_replay_uses_durable_executor(opening, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_hitl import _attach, _rule
    deps,app=opening[:2]
    deps.config.feature_hitl=True
    _attach(deps,'subject',governance=[_rule('message_create','require_approval')])
    cap=activate(opening,audience='nexus-native-session',actions=['message.create'])
    client=TestClient(app,base_url='https://127.0.0.1:8202')
    request={'action_id':'pi-approval','action':'message_create','scope':cap['scope'],
             'payload':{'message':{'subject':'Approval','body':'Hello','target':{'strategy':'direct','agent_id':'other'}}}}
    def send():
        return client.post('/v1/runtime/native-actions',headers={'Authorization':'Bearer '+cap['capability']},json=request)
    first=send()
    assert first.status_code==200,first.text
    assert first.json()['state']=='pending_approval'
    assert send().json()==first.json()
    approval=first.json()['result']['approval_id']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM approvals').fetchone()[0]==1
        assert uow.connection.execute('SELECT count(*) FROM messages').fetchone()[0]==0
    accepted=client.post(f'/api/v1/approvals/{approval}/decision',json={'decision':'approve'},
        headers={'Authorization':'Bearer '+app.state.test_agent_keys['operator']})
    assert accepted.status_code==200,accepted.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM messages').fetchone()[0]==1
        assert uow.connection.execute('SELECT actor_agent_id FROM runtime_causal_roots').fetchone()[0]=='subject'


def test_native_message_receipt_failure_rolls_back_message(opening):
    cap=activate(opening,audience='nexus-native-session',actions=['message.create'])
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER refuse_receipt BEFORE INSERT ON execution_native_messages "
                               "BEGIN SELECT RAISE(ABORT,'receipt unavailable'); END")
    client=TestClient(opening[1],base_url='https://127.0.0.1:8202',raise_server_exceptions=False)
    response=client.post('/v1/runtime/native-actions',headers={'Authorization':'Bearer '+cap['capability']},json={
        'action_id':'pi-rollback','action':'message_create','scope':cap['scope'],
        'payload':{'message':{'subject':'Rollback','body':'Hello','target':{'strategy':'direct','agent_id':'other'}}}})
    assert response.status_code>=400
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        for table in ('execution_native_messages','messages','message_deliveries','runtime_causal_roots'):
            assert uow.connection.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
