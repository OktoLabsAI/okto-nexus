"""R4 native decisions through installed UI/API and real canonical CAS/outbox."""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from test_native_decisions import decision_state, snapshot
from test_open_bootstrap import opening
from test_runtime_selection_dashboard import assets

pytestmark = pytest.mark.skipif(os.environ.get('OKTO_NEXUS_UI_CAMPAIGN') != '1',
                               reason='Isolated browser campaign not enabled')


@pytest.fixture
def native_browser(decision_state, assets):
    from playwright.sync_api import sync_playwright
    _, app, body = decision_state
    client = TestClient(app)
    trace = {'requests': [], 'drop': False}
    with sync_playwright() as driver:
        browser = driver.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1100})
        context.add_init_script('sessionStorage.setItem("okto_nexus_operator_key", ' + json.dumps(app.state.test_agent_keys['operator']) + ');')
        context.add_init_script('localStorage.setItem("okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0", "fixture");')
        def route_request(route):
            request = route.request
            url = urlsplit(request.url)
            if url.netloc != 'nexus.test':
                route.abort()
            elif url.path == '/api/v1/stream':
                route.fulfill(status=200, body=': isolated native UI\n\n', content_type='text/event-stream')
            elif url.path.startswith(('/api/', '/v1/')):
                trace['requests'].append((request.method, url.path, request.post_data))
                response = client.request(request.method, url.path + ('?' + url.query if url.query else ''),
                    headers={key: value for key, value in request.headers.items()
                             if key.lower() in ('authorization', 'x-api-key', 'content-type')}, content=request.post_data)
                if url.path == '/v1/runtime/approval-decisions' and request.method == 'POST' and trace['drop']:
                    assert response.status_code == 202, response.text
                    trace['drop'] = False
                    route.abort('failed')
                else:
                    route.fulfill(status=response.status_code, body=response.content,
                                  content_type=response.headers.get('content-type', 'application/json'))
            else:
                target = (assets / ('index.html' if url.path == '/' else url.path.lstrip('/'))).resolve()
                if target.is_relative_to(assets.resolve()) and target.is_file():
                    route.fulfill(path=str(target))
                else:
                    route.fulfill(status=404)
        context.route('**/*', route_request)
        page = context.new_page()
        page.set_default_timeout(10000)
        try:
            page.goto('http://nexus.test/')
            page.get_by_test_id('onboarding-close').click()
            page.get_by_role('button', name=re.compile('^Approvals')).click()
            page.get_by_test_id('approve-' + body['approval_key']['canonical_request_id']).click()
            yield page, trace
        finally:
            context.close()
            browser.close()
            client.close()


@pytest.mark.parametrize('decision_state', [None, 'input', 'form'], indirect=True)
@pytest.mark.parametrize('lost_reply', [False, True])
def test_native_ui_confirm_and_recover_without_persisting_answers(decision_state, native_browser, lost_reply, tmp_path):
    from playwright.sync_api import expect
    page, trace = native_browser
    deps, _, body = decision_state
    panel = page.get_by_role('region', name='Native runtime decision')
    is_input = body['approval_key']['kind'] == 'native_input'
    is_form = 'content' in body.get('response', {})
    if is_form:
        expect(page.get_by_label('count *', exact=True)).to_have_value('')
        expect(page.get_by_label('enabled *', exact=True)).to_have_value('')
        page.get_by_label('count *', exact=True).fill('3')
        page.get_by_label('enabled *', exact=True).select_option('false')
        page.get_by_label('Send empty text for note', exact=True).check()
    elif is_input:
        page.get_by_label('Choose the next step', exact=True).select_option('custom')
        page.get_by_label('Another answer', exact=True).fill('private-browser-response-marker')
    trace['drop'] = lost_reply
    button = panel.get_by_role('button', name='Send answer' if is_input else 'Approve request', exact=True)
    expect(button).to_be_enabled()
    button.evaluate('(button) => { button.click(); button.click(); }')
    if lost_reply:
        expect(panel.get_by_role('alert')).to_be_visible()
        page.reload()
        page.get_by_role('button', name=re.compile('^Approvals')).click()
        page.get_by_test_id('detail-' + body['approval_key']['canonical_request_id']).click()
    expect(page.get_by_test_id('canonical-native-status')).to_contain_text('Decision: CONFIRMED')
    expect(page.get_by_test_id('canonical-native-status')).to_contain_text('Native delivery: DISPATCH_PENDING')
    posts = [json.loads(data) for method, path, data in trace['requests']
             if method == 'POST' and path == '/v1/runtime/approval-decisions']
    assert len(posts) == 1
    assert posts[0]['approval_key'] == body['approval_key']
    assert posts[0]['request_hash'] == body['request_hash']
    assert posts[0]['cas_token'] == body['cas_token']
    assert posts[0]['expected_revision'] == body['expected_revision']
    if is_form:
        assert posts[0]['response'] == body['response']
    elif is_input:
        assert posts[0]['response'] == {'answers': {'question': {'answers': ['private-browser-response-marker']}}}
    storage = page.evaluate('JSON.stringify([Object.entries(sessionStorage), Object.entries(localStorage)])')
    assert 'private-browser-response-marker' not in storage
    assert 'private-marker' not in page.content()
    stored = snapshot(decision_state)
    assert len(stored['execution_decisions']) == 1
    assert sum(row['action'] in ('approval.decide', 'input.provide') for row in stored['execution_operations']) == 1
    assert 'private-browser-response-marker' not in json.dumps(stored)
    target = Path(os.environ.get('OKTO_NEXUS_UI_SCREENSHOT_DIR', str(tmp_path)))
    target.mkdir(parents=True, exist_ok=True)
    panel.screenshot(path=str(target / f'native-decision-{is_input}-{is_form}-{lost_reply}.png'))


def test_native_ui_denial_is_canonical_and_cannot_use_legacy_decision(decision_state, native_browser):
    from playwright.sync_api import expect
    page, trace = native_browser
    page.get_by_role('button', name='Deny runtime request', exact=True).click()
    expect(page.get_by_test_id('canonical-native-status')).to_contain_text('Decision: DENIED')
    posts = [json.loads(data) for method, path, data in trace['requests']
             if method == 'POST' and path == '/v1/runtime/approval-decisions']
    assert len(posts) == 1 and posts[0]['decision'] == 'deny' and 'response' not in posts[0]
    assert not [path for method, path, _ in trace['requests'] if method == 'POST' and path.startswith('/api/')]


def test_native_ui_expiry_disables_form_while_open(decision_state, native_browser):
    from playwright.sync_api import expect
    page, trace = native_browser
    # Exercise the display clock only; authoritative expiry refusal is covered
    # by the API matrix and is never delegated to this browser check.
    page.clock.install()
    page.clock.fast_forward(121000)
    expect(page.get_by_role('button', name='Approve request', exact=True)).to_have_count(0)
    expect(page.get_by_role('button', name='Deny runtime request', exact=True)).to_be_disabled()
    assert not [path for method, path, _ in trace['requests'] if method == 'POST']


def test_native_ui_storage_failure_prevents_decision(decision_state, native_browser):
    from playwright.sync_api import expect
    page, trace = native_browser
    page.evaluate("""() => {
      const original = Storage.prototype.setItem;
      Storage.prototype.setItem = function(key, value) {
        if (key.startsWith('okto-nexus:r4-native:')) throw new Error('Fixture storage unavailable');
        return original.call(this, key, value);
      };
    }""")
    page.get_by_role('button', name='Approve request', exact=True).click()
    expect(page.get_by_role('region', name='Native runtime decision').get_by_role('alert')).to_contain_text('storage unavailable')
    assert not [path for method, path, _ in trace['requests'] if method == 'POST']
    assert snapshot(decision_state)['execution_decisions'] == []


def test_native_ui_revoked_grant_refuses_confirmation(decision_state, native_browser):
    from playwright.sync_api import expect
    page, trace = native_browser
    with decision_state[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at='2026-01-01T00:00:00Z'")
    page.get_by_role('button', name='Approve request', exact=True).click()
    expect(page.get_by_role('region', name='Native runtime decision').get_by_role('alert')).to_be_visible()
    assert snapshot(decision_state)['execution_decisions'] == []
    assert len([path for method, path, _ in trace['requests'] if method == 'POST']) == 1
