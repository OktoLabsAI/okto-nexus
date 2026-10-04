"""Guided configuration keeps drafts and requires real execution evidence."""
import os
import pytest
from test_local_realization import local_setup
from test_embedded_preparation_dashboard import local_browser
from test_runtime_selection_dashboard import assets

pytestmark = pytest.mark.skipif(os.environ.get('OKTO_NEXUS_UI_CAMPAIGN') != '1',
                               reason='Isolated browser campaign not enabled')


@pytest.fixture(autouse=True, params=[False, True], ids=['version-unknown', 'known-version-needs-selection'])
def version_probe(monkeypatch, local_setup, request):
    from dataclasses import replace
    from types import SimpleNamespace
    import nexus_connector_core.availability as availability
    from okto_nexus.application import execution_local_observations
    from okto_nexus.bootstrap import embedded_inventory
    _, app, client, _, _, candidate, _ = local_setup
    # Qualify the synthetic provider before refreshing inventory, including
    # candidates whose version is already known but selection is not approved.
    monkeypatch.setattr(availability, 'qualified_build', lambda *args, **kwargs: True)
    candidate = replace(candidate, architecture='x86_64',
                        version='0.159.0' if request.param else None,
                        trust='untrusted' if request.param else 'selected')
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', lambda **kwargs: SimpleNamespace(candidates=(candidate,)))
    client.portal.call(app.state.embedded_inventory_owner.refresh)
    async def probe(candidate):
        return replace(candidate, version='0.159.0')
    monkeypatch.setattr(execution_local_observations, 'probe_version', probe)


def start(page, setup):
    from playwright.sync_api import expect
    page.get_by_role('button', name='Agents', exact=True).click()
    page.get_by_test_id('connections-subject').click()
    panel = page.get_by_test_id('agent-connections-subject')
    panel.get_by_test_id('local-runtime-' + setup[4]['adapter_id']).click()
    panel.get_by_role('button', name='Next →', exact=True).click()
    expect(panel.get_by_role('heading', name='Step 2 of 7 · Installation')).to_be_visible()
    panel.get_by_test_id('runtime-candidate-' + setup[4]['candidate_ref']).get_by_role('radio').check()
    panel.get_by_role('checkbox', name='I approve selecting this exact local installation', exact=False).check()
    panel.get_by_role('button', name='Check installation version', exact=True).click()
    try:
        expect(panel.get_by_role('button', name='Next →', exact=True)).to_be_enabled()
    except AssertionError:
        raise AssertionError(panel.inner_text())
    panel.get_by_role('button', name='Next →', exact=True).click()
    expect(panel.get_by_role('heading', name='Step 3 of 7 · Folders & login')).to_be_visible()
    return panel


def test_navigation_preserves_folder_draft_and_blocks_incomplete_steps(local_setup, local_browser):
    from playwright.sync_api import expect
    page, trace = local_browser
    panel = start(page, local_setup)
    expect(panel.get_by_role('button', name='Next →', exact=True)).to_be_disabled()
    root = str(local_setup[-1])
    panel.get_by_label('Workspace directory', exact=True).fill(root)
    panel.get_by_label('New workspace name', exact=True).fill('Wizard workspace')
    panel.get_by_role('button', name='← Back', exact=True).click()
    panel.get_by_role('button', name='← Back', exact=True).click()
    panel.get_by_role('button', name='Next →', exact=True).click()
    panel.get_by_role('button', name='Next →', exact=True).click()
    expect(panel.get_by_label('Workspace directory', exact=True)).to_have_value(root)
    expect(panel.get_by_label('New workspace name', exact=True)).to_have_value('Wizard workspace')
    assert not any(path.endswith('/realizations') for _, path, _ in trace['requests'])


@pytest.mark.parametrize('local_browser', [True], indirect=True)
def test_wizard_reaches_test_only_after_approval_and_authorization(local_setup, local_browser):
    from playwright.sync_api import expect
    page, trace = local_browser
    panel = start(page, local_setup)
    panel.get_by_label('Workspace directory', exact=True).fill(str(local_setup[-1]))
    panel.get_by_label('New workspace name', exact=True).fill('Wizard workspace')
    panel.get_by_role('checkbox', name='I approve these folders', exact=False).check()
    panel.get_by_role('button', name='Approve local preparation', exact=True).click()
    expect(panel.get_by_role('heading', name='Step 4 of 7 · Connection')).to_be_visible()
    panel.get_by_label('Connection name', exact=True).fill('Wizard connection')
    panel.get_by_role('button', name='Review connection', exact=True).click()
    panel.get_by_role('button', name='Approve connection', exact=True).click()
    expect(panel.get_by_role('heading', name='Step 5 of 7 · Preferences')).to_be_visible()
    deps, _, client, *_ = local_setup
    with deps.connection_factory.unit_of_work(write=False) as uow:
        endpoint_id = uow.connection.execute('SELECT endpoint_id FROM execution_bindings').fetchone()[0]
    summary = client.get(f'/api/v1/harness/endpoints/{endpoint_id}/connection-summary')
    assert summary.status_code == 200, summary.text
    assert summary.json()['data']['connection_name'] == 'Wizard connection'
    assert set(summary.json()['data']) == {'endpoint_id', 'agent_id', 'workspace_id', 'connection_name'}
    panel.get_by_role('checkbox', name='Reply automatically to messages in this workspace', exact=True).check()
    expect(panel.get_by_role('button', name='Next →', exact=True)).to_be_disabled()
    expect(panel.get_by_role('button', name='← Back', exact=True)).to_be_disabled()
    panel.get_by_role('button', name='Save message policy', exact=True).click()
    panel.get_by_role('button', name='Next →', exact=True).click()
    expect(panel.get_by_role('heading', name='Step 6 of 7 · Authorization')).to_be_visible()
    expect(panel.get_by_role('button', name='Next →', exact=True)).to_be_disabled()
    panel.get_by_role('checkbox', name='I authorize execution with these settings.', exact=False).check()
    panel.get_by_role('button', name='Authorize local execution', exact=True).click()
    panel.get_by_role('button', name='Next →', exact=True).click()
    expect(panel.get_by_role('heading', name='Step 7 of 7 · Test')).to_be_visible()
    expect(panel.get_by_role('button', name='Test connection', exact=True)).to_be_enabled()
    expect(panel.get_by_text('Connection verified', exact=True)).to_have_count(0)
    # Configuration and navigation must never implicitly start a harness.
    assert not any(path.endswith('/runtime/operations') and method == 'POST' for method, path, _ in trace['requests'])
