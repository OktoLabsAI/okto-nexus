"""Real Edge UI against production API via TestClient; synthetic host inventory.

No independent-host, cross-OS or provider qualification is claimed. Assets build
outside the package tree so the developer's preexisting static files stay intact.
"""
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

import pytest
from test_binding_operator import onboarding

pytestmark = pytest.mark.skipif(os.environ.get('OKTO_NEXUS_UI_CAMPAIGN') != '1',
                               reason='Isolated browser campaign not enabled')


@pytest.fixture(scope='module')
def assets(tmp_path_factory):
    if os.environ.get('OKTO_NEXUS_UI_INSTALLED') == '1':
        import okto_nexus
        package = Path(okto_nexus.__file__).resolve().parent
        assert 'site-packages' in package.parts
        return package / 'adapters/inbound/http/static'
    target = tmp_path_factory.mktemp('r4-selection-assets')
    subprocess.run(['node', 'node_modules/vite/bin/vite.js', 'build', '--outDir', str(target)],
                   cwd=Path(__file__).resolve().parents[2] / 'frontend', check=True,
                   capture_output=True, timeout=120)
    return target


@pytest.mark.parametrize('onboarding', ['duplicate-installations'], indirect=True)
def test_selection_uses_refs_and_invalidates_on_revocation(onboarding, assets, tmp_path):
    from playwright.sync_api import sync_playwright, expect
    deps, client, headers, scope = onboarding
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET control_state='CONTROL_READY' WHERE executor_id=?", (scope['executor_id'],))
    requests = []
    inventory = client.get(f"/v1/agents/subject/runtime-options?executor_id={scope['executor_id']}", headers=headers['operator']).json()
    copies = [row for row in inventory['options'] if row['candidate_ref']]
    assert len(copies) == 2 and copies[0]['candidate_ref'] != copies[1]['candidate_ref']
    from test_runtime_options import bind
    bind(onboarding)
    chosen = scope['candidate_ref']
    options_reads = 0
    with sync_playwright() as driver:
        browser = driver.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1100})
        context.add_init_script('sessionStorage.setItem("okto_nexus_operator_key", ' + json.dumps(headers['operator']['Authorization'][7:]) + ');')
        context.add_init_script('localStorage.setItem("okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0", "fixture");')

        def route_request(route):
            nonlocal options_reads
            request = route.request
            url = urlsplit(request.url)
            if url.netloc != 'nexus.test':
                route.abort()
                return
            if url.path == '/':
                route.fulfill(path=str(assets / 'index.html'), content_type='text/html')
            elif url.path.startswith('/assets/'):
                route.fulfill(path=str(assets / 'assets' / Path(url.path).name))
            elif url.path == '/api/v1/stream':
                # A buffered TestClient request cannot consume an infinite SSE
                # stream. Selection refresh is polled/focus-driven; SSE is not
                # part of this campaign's acceptance scope.
                route.fulfill(status=200, body=': isolated selection test\n\n',
                              content_type='text/event-stream')
            elif url.path.startswith(('/api/', '/v1/')):
                # All authorization and response generation use the real app.
                requests.append((request.method, url.path, request.headers))
                response = client.request(request.method, url.path + ('?' + url.query if url.query else ''),
                    headers={name: value for name, value in request.headers.items() if name.lower() in ('authorization', 'x-api-key', 'content-type')},
                    content=request.post_data)
                content = response.content
                if url.path.endswith('/runtime-options') and response.status_code == 200:
                    # Perturb presentation order only; IDs, revision and all
                    # authority/technical facts still come from the real API.
                    options_reads += 1
                    body = response.json()
                    if options_reads % 2 == 0:
                        body['options'].reverse()
                    content = json.dumps(body).encode()
                route.fulfill(status=response.status_code, body=content,
                              content_type=response.headers.get('content-type', 'application/json'))
            else:
                route.fulfill(status=404)

        context.route('**/*', route_request)
        page = context.new_page()
        page.set_default_timeout(15000)
        try:
            page.goto('http://nexus.test/')
            page.get_by_test_id('onboarding-close').click()
            from test_embedded_preparation_dashboard import open_message_runtime
            open_message_runtime(page, client, headers, scope['workspace_id'])
            panel = page.get_by_test_id('runtime-selection')
            host = panel.get_by_label('Execution host', exact=True)
            expect(host).to_be_enabled()
            expect(host).to_have_value('')
            host.select_option(scope['executor_id'])
            expect(panel.get_by_label('Runtime workspace', exact=True)).to_have_count(0)
            choice = panel.get_by_test_id('runtime-candidate-' + chosen).get_by_role('radio')
            expect(choice).to_be_enabled()
            choice.check()
            expect(panel.get_by_role('radio')).to_have_count(1)
            expect(panel.get_by_role('button', name='Review connection', exact=True)).to_have_count(0)
            expect(panel.get_by_role('button', name='Request host inventory refresh', exact=True)).to_have_count(0)
            expect(panel.get_by_test_id('runtime-selection-summary')).to_be_visible()
            panel.get_by_role('button', name='Reload published inventory').click()
            expect(panel.get_by_role('button', name='Reload published inventory')).to_be_enabled()
            expect(choice).to_be_checked()
            receipts = dict(client.app.state.inventory_fresh_publications)
            client.app.state.inventory_fresh_publications.clear()
            panel.get_by_role('button', name='Reload published inventory').click()
            expect(panel.get_by_test_id('runtime-selection-summary')).to_be_visible()
            expect(choice).to_be_enabled()
            expect(choice).to_be_checked()
            expect(panel.get_by_text('Published inventory is not current.', exact=False)).to_be_visible()
            expect(panel.get_by_test_id('runtime-selection-summary')).to_contain_text('Preparation: unavailable; binding approval: unavailable; start: unavailable.')
            client.app.state.inventory_fresh_publications.update(receipts)
            panel.get_by_role('button', name='Reload published inventory').click()
            expect(choice).to_be_enabled()
            expect(choice).to_be_checked()
            choice.check()
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute('UPDATE execution_executors SET revoked_at=? WHERE executor_id=?',
                                       (deps.clock.now_iso(), scope['executor_id']))
            panel.get_by_role('button', name='Reload published inventory').click()
            expect(host).to_have_value('')
            expect(panel.get_by_test_id('runtime-selection-summary')).to_have_count(0)
            expect(panel.get_by_text('The selected host is no longer available. Select a host again.')).to_be_visible()
            assert all(method == 'GET' for method, path, _ in requests if path.startswith('/v1/'))
            assert all('authorization' in values and 'x-api-key' not in values
                       for _, path, values in requests if path.startswith('/v1/'))
            page.screenshot(path=str(tmp_path / 'runtime-selection-revoked.png'), full_page=True)
        finally:
            context.close()
            browser.close()
