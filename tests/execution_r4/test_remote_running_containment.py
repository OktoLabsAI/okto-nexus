"""T30: stop deadlines never replace physical proof from a remote child."""
import asyncio
from dataclasses import replace
from functools import partial
from pathlib import Path

import pytest
from nexus_connector_core.capacity import capacity_reservation_id

from okto_nexus.adapters.inbound.http import executor_link
from okto_nexus.application.handoff_runtime_scheduler import HandoffScheduleLease
from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_candidates
from okto_nexus.domain.base import iso_plus
from test_binding_operator import onboarding
from test_handoff_executor_selection import bind, running_pair
from test_one_shot_runtime import query
from test_runtime_policy_defaults import save


@pytest.mark.parametrize('onboarding', ['connector-configured'], indirect=True)
@pytest.mark.parametrize('cause', ['grant_revoked', 'runtime_close'])
def test_running_remote_work_retains_slot_past_stop_timeout_until_physical_release(onboarding, tmp_path, monkeypatch, cause):
    from okto_nexus_connector.storage.state_store import StateStore
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    monkeypatch.setattr(executor_link, 'ExecutionLeaseService',
        partial(executor_link.ExecutionLeaseService, max_duration_ms=15000))
    deps, client, headers, proposal = onboarding
    binding = bind(client, headers, proposal, 'containment')
    setup = deps, client.app, client, headers
    assert save(setup, agent='subject', broadcast_handoff_auto_claim=True).status_code == 200
    grants = {}
    for actions in (['execute_work'], ['open', 'send', 'close']):
        response = client.post('/api/v1/harness/grants', headers=headers['operator'], json=dict(
            actor_agent_id='subject', endpoint_id=binding['endpoint_id'], actions=actions,
            max_executions=10, expires_at=iso_plus(deps.clock.now_iso(), 600)))
        assert response.status_code == 200, response.text
        grants[actions[0]] = response.json()['data']['grant_id']
    client.headers['host'] = '127.0.0.1:8000'
    records = [(binding, StateStore(tmp_path / 'connector-state.json'), tmp_path / 'remote-only' / 'codex.exe',
                tmp_path / 'remote-workspace', 'connector', 'register')]

    async def run():
        async with running_pair(onboarding, records, tmp_path) as command:
            async def until(predicate):
                async with asyncio.timeout(30):
                    while True:
                        state = await command(0, 'status')
                        if predicate(state):
                            return state
                        await asyncio.sleep(.03)

            def stage(operation_id):
                response = client.get('/v1/runtime/operations/' + operation_id, headers=headers['subject'])
                assert response.status_code == 200, response.text
                return response.json()['executor_stage']

            made = tool(client, headers['other']['Authorization'].removeprefix('Bearer '), 'handoff_create',
                dict(workspace_id=binding['workspace_id'], from_agent_id='other', visibility='eligible',
                     target={'strategy': 'broadcast'}, payload='Stop this running work without declaring false release'))
            assert made['ok'], made
            hid = made['data']['handoff_id']
            page = build_handoff_runtime_candidates(deps).prepare_page(
                HandoffScheduleLease(hid, binding['workspace_id'], 0, 'containment', 0, 0, ''), limit=4)
            assert len(page.attempt_ids) == 1
            attempts = build_handoff_runtime_attempts(deps)
            held = await attempts.reserve(page.attempt_ids[0])
            assert held.state == 'RESERVED'
            claimed = attempts.claim(page.attempt_ids[0])
            admitted = await build_capacity_admission(deps).consume(claimed.operation_id)
            await until(lambda state: state['sends'] == 1 and stage(admitted.consumption.turn_operation_id) == 'SUBMITTED')
            await command(0, 'hold_stop')
            close_id = None
            remote = deps.runtime_availability
            try:
                if cause == 'grant_revoked':
                    response = client.delete('/api/v1/harness/grants/' + grants['execute_work'], headers=headers['operator'])
                    assert response.status_code == 200, response.text
                else:
                    response = client.post('/v1/runtime/intents:resolve', headers=headers['subject'], json=dict(
                        client_intent_id='cancel-running-native', intent='runtime.close', binding_id=binding['binding_id'],
                        workspace_binding_id=binding['workspace_binding_id'], session_id=held.request.scope.session_id))
                    assert response.status_code == 200 and response.json()['can_submit'], response.text
                    resolved = response.json()
                    response = client.post('/v1/runtime/operations', headers=headers['subject'], json={
                        key: resolved[key] for key in ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')})
                    assert response.status_code == 202, response.text
                    close_id = resolved['operation_id']
                await until(lambda state: state['stopping'] == 1)
                assert (await remote.release_capacity(held.request, held.reservation.reservation_id, 'CANCELLED')).state == 'RELEASE_PENDING'
                # The grant-denial owner uses ShutdownPolicy(5,5). Wait past
                # both observation budgets with the same native close pending.
                await asyncio.sleep(11)
                pending = await command(0, 'status')
                assert pending['ready'] and pending['stopping'] == 1 and pending['stopped'] == 0
                assert pending['opens'] == pending['sends'] == 1
                assert (await remote.get_capacity_reservation(held.request)).state == 'RELEASE_PENDING'
                if close_id:
                    assert stage(close_id) != 'SUCCEEDED'
                else:
                    assert query(setup, 'SELECT state FROM execution_session_containment')[0][0] != 'RELEASED'
                contender = replace(held.request, attempt_id='while-stop-pending', affinity_key='sha256:' + 'a' * 64,
                    scope=replace(held.request.scope, session_id='while-stop-pending'))
                blocked = await remote.try_reserve_capacity(contender)
                assert blocked.reason == 'HOST_FULL', blocked
                assert (await remote.release_capacity(contender, capacity_reservation_id(contender), 'CANCELLED')).state == 'RELEASED'
            finally:
                await command(0, 'release_stop')
            await until(lambda state: state['stopped'] == 1 and (
                stage(close_id) == 'SUCCEEDED' if close_id else bool(query(setup,
                    "SELECT 1 FROM execution_session_containment WHERE state='RELEASED'"))))
            async with asyncio.timeout(15):
                while (await remote.release_capacity(held.request, held.reservation.reservation_id, 'CANCELLED')).state != 'RELEASED':
                    await asyncio.sleep(.03)
            fresh = replace(contender, attempt_id='after-confirmed-stop',
                scope=replace(contender.scope, session_id='after-confirmed-stop'))
            reusable = await remote.try_reserve_capacity(fresh)
            assert reusable.state == 'HELD', reusable
            assert (await remote.release_capacity(fresh, reusable.reservation_id, 'CANCELLED')).state == 'RELEASED'
            assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('CLAIMED', 1)
            assert query(setup, 'SELECT count(*) FROM execution_capacity_compensations')[0][0] == 0
            assert query(setup, 'SELECT count(*) FROM runtime_handoff_bindings')[0][0] == 1
            assert (await command(0, 'status'))['sends'] == 1

    asyncio.run(run())
