"""The canonical owned Core preserves the eight context-only contracts."""
from dataclasses import replace
import json
import threading
import time
import uuid

import pytest

from nexus_connector_core.native import registry
from nexus_connector_core.native.runtime_bridge import CopiedAdapterFactory
from registered_native_peer import ADAPTER, RegisteredPeer
from test_canonical_registered_adapters import registered_setup, subject_key
from test_canonical_identity_lifecycle import second_binding
from test_canonical_delivery import enable, send
from test_embedded_dispatch import admit, wait_receipt
from test_vertical_inventory import _Native
from test_pr34_remediation import tool


@pytest.fixture
def observers(registered_setup, monkeypatch):
    setup, observer = registered_setup
    monkeypatch.setitem(registry._SPECS, ADAPTER,
        replace(registry._SPECS[ADAPTER], context_observation_contract=1))
    monkeypatch.setattr(RegisteredPeer, 'context_contract', 1)
    executor = second_binding(setup, monkeypatch, name='executor', adapter_id='pi_rpc')
    enable(setup, executor)
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET consumption='mirror_only',response_policy='none' WHERE endpoint_id=?",
                               (observer['endpoint_id'],))
    async def environment(prepared):
        return {}
    bridge = CopiedAdapterFactory(environment)
    native = _Native()
    class Factory:
        async def open(self, prepared, session_id, context, *, stream_epoch):
            if prepared.intent.adapter_id == ADAPTER:
                return await bridge.open(prepared, session_id, context, stream_epoch=stream_epoch)
            return native
    setup[1].state.embedded_dispatch_owner.native_factory = Factory()
    setup[1].state.test_owned_factories.append(bridge)
    wait_receipt(setup, admit(setup, executor, 'executor-open', 'runtime.start', new_session=True))
    def open_observer(name='observer-open'):
        opened = admit(setup, observer, name, 'runtime.start', new_session=True)
        wait_receipt(setup, opened)
        return opened, RegisteredPeer.instances[-1]
    yield setup, observer, executor, native, open_observer


def wait_observation(setup, source, status):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute('SELECT * FROM runtime_context_observations WHERE source_operation_id=?',
                                         (source,)).fetchone()
        if row and row['status'] == status:
            return dict(row)
        time.sleep(.02)
    raise AssertionError(dict(row) if row else 'Observation not admitted')


def message(setup, monkeypatch):
    result = tool(setup[2], setup[3]['operator']['Authorization'].removeprefix('Bearer '), 'message_create',
        dict(project_root=str(setup[-1]), from_agent_id='operator', subject='Context observation',
             body='Context ' + uuid.uuid4().hex, target=dict(strategy='direct', agent_id='subject')))
    assert result['ok'], result
    return result['data']


def test_context_observer_receives_delivery_without_another_executor(observers, monkeypatch):
    setup, binding, _, native, open_observer = observers
    opened, peer = open_observer()
    created = message(setup, monkeypatch)
    source = created['runtime_operations'][0]
    row = wait_observation(setup, source, 'SENT_UNCONFIRMED')
    assert len(peer.contexts) == 1 and peer.sent == []
    assert peer.contexts[0]['message_id'] == created['message_id']
    assert peer.contexts[0]['intent'] == 'information' and peer.contexts[0]['response_requested'] is False
    deadline = time.monotonic() + 10
    while not native.sent and time.monotonic() < deadline:
        time.sleep(.02)
    assert len(native.sent) == 1
    original_uow = setup[0].connection_factory.unit_of_work
    def query_only(*, write=True):
        uow = original_uow(write=write)
        if not write:
            uow.connection.execute('PRAGMA query_only=ON')
        return uow
    monkeypatch.setattr(setup[0].connection_factory, 'unit_of_work', query_only)
    viewed = tool(setup[2], setup[3]['operator']['Authorization'].removeprefix('Bearer '),
                  'harness_get', {'operation_id': source})
    assert viewed['ok'], viewed
    item = viewed['data']['context_observations'][0]
    assert item['operation_id'] == row['operation_id']
    assert item['external_acceptance'] == 'not_observed'
    assert item['execution_authority'] is False and item['result_durable'] is False
    denied = tool(setup[2], subject_key(setup), 'harness_send',
        {'session_id': opened['session_id'], 'payload': {'text': 'must not infer'}})
    assert not denied['ok'], denied
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM message_deliveries WHERE message_id=?', (created['message_id'],)).fetchone()[0] == 1
        assert uow.connection.execute('SELECT count(*) FROM delivery_outbox WHERE message_id=?', (created['message_id'],)).fetchone()[0] == 1
        assert uow.connection.execute('SELECT count(*) FROM harness_sessions').fetchone()[0] == 0
        assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()


@pytest.mark.parametrize('change', ['endpoint', 'profile', 'credential', 'flag', 'effective'])
def test_observation_revalidates_authority_before_transport(observers, monkeypatch, change):
    setup, binding, _, _, open_observer = observers
    _, peer = open_observer()
    runner = setup[0].runtime_dispatcher.context_dispatcher
    execute = runner._execute
    reached, release = threading.Event(), threading.Event()
    def held(command, lane):
        reached.set()
        assert release.wait(15)
        execute(command, lane)
    monkeypatch.setattr(runner, '_execute', held)
    try:
        created = message(setup, monkeypatch)
        assert reached.wait(10)
        with setup[0].connection_factory.unit_of_work() as uow:
            if change == 'endpoint':
                uow.connection.execute('UPDATE agent_endpoints SET enabled=0 WHERE endpoint_id=?', (binding['endpoint_id'],))
            elif change == 'profile':
                uow.connection.execute('UPDATE runtime_profiles SET enabled=0 WHERE profile_id=(SELECT profile_id FROM agent_endpoints WHERE endpoint_id=?)', (binding['endpoint_id'],))
            elif change == 'credential':
                uow.connection.execute("UPDATE agents SET api_key_hash='revoked-fixture' WHERE agent_id='operator'")
            elif change == 'flag':
                setup[0].config.feature_harness_integrations = False
            else:
                uow.connection.execute('UPDATE execution_context_observers SET qualified=0')
        release.set()
        wait_observation(setup, created['runtime_operations'][0], 'REJECTED')
        assert peer.contexts == []
        assert all(command.verb == 'end' for command in peer.sent), 'Revocation may close, never infer'
    finally:
        release.set()
        setup[0].config.feature_harness_integrations = True


def test_observation_failure_after_acceptance_is_unknown_and_never_replayed(observers, monkeypatch):
    setup, _, _, _, open_observer = observers
    _, peer = open_observer()
    accept = peer.observe_context
    def uncertain(session, envelope):
        accept(session, envelope)
        raise OSError('Lost context acknowledgement after acceptance')
    monkeypatch.setattr(peer, 'observe_context', uncertain)
    created = message(setup, monkeypatch)
    row = wait_observation(setup, created['runtime_operations'][0], 'OUTCOME_UNKNOWN')
    runner = setup[0].runtime_dispatcher.context_dispatcher
    for _ in range(3):
        runner.scan_once()
    assert len(peer.contexts) == 1 and peer.sent == []
    with setup[0].connection_factory.unit_of_work() as uow:
        assert not runner.repo.observe(uow, operation_id=row['operation_id'], epoch=row['owner_epoch'] - 1,
            attempt_id=row['attempt_id'], expected='OUTCOME_UNKNOWN', status='SENT_UNCONFIRMED', now=setup[0].clock.now_iso())
        assert uow.connection.execute('SELECT count(*) FROM runtime_results').fetchone()[0] == 0


def test_observation_metadata_requires_its_own_endpoint_read_authority(observers, monkeypatch):
    from test_agent_recovery_isolation import create_agent
    from okto_nexus.domain.base import iso_plus
    setup, observer, executor, _, open_observer = observers
    open_observer()
    created = message(setup, monkeypatch)
    source = created['runtime_operations'][0]
    wait_observation(setup, source, 'SENT_UNCONFIRMED')
    caller = create_agent(setup, 'reader')
    def grant(binding):
        result = setup[2].post('/api/v1/harness/grants', headers=setup[3]['operator'], json=dict(
            actor_agent_id='reader', endpoint_id=binding['endpoint_id'], actions=['read'],
            max_executions=1, expires_at=iso_plus(setup[0].clock.now_iso(), 600)))
        assert result.status_code == 200, result.text
        return result.json()['data']['grant_id']
    grant(executor)
    def inspect():
        result = tool(setup[2], caller[3]['subject']['Authorization'].removeprefix('Bearer '),
                      'harness_get', {'operation_id': source})
        assert result['ok'], result
        return result['data']['context_observations']
    assert inspect() == []
    observer_grant = grant(observer)
    assert len(inspect()) == 1
    response = setup[2].delete('/api/v1/harness/grants/' + observer_grant, headers=setup[3]['operator'])
    assert response.status_code == 200, response.text
    assert inspect() == []


@pytest.mark.parametrize('missing', ['probe', 'method'])
def test_unverified_observer_does_not_receive_context_or_execution(observers, monkeypatch, missing):
    setup, _, _, native, open_observer = observers
    if missing == 'probe':
        monkeypatch.setattr(RegisteredPeer, 'context_contract', None)
    else:
        monkeypatch.setattr(RegisteredPeer, 'observe_context', None)
    _, peer = open_observer()
    created = message(setup, monkeypatch)
    deadline = time.monotonic() + 10
    while not native.sent and time.monotonic() < deadline:
        time.sleep(.02)
    assert len(native.sent) == 1 and peer.contexts == peer.sent == []
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT qualified FROM execution_context_observers WHERE session_id LIKE ?', ('ses_%',)).fetchone()[0] == 0
        assert not uow.connection.execute('SELECT 1 FROM runtime_context_observations WHERE source_operation_id=?', (created['runtime_operations'][0],)).fetchone()


def test_observation_insert_failure_rolls_back_the_canonical_delivery(observers, monkeypatch):
    from okto_nexus.adapters.outbound.sqlite.runtime_observations_repo import SqliteRuntimeObservationRepo
    from okto_nexus.errors import ErrorCode, OktoNexusError
    setup, _, _, native, open_observer = observers
    _, peer = open_observer()
    enqueue = SqliteRuntimeObservationRepo.enqueue
    def fail(*args, **kwargs):
        enqueue(*args, **kwargs)
        raise OktoNexusError(ErrorCode.DB_ERROR, 'Cut after observer insert', {})
    with monkeypatch.context() as cut:
        cut.setattr(SqliteRuntimeObservationRepo, 'enqueue', fail)
        result = send(setup, monkeypatch)
    assert not result['ok'], result
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        for table in ('messages', 'message_deliveries', 'delivery_outbox', 'runtime_context_observations', 'execution_domain_deliveries'):
            assert uow.connection.execute('SELECT count(*) FROM ' + table).fetchone()[0] == 0
    assert peer.contexts == peer.sent == native.sent == []
    created = message(setup, monkeypatch)
    wait_observation(setup, created['runtime_operations'][0], 'SENT_UNCONFIRMED')
    assert len(peer.contexts) == 1


def test_timed_out_observation_keeps_its_single_worker_until_return(observers, monkeypatch):
    setup, _, _, native, open_observer = observers
    _, peer = open_observer()
    accept = peer.observe_context
    received, release = threading.Event(), threading.Event()
    def stuck(session, envelope):
        accept(session, envelope)
        received.set()
        assert release.wait(20)
    monkeypatch.setattr(peer, 'observe_context', stuck)
    owner = setup[0].runtime_dispatcher
    try:
        first = message(setup, monkeypatch)
        assert received.wait(10)
        wait_observation(setup, first['runtime_operations'][0], 'SENDING')
        owner.send_timeout_seconds = 0
        owner.context_dispatcher.expire()
        owner.send_timeout_seconds = 45
        wait_observation(setup, first['runtime_operations'][0], 'OUTCOME_UNKNOWN')
        second = message(setup, monkeypatch)
        wait_observation(setup, second['runtime_operations'][0], 'PENDING')
        owner.context_dispatcher.scan_once()
        assert len(owner.context_dispatcher._threads) == 1
        assert not owner.context_dispatcher.idle() and len(peer.contexts) == 1
        deadline = time.monotonic() + 10
        while not native.sent and time.monotonic() < deadline:
            time.sleep(.02)
        assert len(native.sent) == 1, 'The context writer must not block the executor'
    finally:
        owner.send_timeout_seconds = 45
        release.set()


def test_close_cancels_pending_context_without_replaying_unknown_into_new_session(observers, monkeypatch):
    setup, binding, _, _, open_observer = observers
    opened, peer = open_observer()
    accept = peer.observe_context
    def uncertain(session, envelope):
        accept(session, envelope)
        raise OSError('Uncertain context acceptance')
    monkeypatch.setattr(peer, 'observe_context', uncertain)
    first = message(setup, monkeypatch)
    wait_observation(setup, first['runtime_operations'][0], 'OUTCOME_UNKNOWN')
    pending = message(setup, monkeypatch)
    wait_observation(setup, pending['runtime_operations'][0], 'PENDING')
    closed = admit(setup, binding, 'observer-close', 'runtime.close', session_id=opened['session_id'])
    wait_receipt(setup, closed, stages=('SUCCEEDED',))
    wait_observation(setup, pending['runtime_operations'][0], 'CANCELLED')
    reopened, fresh_peer = open_observer('observer-reopen')
    assert reopened['session_id'] != opened['session_id']
    fresh = message(setup, monkeypatch)
    wait_observation(setup, fresh['runtime_operations'][0], 'SENT_UNCONFIRMED')
    wait_observation(setup, first['runtime_operations'][0], 'OUTCOME_UNKNOWN')
    assert [item['message_id'] for item in peer.contexts + fresh_peer.contexts] == [first['message_id'], fresh['message_id']]
    assert fresh_peer.sent == []
