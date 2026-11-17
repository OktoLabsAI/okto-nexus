"""Real setup-test precondition refusal is not a harness effect."""
from pathlib import Path
import sys

import pytest
import nexus_connector_core

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'execution_r4'))
import test_terminal_connect

local_setup = test_terminal_connect.local_setup
checking = test_terminal_connect.checking
terminal = test_terminal_connect.terminal


@pytest.mark.parametrize('local_setup', ['claude_stream'], indirect=True)
def test_missing_claude_home_is_definitive_real_http_refusal_without_model_or_identity_effect(terminal, checking, monkeypatch, tmp_path):
    monkeypatch.setattr(nexus_connector_core, 'discover_provider_home', lambda *_a, **_k: None)
    t=terminal
    home=tmp_path/'synthetic-provider-home'
    home.mkdir()
    document=t.flow.review(t.selection|{'agent':'uncreated-claude','create_agent':True,'client':'claude','provider_home':str(home)})
    # The terminal already checks this field before POST; this deliberately
    # exercises the browser's real HTTP refusal contract, not that CLI guard.
    document['request']['configuration']['provider_home']=None
    assert document['request']['configuration']['provider_home'] is None
    tables=('agents','runtime_profiles','execution_bindings','runtime_execution_grants',
            'execution_sessions','execution_operations','connection_setup_commits')
    def state():
        with t.deps.connection_factory.unit_of_work(write=False) as uow:
            return {table:[dict(row) for row in uow.connection.execute('SELECT * FROM '+table)] for table in tables}
    before=state()
    client=checking[2]
    response=client.post('/api/v1/runtime-management/connections/setup:test',
                         json=document['request'],headers={'X-Nexus-UI':'1'})
    assert response.status_code==422,response.text
    error=response.json()['error']
    assert {key:error[key] for key in ('code','stage','possible_effect','retry_safe','operation_id','action')}=={
        'code':'VALIDATION_ERROR','stage':'connection.test','possible_effect':False,
        'retry_safe':False,'operation_id':None,'action':''}
    assert 'provider_home' in error['message']
    assert state()==before
    assert t.turns==t.probes==[]
    assert not t.app.state.connection_tests.tests
