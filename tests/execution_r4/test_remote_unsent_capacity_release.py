"""Server pre-send refusal releases real remote capacity without native work."""
import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from nexus_connector_core import CoreError

from okto_nexus.application.handoff_runtime_scheduler import HandoffScheduleLease
from okto_nexus.application.handoff_runtime_service import HandoffRuntimeService
from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_candidates, build_handoff_runtime_scheduler
from okto_nexus.domain.base import iso_plus
from test_binding_operator import onboarding
from test_handoff_executor_selection import bind, running_pair
from test_one_shot_runtime import query
from test_runtime_policy_defaults import save


@pytest.mark.parametrize('onboarding', ['connector-configured'], indirect=True)
def test_remote_grant_revocation_after_consume_releases_same_ticket_without_open(onboarding, tmp_path, monkeypatch):
    from okto_nexus_connector.storage.state_store import StateStore
    from okto_nexus.adapters.outbound.sqlite.capacity_admissions import SqliteCapacityAdmissionRepository
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool

    deps, client, headers, proposal = onboarding
    binding = bind(client, headers, proposal, 'revocation')
    setup = deps, client.app, client, headers
    assert save(setup, agent='subject', broadcast_handoff_auto_claim=True).status_code == 200
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none',consumption='exclusive'")
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
    original = SqliteCapacityAdmissionRepository.consumed
    cuts = []
    def revoke_at_consumption_commit(self, uow, admission, observed):
        original(self, uow, admission, observed)
        cuts.append(admission.operation_id)
        # The next writer sees confirmed host consumption and revoked work
        # authority together, deterministically before dispatch authorization.
        uow.connection.execute('UPDATE runtime_execution_grants SET revoked_at=? WHERE grant_id=?',
                               (deps.clock.now_iso(), grants['execute_work']))
    monkeypatch.setattr(SqliteCapacityAdmissionRepository, 'consumed', revoke_at_consumption_commit)

    async def run():
        async with running_pair(onboarding, records, tmp_path) as command:
            made = tool(client, headers['other']['Authorization'].removeprefix('Bearer '), 'handoff_create',
                dict(workspace_id=binding['workspace_id'], from_agent_id='other', visibility='eligible',
                     target={'strategy': 'broadcast'}, payload='This work must not reach the provider'))
            assert made['ok'], made
            hid = made['data']['handoff_id']
            page = build_handoff_runtime_candidates(deps).prepare_page(
                HandoffScheduleLease(hid, binding['workspace_id'], 0, 'remote-revoke', 0, 0, ''), limit=4)
            assert len(page.attempt_ids) == 1
            attempts = build_handoff_runtime_attempts(deps)
            # The remote observation can be revalidated between candidate
            # selection and this read-only capacity assessment.
            async with asyncio.timeout(30):
                while True:
                    try:
                        held = await attempts.reserve(page.attempt_ids[0])
                        break
                    except CoreError as error:
                        if error.code != 'STALE_OBSERVATION':
                            raise
                        await asyncio.sleep(.05)
            assert held.state == 'RESERVED'
            committed = attempts.claim(page.attempt_ids[0])
            await build_capacity_admission(deps).consume(committed.operation_id)
            service = HandoffRuntimeService(build_handoff_runtime_scheduler(deps, acquisition_enabled=False))
            service.start()
            try:
                async with asyncio.timeout(20):
                    while not query(setup, "SELECT 1 FROM execution_capacity_admissions WHERE reason='UNSENT_DISPATCH_RELEASED'"):
                        await asyncio.sleep(.03)
                state = await command(0, 'status')
                assert state['ready'] and state['opens'] == state['sends'] == state['opening'] == 0
                original_ticket = await deps.runtime_availability.get_capacity_reservation(held.request)
                assert original_ticket.state == 'RELEASED'
                assert original_ticket.reservation_id == held.reservation.reservation_id
                assert cuts == [committed.operation_id]
                assert attempts.claim(page.attempt_ids[0]).operation_id == committed.operation_id
                assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('CLAIMED', 1)
                assert query(setup, 'SELECT count(*) FROM execution_capacity_compensations')[0][0] == 0
                # Verify physical reuse through the remote port, not a UI flag.
                fresh = replace(held.request, attempt_id='after-revoked-ticket',
                    scope=replace(held.request.scope, session_id='fresh-after-revocation'))
                available = await deps.runtime_availability.try_reserve_capacity(fresh)
                assert available.state == 'HELD', available
                assert (await deps.runtime_availability.release_capacity(fresh, available.reservation_id, 'CANCELLED')).state == 'RELEASED'
            finally:
                await service.aclose()
    asyncio.run(run())
