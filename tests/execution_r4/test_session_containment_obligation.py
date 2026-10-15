"""A correlated denial persists the exact obligation without stopping siblings."""
import json
import sqlite3
from contextlib import contextmanager

import pytest
from starlette.testclient import TestClient
from nexus_connector_core import R4_PREVIEW_REVISION, encode_r4_frame
from nexus_connector_core.lease_denial import LEASE_DENIAL_REVISION

from okto_nexus.application.execution_leases import ExecutionChannel, ExecutionLeaseService
from okto_nexus.bootstrap.execution_authority import build_execution_access
from okto_nexus.domain.base import iso_plus
from okto_nexus.errors import OktoNexusError
from test_ns09 import setup_authority, negotiate, admit


@contextmanager
def active_lease(tmp_path, monkeypatch, *, extra_capabilities=()):
    setup = setup_authority(tmp_path, monkeypatch)
    deps, app, access, operator, canonical, _, info, revisions, ticket, lane, sid, eid = setup
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{eid}/link',
                headers={'Authorization': f'Bearer {ticket}'}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane, sid, eid,
                                control_capabilities=(LEASE_DENIAL_REVISION, *extra_capabilities))
            opened = admit(deps, app)
            initial = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='lease.renew',
                request_id='initial-request', grant_id=canonical['grant_id'], expected_lease_serial=0,
                scope=opened['scope'], connection_id=channel.connection_id,
                connection_generation=channel.connection_generation, purpose='initial')
            ws.send_text(encode_r4_frame(initial).decode())
            granted = ws.receive_json()
            assert granted['type'] == 'lease.granted'
            ws.send_text(encode_r4_frame(applied(granted, channel)).decode())
            ws.send_text(encode_r4_frame(initial).decode())
            assert ws.receive_json() == granted
            renewal = dict(initial, request_id='renew-request', purpose='renew', expected_lease_serial=1)
            yield setup, ws, channel, opened, renewal


def applied(granted, channel):
    return {k: granted[k] for k in ('protocol_major','contract_revision','request_id',
        'grant_id','lease_id','lease_serial','scope')} | dict(type='lease.applied',
        application_stage='INSTALLED' if granted['lease_serial'] == 1 else 'RENEWED',
        connection_id=channel.connection_id, connection_generation=channel.connection_generation)


@pytest.mark.parametrize('cut', ['before_grant', 'before_applied'])
def test_denied_renewal_is_durable_before_reply_and_preserves_other_sessions(tmp_path, monkeypatch, cut):
    with active_lease(tmp_path, monkeypatch) as (setup, ws, channel, opened, renewal):
        deps, app, access, operator, canonical, *_ = setup
        if cut == 'before_applied':
            ws.send_text(encode_r4_frame(renewal).decode())
            granted = ws.receive_json()
            assert granted['type'] == 'lease.granted' and granted['lease_serial'] == 2
        access.revoke(operator, grant_id=canonical['grant_id'])
        if cut == 'before_applied':
            ws.send_text(encode_r4_frame(applied(granted, channel)).decode())
        ws.send_text(encode_r4_frame(renewal).decode())
        denied = ws.receive_json()
        assert denied['type'] == 'lease.denied' and denied['request'] == renewal
        with deps.connection_factory.unit_of_work(write=False) as uow:
            rows = uow.connection.execute('SELECT * FROM execution_session_containment').fetchall()
            assert len(rows) == 1
            row = dict(rows[0])
            assert row['state'] == 'REQUESTED' and row['release_proof_json'] is None
            assert row['opening_operation_id'] == opened['operation_id']
            assert row['opening_intent_hash'] == opened['intent_hash']
            assert json.loads(row['request_json']) == renewal
            assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions WHERE session_id=?',
                (opened['session_id'],)).fetchone()[0] == 'OPEN_PENDING'
            assert uow.connection.execute('SELECT control_state FROM execution_executors WHERE executor_id=?',
                (channel.executor_id,)).fetchone()[0] == 'CONTROL_READY'
        # Loss of the denial ACK/replay cannot add obligations or replace its identity.
        ws.send_text(encode_r4_frame(renewal).decode())
        assert ws.receive_json() == denied
        replacement = build_execution_access(deps)
        assert replacement.session_containment.denied(
            dict(renewal, request_id='another-denied-request'), channel=channel) is (cut == 'before_grant')
        with deps.connection_factory.unit_of_work(write=False) as uow:
            with pytest.raises(OktoNexusError, match='confirmed resource release'):
                replacement.session_containment.require_not_pending(uow, opened['scope'])
            assert dict(uow.connection.execute('SELECT * FROM execution_session_containment').fetchone()) == row
        # Even restored grant authority must not resurrect a contained session.
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE runtime_execution_grants SET revoked_at=NULL WHERE grant_id=?',
                                   (canonical['grant_id'],))
        service = ExecutionLeaseService(factory=deps.connection_factory, access=replacement,
                                       fresh_publications=app.state.inventory_fresh_publications)
        with pytest.raises(OktoNexusError, match='confirmed resource release'):
            service.issue(renewal, channel=channel)
        from okto_nexus.application.execution_capabilities import ExecutionCapabilityService
        capabilities = ExecutionCapabilityService(factory=deps.connection_factory, access=replacement)
        for audience in ('nexus-native-session', 'nexus-mcp-session'):
            with pytest.raises(OktoNexusError, match='confirmed resource release'):
                capabilities.issue(context=operator, session_id=opened['session_id'],
                    request=dict(capability_request_id=audience, binding_id='binding',
                                 audience=audience, actions=['handoff.get']), mcp_url='http://localhost/mcp')
        from okto_nexus.application.execution_dispatch import (
            reserve_execution_dispatch, begin_execution_send, release_unsent_dispatch)
        reserved = reserve_execution_dispatch(deps.connection_factory, server_id=channel.server_id,
                                             executor_id=channel.executor_id, remote_ready=True)
        assert reserved.operation_id == opened['operation_id']
        with pytest.raises(OktoNexusError, match='confirmed resource release'):
            begin_execution_send(deps.connection_factory, reservation=reserved, remote_ready=True,
                fresh_publications=app.state.inventory_fresh_publications, access=replacement)
        release_unsent_dispatch(deps.connection_factory, reservation=reserved)
        from okto_nexus.application.execution_intents import resolve_execution_intent
        from okto_nexus.application.execution_admission import submit_execution_operation
        other = resolve_execution_intent(deps.connection_factory, actor_agent_id='subject',
            request=dict(client_intent_id='sibling-open', intent='runtime.start', binding_id='binding',
                         workspace_binding_id='wxb', new_session=True), remote_ready=True,
            fresh_publications=app.state.inventory_fresh_publications)
        assert other['can_submit'], other['blockers']
        submit_execution_operation(deps.connection_factory, actor_agent_id='subject',
            request={k: other[k] for k in ('client_intent_id','operation_id','resolution_revision','intent_hash')},
            remote_ready=True, fresh_publications=app.state.inventory_fresh_publications)
        grant = access.issue(operator, actor_agent_id='subject', endpoint_id='ep',
            actions=['open','send','close','interrupt'], max_executions=2,
            expires_at=iso_plus(deps.clock.now_iso(), 600))
        healthy = dict(renewal, scope=other['scope'], request_id='healthy-request',
                       grant_id=grant['grant_id'], purpose='initial', expected_lease_serial=0)
        ws.send_text(encode_r4_frame(healthy).decode())
        reply = ws.receive_json()
        assert reply['type'] == 'lease.granted' and reply['scope'] == other['scope']


def test_containment_rejects_foreign_and_stale_targets_and_rolls_back_failure(tmp_path, monkeypatch):
    with active_lease(tmp_path, monkeypatch) as (setup, ws, channel, opened, renewal):
        deps, _, access, *_ = setup
        service = access.session_containment
        changed = []
        for key, value in [('grant_id','foreign'), ('expected_lease_serial',9),
                           ('connection_id','foreign'), ('connection_generation',99), ('purpose','initial')]:
            changed.append(dict(renewal, **{key:value}))
        for key, value in [('session_id','foreign'), ('agent_id','other'), ('session_owner_generation',2),
                           ('configuration_revision',2), ('binding_id','foreign')]:
            changed.append(dict(renewal, scope=dict(renewal['scope'], **{key:value})))
        for request in changed:
            assert service.denied(request, channel=channel) is False, request
        # A superseded authenticated link cannot create an obligation even if
        # the envelope is rewritten to its new channel generation.
        future = ExecutionChannel(channel.server_id, channel.executor_id, 'replacement', 99)
        assert not service.denied(dict(renewal, connection_id=future.connection_id,
                                       connection_generation=future.connection_generation), channel=future)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT count(*) FROM execution_session_containment').fetchone()[0] == 0
        record = service.repository.record
        def fail_after_insert(*args):
            record(*args)
            raise sqlite3.OperationalError('injected commit failure')
        monkeypatch.setattr(service.repository, 'record', fail_after_insert)
        with pytest.raises(sqlite3.OperationalError):
            service.denied(renewal, channel=channel)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT count(*) FROM execution_session_containment').fetchone()[0] == 0
        monkeypatch.setattr(service.repository, 'record', record)
        assert service.denied(renewal, channel=channel)
        with deps.connection_factory.unit_of_work() as uow:
            with pytest.raises(sqlite3.IntegrityError):
                uow.connection.execute("UPDATE execution_session_containment SET state='RELEASED'")
            assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()
