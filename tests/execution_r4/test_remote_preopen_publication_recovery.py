"""T24: lost publication commit replies must not strand a remote executor."""
import asyncio
from functools import partial
from pathlib import Path

import pytest
from nexus_connector_core import CoreError

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
@pytest.mark.parametrize('boundary', ['reserve', 'bind'])
@pytest.mark.parametrize('lost_ack', [False, True], ids=['acknowledged', 'lost-ack'])
def test_remote_preopen_publication_cut_reconciles_without_reexecuting(onboarding, tmp_path, monkeypatch, boundary, lost_ack):
    from okto_nexus_connector.storage.state_store import StateStore
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    from okto_nexus.application.execution_reconciliation import ExecutionReconciliation
    accept = ExecutionReconciliation.accept
    lost = []
    def lose_refusal_ack(self, report):
        response = accept(self, report)
        if lost_ack and report.get('preopen_refusals') and not lost:
            lost.append(report['preopen_refusals'][0]['receipt']['operation_id'])
            raise OSError('Synthetic lost acknowledgment after committed preopening recovery')
        return response
    monkeypatch.setattr(ExecutionReconciliation, 'accept', lose_refusal_ack)
    monkeypatch.setattr(executor_link, 'ExecutionLeaseService',
        partial(executor_link.ExecutionLeaseService, max_duration_ms=15000))
    deps, client, headers, proposal = onboarding
    binding = bind(client, headers, proposal, 'publication-recovery')
    setup = deps, client.app, client, headers
    assert save(setup, agent='subject', broadcast_handoff_auto_claim=True).status_code == 200
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none',consumption='exclusive'")
    for actions in (['execute_work'], ['open', 'send', 'close']):
        response = client.post('/api/v1/harness/grants', headers=headers['operator'], json=dict(
            actor_agent_id='subject', endpoint_id=binding['endpoint_id'], actions=actions,
            max_executions=10, expires_at=iso_plus(deps.clock.now_iso(), 600)))
        assert response.status_code == 200, response.text
    client.headers['host'] = '127.0.0.1:8000'
    records = [(binding, StateStore(tmp_path / 'connector-state.json'), tmp_path / 'remote-only' / 'codex.exe',
                tmp_path / 'remote-workspace', 'connector', 'register')]

    async def run():
        async with running_pair(onboarding, records, tmp_path) as command:
            before = await command(0, 'cut_publication_' + boundary)
            made = tool(client, headers['other']['Authorization'].removeprefix('Bearer '), 'handoff_create',
                dict(workspace_id=binding['workspace_id'], from_agent_id='other', visibility='eligible',
                     target={'strategy': 'broadcast'}, payload='Do not replay this admitted task after a lost commit reply'))
            assert made['ok'], made
            hid = made['data']['handoff_id']
            page = build_handoff_runtime_candidates(deps).prepare_page(
                HandoffScheduleLease(hid, binding['workspace_id'], 0, 'publication-recovery', 0, 0, ''), limit=4)
            assert len(page.attempt_ids) == 1
            attempts = build_handoff_runtime_attempts(deps)
            async def reserve_fresh(attempt_id):
                async with asyncio.timeout(30):
                    while True:
                        try:
                            return await attempts.reserve(attempt_id)
                        except CoreError as error:
                            if error.code != 'STALE_OBSERVATION':
                                raise
                            await asyncio.sleep(.05)
            held = await reserve_fresh(page.attempt_ids[0])
            assert held.state == 'RESERVED'
            committed = attempts.claim(page.attempt_ids[0])
            await build_capacity_admission(deps).consume(committed.operation_id)
            state = before
            try:
                async with asyncio.timeout(45):
                    while True:
                        state = await command(0, 'status')
                        assert state['opens'] == state['sends'] == 0, state
                        if (state['publication_cuts'] == 1 and state['ready']
                                and state['generation'] > before['generation']):
                            break
                        await asyncio.sleep(.1)
            except TimeoutError:
                pytest.fail('Remote publication recovery did not finish: ' + repr(state))
            assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('CLAIMED', 1)
            assert query(setup, 'SELECT count(*) FROM execution_capacity_compensations')[0][0] == 0
            assert query(setup, 'SELECT count(*) FROM runtime_handoff_bindings')[0][0] == 1
            current = await deps.runtime_availability.get_capacity_reservation(held.request)
            assert current.reservation_id == held.reservation.reservation_id
            assert current.state == 'RELEASED', current
            proofs = query(setup, 'SELECT operation_id FROM execution_preopen_refusals')
            assert len(proofs) == 1
            assert lost == ([proofs[0][0]] if lost_ack else [])
            old = query(setup, 'SELECT stage,possible_effect,retry_safe,error_code FROM execution_receipts WHERE operation_id=?',
                        (proofs[0][0],))
            assert [tuple(row) for row in old] == [('FAILED', 0, 1, 'PRE_EXECUTION_FENCED')]
            fresh = tool(client, headers['other']['Authorization'].removeprefix('Bearer '), 'handoff_create',
                dict(workspace_id=binding['workspace_id'], from_agent_id='other', visibility='eligible',
                     target={'strategy': 'broadcast'}, payload='New work after confirmed preopening recovery'))
            assert fresh['ok'], fresh
            # The reconnect ACK and a fresh capacity notification are distinct
            # messages. Drive the same stale-observation retry as the scheduler.
            async with asyncio.timeout(15):
                while True:
                    fresh_page = build_handoff_runtime_candidates(deps).prepare_page(
                        HandoffScheduleLease(fresh['data']['handoff_id'], binding['workspace_id'], 0,
                                             'fresh-recovery', 0, 0, ''), limit=4)
                    if fresh_page.attempt_ids:
                        break
                    assert fresh_page.reason == 'STALE_OBSERVATION', fresh_page
                    await asyncio.sleep(.05)
            assert len(fresh_page.attempt_ids) == 1
            assert (await reserve_fresh(fresh_page.attempt_ids[0])).state == 'RESERVED'
            fresh_claim = attempts.claim(fresh_page.attempt_ids[0])
            fresh_admission = await build_capacity_admission(deps).consume(fresh_claim.operation_id)
            async with asyncio.timeout(20):
                while True:
                    state = await command(0, 'status')
                    delivered = query(setup, "SELECT 1 FROM execution_receipts WHERE operation_id=? AND stage='SUBMITTED'",
                                      (fresh_admission.consumption.turn_operation_id,))
                    if state['sends'] == 1 and delivered:
                        break
                    await asyncio.sleep(.05)
            assert state['opens'] == state['sends'] == 1
            assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('CLAIMED', 1)

    asyncio.run(run())
