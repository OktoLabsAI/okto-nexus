"""Terminal scrollback in Edge, real event API/storage, synthetic native peer."""
import json
import os
import time
from pathlib import Path

import pytest
from nexus_connector_core import RuntimeEvent
from test_runtime_operations_dashboard import ready_runtime
from test_local_realization import local_setup
from test_embedded_preparation_dashboard import local_browser
from test_runtime_selection_dashboard import assets

pytestmark = pytest.mark.skipif(os.environ.get('OKTO_NEXUS_UI_CAMPAIGN') != '1',
                               reason='Isolated browser campaign not enabled')


def emit(setup, native, session_id, count, expected, *, payload=None, native_type='fixture.progress'):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams WHERE session_id=?', (session_id,)).fetchone())
    for index in range(expected-count, expected):
        setup[2].portal.call(native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
            session_id, stream['stream_epoch'], 0, 'tool_activity', native_type,
            payload if payload is not None else {'step': index+1, 'message': f'Recorded activity {index+1}'}))
    deadline = time.monotonic()+30
    while True:
        response = setup[2].get(f'/v1/runtime/sessions/{session_id}/events', headers=setup[3]['operator'])
        assert response.status_code == 200, response.text
        if response.json()['committed_contiguous'] == expected:
            return response.json()
        assert time.monotonic() < deadline
        time.sleep(.02)


def test_terminal_scrollback_live_resume_history_and_maximize(ready_runtime, request, tmp_path):
    from playwright.sync_api import expect
    from test_embedded_dispatch import admit, wait_receipt
    setup, binding, native = ready_runtime
    opened = admit(setup, binding, 'terminal-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    sid = opened['session_id']
    emit(setup, native, sid, 603, 603)
    page, trace = request.getfixturevalue('local_browser')
    page_errors = []
    page.on('pageerror', lambda error: page_errors.append(str(error)))
    page.get_by_role('button', name='Agents', exact=True).click()
    page.get_by_role('button', name='Runtime administration for subject', exact=True).click()
    page.get_by_role('button', name=f'Inspect session {sid}', exact=True).click()
    tail = page.get_by_role('region', name='Session live tail', exact=True)
    screen = page.get_by_role('list', name='Live runtime events', exact=True)
    rows = screen.locator('[data-action-id]')
    expect(rows).to_have_count(500)
    expect(tail).to_contain_text('Showing 104–603 of 603')
    assert screen.evaluate('e => e.scrollHeight-e.scrollTop-e.clientHeight') < 2
    # Wheel scroll triggers prepend, without a pagination action or loss of tail.
    screen.hover()
    page.mouse.wheel(0, -100000)
    expect(rows).to_have_count(600)
    expect(tail.get_by_label('Auto-scroll')).not_to_be_checked()
    expect(rows.first).to_contain_text('Recorded activity 4')
    assert screen.evaluate('e => e.scrollTop') > 1000
    before = screen.evaluate('e => e.scrollTop')
    emit(setup, native, sid, 2, 605)
    expect(rows).to_have_count(602)
    assert abs(screen.evaluate('e => e.scrollTop')-before) < 2
    # The last short previous page overlaps existing rows; no duplicates.
    screen.hover()
    page.mouse.wheel(0, -100000)
    expect(rows).to_have_count(605)
    expect(rows.first).to_contain_text('Recorded activity 1')
    expect(screen.get_by_role('button', name='Load previous events')).to_have_count(0)
    assert len(set(rows.evaluate_all('rows => rows.map(e => e.dataset.actionId)'))) == 605
    tail.get_by_role('button', name='Pause tail', exact=True).click()
    emit(setup, native, sid, 1, 606)
    expect(rows).to_have_count(605)
    tail.get_by_role('button', name='Resume tail', exact=True).click()
    expect(rows).to_have_count(606)
    tail.get_by_role('button', name='Latest events', exact=True).click()
    expect(tail.get_by_label('Auto-scroll')).to_be_checked()
    assert screen.evaluate('e => e.scrollHeight-e.scrollTop-e.clientHeight') < 2
    tail.get_by_role('button', name='Maximize terminal', exact=True).click()
    maximized = page.get_by_role('dialog', name='Live runtime events · maximized', exact=True)
    expect(maximized).to_be_visible()
    expect(maximized.locator('[data-action-id]')).to_have_count(606)
    maximized.get_by_role('button', name='Increase terminal font size').click()
    expect(maximized.get_by_role('button', name='Reset terminal font size')).to_contain_text('13px')
    screenshot_root = Path(os.environ.get('OKTO_NEXUS_UI_SCREENSHOT_DIR', str(tmp_path)))
    screenshot_root.mkdir(parents=True, exist_ok=True)
    maximized.screenshot(path=str(screenshot_root/'terminal-scrollback.png'))
    maximized.get_by_role('button', name='Restore terminal').click()
    expect(rows).to_have_count(606)
    baseline = len([r for r in trace['requests'] if r[0] == 'POST'])
    page.get_by_role('button', name='History', exact=True).click()
    history = page.get_by_role('region', name='Runtime session history', exact=True)
    recorded = history.get_by_role('list', name='Recorded runtime events', exact=True)
    expect(recorded.locator('[data-action-id]')).to_have_count(500)
    expect(history.get_by_role('button', name='Next events', exact=True)).to_have_count(0)
    recorded.hover()
    page.mouse.wheel(0, -100000)
    expect(recorded.locator('[data-action-id]')).to_have_count(600)
    # The actual Nexus delivery wrapper is presentation, not raw protocol JSON.
    body = 'Review these changes.\n' + 'Complete input context.\n'*1800 + 'END OF INPUT'
    envelope = dict(operation_id='fixture-op', workspace_id=binding['workspace_id'],
        sender_agent_id='operator', recipient_agent_id='subject', intent='conversation',
        subject='Readable request', content=[dict(type='text', text=body)],
        runtime_context=dict(instructions='Use available Nexus tools.'))
    prompt = 'NEXUS DELIVERY: respond to the sender request.\n' + json.dumps(envelope)
    emit(setup, native, sid, 1, 607, native_type='item/completed',
        payload=dict(item=dict(id='fixture-input', type='userMessage', content=[dict(type='text', text=prompt)])))
    history.get_by_role('button', name='Refresh history', exact=True).click()
    expect(recorded.locator('[data-action-id]')).to_have_count(601)
    message = recorded.locator('.runtime-terminal-user')
    expect(message).to_contain_text('Incoming message')
    expect(message).to_contain_text('Readable request')
    expect(message).to_contain_text('END OF INPUT')
    assert 'NEXUS DELIVERY:' not in message.inner_text()
    message.get_by_text('Delivery context', exact=True).click()
    expect(message).to_contain_text('Use available Nexus tools.')
    # A response for another scope is rejected without clearing loaded history.
    sample = setup[2].get(f'/v1/runtime/sessions/{sid}/events', headers=setup[3]['operator']).json()
    altered = {**sample, 'scope': {**sample['scope'], 'executor_id': 'foreign'}}
    intercepted = []
    def corrupt_scope(route):
        intercepted.append(route.request.url)
        route.fulfill(json=altered)
    page.route('**/api/v1/runtime-management/runtime/sessions/*/events?*', corrupt_scope)
    history.get_by_role('button', name='Refresh history', exact=True).click()
    try:
        expect(history.get_by_role('alert')).to_contain_text('does not match')
    except AssertionError:
        print('Intercepted reads:', intercepted)
        print('History after rejection:', history.inner_text()[:1500])
        print('Browser errors:', page_errors)
        raise
    expect(recorded.locator('[data-action-id]')).to_have_count(601)
    assert len([r for r in trace['requests'] if r[0] == 'POST']) == baseline
    assert native.opens == 1 and not page_errors
