"""Browser actions against the real API/dispatcher and synthetic native peer."""
from dataclasses import replace
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_local_realization import local_setup
from test_embedded_preparation_dashboard import local_browser, select_local
from test_runtime_selection_dashboard import assets

pytestmark = pytest.mark.skipif(os.environ.get('OKTO_NEXUS_UI_CAMPAIGN') != '1',
                               reason='Isolated browser campaign not enabled')


@pytest.fixture
def ready_runtime(local_setup, monkeypatch):
    import nexus_connector_core.availability as availability
    from okto_nexus.bootstrap import embedded_inventory
    from okto_nexus.application import execution_local_observations
    from test_embedded_dispatch import connect_local
    setup = list(local_setup)
    owner = setup[1].state.embedded_inventory_owner
    source = replace(setup[5], architecture='x86_64')
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
                        lambda **_: SimpleNamespace(candidates=(source,)))
    # Native qualification is the explicit synthetic boundary of this UI test.
    # Production selection, consent, grants, admission and dispatch remain real.
    monkeypatch.setattr(availability, 'qualified_build', lambda *args, **kwargs: True)
    setup[2].portal.call(owner.refresh)
    before = setup[2].get(f'/v1/runtime/executors/{owner.key.executor_id}/inventory',
                         headers=setup[3]['operator']).json()['snapshot']
    setup[4].update(inventory_revision=before['inventory_revision'], candidate_ref=before['evidence'][0]['candidate_ref'])
    async def probe(selected):
        return replace(selected, version='0.159.0')
    monkeypatch.setattr(execution_local_observations, 'probe_version', probe)
    checked = setup[2].post(f'/v1/runtime/executors/{owner.key.executor_id}/installations:check',
        headers=setup[3]['operator'], json={key: setup[4][key] for key in
        ('agent_id', 'adapter_id', 'candidate_ref', 'inventory_revision', 'approved')})
    assert checked.status_code == 200, checked.text
    snapshot = setup[2].get(f'/v1/runtime/executors/{owner.key.executor_id}/inventory',
                           headers=setup[3]['operator']).json()['snapshot']
    setup[4].update(inventory_revision=snapshot['inventory_revision'],
                    candidate_ref=snapshot['evidence'][0]['candidate_ref'])
    setup[5] = owner.candidates[0]
    connected = connect_local(tuple(setup))
    binding = connected[1]
    options = setup[2].get('/v1/agents/subject/runtime-options', params={
        'executor_id': binding['executor_id'], 'workspace_id': binding['workspace_id']},
        headers=setup[3]['operator']).json()
    choice = next(row for row in options['options'] if row['candidate_ref'] == setup[4]['candidate_ref'])
    assert choice['can_start'], choice
    return connected


def panel_for(page, setup, binding):
    from playwright.sync_api import expect
    panel = select_local(page, setup)
    panel.get_by_label('Runtime workspace', exact=True).select_option(binding['workspace_id'])
    candidate = panel.get_by_test_id('runtime-candidate-' + setup[4]['candidate_ref']).get_by_role('radio')
    expect(candidate).to_be_enabled()
    candidate.check()
    return panel.get_by_role('region', name='Runtime operations', exact=True)


def submit(panel, stage='SUBMITTED'):
    from playwright.sync_api import expect
    panel.get_by_role('button', name='Review runtime action', exact=True).click()
    panel.get_by_role('button', name='Submit reviewed action', exact=True).click()
    expect(panel.get_by_test_id('runtime-operation-status')).to_contain_text(stage)
    expect(panel.get_by_role('button', name='Prepare another action', exact=True)).to_be_enabled()


@pytest.mark.parametrize('lost_reply', ['none', 'resolve', 'admit'])
def test_browser_runtime_cycle_and_lost_reply_recovery(ready_runtime, request, tmp_path, lost_reply):
    from playwright.sync_api import expect
    setup, binding, native = ready_runtime
    page, trace = request.getfixturevalue('local_browser')
    panel = panel_for(page, setup, binding)
    page_errors = []
    page.on('pageerror', lambda error: page_errors.append(str(error)))
    panel.get_by_label('Session selection', exact=True).select_option('new')
    assert native.opens == 0
    trace['drop_resolution'] = lost_reply == 'resolve'
    panel.get_by_role('button', name='Review runtime action', exact=True).click()
    if lost_reply == 'resolve':
        expect(panel.get_by_role('alert')).to_be_visible()
        page.reload()
        panel = panel_for(page, setup, binding)
    expect(panel.get_by_role('button', name='Submit reviewed action', exact=True)).to_be_enabled()
    assert native.opens == 0  # Resolution and recovery have no native effect.
    trace['drop_operation'] = lost_reply == 'admit'
    panel.get_by_role('button', name='Submit reviewed action', exact=True).click()
    if lost_reply == 'admit':
        expect(panel.get_by_role('alert')).to_be_visible()
        page.reload()
        panel = panel_for(page, setup, binding)
    expect(panel.get_by_test_id('runtime-operation-status')).to_contain_text('SUBMITTED')
    expect(panel.get_by_role('button', name='Prepare another action', exact=True)).to_be_enabled()
    session_id = panel.get_by_test_id('runtime-operation-session').inner_text()
    assert native.opens == 1
    target = Path(os.environ.get('OKTO_NEXUS_UI_SCREENSHOT_DIR', str(tmp_path)))
    target.mkdir(parents=True, exist_ok=True)
    panel.screenshot(path=str(target / f'runtime-open-{lost_reply}.png'))
    panel.get_by_role('button', name='Prepare another action', exact=True).click()
    # Explicit reuse must not start a second native runtime.
    panel.get_by_label('Runtime action', exact=True).select_option('runtime.start')
    panel.get_by_label('Session selection', exact=True).select_option('existing')
    panel.get_by_label('Runtime session ID', exact=True).fill(session_id)
    panel.get_by_role('button', name='Review runtime action', exact=True).click()
    panel.get_by_role('button', name='Check action result', exact=True).click()
    expect(panel.get_by_role('button', name='Submit reviewed action', exact=True)).to_be_enabled()
    expect(panel.get_by_test_id('runtime-operation-status')).to_have_count(0)
    panel.get_by_role('button', name='Submit reviewed action', exact=True).click()
    expect(panel.get_by_test_id('runtime-operation-status')).to_contain_text('SUBMITTED')
    expect(panel.get_by_role('button', name='Prepare another action', exact=True)).to_be_enabled()
    assert native.opens == 1
    actions = [('turn.submit', 'Hello from browser'), ('turn.steer', 'Continue carefully'),
               ('turn.interrupt', None), ('runtime.close', None)]
    for action, message in actions:
        panel.get_by_role('button', name='Prepare another action', exact=True).click()
        panel.get_by_label('Runtime action', exact=True).select_option(action)
        expect(panel.get_by_label('Runtime session ID', exact=True)).to_have_value(session_id)
        if message:
            panel.get_by_label('Runtime message', exact=True).fill(message)
        if action == 'turn.steer':
            panel.get_by_label('Native turn ID', exact=True).fill('turn-from-native')
        if action == 'turn.interrupt':
            panel.get_by_label('Turn target', exact=True).select_option('current_run')
        submit(panel, 'SUCCEEDED' if action == 'runtime.close' else 'SUBMITTED')
    assert native.native.stopped and native.opens == 1
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute('SELECT actor_agent_id,subject_agent_id FROM execution_operations').fetchall()
        assert len(rows) == 5 and all(tuple(row) == ('operator', 'subject') for row in rows)
        assert uow.connection.execute('SELECT MAX(attempt_no) FROM execution_dispatch_outbox').fetchone()[0] == 1
    posts = [(path, json.loads(body)) for method, path, body in trace['requests']
             if method == 'POST' and path in ('/v1/runtime/intents:resolve', '/v1/runtime/operations')]
    assert len([row for row in posts if row[0].endswith(':resolve')]) == 6
    assert len([row for row in posts if row[0].endswith('/operations')]) == 6
    assert not page_errors


def test_browser_refuses_changed_authority_after_review(ready_runtime, request):
    from playwright.sync_api import expect
    setup, binding, native = ready_runtime
    page, trace = request.getfixturevalue('local_browser')
    panel = panel_for(page, setup, binding)
    panel.get_by_role('button', name='Review runtime action', exact=True).click()
    expect(panel.get_by_role('button', name='Submit reviewed action', exact=True)).to_be_enabled()
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET permissions='{}' WHERE agent_id='operator'")
    panel.get_by_role('button', name='Submit reviewed action', exact=True).click()
    expect(panel.get_by_role('alert')).to_be_visible()
    expect(panel.get_by_role('button', name='Retry the same submission', exact=True)).to_be_visible()
    expect(panel.get_by_role('button', name='Prepare another action', exact=True)).to_have_count(0)
    assert native.opens == 0
    assert len([row for row in trace['requests'] if row[:2] == ('POST', '/v1/runtime/operations')]) == 1


def test_browser_storage_failure_prevents_resolution(ready_runtime, request):
    from playwright.sync_api import expect
    setup, binding, native = ready_runtime
    page, trace = request.getfixturevalue('local_browser')
    panel = panel_for(page, setup, binding)
    page.evaluate("""() => {
      const original = Storage.prototype.setItem;
      Storage.prototype.setItem = function(key, value) {
        if (key.startsWith('okto-nexus:r4-runtime:')) throw new Error('Fixture storage unavailable');
        return original.call(this, key, value);
      };
    }""")
    panel.get_by_role('button', name='Review runtime action', exact=True).click()
    expect(panel.get_by_role('alert')).to_contain_text('storage unavailable')
    assert not [row for row in trace['requests'] if row[:2] == ('POST', '/v1/runtime/intents:resolve')]
    assert native.opens == 0


def test_browser_initial_message_and_double_click_use_one_request(ready_runtime, request):
    from playwright.sync_api import expect
    setup, binding, native = ready_runtime
    page, trace = request.getfixturevalue('local_browser')
    panel = panel_for(page, setup, binding)
    panel.get_by_label('Runtime message', exact=True).fill('Initial message from browser')
    panel.get_by_role('button', name='Review runtime action', exact=True).click()
    button = panel.get_by_role('button', name='Submit reviewed action', exact=True)
    expect(button).to_be_enabled()
    button.evaluate('(button) => { button.click(); button.click(); }')
    expect(panel.get_by_test_id('runtime-operation-status')).to_contain_text('Initial turn: SUBMITTED')
    expect(panel.get_by_role('button', name='Prepare another action', exact=True)).to_be_enabled()
    assert native.opens == 1 and [name for name, _ in native.native.sent] == ['send_turn']
    assert len([row for row in trace['requests'] if row[:2] == ('POST', '/v1/runtime/operations')]) == 1
