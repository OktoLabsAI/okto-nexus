"""T27: actual Connector ledger expiry, delayed consume and lost reply."""
import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from nexus_connector_core import CoreError

from okto_nexus.adapters.outbound.sqlite.handoff_runtime_candidates import SqliteHandoffCandidateRepository
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
@pytest.mark.parametrize('cut', ['before_lookup', 'before_consume', 'lost_consume_reply'])
def test_expired_remote_ticket_cannot_execute_and_recovers_original_identity(onboarding, tmp_path, monkeypatch, cut):
    from okto_nexus_connector.storage.state_store import StateStore
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool

    deps, client, headers, proposal = onboarding
    binding = bind(client, headers, proposal, 'expiry')
    setup = deps, client.app, client, headers
    assert save(setup, agent='subject', broadcast_handoff_auto_claim=True).status_code == 200
    for actions in (['execute_work'], ['open', 'send', 'close']):
        response = client.post('/api/v1/harness/grants', headers=headers['operator'], json=dict(
            actor_agent_id='subject', endpoint_id=binding['endpoint_id'], actions=actions,
            max_executions=10, expires_at=iso_plus(deps.clock.now_iso(), 600)))
        assert response.status_code == 200, response.text
    client.headers['host'] = '127.0.0.1:8000'
    records = [(binding, StateStore(tmp_path / 'connector-state.json'), tmp_path / 'remote-only' / 'codex.exe',
                tmp_path / 'remote-workspace', 'connector', 'register')]
    original_request = SqliteHandoffCandidateRepository.request

    def short_request(self, *args, **kwargs):
        # Persist this exact request before reservation. Do not edit a ticket,
        # mock the host clock or fabricate an expired response.
        return replace(original_request(self, *args, **kwargs), ttl_ms=2000)

    monkeypatch.setattr(SqliteHandoffCandidateRepository, 'request', short_request)

    async def run():
        async with running_pair(onboarding, records, tmp_path) as command:
            made = tool(client, headers['other']['Authorization'].removeprefix('Bearer '), 'handoff_create',
                dict(workspace_id=binding['workspace_id'], from_agent_id='other', visibility='eligible',
                     target={'strategy': 'broadcast'}, payload='Expired capacity must never start this work'))
            assert made['ok'], made
            hid = made['data']['handoff_id']
            page = build_handoff_runtime_candidates(deps).prepare_page(
                HandoffScheduleLease(hid, binding['workspace_id'], 0, 'remote-expiry', 0, 0, ''), limit=4)
            assert len(page.attempt_ids) == 1
            attempts = build_handoff_runtime_attempts(deps)
            held = await attempts.reserve(page.attempt_ids[0])
            assert held.state == 'RESERVED'
            claimed = attempts.claim(page.attempt_ids[0])
            remote = deps.runtime_availability
            calls = []

            class DelayedTransport:
                async def get_capacity_reservation(self, request):
                    if cut == 'before_lookup':
                        await asyncio.sleep(2.1)
                    observed = await remote.get_capacity_reservation(request)
                    if cut != 'before_lookup':
                        assert observed.state == 'HELD', observed
                    return observed

                async def consume_capacity(self, request, reservation_id, consumption):
                    calls.append((request, reservation_id, consumption))
                    await asyncio.sleep(2.1)
                    observed = await remote.consume_capacity(request, reservation_id, consumption)
                    assert observed.state == 'EXPIRED_UNCONSUMED' and observed.consumption is None
                    if cut == 'lost_consume_reply':
                        raise TimeoutError('Real remote expiry committed, reply lost')
                    return observed

            transfer = build_capacity_admission(deps, capacity=DelayedTransport())
            if cut == 'lost_consume_reply':
                with pytest.raises(TimeoutError):
                    await transfer.consume(claimed.operation_id)
                assert query(setup, 'SELECT state FROM execution_capacity_admissions')[0][0] == 'NEEDS_RECONCILIATION'
                assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('CLAIMED', 1)
                assert query(setup, 'SELECT count(*) FROM execution_capacity_compensations')[0][0] == 0
                transfer = build_capacity_admission(deps)
            result = await transfer.consume(claimed.operation_id)
            assert result.state == 'CANCELLED_NO_EFFECT'
            assert result.reservation.state == 'EXPIRED_UNCONSUMED'
            assert result.reservation.reservation_id == held.reservation.reservation_id
            assert result.reservation.consumption is None
            assert len(calls) == int(cut != 'before_lookup')
            assert not attempts.get(page.attempt_ids[0]).active
            assert attempts.get(page.attempt_ids[0]).operation_id == claimed.operation_id
            assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('OPEN', 1)
            assert query(setup, 'SELECT count(*) FROM execution_capacity_compensations')[0][0] == 1
            assert set(row[0] for row in query(setup, 'SELECT admission_state FROM execution_operations')) == {'RESOLVED_TERMINAL'}
            assert await transfer.consume(claimed.operation_id) == result
            # A delayed frame with the exact original identity cannot resurrect
            # the expired ticket after the Server has reopened the handoff.
            with pytest.raises(CoreError, match='RECOVERING'):
                await remote.consume_capacity(held.request, held.reservation.reservation_id, result.consumption)
            old = await remote.get_capacity_reservation(held.request)
            assert old.state == 'EXPIRED_UNCONSUMED' and old.consumption is None
            state = await command(0, 'status')
            assert state['ready'] and state['opens'] == state['sends'] == state['opening'] == 0
            fresh = replace(held.request, attempt_id='after-expiry',
                            scope=replace(held.request.scope, session_id='after-expiry'))
            reusable = await remote.try_reserve_capacity(fresh)
            assert reusable.state == 'HELD', reusable
            assert (await remote.release_capacity(fresh, reusable.reservation_id, 'CANCELLED')).state == 'RELEASED'

    asyncio.run(run())
