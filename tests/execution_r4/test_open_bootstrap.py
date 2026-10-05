"""Opening bootstrap authority, durable fencing, and lease application faults."""

import json

from fastapi.testclient import TestClient
import pytest

from nexus_connector_core import R4_PREVIEW_REVISION
from okto_nexus.application.execution_dispatch import (
    AuthorizedOpenBootstrap, begin_execution_send, reserve_execution_dispatch,
)
from okto_nexus.application.execution_leases import ExecutionChannel, ExecutionLeaseService
from okto_nexus.domain.base import iso_plus
from okto_nexus.errors import OktoNexusError

from test_ns09 import admit, negotiate, setup_authority


@pytest.fixture
def opening(tmp_path, monkeypatch, request):
    options = getattr(request, "param", None)
    options = options if isinstance(options, dict) else {"trust_mode": options}
    state = setup_authority(tmp_path, monkeypatch, **options)
    deps, app, access, operator, grant, candidate, info, revisions, link, lane, server, executor = state
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor}/link',
                headers={'Authorization': f'Bearer {link}'}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane, server, executor)
            resolution = admit(deps, app)
            reservation = reserve_execution_dispatch(deps.connection_factory,
                server_id=server, executor_id=executor, remote_ready=True)
            app.state.test_opening_socket = ws
            app.state.test_opening_ticket = link
            yield deps, app, access, operator, grant, channel, resolution, reservation


def begin(state):
    deps, app, access, _, _, _, _, reservation = state
    return begin_execution_send(deps.connection_factory, reservation=reservation,
        remote_ready=True, fresh_publications=app.state.inventory_fresh_publications, access=access)


@pytest.mark.parametrize('change', [
    'grant_revoked', 'open_not_granted', 'ticket_revoked', 'inventory_stale',
    'profile_disabled', 'subject_policy', 'connection_changed', 'lease_state_changed',
])
def test_open_bootstrap_revalidates_authority_after_reservation(opening, change):
    deps, app, access, operator, grant, channel, resolution, reservation = opening
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        if change == 'grant_revoked':
            conn.execute('UPDATE runtime_execution_grants SET revoked_at=?', (deps.clock.now_iso(),))
        elif change == 'open_not_granted':
            conn.execute('UPDATE runtime_execution_grants SET actions=?', (json.dumps(['send']),))
        elif change == 'ticket_revoked':
            conn.execute("UPDATE execution_link_tickets SET revoked_at=? WHERE binding_id IS NOT NULL",
                         (deps.clock.now_iso(),))
        elif change == 'inventory_stale':
            app.state.inventory_fresh_publications.clear()
        elif change == 'profile_disabled':
            conn.execute('UPDATE runtime_profiles SET enabled=0')
        elif change == 'subject_policy':
            conn.execute("UPDATE agents SET permissions=? WHERE agent_id='subject'",
                         (json.dumps({'messages': {'send_direct': False}}),))
        elif change == 'connection_changed':
            conn.execute("UPDATE execution_executors SET owner_instance_id='other-owner',generation=generation+1")
        else:
            conn.execute("UPDATE execution_sessions SET lease_state='LEASE_PENDING'")
    with pytest.raises(OktoNexusError):
        begin(opening)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert tuple(uow.connection.execute(
            'SELECT dispatch_state,dispatch_phase,dispatch_grant_id FROM execution_dispatch_outbox').fetchone()) == (
                'RESERVED', None, None)
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_leases').fetchone()[0] == 0


def test_open_bootstrap_pins_grant_and_applied_ack_commits_atomically(opening):
    deps, app, access, operator, original, channel, resolution, reservation = opening
    sent = begin(opening)
    assert isinstance(sent, AuthorizedOpenBootstrap)
    service = ExecutionLeaseService(factory=deps.connection_factory, access=access,
                                    fresh_publications=app.state.inventory_fresh_publications)
    replacement = access.issue(operator, actor_agent_id='subject', endpoint_id='ep',
        actions=['open'], expires_at=iso_plus(deps.clock.now_iso(), 600))
    request = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='lease.renew',
        request_id='initial', grant_id=replacement['grant_id'], expected_lease_serial=0,
        scope=sent.scope, connection_id=channel.connection_id,
        connection_generation=channel.connection_generation, purpose='initial')
    with pytest.raises(OktoNexusError, match='does not match the dispatched operation'):
        service.issue(request, channel=channel)
    request['grant_id'] = sent.grant_id
    grant = service.issue(request, channel=channel)
    ack = {k: grant[k] for k in ('protocol_major', 'contract_revision', 'request_id',
                                'lease_id', 'lease_serial', 'grant_id', 'scope')}
    ack.update(type='lease.applied', application_stage='INSTALLED',
               connection_id=channel.connection_id, connection_generation=channel.connection_generation)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER reject_applied_lease BEFORE UPDATE OF status ON execution_leases "
                               "WHEN NEW.status='ACTIVE' BEGIN SELECT RAISE(ABORT,'injected application failure'); END")
    with pytest.raises(Exception, match='injected application failure'):
        service.applied(ack, channel=channel)
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        assert tuple(conn.execute('SELECT status,applied_at FROM execution_leases').fetchone()) == ('ISSUED', None)
        assert conn.execute('SELECT lease_state FROM execution_sessions').fetchone()[0] == 'LEASE_PENDING'
        assert tuple(conn.execute('SELECT dispatch_phase,lease_id FROM execution_dispatch_outbox').fetchone()) == (
            'OPEN_AUTHORIZED_PENDING_LEASE', None)
        conn.execute('DROP TRIGGER reject_applied_lease')
    service.applied(ack, channel=channel)
    service.applied(ack, channel=channel)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert tuple(uow.connection.execute(
            'SELECT dispatch_state,dispatch_phase,dispatch_grant_id,lease_id,lease_serial FROM execution_dispatch_outbox').fetchone()) == (
                'SENDING', 'LEASE_AUTHORIZED', sent.grant_id, grant['lease_id'], 1)
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_leases').fetchone()[0] == 1


def test_open_bootstrap_cannot_move_initial_lease_to_another_connection(opening):
    deps, app, access, _, _, channel, resolution, _ = opening
    sent = begin(opening)
    # Simulate a replacement owner that has independently reached control and
    # lane readiness. It still cannot take the already dispatched opening.
    replacement = ExecutionChannel(channel.server_id, channel.executor_id, 'replacement', channel.connection_generation + 1)
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        conn.execute('UPDATE execution_executors SET owner_instance_id=?,generation=? WHERE executor_id=?',
                     (replacement.connection_id, replacement.connection_generation, channel.executor_id))
        conn.execute('UPDATE execution_control_lanes SET connection_id=?,connection_generation=?',
                     (replacement.connection_id, replacement.connection_generation))
        conn.execute('UPDATE execution_link_tickets SET bound_connection_id=? WHERE binding_id IS NOT NULL',
                     (replacement.connection_id,))
    service = ExecutionLeaseService(factory=deps.connection_factory, access=access,
                                    fresh_publications=app.state.inventory_fresh_publications)
    request = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='lease.renew',
        request_id='replacement', grant_id=sent.grant_id, expected_lease_serial=0,
        scope=sent.scope, connection_id=replacement.connection_id,
        connection_generation=replacement.connection_generation, purpose='initial')
    with pytest.raises(OktoNexusError, match='belongs to a different connection'):
        service.issue(request, channel=replacement)
