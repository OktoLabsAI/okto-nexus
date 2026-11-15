"""Direct operations retain their canonical executor/session namespace."""
# ruff: noqa: F811 -- imported fixture dependency names
import pytest

from .fixtures import home_scenario as home_scenario, OPERATOR
from .test_home_queries import service as service


def clone(c, table, row, **changes):
    row=dict(row,**changes)
    c.execute('INSERT INTO '+table+'('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))


@pytest.fixture
def namespace_pair(service,home_scenario):
    with home_scenario.factory.unit_of_work() as uow:
        c=uow.connection
        c.execute("UPDATE execution_receipts SET stage='SUBMITTED'")
        clone(c,'execution_executors',c.execute('SELECT * FROM execution_executors').fetchone(),executor_id='second-executor')
        clone(c,'agent_endpoints',c.execute("SELECT * FROM agent_endpoints WHERE endpoint_id='fixture-endpoint'").fetchone(),endpoint_id='second-endpoint')
        clone(c,'execution_workspace_bindings',c.execute('SELECT * FROM execution_workspace_bindings').fetchone(),executor_id='second-executor',workspace_binding_id='second-wb')
        clone(c,'execution_bindings',c.execute('SELECT * FROM execution_bindings').fetchone(),executor_id='second-executor',binding_id='second-binding',workspace_binding_id='second-wb',endpoint_id='second-endpoint')
        for row in c.execute('SELECT * FROM execution_operations').fetchall():
            clone(c,'execution_operations',row,executor_id='second-executor',binding_id='second-binding',workspace_binding_id='second-wb',session_id='second-session')
        clone(c,'execution_sessions',c.execute('SELECT * FROM execution_sessions').fetchone(),executor_id='second-executor',binding_id='second-binding',workspace_binding_id='second-wb',session_id='second-session')
        clone(c,'execution_receipts',c.execute('SELECT * FROM execution_receipts').fetchone(),executor_id='second-executor')
    return service,home_scenario


@pytest.mark.parametrize('check',['ids','pagination'])
def test_direct_operation_namespace(namespace_pair,check):
    service,_=namespace_pair
    view=service.read(context=OPERATOR,section='work',filters={'state':'native_accepted'})
    assert view['total']==2
    assert {i['detail_target']['executor_id'] for i in view['items']}=={'fixture-executor','second-executor'}
    assert {i['detail_target']['session_id'] for i in view['items']}=={'fixture-native-session','second-session'}
    assert {i['detail_target']['operation_id'] for i in view['items']}=={'fixture-success'}
    if check=='ids':
        assert len({i['id'] for i in view['items']})==2
    else:
        first=service.read(context=OPERATOR,section='work',filters={'state':'native_accepted'},limit=1)
        second=service.read(context=OPERATOR,section='work',filters={'state':'native_accepted'},limit=1,cursor=first['next_cursor'])
        assert first['total']==second['total']==2
        assert len(first['items'])==len(second['items'])==1
        assert first['items'][0]['id']!=second['items'][0]['id']


def test_execution_attention_does_not_cross_executor_namespace(namespace_pair):
    service,scenario=namespace_pair
    with scenario.factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO execution_dispatch_outbox(server_id,executor_id,operation_id,dispatch_state) VALUES('fixture-server','fixture-executor','fixture-success','RECONCILING')")
    view=service.read(context=OPERATOR,section='work',filters={'state':'native_accepted'})
    rows={i['detail_target']['executor_id']:i for i in view['items']}
    assert rows['fixture-executor']['attention_refs']
    assert rows['second-executor']['attention_refs']==[]
