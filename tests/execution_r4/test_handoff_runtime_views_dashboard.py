"""Rendered read models use real domain/HTTP state and synthetic native peers."""
import os
from pathlib import Path

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime
from test_handoff_runtime_attempts import prepared
from test_canonical_result_publication import current_turn, emit
from test_embedded_preparation_dashboard import local_browser
from test_runtime_selection_dashboard import assets
from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from test_capacity_observation_views import assessed

pytestmark = pytest.mark.skipif(os.environ.get('OKTO_NEXUS_UI_CAMPAIGN') != '1',
                               reason='Browser campaign disabled')


def test_broadcast_progress_and_bounded_attempt_panel(runtime, local_browser):
    from playwright.sync_api import expect
    setup, _, native = runtime
    service, port, attempt, hid, _ = prepared(runtime)
    page, _ = local_browser
    page.get_by_role('button', name='Handoffs', exact=True).click()
    card = page.get_by_test_id('handoff-card-' + hid)
    expect(card.get_by_text('Available for an explicit claim', exact=True)).to_be_visible()
    setup[2].portal.call(service.reserve, attempt.request.attempt_id)
    claimed = service.claim(attempt.request.attempt_id)
    setup[2].portal.call(build_capacity_admission(setup[0], capacity=port).consume, claimed.operation_id)
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    emit(setup, native, turn, 'Native output is not a business decision.')
    page.get_by_role('button', name='Agents', exact=True).click()
    page.get_by_role('button', name='Handoffs', exact=True).click()
    expect(card.get_by_text('Waiting for handoff decision', exact=False)).to_be_visible()
    card.click()
    detail = page.get_by_test_id('handoff-detail-' + hid)
    expect(detail.get_by_text('An authenticated handoff decision is still required.', exact=False)).to_be_visible()
    expect(detail.get_by_text('Source-session isolation uses the per-sender fallback.', exact=False)).to_be_visible()
    target = Path('output/playwright/handoff-runtime-views')
    target.mkdir(parents=True, exist_ok=True)
    detail.screenshot(path=str(target / 'creator-pending-decision.png'))
    page.get_by_test_id('close-handoff-detail').click()
    page.get_by_role('button', name='Agents', exact=True).click()
    page.get_by_role('button', name='Runtime administration for subject', exact=True).click()
    dialog = page.get_by_role('dialog', name='Runtime administration · subject', exact=True)
    attempts = dialog.locator('details[aria-label="Broadcast handoff attempts"]')
    expect(attempts).to_have_count(1)
    assert not attempts.evaluate('(element) => element.open')
    attempts.locator('summary').click()
    expect(attempts.get_by_text('Current managed claim', exact=False)).to_be_visible()
    expect(attempts.get_by_text('Waiting for handoff decision', exact=False)).to_be_visible()
    dialog.screenshot(path=str(target / 'agent-attempt-history.png'))
    for width in (900, 1440):
        page.set_viewport_size({'width': width, 'height': 1000})
        assert dialog.evaluate('(element) => element.scrollWidth <= element.clientWidth + 1')


def test_contextual_capacity_expires_in_browser_without_a_new_response(runtime, local_browser):
    from playwright.sync_api import expect
    setup = runtime[0]
    service, _, attempt, _ = assessed(runtime)
    page, _ = local_browser
    page.get_by_role('button', name='Agents', exact=True).click()
    page.get_by_role('button', name='Runtime administration for subject', exact=True).click()
    dialog = page.get_by_role('dialog', name='Runtime administration · subject', exact=True)
    panel = dialog.locator('details[aria-label="Contextual capacity observations"]')
    expect(panel).to_have_count(1)
    assert not panel.evaluate('(element) => element.open')
    panel.locator('summary').click()
    setup[2].portal.call(service.reserve, attempt.request.attempt_id)
    page.get_by_role('button', name='Refresh runtime instances', exact=True).click()
    expect(panel.get_by_text('Capacity reserved', exact=True)).to_be_visible()
    target = Path('output/playwright/handoff-runtime-views')
    target.mkdir(parents=True, exist_ok=True)
    dialog.screenshot(path=str(target / 'contextual-capacity-reserved.png'))
    for width in (900, 1440):
        page.set_viewport_size({'width': width, 'height': 1000})
        assert dialog.evaluate('(element) => element.scrollWidth <= element.clientWidth + 1')
    # Drop subsequent reads; the browser itself must expire the old observation.
    # A pending fetch is stronger than an immediate error that would clear it.
    pending = []
    page.route('**/api/v1/agents/subject/runtime-administration**', lambda route: pending.append(route))
    expect(panel.get_by_text('Availability unknown', exact=True)).to_be_visible(timeout=7000)
    expect(panel.get_by_text('stale observation', exact=False)).to_be_visible()
    dialog.screenshot(path=str(target / 'contextual-capacity-expired.png'))
    for route in pending:
        route.abort()
