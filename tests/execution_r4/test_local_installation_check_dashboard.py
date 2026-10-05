"""Real packaged UI and HTTP consent; version process substituted at the Core seam."""
import json
import os
from pathlib import Path

import pytest
from test_local_installation_check import checking
from test_local_realization import local_setup
from test_embedded_preparation_dashboard import local_browser, select_local
from test_runtime_selection_dashboard import assets

pytestmark = pytest.mark.skipif(os.environ.get('OKTO_NEXUS_UI_CAMPAIGN') != '1',
                               reason='Isolated browser campaign not enabled')


@pytest.mark.parametrize('lost_reply', [False, True])
def test_version_check_requires_consent_and_refreshes_selected_inventory(checking, local_setup, local_browser, lost_reply):
    from playwright.sync_api import expect
    deps, app, _, _, body, route, _, calls = checking
    page, trace = local_browser
    trace['drop_check'] = lost_reply
    panel = select_local(page, local_setup)
    button = panel.get_by_role('button', name='Check installation version', exact=True)
    expect(button).to_be_disabled()
    assert not calls
    target = Path(__file__).parents[2] / 'plans/r4_execution/evidence/local-check-ui'
    target.mkdir(parents=True, exist_ok=True)
    panel.get_by_role('region', name='Local installation version check').screenshot(path=str(target / f'consent-{lost_reply}.png'))
    panel.get_by_label('I approve selecting this exact local installation and running its version check.').check()
    button.click()
    if lost_reply:
        expect(panel.get_by_role('alert')).to_contain_text('Refresh inventory before checking again.')
        expect(button).to_be_disabled()
        panel.get_by_role('button', name='Reload published inventory', exact=True).click()
        expect(panel.get_by_text('The inventory changed or became unavailable. Review the current options and select the installation again.', exact=True)).to_be_visible()
    else:
        expect(panel.get_by_text('Version checked. Review the refreshed installation before preparing its workspace.', exact=True)).to_be_visible()
    assert len(calls) == 1
    sent = [json.loads(content) for method, path, content in trace['requests'] if method == 'POST' and path == route]
    assert sent == [body]
    assert app.state.embedded_inventory_owner.candidates[0].version == '0.159.0'
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_sessions').fetchone()[0] == 0
