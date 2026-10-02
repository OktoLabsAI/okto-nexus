"""Packaged local preparation UI, real API/SQLite, synthetic passive candidate."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from test_local_realization import local_setup
from test_runtime_selection_dashboard import assets

pytestmark = pytest.mark.skipif(os.environ.get('OKTO_NEXUS_UI_CAMPAIGN') != '1',
                               reason='Isolated browser campaign not enabled')


@pytest.fixture
def local_browser(local_setup, assets):
    from playwright.sync_api import sync_playwright
    _, _, client, headers, _, _, _ = local_setup
    trace = {'requests': [], 'drop_response': False}
    with sync_playwright() as driver:
        browser = driver.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1200})
        context.add_init_script('sessionStorage.setItem("okto_nexus_operator_key", ' + json.dumps(headers['operator']['Authorization'][7:]) + ');')
        context.add_init_script('localStorage.setItem("okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0", "fixture");')

        def route_request(route):
            request = route.request
            url = urlsplit(request.url)
            if url.netloc != 'nexus.test':
                route.abort()
                return
            if url.path == '/api/v1/stream':
                route.fulfill(status=200, body=': isolated preparation test\n\n', content_type='text/event-stream')
                return
            if url.path.startswith(('/api/', '/v1/')):
                trace['requests'].append((request.method, url.path, request.post_data))
                response = client.request(request.method, url.path + ('?' + url.query if url.query else ''),
                    headers={name: value for name, value in request.headers.items() if name.lower() in ('authorization', 'x-api-key', 'content-type')},
                    content=request.post_data)
                if url.path.endswith('/realizations') and trace['drop_response']:
                    assert response.status_code == 201, response.text
                    trace['drop_response'] = False
                    route.abort('failed')
                    return
                if url.path.endswith('/installations:check') and trace.get('drop_check'):
                    assert response.status_code == 200, response.text
                    trace['drop_check'] = False
                    route.abort('failed')
                    return
                route.fulfill(status=response.status_code, body=response.content,
                              content_type=response.headers.get('content-type', 'application/json'))
                return
            target = (assets / ('index.html' if url.path == '/' else url.path.lstrip('/'))).resolve()
            if target.is_relative_to(assets.resolve()) and target.is_file():
                route.fulfill(path=str(target))
            else:
                route.fulfill(status=404)

        context.route('**/*', route_request)
        page = context.new_page()
        page.set_default_timeout(15000)
        try:
            page.goto('http://nexus.test/')
            page.get_by_test_id('onboarding-close').click()
            yield page, trace
        finally:
            context.close()
            browser.close()


def select_local(page, setup):
    from playwright.sync_api import expect
    _, app, _, _, body, _, _ = setup
    page.get_by_role('button', name='Agents', exact=True).click()
    page.get_by_test_id('connections-subject').click()
    panel = page.get_by_test_id('runtime-selection')
    host = panel.get_by_label('Execution host', exact=True)
    expect(host).to_be_enabled()
    host.select_option(app.state.embedded_inventory_owner.key.executor_id)
    candidate = panel.get_by_test_id('runtime-candidate-' + body['candidate_ref']).get_by_role('radio')
    expect(candidate).to_be_enabled()
    candidate.check()
    return panel


def fill_preparation(panel, root):
    panel.get_by_label('Workspace directory', exact=True).fill(str(root))
    panel.get_by_label('New workspace name', exact=True).fill('Browser project')
    panel.get_by_label('Provider home directory', exact=True).fill(str(root.parent))
    panel.get_by_label('Protected credential references', exact=True).fill('OPENAI_API_KEY=vault:provider-key')


@pytest.mark.parametrize('lost_reply', [False, True])
def test_local_preparation_reaches_binding_without_start_and_retries_same_consent(local_setup, local_browser, tmp_path, lost_reply):
    from playwright.sync_api import expect
    deps, _, _, _, _, _, root = local_setup
    page, trace = local_browser
    panel = select_local(page, local_setup)
    fill_preparation(panel, root)
    # Refresh must not unmount the form and discard a partially reviewed draft.
    panel.get_by_role('button', name='Reload published inventory', exact=True).click()
    expect(panel.get_by_label('Workspace directory', exact=True)).to_have_value(str(root))
    approve = panel.get_by_role('button', name='Approve local preparation', exact=True)
    expect(approve).to_be_disabled()
    panel.get_by_role('checkbox', name='I approve these folders', exact=False).check()
    expect(approve).to_be_enabled()
    target = Path(os.environ.get('OKTO_NEXUS_UI_SCREENSHOT_DIR', str(tmp_path)))
    target.mkdir(parents=True, exist_ok=True)
    panel.get_by_role('region', name='Local workspace preparation').screenshot(path=str(target / f'embedded-preparation-form-{lost_reply}.png'))
    trace['drop_response'] = lost_reply
    approve.click()
    if lost_reply:
        expect(panel.get_by_role('button', name='Retry the same preparation', exact=True)).to_be_enabled()
        expect(panel.get_by_role('alert')).to_be_visible()
        page.reload()
        if page.get_by_test_id('onboarding-close').is_visible():
            page.get_by_test_id('onboarding-close').click()
        panel = select_local(page, local_setup)
        expect(panel.get_by_label('Workspace directory', exact=True)).to_have_value(str(root))
        expect(panel.get_by_label('Workspace directory', exact=True)).to_be_disabled()
        panel.get_by_role('button', name='Retry the same preparation', exact=True).click()
    expect(panel.get_by_label('Connection name', exact=True)).to_be_visible()
    requests = [json.loads(body) for _, path, body in trace['requests'] if path.endswith('/realizations')]
    assert len(requests) == (2 if lost_reply else 1)
    assert all(body == requests[0] for body in requests)
    assert requests[0]['approved'] is True
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_local_realizations').fetchone()[0] == 1
        record = json.loads(uow.connection.execute('SELECT local_record_json FROM execution_local_realizations').fetchone()[0])
        assert record['root']['path'] == str(root.resolve())
        assert record['provider_home']['path'] == str(root.parent.resolve())
        assert record['configuration']['secret_bindings'] == {'OPENAI_API_KEY': 'vault:provider-key'}
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_bindings').fetchone()[0] == 0
    panel.get_by_label('Connection name', exact=True).fill('Local workbench')
    panel.get_by_role('button', name='Review connection', exact=True).click()
    panel.get_by_role('button', name='Approve connection', exact=True).click()
    expect(panel.get_by_role('region', name='Connection status')).to_contain_text('Connection: APPROVED')
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_bindings').fetchone()[0] == 1
        for table in ('execution_operations', 'execution_sessions', 'runtime_execution_grants'):
            assert uow.connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0
    expect(panel.get_by_role('button', name='Reload published inventory', exact=True)).to_be_enabled()
    page.screenshot(path=str(target / f'embedded-preparation-{lost_reply}.png'), full_page=True)


def test_existing_workspace_keeps_identity_and_display_name(local_setup, local_browser):
    from playwright.sync_api import expect
    deps, _, _, _, body, _, root = local_setup
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('INSERT INTO workspaces(workspace_id,display_name,created_at) VALUES (?,?,?)',
                               ('existing-project', 'Existing: project / display name', deps.clock.now_iso()))
        before = uow.connection.execute('SELECT COUNT(*) FROM workspaces').fetchone()[0]
    page, trace = local_browser
    panel = select_local(page, local_setup)
    panel.get_by_label('Runtime workspace', exact=True).select_option('existing-project')
    candidate = panel.get_by_test_id('runtime-candidate-' + body['candidate_ref']).get_by_role('radio')
    expect(candidate).to_be_enabled()
    candidate.check()
    expect(panel.get_by_label('New workspace name', exact=True)).to_have_count(0)
    panel.get_by_label('Workspace directory', exact=True).fill(str(root))
    panel.get_by_role('checkbox', name='I approve these folders', exact=False).check()
    panel.get_by_role('button', name='Approve local preparation', exact=True).click()
    expect(panel.get_by_label('Connection name', exact=True)).to_be_visible()
    request = next(json.loads(data) for _, path, data in trace['requests'] if path.endswith('/realizations'))
    assert request['workspace_id'] == 'existing-project' and request['workspace_label'] == ''
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM workspaces').fetchone()[0] == before
        assert uow.connection.execute("SELECT display_name FROM workspaces WHERE workspace_id='existing-project'").fetchone()[0] == 'Existing: project / display name'


@pytest.mark.parametrize('failure', ['storage', 'plaintext', 'directory', 'authority'])
def test_local_preparation_refusal_has_no_persistent_effect(local_setup, local_browser, failure):
    from playwright.sync_api import expect
    deps, _, _, _, _, _, root = local_setup
    page, trace = local_browser
    panel = select_local(page, local_setup)
    fill_preparation(panel, root)
    if failure == 'storage':
        page.evaluate('() => { Storage.prototype.setItem = function() { throw new Error("Storage unavailable"); }; }')
    elif failure == 'plaintext':
        panel.get_by_label('Protected credential references', exact=True).fill('OPENAI_API_KEY=plaintext')
    elif failure == 'directory':
        panel.get_by_label('Workspace directory', exact=True).fill(str(root / 'missing-directory'))
    else:
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='subject'")
    panel.get_by_role('checkbox', name='I approve these folders', exact=False).check()
    panel.get_by_role('button', name='Approve local preparation', exact=True).click()
    expect(panel.get_by_role('alert')).to_be_visible()
    writes = [row for row in trace['requests'] if row[1].endswith('/realizations')]
    assert len(writes) == (0 if failure in ('storage', 'plaintext') else 1)
    if failure == 'directory':
        expect(panel.get_by_label('Workspace directory', exact=True)).to_be_enabled()
        expect(panel.get_by_role('checkbox', name='I approve these folders', exact=False)).not_to_be_checked()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ('execution_local_realizations', 'execution_realizations', 'execution_operations', 'execution_sessions'):
            assert uow.connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0
