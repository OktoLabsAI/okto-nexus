"""A remote preparation failure closes only its pending canonical session."""
import asyncio
from pathlib import Path
import pytest

from starlette.testclient import TestClient
from nexus_connector_core import (
    R4_PREVIEW_REVISION, OperationKey, prepare_r4_startup_refusal,
    persist_r4_startup_refusal, project_r4_bound_receipt,
)
from nexus_connector_core.journal import open_journal
from nexus_connector_core.startup_refusal_link import (
    STARTUP_REFUSAL_REVISION, encode_startup_refusal,
)
from okto_nexus.application.execution_dispatch import reserve_execution_dispatch, begin_execution_send
from okto_nexus.application.execution_leases import ExecutionLeaseService
from okto_nexus.application.handoff_runtime_scheduler import HandoffScheduleLease
from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_candidates
from okto_nexus.adapters.outbound.sqlite.execution_tickets import issue_execution_ticket
from test_ns09 import setup_authority, negotiate, admit
from test_binding_operator import onboarding
from test_handoff_executor_selection import bind, running_pair
from test_one_shot_runtime import query
from test_runtime_policy_defaults import save


def test_prelease_startup_refusal_requires_current_control_channel(tmp_path, monkeypatch):
    deps, app, access, _, _, _, info, revisions, link_ticket, lane_ticket, server_id, executor_id = setup_authority(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://127.0.0.1:8202', raise_server_exceptions=False) as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor_id}/link',
                headers={'Authorization': f'Bearer {link_ticket}'}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane_ticket, server_id, executor_id,
                control_capabilities=(STARTUP_REFUSAL_REVISION,))
            assert STARTUP_REFUSAL_REVISION in channel.control_capabilities
            resolved = admit(deps, app)
            reservation = reserve_execution_dispatch(deps.connection_factory, server_id=server_id,
                executor_id=executor_id, remote_ready=True)
            opening = begin_execution_send(deps.connection_factory, reservation=reservation,
                remote_ready=True, fresh_publications=app.state.inventory_fresh_publications, access=access)

            async def fact():
                journal = await open_journal(tmp_path / 'prelease-core.db')
                try:
                    refusal = prepare_r4_startup_refusal(opening.frame)
                    receipt = await persist_r4_startup_refusal(journal, refusal)
                    return refusal, project_r4_bound_receipt(refusal['binding'], receipt,
                        key=OperationKey(server_id, executor_id, resolved['operation_id']), receipt_revision=1)
                finally:
                    await journal.aclose()
            refusal, receipt = asyncio.run(fact())
            ticket = issue_execution_ticket(deps.connection_factory, server_id=server_id,
                executor_id=executor_id, agent_id='subject', binding_id='binding',
                scopes=frozenset({'receipt:publish'})).ticket
            path = f'/v1/runtime/operations/{resolved["operation_id"]}/receipts'
            assert client.post(path, json=receipt,
                headers={'Authorization': f'Bearer {ticket}'}).status_code == 409
            report = dict(contract_revision=STARTUP_REFUSAL_REVISION, type='startup.refuse',
                request_id='startup-refusal-1', server_id=server_id, executor_id=executor_id,
                connection_id=channel.connection_id,
                connection_generation=channel.connection_generation,
                refusal=refusal, receipt=receipt, capacity=None, native_absent=True)
            for _ in range(2):
                ws.send_text(encode_startup_refusal(report).decode())
                ack = ws.receive_json()
                assert ack['type'] == 'startup.refuse.accepted'
                assert ack['request'] == report
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert tuple(uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()) == ('CLOSED', 'CLOSED')
                assert uow.connection.execute('SELECT count(*) FROM execution_receipts').fetchone()[0] == 1
                assert uow.connection.execute('SELECT control_state FROM execution_executors').fetchone()[0] == 'CONTROL_READY'


def test_remote_failed_preparation_receipt_closes_pending_session_without_disconnect(tmp_path, monkeypatch):
    deps, app, access, _, grant, _, info, revisions, link_ticket, lane_ticket, server_id, executor_id = setup_authority(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://127.0.0.1:8202', raise_server_exceptions=False) as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor_id}/link',
                headers={'Authorization': f'Bearer {link_ticket}'}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane_ticket, server_id, executor_id)
            resolved = admit(deps, app)
            reservation = reserve_execution_dispatch(deps.connection_factory, server_id=server_id,
                executor_id=executor_id, remote_ready=True)
            opening = begin_execution_send(deps.connection_factory, reservation=reservation, remote_ready=True,
                fresh_publications=app.state.inventory_fresh_publications, access=access)
            service = ExecutionLeaseService(factory=deps.connection_factory, access=access,
                fresh_publications=app.state.inventory_fresh_publications)
            request = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='lease.renew',
                request_id='startup', grant_id=grant['grant_id'], expected_lease_serial=0,
                scope=resolved['scope'], connection_id=channel.connection_id,
                connection_generation=channel.connection_generation, purpose='initial')
            lease = service.issue(request, channel=channel)
            applied = {k: lease[k] for k in ('protocol_major', 'contract_revision', 'request_id',
                'lease_id', 'lease_serial', 'grant_id', 'scope')}
            applied.update(type='lease.applied', connection_id=channel.connection_id,
                connection_generation=channel.connection_generation, application_stage='INSTALLED')
            service.applied(applied, channel=channel)

            async def fact():
                journal = await open_journal(tmp_path / 'startup-core.db')
                try:
                    refusal = prepare_r4_startup_refusal(opening.frame)
                    receipt = await persist_r4_startup_refusal(journal, refusal)
                    return project_r4_bound_receipt(refusal['binding'], receipt,
                        key=OperationKey(server_id, executor_id, resolved['operation_id']), receipt_revision=1)
                finally:
                    await journal.aclose()
            receipt = asyncio.run(fact())
            ticket = issue_execution_ticket(deps.connection_factory, server_id=server_id,
                executor_id=executor_id, agent_id='subject', binding_id='binding',
                scopes=frozenset({'receipt:publish'})).ticket
            path = f'/v1/runtime/operations/{resolved["operation_id"]}/receipts'
            headers = {'Authorization': f'Bearer {ticket}'}
            for forged in (dict(receipt, possible_effect=True, retry_safe=False),
                           dict(receipt, connection_generation=channel.connection_generation + 1)):
                assert client.post(path, json=forged, headers=headers).status_code == 409
            response = client.post(path, json=receipt, headers=headers)
            assert response.status_code == 200, response.text
            assert client.post(path, json=receipt, headers=headers).json()['reused']
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert tuple(uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()) == ('CLOSED', 'CLOSED')
                assert uow.connection.execute('SELECT control_state FROM execution_executors').fetchone()[0] == 'CONTROL_READY'
                assert uow.connection.execute('SELECT count(*) FROM execution_receipts').fetchone()[0] == 1


@pytest.mark.parametrize('onboarding', ['connector-configured'], indirect=True)
@pytest.mark.parametrize('failure', ['prepare', 'candidate'])
def test_remote_failed_preparation_releases_capacity_and_keeps_next_work_available(onboarding, tmp_path, monkeypatch, failure):
    from okto_nexus_connector.storage.state_store import StateStore
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    deps, client, headers, proposal = onboarding
    binding = bind(client, headers, proposal, 'startup-refusal')
    setup = deps, client.app, client, headers
    assert save(setup, agent='subject', broadcast_handoff_auto_claim=True).status_code == 200
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none',consumption='exclusive'")
    from okto_nexus.domain.base import iso_plus
    for actions in (['execute_work'], ['open', 'send', 'close']):
        response = client.post('/api/v1/harness/grants', headers=headers['operator'], json=dict(
            actor_agent_id='subject', endpoint_id=binding['endpoint_id'], actions=actions,
            max_executions=10, expires_at=iso_plus(deps.clock.now_iso(), 600)))
        assert response.status_code == 200, response.text
    client.headers['host'] = '127.0.0.1:8000'
    records = [(binding, StateStore(tmp_path/'connector-state.json'),
        tmp_path/'remote-only'/'codex.exe', tmp_path/'remote-workspace', 'connector', 'register')]

    async def run():
        async with running_pair(onboarding, records, tmp_path) as command:
            await command(0, 'fail_next_' + failure)
            attempts = build_handoff_runtime_attempts(deps)
            for ordinal in (0, 1):
                made = tool(client, headers['other']['Authorization'].removeprefix('Bearer '),
                    'handoff_create', dict(workspace_id=binding['workspace_id'], from_agent_id='other',
                        visibility='eligible', target={'strategy': 'broadcast'},
                        payload='Startup failure' if ordinal == 0 else 'Healthy follow-up'))
                assert made['ok'], made
                hid = made['data']['handoff_id']
                async with asyncio.timeout(15):
                    while True:
                        page = build_handoff_runtime_candidates(deps).prepare_page(
                            HandoffScheduleLease(hid, binding['workspace_id'], 0,
                                'startup-refusal', 0, 0, ''), limit=4)
                        if page.attempt_ids:
                            break
                        assert page.reason == 'STALE_OBSERVATION', page
                        await asyncio.sleep(.05)
                assert len(page.attempt_ids) == 1
                held = await attempts.reserve(page.attempt_ids[0])
                assert held.state == 'RESERVED'
                claimed = attempts.claim(page.attempt_ids[0])
                consumed = await build_capacity_admission(deps).consume(claimed.operation_id)
                async with asyncio.timeout(35):
                    while True:
                        state = await command(0, 'status')
                        receipt = query(setup, 'SELECT stage,error_code,possible_effect FROM execution_receipts '
                            'WHERE operation_id=?', (consumed.consumption.turn_operation_id,))
                        opening = query(setup, 'SELECT operation_id,stage,error_code,possible_effect FROM '
                            'execution_receipts WHERE operation_id IN (SELECT open_operation_id FROM '
                            'execution_sessions WHERE session_id=?)', (held.request.scope.session_id,))
                        if opening and (ordinal == 0 or receipt):
                            break
                        await asyncio.sleep(.05)
                if ordinal == 0:
                    assert state['preparation_failures' if failure == 'prepare' else 'candidate_failures'] == 1 and state['ready']
                    assert state['opens'] == state['sends'] == 0
                    assert opening[0][1:] == ('FAILED', 'PREPARATION_FAILED', 0)
                    assert query(setup, 'SELECT status FROM delivery_outbox WHERE operation_id=?',
                        (claimed.operation_id,))[0][0] == 'FAILED_FINAL'
                    assert query(setup, 'SELECT lifecycle_state FROM execution_sessions '
                        'WHERE session_id=?', (held.request.scope.session_id,))[0][0] == 'CLOSED'
                    released = await deps.runtime_availability.get_capacity_reservation(held.request)
                    assert released.state == 'RELEASED'
                else:
                    assert state['opens'] == state['sends'] == 1
                    assert opening[0][1] == 'SUBMITTED'
                    assert receipt[0][0] == 'SUBMITTED'
                    assert state['ready']
    asyncio.run(run())
