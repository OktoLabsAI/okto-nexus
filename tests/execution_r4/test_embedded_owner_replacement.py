"""Automatic replacement retains the previous generation until actual release."""
import asyncio
import threading
import time

import pytest

from okto_nexus.errors import ErrorCode, OktoNexusError
from nexus_connector_core import RuntimeEvent
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt


def wait_until(predicate, *, timeout=30):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, 'Retained replacement did not finish'
        time.sleep(.02)


def fail_owner(client, owner):
    async def fail():
        owner.failure = OktoNexusError(ErrorCode.DB_ERROR, 'Fixture host failure', {}, retryable=False)
        await owner.failed()
    client.portal.call(fail)


@pytest.mark.parametrize('local_setup', ['pi_rpc', 'claude_stream', 'codex_app_server'], indirect=True)
def test_failed_owner_replaced_and_new_work_runs_without_replaying(connected_local):
    setup, binding, factory = connected_local
    deps, app, client, *_ = setup
    old = app.state.embedded_dispatch_owner
    opened = admit(setup, binding, 'before-replacement-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    turn = admit(setup, binding, 'before-replacement-turn', 'turn.submit',
                 session_id=opened['session_id'], text='Exactly one effect')
    wait_receipt(setup, turn)
    native = factory.native
    assert len(native.sent) == 1
    dispatcher = deps.runtime_dispatcher
    fail_owner(client, old)
    wait_until(lambda: app.state.embedded_dispatch_owner is not old
               and app.state.embedded_dispatch_owner.pump is not None)
    new = app.state.embedded_dispatch_owner
    client.portal.call(new.inventory.wait_usable_observation, setup[5].adapter_id)
    assert new.channel.connection_generation == old.channel.connection_generation + 1
    assert old.shutdown_status()['state'] == 'DRAINED'
    assert native.stopped and len(native.sent) == 1 and factory.opens == 1
    assert not old.workers and not old.renewals
    assert deps.runtime_dispatcher is dispatcher and not dispatcher._shutdown_finished.is_set()
    assert client.get('/healthz').status_code == 200
    assert app.state.runtime_shutdown.embedded is new
    assert app.state.runtime_shutdown.host is new.host
    assert app.state.embedded_runtime_supervisor.failure is None
    fresh = admit(setup, binding, 'after-replacement-open', 'runtime.start', new_session=True)
    wait_receipt(setup, fresh)
    wait_receipt(setup, admit(setup, binding, 'after-replacement-turn', 'turn.submit',
                             session_id=fresh['session_id'], text='New work on the successor'))
    assert factory.opens == 2 and len(native.sent) == 1
    assert len(factory.native.sent) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT MAX(attempt_no) FROM execution_dispatch_outbox').fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_bindings').fetchone()[0] == 1


@pytest.mark.parametrize('shutdown', [False, True])
def test_uncertain_native_prevents_replacement_and_shutdown_never_restarts(connected_local, monkeypatch, shutdown):
    setup, binding, factory = connected_local
    deps, app, client, headers, *_ = setup
    old = app.state.embedded_dispatch_owner
    wait_receipt(setup, admit(setup, binding, 'held-close-open', 'runtime.start', new_session=True))
    native = factory.native
    release, attempted = threading.Event(), threading.Event()
    original = native.close
    async def held():
        attempted.set()
        return await original() if release.is_set() else 'unknown'
    monkeypatch.setattr(native, 'close', held)
    try:
        fail_owner(client, old)
        assert attempted.wait(10)
        wait_until(lambda: old._shutdown_recovery_task is not None)
        assert app.state.embedded_dispatch_owner is old
        assert old.host._runtime_tasks and not native.stopped
        assert client.get('/healthz').status_code == 200
        if shutdown:
            response = client.post('/v1/runtime/shutdown', headers=headers['operator'],
                                   json={'timeout_seconds': .1})
            assert response.status_code == 202, response.text
            assert response.json()['state'] == 'DRAINING_PENDING'
            assert not deps.runtime_dispatcher._shutdown_finished.is_set()
    finally:
        release.set()
    if shutdown:
        wait_until(lambda: app.state.runtime_shutdown.status()['state'] == 'DRAINED')
        assert app.state.embedded_dispatch_owner is old
        assert app.state.embedded_runtime_supervisor.drained
    else:
        wait_until(lambda: app.state.embedded_dispatch_owner is not old)
    assert native.stopped and factory.opens == 1


def test_stale_generation_is_not_taken_back_by_supervisor(connected_local):
    setup, _, factory = connected_local
    deps, app, client, *_ = setup
    old = app.state.embedded_dispatch_owner
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET generation=generation+1 WHERE kind='embedded'")
    wait_until(lambda: app.state.embedded_runtime_supervisor.failure is not None)
    assert app.state.embedded_dispatch_owner is old
    assert factory.opens == 0
    assert client.get('/healthz').status_code == 200
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT generation FROM execution_executors WHERE kind='embedded'").fetchone()[0] == old.channel.connection_generation + 1


def test_inventory_producer_is_joined_before_successor_claim(connected_local, monkeypatch):
    setup, _, factory = connected_local
    _, app, client, *_ = setup
    old = app.state.embedded_dispatch_owner
    entered, release = threading.Event(), threading.Event()
    original = old.inventory.discover_candidates
    async def held(adapter_id=None):
        entered.set()
        await asyncio.to_thread(release.wait)
        return await original(adapter_id)
    monkeypatch.setattr(old.inventory, 'discover_candidates', held)
    refreshing = client.portal.start_task_soon(old.inventory.refresh, (setup[5].adapter_id,))
    try:
        assert entered.wait(10)
        fail_owner(client, old)
        wait_until(lambda: old.shutdown_status()['state'] == 'DRAINED')
        assert app.state.embedded_dispatch_owner is old
        assert old.inventory._close_task is not None and not old.inventory._close_task.done()
        assert factory.opens == 0
        assert client.get('/healthz').status_code == 200
    finally:
        release.set()
    refreshing.result(timeout=30)
    wait_until(lambda: app.state.embedded_dispatch_owner is not old)
    assert old.inventory._close_task.done()


def test_policy_opt_out_prevents_replacement_until_reenabled(connected_local, monkeypatch):
    from test_runtime_policy_defaults import save
    setup, _, factory = connected_local
    _, app, client, *_ = setup
    old = app.state.embedded_dispatch_owner
    assert save(setup, automatic_recovery=False).status_code == 200
    observed = []
    original = old._recovery_enabled
    def policy():
        value = original()
        observed.append(value)
        return value
    monkeypatch.setattr(old, '_recovery_enabled', policy)
    fail_owner(client, old)
    wait_until(lambda: len(observed) >= 2)
    assert observed == [False] * len(observed)
    assert app.state.embedded_dispatch_owner is old and factory.opens == 0
    assert save(setup, automatic_recovery=True).status_code == 200
    wait_until(lambda: app.state.embedded_dispatch_owner is not old)


@pytest.mark.parametrize('shutdown', [False, True])
def test_failed_successor_claim_retains_candidate_and_obeys_shutdown(connected_local, monkeypatch, shutdown):
    from okto_nexus.bootstrap.embedded_inventory import EmbeddedInventoryOwner
    setup, _, factory = connected_local
    _, app, client, headers, *_ = setup
    old = app.state.embedded_dispatch_owner
    release, attempted = threading.Event(), threading.Event()
    original = EmbeddedInventoryOwner._claim
    def claim(owner):
        if owner.predecessor_generation is not None and not release.is_set():
            attempted.set()
            raise OktoNexusError(ErrorCode.DB_ERROR, 'Fixture claim contention', {}, retryable=True)
        return original(owner)
    monkeypatch.setattr(EmbeddedInventoryOwner, '_claim', claim)
    try:
        fail_owner(client, old)
        assert attempted.wait(15)
        wait_until(lambda: app.state.embedded_runtime_supervisor.failure is not None)
        candidate = app.state.embedded_runtime_supervisor._candidate
        assert candidate is not None and candidate.generation is None
        assert app.state.embedded_dispatch_owner is old and factory.opens == 0
        if shutdown:
            response = client.post('/v1/runtime/shutdown', headers=headers['operator'],
                                   json={'timeout_seconds': .1})
            assert response.status_code in (200, 202), response.text
            wait_until(lambda: app.state.runtime_shutdown.status()['state'] == 'DRAINED')
            assert app.state.embedded_runtime_supervisor.drained
    finally:
        release.set()
    if shutdown:
        assert app.state.embedded_dispatch_owner is old
    else:
        wait_until(lambda: app.state.embedded_dispatch_owner is not old)
        assert app.state.embedded_inventory_owner is candidate
        assert candidate.generation == old.channel.connection_generation + 1


def test_opening_producer_finishing_late_is_contained_before_replacement(connected_local, monkeypatch):
    setup, binding, factory = connected_local
    _, app, client, *_ = setup
    old = app.state.embedded_dispatch_owner
    release, entered = threading.Event(), threading.Event()
    original = factory.open
    async def held(*args, **kwargs):
        entered.set()
        await asyncio.to_thread(release.wait)
        return await original(*args, **kwargs)
    monkeypatch.setattr(factory, 'open', held)
    admit(setup, binding, 'late-open-replacement', 'runtime.start', new_session=True)
    try:
        assert entered.wait(10)
        fail_owner(client, old)
        wait_until(lambda: old._shutdown_recovery_task is not None)
        assert old.workers and old.host._runtime_tasks
        assert app.state.embedded_dispatch_owner is old
        assert factory.opens == 0
        assert client.get('/healthz').status_code == 200
    finally:
        release.set()
    wait_until(lambda: app.state.embedded_dispatch_owner is not old)
    assert factory.opens == 1 and factory.native.stopped
    assert not old.workers and old.shutdown_status()['state'] == 'DRAINED'


@pytest.mark.parametrize('local_setup', ['pi_rpc', 'claude_stream', 'codex_app_server'], indirect=True)
@pytest.mark.parametrize('kind', ['approval', 'input'])
def test_native_decision_in_flight_is_contained_before_owner_replacement(connected_local, kind):
    setup, binding, factory = connected_local
    deps, app, client, headers, *_ = setup
    deps.config.feature_hitl = True
    old = app.state.embedded_dispatch_owner
    opened = admit(setup, binding, 'native-race-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    session_id = opened['scope']['session_id']
    turned = admit(setup, binding, 'native-race-turn', 'turn.submit',
                   session_id=session_id, text='Wait for approval')
    wait_receipt(setup, turned)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams WHERE session_id=?',
                                             (session_id,)).fetchone())
    request = dict(schema_version=1, request_id=7, request_hash='a' * 64,
                   method=('item/tool/requestUserInput' if kind == 'input'
                           else 'item/commandExecution/requestApproval'),
                   params={'threadId': 'native-thread', 'turnId': 'turn-from-native', 'itemId': 'item'})
    if kind == 'input':
        request['params'].update(isBlocking=True, questions=[
            {'id': 'question', 'header': 'Response', 'question': 'Provide input.', 'isOther': True}])
    client.portal.call(factory.native.queue.put, RuntimeEvent(
        stream['server_id'], stream['executor_id'], session_id, stream['stream_epoch'], 0,
        'input_request' if kind == 'input' else 'approval_request', request['method'],
        {'native_approval': request, 'native_approval_display': dict(request)},
        turned['operation_id']))

    def pending():
        response = client.get('/api/v1/approvals', headers=headers['operator'],
                              params={'workspace': binding['workspace_id'], 'status': 'pending'})
        assert response.status_code == 200, response.text
        return next((row for row in response.json()['data']['items']
                     if row['action'] == 'execution.native.respond'), None)

    wait_until(pending)
    row = pending()
    detail = client.get('/api/v1/approvals/' + row['approval_id'], headers=headers['operator'])
    assert detail.status_code == 200, detail.text
    proposal = detail.json()['data']['request_payload']['kwargs']
    body = {key: proposal[key] for key in ('approval_key', 'expected_revision',
                                            'request_hash', 'cas_token')}
    body.update(client_intent_id='native-owner-race', decision='approve')
    if kind == 'input':
        body['response'] = {'answers': {'question': {'answers': ['fixture answer']}}}
    responder = headers['subject' if kind == 'input' else 'operator']
    entered, release = threading.Event(), threading.Event()
    effects = []

    async def held_reply(native_request, decision, response):
        entered.set()
        await asyncio.to_thread(release.wait)
        effects.append((native_request, decision, response))

    factory.native.reply_native_approval = held_reply
    try:
        accepted = client.post('/v1/runtime/approval-decisions', headers=responder, json=body)
        assert accepted.status_code == 202, accepted.text
        decision_id = accepted.json()['decision_id']
        assert entered.wait(10)
        fail_owner(client, old)
        wait_until(lambda: old._shutdown_recovery_task is not None)
        assert app.state.embedded_dispatch_owner is old
        assert client.get('/healthz').status_code == 200
    finally:
        release.set()

    wait_until(lambda: app.state.embedded_dispatch_owner is not old)
    result = client.get('/v1/runtime/approval-decisions/' + decision_id,
                        headers=headers['operator'])
    assert result.status_code == 200, result.text
    assert result.json()['native_stage'] == 'SUBMITTED'
    repeated = client.post('/v1/runtime/approval-decisions', headers=responder, json=body)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()['native_operation_id'] == accepted.json()['native_operation_id']
    assert len(effects) == 1
    assert old.shutdown_status()['state'] == 'DRAINED'
    assert factory.native.stopped
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT MAX(attempt_no) FROM execution_dispatch_outbox').fetchone()[0] == 1
