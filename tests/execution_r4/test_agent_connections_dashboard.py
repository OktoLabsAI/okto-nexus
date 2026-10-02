"""Agents owns all local configuration; message workspaces are contextual."""
import os
from pathlib import Path
import pytest
from test_local_realization import local_setup
from test_embedded_preparation_dashboard import local_browser
from test_runtime_selection_dashboard import assets

pytestmark = pytest.mark.skipif(os.environ.get('OKTO_NEXUS_UI_CAMPAIGN') != '1',
                               reason='Isolated browser campaign not enabled')


def test_agent_connections_has_original_mcp_policy_and_local_configuration(local_setup, local_browser, tmp_path):
    from playwright.sync_api import expect
    deps, app, client, headers, *_ = local_setup
    page, trace = local_browser
    page.get_by_role('button', name='Agents', exact=True).click()
    button = page.get_by_test_id('connections-subject')
    expect(button).to_have_attribute('title', 'Connections')
    expect(button).to_have_text('')
    button.click()
    panel = page.get_by_test_id('agent-connections-subject')
    expect(panel).to_contain_text('http://nexus.test/mcp')
    expect(panel).to_contain_text("existing API key")
    expect(panel.get_by_text('Legacy', exact=False)).to_have_count(0)
    panel.get_by_label('Execution access', exact=True).select_option('remote')
    remote = panel.get_by_role('region', name='Remote Connector setup')
    expect(remote).to_be_visible()
    remote.get_by_label('Remote Nexus address').fill('https://nexus.lan:8202')
    expect(remote.get_by_test_id('connector-command')).to_contain_text("okto-nexus-connector connect --server='https://nexus.lan:8202' --agent='subject'")
    page.evaluate("Object.defineProperty(navigator, 'clipboard', {configurable:true,value:{writeText:async text=>{window.copiedCommand=text}}})")
    remote.get_by_role('button', name='Copy Connector command').click()
    expect(remote.get_by_role('button', name='Command copied')).to_be_visible()
    assert page.evaluate('window.copiedCommand') == remote.get_by_test_id('connector-command').inner_text()
    panel.get_by_role('button', name='Save execution policy', exact=True).click()
    expect(panel.get_by_text('Execution policy saved.', exact=True)).to_be_visible()
    expect(panel.get_by_test_id('runtime-selection')).to_have_count(0)
    expect(panel).to_contain_text('in the Connector')
    panel.get_by_label('Execution access', exact=True).select_option('local')
    expect(remote).to_have_count(0)
    expect(panel.get_by_label('Local runtime integration', exact=True)).to_have_count(0)
    expect(panel.get_by_test_id('local-runtime-pi_rpc')).to_be_disabled()
    panel.get_by_test_id('local-runtime-codex_app_server').click()
    panel.get_by_role('button', name='Save execution policy', exact=True).click()
    expect(panel.get_by_text('Execution policy saved.', exact=True)).to_be_visible()
    local = panel.get_by_test_id('runtime-selection')
    expect(local.get_by_label('Execution host', exact=True)).to_have_count(0)
    expect(local).to_contain_text('Local harness configuration')
    with deps.connection_factory.unit_of_work(write=False) as uow:
        policy = dict(uow.connection.execute('SELECT * FROM agent_execution_policies WHERE agent_id=?', ('subject',)).fetchone())
        assert policy['execution_location'] == 'local' and policy['local_adapter_id'] == 'codex_app_server'
        assert 'workspace_id' not in policy
        assert uow.connection.execute('SELECT COUNT(*) FROM agent_connection_keys').fetchone()[0] == 0
    assert not any('/connection-keys' in path for _, path, _ in trace['requests'])
    panel.get_by_label('Execution access', exact=True).select_option('all')
    expect(panel.get_by_role('region', name='Remote Connector setup')).to_be_visible()
    expect(panel.get_by_role('group', name='Local runtime', exact=True)).to_be_visible()
    target = Path(os.environ.get('OKTO_NEXUS_UI_SCREENSHOT_DIR', str(tmp_path)))
    target.mkdir(parents=True, exist_ok=True)
    panel.screenshot(path=str(target / 'agent-connections-local-and-remote.png'))
    page.evaluate("document.documentElement.classList.add('dark')")
    panel.screenshot(path=str(target / 'agent-connections-local-and-remote-dark.png'))


@pytest.mark.parametrize('local_browser', [True], indirect=True)
def test_keyless_dashboard_can_select_and_save_local_configuration(local_setup, local_browser):
    from playwright.sync_api import expect
    from test_embedded_preparation_dashboard import select_local, fill_preparation
    deps, _, _, _, _, _, root = local_setup
    page, trace = local_browser
    page.get_by_role('button', name='Agents', exact=True).click()
    page.get_by_test_id('connections-subject').click()
    connections = page.get_by_test_id('agent-connections-subject')
    connections.get_by_test_id('local-runtime-codex_app_server').click()
    # Fill options before a separate policy save: preparation saves the draft.
    panel = connections.get_by_test_id('runtime-selection')
    fill_preparation(panel, root)
    panel.get_by_role('checkbox', name='I approve these folders', exact=False).check()
    panel.get_by_role('button', name='Approve local preparation', exact=True).click()
    expect(panel.get_by_label('Connection name', exact=True)).to_be_visible()
    panel.get_by_label('Connection name', exact=True).fill('Keyless local dashboard')
    panel.get_by_role('button', name='Review connection', exact=True).click()
    panel.get_by_role('button', name='Approve connection', exact=True).click()
    expect(panel.get_by_role('region', name='Connection status')).to_contain_text('Connection: APPROVED')
    assert any(path.startswith('/api/v1/runtime-management/') for _, path, _ in trace['requests'])
    assert not page.get_by_role('alert').count()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT api_key_hash FROM agents WHERE agent_id='operator'").fetchone()[0] is None
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_bindings').fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_sessions').fetchone()[0] == 0
    # Referential conflicts stay in the dialog, with no unhandled rejection.
    failures = []
    page.on('pageerror', lambda error: failures.append(str(error)))
    page.get_by_test_id('agent-subject').get_by_title('Delete agent', exact=True).click()
    dialog = page.get_by_test_id('confirm-dialog')
    dialog.get_by_role('button', name='Confirm', exact=True).click()
    expect(dialog.get_by_role('alert')).to_contain_text('Deactivate')
    expect(dialog.get_by_role('button', name='Confirm', exact=True)).to_be_enabled()
    assert not failures
    expect(page.get_by_test_id('agent-subject')).to_be_visible()


def test_delete_configured_agent_from_dashboard(local_setup, local_browser):
    from playwright.sync_api import expect
    from test_embedded_preparation_dashboard import select_local
    deps, _, client, headers, *_ = local_setup
    page, _ = local_browser
    select_local(page, local_setup)
    page.get_by_test_id('agent-subject').get_by_title('Delete agent', exact=True).click()
    dialog = page.get_by_test_id('confirm-dialog')
    dialog.get_by_role('button', name='Confirm', exact=True).click()
    expect(dialog).to_have_count(0)
    expect(page.get_by_test_id('agent-subject')).to_have_count(0)
    assert client.get('/api/v1/agents/subject', headers=headers['operator']).status_code == 404
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()
