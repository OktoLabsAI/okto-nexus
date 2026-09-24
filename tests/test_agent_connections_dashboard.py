"""Isolated browser proof of the operator connection setup and copied request."""
import json
import os

import pytest
from test_pr34_remediation import runtime as runtime_fixture
from test_runtime_input_dashboard import dashboard as dashboard_fixture
from test_runtime_input_dashboard import dashboard_build as build_fixture

runtime = runtime_fixture
dashboard = dashboard_fixture
dashboard_build = build_fixture
pytestmark = pytest.mark.skipif(os.environ.get('OKTO_NEXUS_UI_CAMPAIGN') != '1', reason='Isolated browser campaign not enabled')


def test_agent_connection_policy_issue_copy_and_revoke(runtime, dashboard):
    from playwright.sync_api import expect

    page = dashboard
    page.get_by_role('button', name='Agents', exact=True).click()
    panel = page.get_by_test_id('agent-connections-worker')
    page.get_by_test_id('connections-worker').click()
    expect(panel.get_by_label('Pi · RPC', exact=True)).to_be_checked()
    panel.get_by_label('Connection key expiration', exact=True).select_option('unlimited')
    panel.get_by_role('button', name='Save connection policy').click()
    expect(panel.get_by_role('status')).to_have_text('Connection policy saved.')
    panel.get_by_test_id('connection-endpoint-endpoint-pi').get_by_role('button', name='Generate connection command').click()
    field = panel.get_by_label('Connection request', exact=True)
    expect(field).to_be_visible()
    panel.get_by_label('Connection command format').select_option('json')
    request = json.loads(field.input_value())
    assert request['body'] == {}
    assert request['headers']['Authorization'].startswith('Bearer nxsconn_')
    page.context.grant_permissions(['clipboard-read', 'clipboard-write'])
    panel.get_by_role('button', name='Copy connection command', exact=True).click()
    expect(panel.get_by_role('status')).to_have_text('Connection command copied.')
    assert json.loads(page.evaluate('navigator.clipboard.readText()')) == request
    response = runtime[1].post(request['url'], headers=request['headers'], json=request['body'])
    assert response.status_code == 200, response.text
    panel.get_by_role('button', name='Revoke', exact=True).click()
    expect(field).to_have_count(0)
    assert runtime[1].post(request['url'], headers=request['headers'], json={}).status_code == 403
    page.screenshot(path=str(__import__('pathlib').Path(runtime[2]).parent / 'agent-connections.png'), full_page=True)


def test_empty_agent_can_configure_endpoint_and_execute_copied_command(runtime, dashboard):
    import subprocess

    from playwright.sync_api import expect
    from test_pr34_remediation import tool

    from okto_nexus.application.auth import AgentKeyAuthService

    deps, client, root, peers, operator, _ = runtime
    assert client.post('/api/v1/agents', headers={'x-api-key': operator}, json={'agent_id': 'empty-worker'}).status_code == 200
    with deps.connection_factory.unit_of_work() as uow:
        key = AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id='empty-worker')
    page = dashboard
    page.get_by_role('button', name='Agents', exact=True).click()
    page.get_by_test_id('connections-empty-worker').click()
    panel = page.get_by_test_id('agent-connections-empty-worker')
    expect(panel.get_by_text('No endpoints configured.', exact=False)).to_be_visible()
    panel.get_by_role('button', name='Configure endpoint', exact=True).click()
    setup = panel.get_by_test_id('endpoint-setup')
    setup.get_by_label('Endpoint connection method').select_option('pi')
    setup.get_by_label('Endpoint name', exact=True).fill('ui-empty-pi')
    setup.get_by_label('Endpoint project directory').fill(root)
    expect(setup.get_by_role('button', name='Create approved endpoint')).to_be_disabled()
    setup.screenshot(path=str(__import__('pathlib').Path(root).parent / 'endpoint-setup.png'))
    setup.get_by_role('checkbox').check()
    setup.get_by_role('button', name='Create approved endpoint').click()
    endpoint = panel.get_by_test_id('connection-endpoint-ui-empty-pi')
    expect(endpoint).to_be_visible()
    assert not peers
    endpoint.get_by_role('button', name='Authorize MCP opening (1 hour)').click()
    expect(panel.get_by_role('status')).to_contain_text('MCP discovery and opening authorized')
    discovered = tool(client, key, 'harness_list', {'view': 'connections', 'maintenance': {'action': 'available'}})
    assert discovered['ok'] and next(m for m in discovered['data']['methods'] if m['method'] == 'pi')['available']
    endpoint.get_by_role('button', name='Generate connection command').click()
    field = panel.get_by_label('Connection request', exact=True)
    expect(field).to_be_visible()
    panel.get_by_label('Connection command format').select_option('powershell')
    page.context.grant_permissions(['clipboard-read', 'clipboard-write'])
    panel.get_by_role('button', name='Copy connection command', exact=True).click()
    expect(panel.get_by_role('status')).to_have_text('Connection command copied.')
    command = page.evaluate('navigator.clipboard.readText()')
    assert command.startswith('Invoke-RestMethod ')
    result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', command + ' | ConvertTo-Json -Depth 8'],
        capture_output=True, text=True, timeout=30, check=False, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    assert result.returncode == 0, 'Copied PowerShell command failed'
    assert json.loads(result.stdout)['data']['agent_id'] == 'empty-worker'
    assert len(peers) == 1
    panel.get_by_label('Connection command format').select_option('bash')
    assert field.input_value().startswith('curl --fail-with-body ')
    panel.get_by_role('button', name='Revoke', exact=True).click()
    expect(field).to_have_count(0)
    expect(endpoint.get_by_role('button', name='Generate connection command')).to_be_enabled()
    panel.screenshot(path=str(__import__('pathlib').Path(root).parent / 'connection-command-cleared.png'))
    page.evaluate("document.documentElement.classList.add('dark')")
    page.wait_for_timeout(300)  # Let the existing theme color transition finish.
    panel.screenshot(path=str(__import__('pathlib').Path(root).parent / 'connection-panel-dark.png'))
