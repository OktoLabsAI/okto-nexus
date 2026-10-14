"""Work revocation contains its native session, not every session of an agent."""
import asyncio
import time
from types import SimpleNamespace

import pytest
from nexus_connector_core import CoreError

from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt, admit
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, call
from test_canonical_result_publication import current_turn
from test_reserved_handoff_admission import reserve
from test_runtime_policy_defaults import save
from test_sender_sessions import complete


def running(runtime, **options):
    setup, _, native = runtime
    _, hid, gid, port, held, claim = reserve(runtime, **options)
    made = claim()
    setup[2].portal.call(build_capacity_admission(setup[0], capacity=port).consume,
                        made['runtime_operation']['operation_id'])
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    owner = setup[1].state.embedded_dispatch_owner
    setup[2].portal.call(owner._renew_owned, turn['session_id'], owner.sessions[turn['session_id']])
    assert not owner.sessions[turn['session_id']].get('recovering')
    return hid, gid, port, held, made, turn, native.native


def wait_for(predicate):
    deadline = time.monotonic() + 15
    while not predicate():
        assert time.monotonic() < deadline, 'Scoped work containment did not settle'
        time.sleep(.02)


@pytest.mark.parametrize('revocation', ['work_grant', 'automation'])
def test_revoked_running_work_retains_capacity_and_siblings_during_delayed_stop(runtime, monkeypatch, revocation):
    setup, binding, _ = runtime
    deps, app, client, *_ = setup
    hid, gid, port, held, made, turn, _ = running(runtime)
    sid = turn['session_id']
    owner = app.state.embedded_dispatch_owner
    session = owner.sessions[sid]
    sibling = admit(setup, binding, 'healthy-sibling', 'runtime.start', new_session=True)
    wait_receipt(setup, sibling)
    native_runtime = client.portal.call(session['executor']._runtime)
    original_stop = native_runtime.shutdown
    entered, proceed = asyncio.Event(), asyncio.Event()
    attempts = []

    async def delayed_stop(policy):
        attempts.append(sid)
        if len(attempts) == 1:
            entered.set()
            await proceed.wait()
            raise CoreError('RECONCILIATION_REQUIRED', 'delayed_stop_proof')
        return await original_stop(policy)

    monkeypatch.setattr(native_runtime, 'shutdown', delayed_stop)
    if revocation == 'automation':
        assert save(setup, agent='subject', broadcast_handoff_auto_claim=False).status_code == 200
    else:
        response = client.delete('/api/v1/harness/grants/' + gid, headers=setup[3]['operator'])
        assert response.status_code == 200, response.text
    try:
        client.portal.call(owner._renew_owned, sid, session)
        client.portal.call(asyncio.wait_for, entered.wait(), 5)
        cleanup = owner.agents.session_tasks[sid]
        assert session['recovering'] and not owner.agents.blocked
        assert owner.failure is None and sibling['session_id'] in owner.sessions
        assert client.portal.call(port.release_capacity, held.request, held.reservation_id, 'REVOKED').state == 'RELEASE_PENDING'
        # Another session remains productive while the first stop has no proof.
        other_turn = admit(setup, binding, 'sibling-turn', 'turn.submit',
                           session_id=sibling['session_id'], text='Continue independently')
        wait_receipt(setup, other_turn)
        client.portal.call(owner.agents.recover_session, sid)
        assert owner.agents.session_tasks[sid] is cleanup and len(attempts) == 1
    finally:
        client.portal.call(proceed.set)
    wait_for(cleanup.done)
    assert not owner.agents.blocked and sid in owner.sessions
    assert client.portal.call(port.get_capacity_reservation, held.request).state == 'RELEASE_PENDING'
    # The retained owner retries the same session, never a second productive call.
    async def retry():
        owner.agents.session_retry_at[sid] = 0
        owner.agents.recover_session(sid)
    client.portal.call(retry)
    wait_for(lambda: sid not in owner.sessions)
    assert client.portal.call(port.get_capacity_reservation, held.request).state == 'RELEASED'
    assert not owner.agents.blocked and owner.failure is None
    assert sibling['session_id'] in owner.sessions
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?',
                                      (hid,)).fetchone()[:] == ('CLAIMED', made['claim_epoch'])
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?',
                                      (gid,)).fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_capacity_compensations').fetchone()[0] == 0
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_handoff_bindings').fetchone()[0] == 1


@pytest.mark.parametrize('verification', [False, True])
def test_business_completion_does_not_revoke_running_session_lease(runtime, verification):
    setup = runtime[0]
    deps, app, client, *_ = setup
    deps.config.feature_verification = verification
    hid, _, port, held, made, turn, _ = running(runtime,
        **({'acceptance_criteria': ['Review the evidence']} if verification else {}))
    result = call(runtime, 'handoff_complete', actor='subject', handoff_id=hid,
                  agent_id='subject', claim_epoch=made['claim_epoch'], result='Evidence submitted')
    assert result['ok'], result
    owner = app.state.embedded_dispatch_owner
    sid = turn['session_id']
    client.portal.call(owner._renew_owned, sid, owner.sessions[sid])
    assert sid in owner.sessions and not owner.sessions[sid].get('recovering')
    assert client.portal.call(port.get_capacity_reservation, held.request).state == 'CONSUMED'
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT max(lease_serial) FROM execution_leases WHERE session_id=?',
                                      (sid,)).fetchone()[0] >= 2


def test_native_terminal_work_is_history_and_does_not_poison_reused_session(runtime):
    setup, binding, _ = runtime
    deps, app, client, *_ = setup
    hid, gid, _, _, _, turn, peer = running(runtime)
    complete(setup, SimpleNamespace(sessions={turn['session_id']: peer}), turn, 'Native result')
    response = client.delete('/api/v1/harness/grants/' + gid, headers=setup[3]['operator'])
    assert response.status_code == 200, response.text
    ordinary = admit(setup, binding, 'ordinary-after-work', 'turn.submit',
                     session_id=turn['session_id'], text='This is independent ordinary work')
    wait_receipt(setup, ordinary)
    owner = app.state.embedded_dispatch_owner
    client.portal.call(owner._renew_owned, turn['session_id'], owner.sessions[turn['session_id']])
    assert not owner.sessions[turn['session_id']].get('recovering') and not owner.agents.blocked
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[0] == 'CLAIMED'


@pytest.mark.parametrize('decision', ['reject', 'rework'])
def test_obsolete_running_claim_is_contained_without_undoing_business_decision(runtime, decision):
    setup = runtime[0]
    deps, app, client, *_ = setup
    deps.config.feature_verification = decision == 'rework'
    hid, _, port, held, made, turn, _ = running(runtime,
        **({'acceptance_criteria': ['Review the evidence']} if decision == 'rework' else {}))
    if decision == 'reject':
        response = call(runtime, 'handoff_reject', actor='subject', handoff_id=hid,
            agent_id='subject', claim_epoch=made['claim_epoch'], reason='Cannot continue this work')
        assert response['ok'], response
        expected = ('REJECTED', made['claim_epoch'])
    else:
        response = call(runtime, 'handoff_complete', actor='subject', handoff_id=hid,
            agent_id='subject', claim_epoch=made['claim_epoch'], result='Evidence to review')
        assert response['ok'], response
        response = call(runtime, 'handoff_verify', handoff_id=hid, agent_id='caller',
            claim_epoch=made['claim_epoch'], verdict='fail', feedback='Retain ownership for rework')
        assert response['ok'], response
        expected = ('CLAIMED', made['claim_epoch'] + 1)
    owner = app.state.embedded_dispatch_owner
    client.portal.call(owner._renew_owned, turn['session_id'], owner.sessions[turn['session_id']])
    wait_for(lambda: turn['session_id'] not in owner.sessions)
    assert client.portal.call(port.get_capacity_reservation, held.request).state == 'RELEASED'
    assert not owner.agents.blocked and owner.failure is None
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?',
                                      (hid,)).fetchone()[:] == expected
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_capacity_compensations').fetchone()[0] == 0
