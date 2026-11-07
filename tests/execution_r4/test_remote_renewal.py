"""Remote renewal over real HTTP, IPC, WebSocket, Connector and Core storage.

Native/provider peers and installation probing are explicitly synthetic. These
cases do not qualify Windows services, personal vaults, TLS or real-provider M1.
"""
import asyncio
from copy import deepcopy

import httpx
import pytest

import test_pr34_remediation as tcp
from okto_nexus.application.terminal_connection import ConnectionError, PREFIX
from remote_renewal_helpers import RemoteProject
from okto_nexus_connector.cli.commands import connect
from okto_nexus_connector.cli.main import build_parser
from okto_nexus_connector.services import remote_setup

runtime_source = tcp.runtime


class RedactedRuntime(tuple):
    def __repr__(self):
        return '<isolated HTTP runtime; synthetic credentials redacted>'


@pytest.fixture
def runtime(runtime_source):
    return RedactedRuntime(runtime_source)


@pytest.mark.parametrize('disabled_state', ['exhausted', 'expired'])
def test_remote_renewal_lost_issue_recovers_one_grant_without_migrating_session(runtime, tmp_path, monkeypatch, disabled_state):
    project = RemoteProject(runtime, tmp_path, monkeypatch, actions=1 if disabled_state == 'exhausted' else 4)

    async def run():
        try:
            await project.start()
            first = await project.send_and_complete(request_id='first-remote-work')
            if disabled_state == 'expired':
                # Controlled temporal fixture: shorten only this grant to the
                # current instant after its first real operation. No ticket,
                # lease, clock or admission policy is extended or bypassed.
                with project.deps.connection_factory.unit_of_work() as uow:
                    uow.connection.execute('UPDATE runtime_execution_grants SET expires_at=?',
                        (project.deps.clock.now_iso(),))
            original_grant, = project.rows('runtime_execution_grants')
            assert original_grant['used_executions'] == 1
            assert original_grant['max_executions'] == (1 if disabled_state == 'exhausted' else 4)
            leases = deepcopy(project.rows('execution_leases'))
            operations = deepcopy(project.rows('execution_operations'))
            sessions = deepcopy(project.rows('execution_sessions'))
            flow = project.work()
            review = await asyncio.to_thread(flow.authorization_review, minutes=30, max_executions=4)
            assert review['can_issue'] and review['current_grants'][0]['state'] == disabled_state
            assert project.rows('runtime_execution_grants') == [original_grant]
            project.lose_next = PREFIX + '/connections/authorizations:issue'
            with pytest.raises(ConnectionError) as lost:
                await asyncio.to_thread(flow.authorize, approval=review['review_revision'])
            assert lost.value.possible_effect
            assert project.work().document['authorization']['state'] == 'submitted'
            committed, = project.rows('connection_authorization_receipts')
            before = len(project.calls)
            receipt = await asyncio.to_thread(project.work().authorize)
            assert receipt['client_request_id'] == committed['client_request_id']
            assert not any(path.endswith(':issue') for _, path in project.calls[before:])
            assert len(project.rows('runtime_execution_grants')) == 2
            assert project.rows('execution_operations') == operations
            assert project.rows('execution_leases') == leases
            assert project.rows('execution_sessions') == sessions
            assert len(project.native.opened) == 1
            # Explicit containment is separate from renewal; the preset's one
            # session slot is not silently moved to the new grant.
            await project.close_session(first['scope']['session_id'])
            second = await project.send_and_complete(request_id='second-explicit-remote-work')
            assert second['scope']['session_id'] != first['scope']['session_id']
            new_grant = receipt['result']['grant']['grant_id']
            current = project.rows('execution_leases')
            assert {r['grant_id'] for r in current if r['session_id'] == first['scope']['session_id']} == {original_grant['grant_id']}
            assert {r['grant_id'] for r in current if r['session_id'] == second['scope']['session_id']} == {new_grant}
            assert len(project.rows('connection_authorization_receipts')) == 1
            assert len(project.native.opened) == 2
            assert all(len(native.sent) == 1 for native, _, _ in project.native.opened.values())
            project.assert_redacted()
        finally:
            await project.close()

    asyncio.run(run())


def test_rotated_credential_reconnects_completed_setup_and_fences_stale_review_and_tickets(runtime, tmp_path, monkeypatch):
    project = RemoteProject(runtime, tmp_path, monkeypatch)

    async def run():
        try:
            await project.start()
            first = await project.send_and_complete(request_id='before-rotation')
            await project.close_session(first['scope']['session_id'])
            review = await asyncio.to_thread(project.work().authorization_review)
            assert review['can_issue']
            old_key = project.key
            lane = project.control.execution.lanes[project.binding['binding_id']]
            old_ticket = lane.ticket.ticket
            frame = deepcopy(project.receipt_frames[-1])
            receipt_url = '/v1/runtime/operations/' + frame['operation_id'] + '/receipts'
            async with httpx.AsyncClient(base_url=project.origin) as wire:
                replay = await wire.post(receipt_url, json=frame, headers={'Authorization': 'Bearer ' + old_ticket})
                assert replay.status_code == 200 and replay.json()['reused'], replay.text
            original_root = deepcopy(remote_setup.load(project.store, 'renewal-root'))
            original_binding = deepcopy(project.rows('execution_bindings'))
            original_commits = deepcopy(project.rows('connection_setup_commits'))
            original_proposals = deepcopy(project.rows('execution_proposals'))
            me = await project.rotate(monkeypatch)
            assert (me.server_id, me.agent_id) == (project.server_id, project.agent_id)
            async with httpx.AsyncClient(base_url=project.origin) as wire:
                refused = await wire.get('/v1/connections/me', headers={'Authorization': 'Bearer ' + old_key})
                assert refused.status_code == 401
                stale = await wire.post(receipt_url, json=frame, headers={'Authorization': 'Bearer ' + old_ticket})
                assert stale.status_code in (401, 403), stale.text
            with pytest.raises(ConnectionError) as changed:
                await asyncio.to_thread(project.work().authorize, approval=review['review_revision'])
            assert changed.value.code == 'CONFLICT' and not changed.value.possible_effect
            assert project.rows('connection_authorization_receipts') == []
            assert len(project.rows('runtime_execution_grants')) == 1
            args = build_parser().parse_args(['connect', '--project', str(project.project)])
            reused = await connect.run_connect(args, project.output, project.root)
            assert reused['saved'], reused
            assert project.rows('execution_bindings') == original_binding
            assert project.rows('connection_setup_commits') == original_commits
            assert project.rows('execution_proposals') == original_proposals
            assert remote_setup.load(project.store, 'renewal-root') == original_root
            assert len(project.probes) == 1 and len(project.native.opened) == 1
            assert project.store.load().identity_by_alias('project').credential_epoch == me.credential_epoch
            assert original_root['handoff']['bootstrap']['credential_epoch'] < me.credential_epoch
            refreshed = await asyncio.to_thread(project.work().authorization_review)
            assert refreshed['can_issue'] and refreshed['current_grants'][0]['state'] == 'superseded'
            receipt = await asyncio.to_thread(project.work().authorize, approval=refreshed['review_revision'])
            assert receipt['state'] == 'authorization_committed'
            await project.eventually(lambda: project.control.status()['execution_ready'] and
                project.control.execution.lanes[project.binding['binding_id']].identity.credential_epoch == me.credential_epoch)
            await project.inventory_ready()
            second = await project.send_and_complete(request_id='after-rotation-explicit')
            assert second['scope']['session_id'] != first['scope']['session_id']
            leases = project.rows('execution_leases')
            assert {row['grant_id'] for row in leases if row['session_id'] == second['scope']['session_id']} == {receipt['result']['grant']['grant_id']}
            project.assert_redacted()
        finally:
            await project.close()

    asyncio.run(run())


def test_remote_revocation_keeps_recovered_receipt_historical_and_participant_cannot_renew(runtime, tmp_path, monkeypatch):
    project = RemoteProject(runtime, tmp_path, monkeypatch)

    async def run():
        try:
            await project.start()
            grant, = project.rows('runtime_execution_grants')
            await asyncio.to_thread(project.call, 'DELETE', '/api/v1/harness/grants/' + grant['grant_id'])
            review = await asyncio.to_thread(project.work().authorization_review)
            assert review['can_issue'] and review['current_grants'][0]['state'] == 'revoked'
            async with httpx.AsyncClient(base_url=project.origin) as wire:
                for route, body in (
                    ('review', dict(binding_id=project.binding['binding_id'], client_request_id='participant-renewal')),
                    ('issue', review['request']), ('recover', review['request'])):
                    denied = await wire.post(PREFIX + '/connections/authorizations:' + route,
                        json=body, headers={'Authorization': 'Bearer ' + project.key})
                    assert denied.status_code == 403, denied.text
            project.lose_next = PREFIX + '/connections/authorizations:issue'
            with pytest.raises(ConnectionError) as lost:
                await asyncio.to_thread(project.work().authorize, approval=review['review_revision'])
            assert lost.value.possible_effect
            current = next(row for row in project.rows('runtime_execution_grants') if row['grant_id'] != grant['grant_id'])
            await asyncio.to_thread(project.call, 'DELETE', '/api/v1/harness/grants/' + current['grant_id'])
            before = deepcopy(project.rows('runtime_execution_grants'))
            historical = await asyncio.to_thread(project.work().authorize)
            assert historical['result']['grant']['grant_id'] == current['grant_id']
            assert project.rows('runtime_execution_grants') == before
            assert all(row['revoked_at'] for row in before)
            assert len(project.rows('connection_authorization_receipts')) == 1
            assert not project.native.opened and not project.rows('execution_operations')
            project.assert_redacted()
        finally:
            await project.close()

    asyncio.run(run())
