"""Automation is scoped work authority, never an impersonated agent API key."""
from dataclasses import replace
import time

import pytest

from okto_nexus.adapters.inbound.mcp.tools.handoff import build_service
from okto_nexus.application.handoff_automation import create_context, PREFIX
from okto_nexus.domain.base import iso_plus
from okto_nexus.errors import OktoNexusError
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, call, work, assert_unclaimed
from test_canonical_result_publication import current_turn, workspace
from test_runtime_policy_defaults import save


def prepare(runtime, *, strategy='broadcast', enable=True):
    setup, binding, _ = runtime
    deps, _, client, headers, *_ = setup
    target = dict(strategy=strategy)
    if strategy == 'direct':
        target['agent_id'] = 'subject'
    made = call(runtime, 'handoff_create', from_agent_id='caller', visibility='eligible',
                target=target, payload='Perform the authorized broadcast work')
    assert made['ok'], made
    hid = made['data']['handoff_id']
    response = client.post('/api/v1/harness/grants', headers=headers['operator'], json=dict(
        actor_agent_id='subject', endpoint_id=binding['endpoint_id'], actions=['execute_work'],
        max_executions=2, expires_at=iso_plus(deps.clock.now_iso(), 600)))
    assert response.status_code == 200, response.text
    gid = response.json()['data']['grant_id']
    if enable:
        assert save(setup, agent='subject', broadcast_handoff_auto_claim=True).status_code == 200
    service = build_service(deps)
    return service, hid, gid


def candidate(runtime, service, hid, gid):
    with runtime[0][0].connection_factory.unit_of_work() as uow:
        return create_context(uow, access=service.runtime_work.access, agent_id='subject',
            workspace_id=workspace(runtime[0]), endpoint_id=runtime[1]['endpoint_id'],
            handoff_id=hid, grant_id=gid, attempt_id='attempt-automation')


def commit(runtime, service, hid, gid, context):
    with runtime[0][0].connection_factory.unit_of_work() as uow:
        return service.claim_managed_in_transaction(uow, workspace_id=workspace(runtime[0]),
            handoff_id=hid, agent_id='subject', context=context, runtime_endpoint_id=runtime[1]['endpoint_id'],
            execution_grant_id=gid, idempotency_key='attempt-automation')


def test_scoped_automation_claim_dispatches_once_and_preserves_roles(runtime):
    service, hid, gid = prepare(runtime)
    context = candidate(runtime, service, hid, gid)
    assert context.authentication_source == 'handoff_automation'
    assert context.credential_binding.startswith(PREFIX) and not context.trusted_local_operator
    result = commit(runtime, service, hid, gid, context)
    repeated = commit(runtime, service, hid, gid, context)
    assert repeated['runtime_operation']['reused']
    assert repeated['runtime_operation']['operation_id'] == result['runtime_operation']['operation_id']
    wait_receipt(runtime[0], current_turn(runtime[0]))
    with runtime[0][0].connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute('SELECT h.from_agent_id,h.claimed_by,b.actor_agent_id,g.issuer_agent_id,'
            'g.used_executions,o.credential_binding FROM handoffs h JOIN runtime_handoff_bindings b USING(handoff_id) '
            'JOIN runtime_execution_grants g USING(grant_id) JOIN delivery_outbox o USING(operation_id) WHERE h.handoff_id=?', (hid,)).fetchone()
        assert row[:5] == ('caller', 'subject', 'subject', 'operator', 1)
        assert row['credential_binding'] == context.credential_binding
    assert runtime[2].opens == len(runtime[2].native.sent) == 1


@pytest.mark.parametrize('reason', ['disabled', 'direct', 'grant_revoked', 'policy_cycle'])
def test_automation_cannot_claim_without_current_specific_authority(runtime, reason):
    service, hid, gid = prepare(runtime, strategy='direct' if reason == 'direct' else 'broadcast',
                                enable=reason != 'disabled')
    if reason in ('disabled', 'direct'):
        with pytest.raises(OktoNexusError):
            candidate(runtime, service, hid, gid)
    else:
        context = candidate(runtime, service, hid, gid)
        if reason == 'grant_revoked':
            with runtime[0][0].connection_factory.unit_of_work() as uow:
                uow.connection.execute('UPDATE runtime_execution_grants SET revoked_at=? WHERE grant_id=?',
                                       (runtime[0][0].clock.now_iso(), gid))
        else:
            assert save(runtime[0], agent='subject', broadcast_handoff_auto_claim=False).status_code == 200
            assert save(runtime[0], agent='subject', broadcast_handoff_auto_claim=True).status_code == 200
        with pytest.raises(OktoNexusError):
            commit(runtime, service, hid, gid, context)
    assert_unclaimed(runtime, hid, gid)


def test_principal_cannot_be_reused_for_other_handoff_action_or_authentication(runtime):
    service, hid, gid = prepare(runtime)
    context = candidate(runtime, service, hid, gid)
    other = work(runtime)
    with pytest.raises(OktoNexusError):
        commit(runtime, service, other, gid, context)
    # The public service delegates to the same scoped core; a composition must
    # not accidentally bypass the task binding by choosing the other entry.
    service._request_context_provider = lambda: context
    with pytest.raises(OktoNexusError):
        service.handoff_claim(workspace_id=workspace(runtime[0]), handoff_id=other,
            agent_id='subject', runtime_endpoint_id=runtime[1]['endpoint_id'],
            execution_grant_id=gid, idempotency_key=context.request_id)
    with pytest.raises(OktoNexusError):
        service.handoff_claim(workspace_id=workspace(runtime[0]), handoff_id=hid,
            agent_id='subject', runtime_endpoint_id=runtime[1]['endpoint_id'],
            execution_grant_id=gid, idempotency_key='different-attempt')
    access = service.runtime_work.access
    for action in ('send', 'open', 'read', 'admin'):
        with pytest.raises(OktoNexusError):
            with runtime[0][0].connection_factory.unit_of_work() as uow:
                access.authorize(context, action=action, endpoint_id=runtime[1]['endpoint_id'],
                    represented_agent_id='subject', workspace_id=workspace(runtime[0]), uow=uow)
    for forged in (replace(context, authentication_source='agent_key'),
                   replace(context, actor_agent_id='operator'), replace(context, trusted_local_operator=True),
                   replace(context, handoff_automation=None)):
        with pytest.raises(OktoNexusError):
            commit(runtime, service, hid, gid, forged)
    response = runtime[0][2].get('/api/v1/agents', headers={'Authorization': 'Bearer ' + context.credential_binding})
    assert response.status_code == 401
    assert_unclaimed(runtime, hid, gid)


def test_revocation_after_committed_claim_prevents_native_effect(runtime):
    setup = runtime[0]
    service, hid, gid = prepare(runtime)
    context = candidate(runtime, service, hid, gid)
    lock = setup[1].state.embedded_dispatch_owner.pump.send_lock
    setup[2].portal.call(lock.acquire)
    try:
        commit(runtime, service, hid, gid, context)
        assert save(setup, agent='subject', broadcast_handoff_auto_claim=False).status_code == 200
    finally:
        setup[2].portal.call(lock.release)
    deadline = time.monotonic() + 10
    while True:
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute('SELECT dispatch_state,last_error FROM execution_dispatch_outbox').fetchone()
        if row['dispatch_state'] == 'RESOLVED_TERMINAL':
            assert 'PERMISSION_DENIED' in row['last_error']
            break
        assert time.monotonic() < deadline, tuple(row)
        time.sleep(.02)
    assert runtime[2].opens == 0
