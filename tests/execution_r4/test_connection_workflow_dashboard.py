"""Browser + real API/SQLite: draft navigation cannot activate a connection."""
import os
from dataclasses import replace
from types import SimpleNamespace
import pytest
from test_local_realization import local_setup
from test_embedded_preparation_dashboard import local_browser
from test_runtime_selection_dashboard import assets

pytestmark=pytest.mark.skipif(os.environ.get('OKTO_NEXUS_UI_CAMPAIGN')!='1',reason='Browser campaign disabled')


@pytest.fixture(autouse=True,params=[False,True],ids=['unknown-version','selection-required'])
def version_probe(monkeypatch,local_setup,request):
    import nexus_connector_core.availability as availability
    from okto_nexus.application import execution_local_observations
    from okto_nexus.bootstrap import embedded_inventory
    _,app,client,_,_,candidate,_=local_setup
    monkeypatch.setattr(availability,'qualified_build',lambda *a,**k:True)
    candidate=replace(candidate,architecture='x86_64',version='0.159.0' if request.param else None,trust='untrusted' if request.param else 'selected')
    monkeypatch.setattr(embedded_inventory,'discover_local_candidates',lambda **k:SimpleNamespace(candidates=(candidate,)))
    client.portal.call(app.state.embedded_inventory_owner.refresh)
    async def probe(candidate): return replace(candidate,version='0.159.0')
    monkeypatch.setattr(execution_local_observations,'probe_version',probe)


def start(page,setup):
    from playwright.sync_api import expect
    page.get_by_role('button',name='Agents',exact=True).click()
    page.get_by_test_id('connections-subject').click()
    panel=page.get_by_test_id('agent-connections-subject')
    expect(panel.get_by_role('button',name='Import JSON',exact=True)).to_be_visible()
    panel.get_by_test_id('local-runtime-'+setup[4]['adapter_id']).click()
    panel.get_by_role('button',name='Next →',exact=True).click()
    expect(panel.get_by_role('radio')).to_be_checked()
    expect(panel.get_by_role('button',name='Check installation version',exact=True)).to_have_count(0)
    expect(panel.get_by_text('Installation verified',exact=True)).to_be_visible()
    expect(panel.get_by_role('button',name='Next →',exact=True)).to_be_enabled()
    panel.get_by_role('button',name='Next →',exact=True).click()
    return panel


def test_drafts_survive_navigation_without_writes(local_setup,local_browser):
    from playwright.sync_api import expect
    page,trace=local_browser
    panel=start(page,local_setup)
    expect(panel.get_by_role('button',name='Next →',exact=True)).to_be_disabled()
    panel.get_by_label('Workspace folder',exact=True).fill(str(local_setup[-1]))
    panel.get_by_label('Workspace name',exact=True).fill('Wizard workspace')
    panel.get_by_role('button',name='← Back',exact=True).click()
    panel.get_by_role('button',name='← Back',exact=True).click()
    panel.get_by_role('button',name='Next →',exact=True).click()
    panel.get_by_role('button',name='Next →',exact=True).click()
    expect(panel.get_by_label('Workspace folder',exact=True)).to_have_value(str(local_setup[-1]))
    assert len([path for method,path,_ in trace['requests'] if path.endswith('/installations:check')]) == 1
    expect(panel.get_by_label('Workspace name',exact=True)).to_have_value('Wizard workspace')
    with local_setup[0].connection_factory.unit_of_work(write=False) as uow:
        for table in ('execution_bindings','execution_local_realizations','agent_execution_policies'):
            assert uow.connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0


def test_automatic_check_recovers_lost_reply(local_setup,local_browser):
    from playwright.sync_api import expect
    page,trace=local_browser
    trace['drop_check']=True
    page.get_by_role('button',name='Agents',exact=True).click()
    page.get_by_test_id('connections-subject').click()
    panel=page.get_by_test_id('agent-connections-subject')
    panel.get_by_test_id('local-runtime-'+local_setup[4]['adapter_id']).click()
    panel.get_by_role('button',name='Next →',exact=True).click()
    expect(panel.get_by_text('Could not verify this installation.',exact=True)).to_be_visible()
    expect(panel.get_by_role('button',name='Next →',exact=True)).to_be_disabled()
    panel.get_by_role('button',name='Retry',exact=True).click()
    expect(panel.get_by_text('Installation verified',exact=True)).to_be_visible()
    expect(panel.get_by_role('button',name='Next →',exact=True)).to_be_enabled()
    assert len([path for method,path,_ in trace['requests'] if path.endswith('/installations:check')]) == 1


@pytest.mark.parametrize('local_browser',[True],indirect=True)
def test_next_stages_preferences_and_authorization(local_setup,local_browser):
    from playwright.sync_api import expect
    page,trace=local_browser
    panel=start(page,local_setup)
    panel.get_by_label('Workspace folder',exact=True).fill(str(local_setup[-1]))
    panel.get_by_label('Workspace name',exact=True).fill('Wizard workspace')
    panel.get_by_role('button',name='Next →',exact=True).click()
    panel.get_by_label('Connection name',exact=True).fill('Wizard connection')
    panel.get_by_role('button',name='Next →',exact=True).click()
    panel.get_by_label('Nexus tool access',exact=True).select_option('always_allow')
    expect(panel.get_by_role('button',name='Save harness settings',exact=True)).to_have_count(0)
    expect(panel.get_by_role('button',name='Import JSON',exact=True)).to_have_count(0)
    panel.get_by_role('button',name='Next →',exact=True).click()
    expect(panel.get_by_role('button',name='Authorize local execution',exact=True)).to_have_count(0)
    panel.get_by_role('button',name='Next →',exact=True).click()
    expect(panel.get_by_role('button',name='Test connection',exact=True)).to_be_enabled()
    expect(panel.get_by_role('button',name='Finish',exact=True)).to_have_count(0)
    panel.get_by_role('button',name='Details',exact=True).click()
    expect(panel.get_by_text('Checks installation, provider login',exact=False)).to_be_visible()
    writes=[path for method,path,_ in trace['requests'] if method in ('POST','PUT') and any(word in path for word in ('realizations','bindings:','harness/grants','tool-permission','harness-settings','conversation-policy','execution-policy','runtime-policy'))]
    assert not writes


def test_verified_probe_enables_atomic_finish(local_setup,local_browser,monkeypatch):
    import asyncio
    from playwright.sync_api import expect
    from okto_nexus.application.connection_test import ConnectionTests
    async def native_probe(self,entry,request,candidate):
        # Native transport alone is simulated; UI, auth and Finish use real services.
        entry['stage']='Waiting for a model response'
        entry['details'].append(entry['stage'])
        await asyncio.sleep(.2)
        entry.update(status='succeeded',stage='Connection verified')
    monkeypatch.setattr(ConnectionTests,'run',native_probe)
    page,_=local_browser
    panel=start(page,local_setup)
    panel.get_by_label('Workspace folder',exact=True).fill(str(local_setup[-1]))
    panel.get_by_label('Workspace name',exact=True).fill('Wizard workspace')
    panel.get_by_label('Login directory',exact=True).fill('')
    for _ in range(4):panel.get_by_role('button',name='Next →',exact=True).click()
    panel.get_by_role('button',name='Test connection',exact=True).click()
    finish=panel.get_by_role('button',name='Finish',exact=True)
    expect(finish).to_be_visible(timeout=15000)
    with local_setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_bindings').fetchone()[0]==0
    finish.click()
    expect(panel).to_have_count(0)
    with local_setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_bindings').fetchone()[0]==1
        assert uow.connection.execute('SELECT COUNT(*) FROM connection_setup_commits').fetchone()[0]==1
    # Reopen on step 1: export must contain the saved connection, not empty defaults.
    import json
    from pathlib import Path
    from nexus_connector_core.connection_configuration import parse_portable_connection_configuration
    page.get_by_test_id('connections-subject').click()
    panel=page.get_by_test_id('agent-connections-subject')
    export=panel.get_by_role('button',name='Export JSON',exact=True)
    expect(export).to_be_enabled()
    with page.expect_download() as download:
        export.click()
    contents=Path(download.value.path()).read_text(encoding='utf-8')
    configuration=parse_portable_connection_configuration(contents)
    assert configuration['version']==2
    assert 'workspace_root' not in configuration
    assert 'provider_home' not in configuration
    assert configuration['runtime_enabled'] is None
    configuration['alias']='Imported connection'
    panel.get_by_label('Import connection JSON',exact=True).set_input_files({
        'name':'connection.json','mimeType':'application/json','buffer':json.dumps(configuration).encode()})
    expect(panel.get_by_text('Configuration imported.',exact=False)).to_be_visible()
    with page.expect_download() as imported_download:
        export.click()
    assert parse_portable_connection_configuration(Path(imported_download.value.path()).read_text(encoding='utf-8'))==configuration
    expect(panel.get_by_label('Partial',exact=True)).not_to_have_count(0)
    expect(panel.get_by_label('Not completed',exact=True)).not_to_have_count(0)
    with local_setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM connection_setup_commits').fetchone()[0]==1
