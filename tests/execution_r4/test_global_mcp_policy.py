import json
from pathlib import Path

import pytest

from test_embedded_dispatch import connected_local, local_setup, qualified_contract, connect_local, admit, wait_receipt
from test_embedded_tools import enable_tools
from test_runtime_policy_defaults import read, save


def test_global_agent_and_harness_precedence_with_backward_compatible_updates(connected_local):
    from okto_nexus.application.runtime_policy import harness_mcp_settings
    setup, binding, _ = connected_local
    assert read(setup)['inherit_global_mcps'] is False
    assert read(setup, 'subject')['inherit_global_mcps'] is None
    assert save(setup, inherit_global_mcps=True).status_code == 200
    assert read(setup, 'subject')['effective']['inherit_global_mcps'] is True
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert harness_mcp_settings(uow.connection, 'subject', 'codex_app_server', {}) == {'inherit_global_mcps':'enabled'}
        assert harness_mcp_settings(uow.connection, 'subject', 'claude_stream', {'inherit_global_mcps':'disabled'}) == {'inherit_global_mcps':'disabled'}
        assert harness_mcp_settings(uow.connection, 'subject', 'pi_rpc', {}) == {}
    assert save(setup, agent='subject', inherit_global_mcps=False).status_code == 200
    assert save(setup, agent='subject').json()['data']['effective']['inherit_global_mcps'] is False
    assert save(setup, agent='subject', inherit_global_mcps=None).json()['data']['effective']['inherit_global_mcps'] is True
    assert save(setup, inherit_global_mcps=None).status_code == 422
    assert save(setup, inherit_global_mcps='enabled').status_code == 422


@pytest.mark.parametrize('local_setup',['codex_app_server','claude_stream'],indirect=True)
def test_inheritance_reaches_local_launch_preserves_login_and_running_sessions(local_setup, tmp_path, monkeypatch):
    from nexus_connector_core.harness_config import process_http_arguments
    home = tmp_path/'approved-home'
    home.mkdir()
    adapter = local_setup[5].adapter_id
    path = home/('config.toml' if adapter == 'codex_app_server' else '.claude.json')
    content = ('[mcp_servers.external]\nurl="http://127.0.0.1:1/mcp"\nbearer_token_env_var="EXTERNAL_TOKEN"\n'
        if adapter == 'codex_app_server' else json.dumps({'mcpServers': {'external': {
            'type':'http','url':'http://127.0.0.1:1/mcp','headers':{'Authorization':'${EXTERNAL_TOKEN}'}}}}))
    path.write_text(content)
    monkeypatch.setenv('EXTERNAL_TOKEN','local-only-secret')
    local_setup[4]['provider_home'] = str(home)
    setup,binding,native,vault,environments = enable_tools(connect_local(local_setup))
    assert save(setup, inherit_global_mcps=True).status_code == 200
    opened = admit(setup,binding,'inherited-open','runtime.start',new_session=True)
    wait_receipt(setup,opened)
    environment = environments[0]
    assert environment['EXTERNAL_TOKEN'] == 'local-only-secret'
    assert Path(environment['HOME']) == home.resolve()
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT semantic_payload FROM execution_operations WHERE action='runtime.open'").fetchone()
        assert json.loads(row[0])['payload']['harness_settings']['inherit_global_mcps'] == 'enabled'
        assert 'local-only-secret' not in row[0]
    # Global changes do not revoke a running session. Explicit harness edits
    # retain the existing close-and-authorize configuration workflow.
    assert save(setup, inherit_global_mcps=False).status_code == 200
    owner = setup[1].state.embedded_dispatch_owner
    setup[2].portal.call(owner._renew_owned, opened['session_id'], owner.sessions[opened['session_id']])
    assert owner.failure is None and not native.native.stopped
    endpoint = f"/api/v1/harness/endpoints/{binding['endpoint_id']}/harness-settings"
    current = setup[2].get(endpoint,headers=setup[3]['operator']).json()['data']
    response = setup[2].put(endpoint,headers=setup[3]['operator'],json={
        'expected_revision':current['revision'],'settings':{'inherit_global_mcps':'enabled'}})
    assert response.status_code == 409, response.text
    wait_receipt(setup,admit(setup,binding,'inherited-close','runtime.close',session_id=opened['session_id']),stages=('SUCCEEDED',))
    response = setup[2].put(endpoint,headers=setup[3]['operator'],json={
        'expected_revision':current['revision'],'settings':{'inherit_global_mcps':'enabled'}})
    assert response.status_code == 200, response.text
    assert response.json()['data']['effective_settings']['inherit_global_mcps'] == 'enabled'
    assert path.read_text() == content
