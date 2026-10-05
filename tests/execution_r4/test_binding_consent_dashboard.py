"""Installed-browser consent, same-request recovery and reuse; synthetic host.

Production routes run through TestClient. SSE is outside this test's scope.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from test_local_realization import local_setup, publish
from test_runtime_selection_dashboard import assets

pytestmark = pytest.mark.skipif(os.environ.get('OKTO_NEXUS_UI_CAMPAIGN') != '1',
                               reason='Isolated browser campaign not enabled')


@pytest.fixture
def onboarding(local_setup):
    deps, app, client, headers, body, *_ = local_setup
    response = publish(local_setup)
    assert response.status_code == 201, response.text
    realization = response.json()
    yield deps, client, headers, dict(executor_id=app.state.embedded_inventory_owner.key.executor_id,
        workspace_id=realization['workspace_id'], candidate_ref=body['candidate_ref'])


@pytest.fixture
def consent_browser(onboarding, assets):
    from playwright.sync_api import sync_playwright
    deps, client, headers, scope = onboarding
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET control_state='CONTROL_READY' WHERE executor_id=?", (scope['executor_id'],))
    trace = {'requests': [], 'drop_apply_response': False}
    with sync_playwright() as driver:
        browser = driver.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1100})
        context.add_init_script('sessionStorage.setItem("okto_nexus_operator_key", ' + json.dumps(headers['operator']['Authorization'][7:]) + ');')
        context.add_init_script('localStorage.setItem("okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0", "fixture");')

        def route_request(route):
            request = route.request
            url = urlsplit(request.url)
            if url.netloc != 'nexus.test':
                route.abort()
                return
            if url.path == '/api/v1/stream':
                route.fulfill(status=200, body=': isolated consent test\n\n', content_type='text/event-stream')
                return
            if url.path.startswith(('/api/', '/v1/')):
                trace['requests'].append((request.method, url.path, request.post_data))
                response = client.request(request.method, url.path + ('?' + url.query if url.query else ''),
                    headers={name: value for name, value in request.headers.items() if name.lower() in ('authorization', 'x-api-key', 'content-type')},
                    content=request.post_data)
                if url.path.endswith('/bindings:apply') and trace['drop_apply_response']:
                    assert response.status_code == 200, response.text
                    trace['drop_apply_response'] = False
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
            page.get_by_role('button', name='Agents', exact=True).click()
            page.get_by_test_id('connections-subject').click()
            from test_embedded_preparation_dashboard import configure_local_integration
            configure_local_integration(page)
            yield page, trace
        finally:
            context.close()
            browser.close()


def select(page, scope):
    from playwright.sync_api import expect
    panel = page.get_by_test_id('runtime-selection')
    expect(panel.get_by_label('Execution host', exact=True)).to_have_count(0)
    workspace = panel.get_by_label('Runtime workspace', exact=True)
    expect(workspace).to_be_enabled()
    workspace.select_option(scope['workspace_id'])
    candidate = panel.get_by_test_id('runtime-candidate-' + scope['candidate_ref']).get_by_role('radio')
    expect(candidate).to_be_enabled()
    candidate.check()
    return panel


@pytest.mark.parametrize('lost_response', [False, True])
def test_consent_applies_once_and_second_visit_reuses_binding(onboarding, consent_browser, tmp_path, lost_response):
    from playwright.sync_api import expect
    deps, _, _, scope = onboarding
    page, trace = consent_browser
    panel = select(page, scope)
    panel.get_by_label('Connection name', exact=True).fill('Workbench')
    panel.get_by_role('button', name='Review connection', exact=True).click()
    approve = panel.get_by_role('button', name='Approve connection', exact=True)
    expect(approve).to_be_enabled()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_bindings').fetchone()[0] == 0
    trace['drop_apply_response'] = lost_response
    approve.click()
    if lost_response:
        retry = panel.get_by_role('button', name='Retry the same approval request', exact=True)
        expect(retry).to_be_enabled()
        expect(panel.get_by_text('The approval result is not confirmed.', exact=False)).to_be_visible()
        assert len([row for row in trace['requests'] if row[1].endswith('/bindings:apply')]) == 1
        retry.click()
    current = panel.get_by_role('region', name='Connection status')
    expect(current).to_contain_text('Connection: APPROVED')
    bodies = [json.loads(body) for _, path, body in trace['requests'] if path.endswith('/bindings:apply')]
    assert len(bodies) == (2 if lost_response else 1)
    assert all(body == bodies[0] for body in bodies)
    stored = page.evaluate('Object.entries(sessionStorage).filter(([key]) => key.startsWith("okto-nexus:r4-binding:")).map(([, value]) => JSON.parse(value))')
    assert bodies[0] in stored
    page.get_by_test_id('agent-connections-subject').get_by_role('button', name='Close', exact=True).click()
    page.get_by_test_id('connections-subject').click()
    panel = select(page, scope)
    expect(panel.get_by_role('region', name='Connection status')).to_contain_text('Connection: APPROVED')
    expect(panel.get_by_role('button', name='Review connection', exact=True)).to_have_count(0)
    assert len([row for row in trace['requests'] if row[1].endswith('/bindings:apply')]) == len(bodies)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_bindings').fetchone()[0] == 1
        for table in ('execution_operations', 'execution_sessions', 'runtime_execution_grants'):
            assert uow.connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0
    page.screenshot(path=str(tmp_path / 'binding-reused.png'), full_page=True)


def test_stale_inventory_after_review_refuses_approval(onboarding, consent_browser):
    from playwright.sync_api import expect
    deps, client, _, scope = onboarding
    page, trace = consent_browser
    panel = select(page, scope)
    panel.get_by_label('Connection name', exact=True).fill('Workbench')
    panel.get_by_role('button', name='Review connection', exact=True).click()
    approve = panel.get_by_role('button', name='Approve connection', exact=True)
    expect(approve).to_be_enabled()
    client.app.state.inventory_fresh_publications.clear()
    approve.click()
    expect(panel.get_by_role('alert')).to_be_visible()
    expect(panel.get_by_role('region', name='Connection status')).to_have_count(0)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_bindings').fetchone()[0] == 0
    assert len([row for row in trace['requests'] if row[1].endswith('/bindings:apply')]) == 1


def test_storage_failure_prevents_sending_unrecorded_intent(onboarding, consent_browser):
    from playwright.sync_api import expect
    _, _, _, scope = onboarding
    page, trace = consent_browser
    panel = select(page, scope)
    panel.get_by_label('Connection name', exact=True).fill('Workbench')
    page.evaluate('() => { Storage.prototype.setItem = function() { throw new Error("Storage unavailable"); }; }')
    panel.get_by_role('button', name='Review connection', exact=True).click()
    expect(panel.get_by_role('alert')).to_contain_text('Storage unavailable')
    assert not [row for row in trace['requests'] if row[1].endswith('/bindings:prepare')]
