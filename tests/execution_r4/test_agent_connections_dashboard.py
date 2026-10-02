"""Agents owns all local configuration; message workspaces are contextual."""
import os
import pytest
from test_local_realization import local_setup
from test_embedded_preparation_dashboard import local_browser
from test_runtime_selection_dashboard import assets

pytestmark = pytest.mark.skipif(os.environ.get('OKTO_NEXUS_UI_CAMPAIGN') != '1',
                               reason='Isolated browser campaign not enabled')


def test_agent_connections_has_original_mcp_policy_and_local_configuration(local_setup, local_browser):
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
    panel.get_by_role('button', name='Save execution policy', exact=True).click()
    expect(panel.get_by_text('Execution policy saved.', exact=True)).to_be_visible()
    expect(panel.get_by_test_id('runtime-selection')).to_have_count(0)
    expect(panel).to_contain_text('in the Connector')
    panel.get_by_label('Execution access', exact=True).select_option('local')
    panel.get_by_label('Local runtime integration', exact=True).select_option('codex_app_server')
    panel.get_by_role('button', name='Save execution policy', exact=True).click()
    expect(panel.get_by_text('Execution policy saved.', exact=True)).to_be_visible()
    local = panel.get_by_test_id('runtime-selection')
    host = local.get_by_label('Execution host', exact=True)
    expect(host).to_be_enabled()
    host.select_option(app.state.embedded_inventory_owner.key.executor_id)
    expect(local).to_contain_text('Local harness configuration')
    with deps.connection_factory.unit_of_work(write=False) as uow:
        policy = dict(uow.connection.execute('SELECT * FROM agent_execution_policies WHERE agent_id=?', ('subject',)).fetchone())
        assert policy['execution_location'] == 'local' and policy['local_adapter_id'] == 'codex_app_server'
        assert 'workspace_id' not in policy
        assert uow.connection.execute('SELECT COUNT(*) FROM agent_connection_keys').fetchone()[0] == 0
    assert not any('/connection-keys' in path for _, path, _ in trace['requests'])
