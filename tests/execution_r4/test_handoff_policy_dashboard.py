"""Policy UI against real HTTP services and SQLite; no live harnesses."""
import os
from pathlib import Path

import pytest
from test_local_realization import local_setup
from test_embedded_preparation_dashboard import local_browser
from test_runtime_selection_dashboard import assets

pytestmark = pytest.mark.skipif(os.environ.get('OKTO_NEXUS_UI_CAMPAIGN') != '1',
                               reason='Browser campaign disabled')


def test_global_auto_claim_and_agent_override(local_setup, local_browser):
    from playwright.sync_api import expect
    page, _ = local_browser
    page.get_by_test_id('header-menu').click()
    page.get_by_role('button', name='Settings', exact=True).click()
    policy = page.get_by_role('region', name='Global runtime defaults', exact=True)
    choice = policy.get_by_label('Automatically claim broadcast handoffs', exact=True)
    expect(choice).to_have_value('false')
    choice.select_option('true')
    policy.get_by_role('button', name='Save global runtime defaults', exact=True).click()
    expect(policy.get_by_role('status')).to_have_text('Runtime policy saved.')
    expect(policy.get_by_text('Automatic acquisition is disabled on this server.', exact=False)).to_be_visible()
    policy.get_by_role('button', name='Reload runtime policy', exact=True).click()
    expect(choice).to_have_value('true')
    target = Path('output/playwright/auto-claim-policy')
    target.mkdir(parents=True, exist_ok=True)
    policy.screenshot(path=str(target / 'global-defaults.png'))
    page.get_by_role('button', name='Agents', exact=True).click()
    page.get_by_test_id('connections-subject').click()
    panel = page.get_by_test_id('agent-action-subject')
    choice = panel.get_by_label('Automatically claim broadcast handoffs', exact=True)
    expect(choice).to_have_value('inherit')
    expect(choice.get_by_role('option', name='Use global setting (Enabled)', exact=True)).to_have_count(1)
    panel.get_by_label('Execution access', exact=True).select_option('remote')
    choice.select_option('false')
    with local_setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM agent_runtime_overrides').fetchone()[0] == 0
    panel.get_by_role('button', name='Finish', exact=True).click()
    expect(panel).to_have_count(0)
    page.get_by_test_id('connections-subject').click()
    panel = page.get_by_test_id('agent-action-subject')
    expect(panel.get_by_label('Automatically claim broadcast handoffs', exact=True)).to_have_value('false')
    panel.get_by_label('Automatically claim broadcast handoffs', exact=True).select_option('inherit')
    panel.get_by_role('button', name='Finish', exact=True).click()
    expect(panel).to_have_count(0)
    response = local_setup[2].get('/api/v1/agents/subject/runtime-policy', headers=local_setup[3]['operator'])
    assert response.status_code == 200
    policy = response.json()['data']
    assert policy['broadcast_handoff_auto_claim'] is None
    assert policy['effective']['broadcast_handoff_auto_claim'] is True
    assert policy['handoff_auto_claim_rollout_enabled'] is False


@pytest.mark.parametrize('agent', [None, 'subject'])
def test_import_cannot_rebase_stale_automation_policy(local_setup, local_browser, agent):
    from playwright.sync_api import expect
    from test_runtime_policy_defaults import save
    page, _ = local_browser
    page.get_by_role('button', name='Agents', exact=True).click()
    page.get_by_test_id('connections-subject').click()
    panel = page.get_by_test_id('agent-action-subject')
    choice = panel.get_by_label('Automatically claim broadcast handoffs', exact=True)
    expect(choice).to_have_value('inherit')
    choice.select_option('true')
    with page.expect_download() as download:
        panel.get_by_role('button', name='Export JSON', exact=True).click()
    contents = Path(download.value.path()).read_bytes()
    # Another operator changes the governing policy after this draft loaded.
    assert save(local_setup, agent=agent, broadcast_handoff_auto_claim=False if agent else True).status_code == 200
    panel.get_by_label('Import connection JSON', exact=True).set_input_files({
        'name': 'connection.json', 'mimeType': 'application/json', 'buffer': contents})
    expect(panel.get_by_text('Configuration imported.', exact=False)).to_be_visible()
    expect(choice).to_have_value('true')
    panel.get_by_label('Execution access', exact=True).select_option('remote')
    panel.get_by_role('button', name='Finish', exact=True).click()
    expect(panel.get_by_role('alert')).to_contain_text('The active configuration changed')
    with local_setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM connection_setup_commits').fetchone()[0] == 0
        row = uow.connection.execute("SELECT broadcast_handoff_auto_claim FROM agent_runtime_overrides WHERE agent_id='subject'").fetchone()
        assert (row is not None and row[0] == 0) if agent else row is None
