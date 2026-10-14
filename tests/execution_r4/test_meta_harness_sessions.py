"""Conversation sidebar follows actual operator delivery/session provenance."""
import json
import time
import pytest

from test_embedded_dispatch import connected_local, local_setup, qualified_contract, admit, wait_receipt
from test_canonical_result_publication import current_turn, emit

PATH = '/api/v1/meta-harness/runtime-sessions'


def send(setup, binding, *, kind='message', audience='private'):
    response = setup[2].post('/api/v1/meta-harness/send', headers=setup[3]['operator'], json=dict(
        workspace=binding['workspace_id'], kind=kind, audience=audience,
        to_agent_id='subject' if audience=='private' else None, subject='Sidebar test', body='Inspect this request'))
    assert response.status_code == 200, response.text
    return response.json()['data']


@pytest.mark.parametrize('kind,audience', [('message','private'),('message','broadcast'),('handoff','private'),('handoff','broadcast')])
def test_operator_message_and_handoff_sessions_are_scoped(connected_local, kind, audience):
    setup,binding,native=connected_local
    client,headers=setup[2:4]
    assert client.get(PATH,headers=headers['operator']).json()['data']['items']==[]
    from test_canonical_delivery import enable
    enable(setup,binding)
    send(setup,binding,kind=kind,audience=audience)
    deadline=time.monotonic()+15
    while True:
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            ready=uow.connection.execute("SELECT 1 FROM execution_operations WHERE action='turn.submit'").fetchone()
        if ready: break
        assert time.monotonic()<deadline
        time.sleep(.05)
    turn=current_turn(setup)
    wait_receipt(setup,turn)
    response=client.get(PATH,headers=headers['operator'])
    assert response.status_code==200,response.text
    view=response.json()['data']
    assert view['total']==view['active_count']==1
    item,=view['items']
    assert item['scope']['session_id']==turn['session_id']
    assert item['scope']['agent_id']=='subject' and item['scope']['workspace_id']==binding['workspace_id']
    assert item['interaction_count']==1  # open + send are one message
    assert item['harness']==binding['adapter_id'] and item['is_open']
    for params in [dict(workspace='other-workspace'),dict(agent='operator')]:
        assert client.get(PATH,headers=headers['operator'],params=params).json()['data']['total']==0
    assert client.get(PATH,headers=headers['operator'],params=dict(workspace=binding['workspace_id'],agent='subject')).json()['data']['total']==1
    assert client.get(PATH,headers=headers['subject']).status_code==403
    assert client.get(PATH,headers={'Authorization':'Bearer invalid'}).status_code==401
    assert client.get(PATH,headers=headers['operator'],params={'page':0}).status_code==422
    emit(setup,native,turn,'Done')
    wait_receipt(setup,admit(setup,binding,'sidebar-close','runtime.close',session_id=turn['session_id']),stages=('SUCCEEDED',))
    ended=client.get(PATH,headers=headers['operator']).json()['data']
    assert ended['active_count']==0 and ended['total']==1
    assert not ended['items'][0]['is_open']


def test_unrelated_instances_are_excluded_and_shared_turns_count_once(connected_local):
    setup,binding,native=connected_local
    send(setup,binding)
    turn=current_turn(setup);wait_receipt(setup,turn);emit(setup,native,turn,'Done')
    send(setup,binding)
    result=setup[2].get(PATH,headers=setup[3]['operator']).json()['data']
    assert result['total']==1 and result['items'][0]['interaction_count']==2
    opened=admit(setup,binding,'unused-warm-instance','runtime.start',new_session=True)
    wait_receipt(setup,opened)
    result=setup[2].get(PATH,headers=setup[3]['operator']).json()['data']
    assert result['total']==1 and result['items'][0]['scope']['session_id']!=opened['session_id']
    # A full-access agent's own delivery is not an operator interaction.
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE messages SET from_agent_id='subject' WHERE from_agent_id='operator'")
    assert setup[2].get(PATH,headers=setup[3]['operator']).json()['data']['total']==0


def test_session_pagination_deduplicates_runtime_operations(connected_local):
    setup,binding,native=connected_local
    send(setup,binding);turn=current_turn(setup);wait_receipt(setup,turn)
    with setup[0].connection_factory.unit_of_work() as uow:
        conn=uow.connection
        operation=dict(conn.execute('SELECT * FROM execution_operations WHERE operation_id=?',(turn['operation_id'],)).fetchone())
        session=dict(conn.execute('SELECT * FROM execution_sessions WHERE session_id=?',(turn['session_id'],)).fetchone())
        link=dict(conn.execute('SELECT * FROM execution_domain_deliveries WHERE operation_id=?',(turn['operation_id'],)).fetchone())
        for index in range(22):
            sid,oid=f'prior-session-{index}',f'prior-operation-{index}'
            op=operation | dict(operation_id=oid,session_id=sid,
                expected_revisions_json=json.dumps(json.loads(operation['expected_revisions_json']) | dict(session_id=sid)))
            record=session | dict(session_id=sid,open_operation_id=oid,lifecycle_state='CLOSED',lease_state='CLOSED')
            mapping=link | dict(operation_id=oid)
            for table,row in [('execution_operations',op),('execution_sessions',record),('execution_domain_deliveries',mapping)]:
                conn.execute('INSERT INTO '+table+'('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
    first=setup[2].get(PATH,headers=setup[3]['operator']).json()['data']
    second=setup[2].get(PATH,headers=setup[3]['operator'],params={'page':2}).json()['data']
    assert first['total']==23 and len(first['items'])==20 and first['has_more']
    assert first['items'][0]['is_open']
    assert len(second['items'])==3 and not second['has_more']
    assert len({r['scope']['session_id'] for r in first['items']+second['items']})==23
