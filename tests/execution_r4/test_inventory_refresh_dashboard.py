"""Real browser/API refresh UX; synthetic host inventory, no independent host."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from test_binding_operator import onboarding
from test_runtime_selection_dashboard import assets

pytestmark = pytest.mark.skipif(os.environ.get('OKTO_NEXUS_UI_CAMPAIGN') != '1',
                               reason='Isolated browser campaign not enabled')


def test_local_refresh_survives_lost_reply_selection_and_reload(onboarding, assets, tmp_path):
    from playwright.sync_api import sync_playwright, expect
    deps, client, headers, scope = onboarding
    remote = scope['executor_id']
    local = client.app.state.embedded_inventory_owner
    seen = []
    lose_reply = True
    with sync_playwright() as driver:
        browser = driver.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1100})
        context.add_init_script('sessionStorage.setItem("okto_nexus_operator_key", ' + json.dumps(headers['operator']['Authorization'][7:]) + ');')
        context.add_init_script('localStorage.setItem("okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0", "fixture");')
        def routed(route):
            nonlocal lose_reply
            request = route.request
            url = urlsplit(request.url)
            if url.netloc != 'nexus.test':
                route.abort()
            elif url.path == '/':
                route.fulfill(path=str(assets / 'index.html'), content_type='text/html')
            elif url.path.startswith('/assets/'):
                route.fulfill(path=str(assets / 'assets' / Path(url.path).name))
            elif url.path.startswith('/logos/'):
                route.fulfill(path=str(assets / 'logos' / Path(url.path).name))
            elif url.path == '/api/v1/stream':
                route.fulfill(status=200, body=': isolated refresh test\n\n', content_type='text/event-stream')
            elif url.path.startswith(('/api/', '/v1/')):
                response = client.request(request.method, url.path + ('?' + url.query if url.query else ''),
                    headers={k:v for k,v in request.headers.items() if k.lower() in ('authorization','x-api-key','content-type')},
                    content=request.post_data)
                if url.path.endswith('/inventory:refresh'):
                    seen.append((url.path, json.loads(request.post_data)['client_intent_id'], response.status_code))
                    if lose_reply:
                        lose_reply = False
                        assert response.status_code == 202
                        route.abort('failed')
                        return
                route.fulfill(status=response.status_code, body=response.content,
                              content_type=response.headers.get('content-type','application/json'))
            else:
                route.fulfill(status=404)
        context.route('**/*', routed)
        page = context.new_page()
        page.set_default_timeout(15000)
        def open_panel():
            page.get_by_role('button', name='Agents', exact=True).click()
            page.get_by_test_id('connections-subject').click()
            from test_embedded_preparation_dashboard import configure_local_integration
            configure_local_integration(page)
            return page.get_by_test_id('runtime-selection')
        try:
            page.goto('http://nexus.test/')
            page.get_by_test_id('onboarding-close').click()
            panel = open_panel()
            host = panel.get_by_label('Execution host', exact=True)
            expect(host).to_be_enabled()
            expect(host.locator(f'option[value="{remote}"]')).to_have_count(0)
            host.select_option(local.key.executor_id)
            refresh = panel.get_by_test_id('inventory-refresh')
            refresh.get_by_role('button', name='Request host inventory refresh').click()
            expect(refresh.get_by_role('alert')).to_contain_text('Retry to check the same request')
            refresh.get_by_role('button', name='Retry inventory refresh').click()
            assert len(seen) >= 2 and seen[0][1] == seen[1][1]
            local_intent = seen[0][1]
            expect(host).to_be_enabled()
            host.select_option('')
            host.select_option(local.key.executor_id)
            client.portal.call(local.refresh)
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT completed_sequence FROM execution_inventory_refresh '
                    'WHERE executor_id=?', (local.key.executor_id,)).fetchone()[0] is not None
            # The production poll interval is five seconds, equal to Playwright's
            # default assertion timeout. Observe up to three polling intervals.
            expect(refresh.get_by_text('The host published a new inventory. Review the current choices.')).to_be_visible(timeout=15000)
            page.reload()
            panel = open_panel()
            host = panel.get_by_label('Execution host', exact=True)
            expect(host).to_be_enabled()
            host.select_option(local.key.executor_id)
            expect(panel.get_by_test_id('inventory-refresh').get_by_role('button', name='Request host inventory refresh', exact=True)).to_be_enabled()
            # A confirmed completion clears the pending request, so reloading
            # offers a new refresh without automatically issuing one.
            assert {intent for path, intent, _ in seen} == {local_intent}
            assert page.get_by_role('img', name='Okto Nexus', exact=True).evaluate('(image) => image.complete && image.naturalWidth > 0')
            page.screenshot(path=str(tmp_path / 'refresh-offline-restored.png'), full_page=True)
            with deps.connection_factory.unit_of_work(write=False) as uow:
                rows = uow.connection.execute('SELECT executor_id,completed_sequence FROM execution_inventory_refresh').fetchall()
                assert len(rows) == 1
                assert next(row for row in rows if row['executor_id'] == local.key.executor_id)['completed_sequence'] is not None
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
        finally:
            context.close()
            browser.close()
