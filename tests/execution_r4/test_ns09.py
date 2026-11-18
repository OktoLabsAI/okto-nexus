"""Server-issued leases use canonical delegation and actual Core application.

The executor's qualification gate is synthetic. Setup seeds approved selection
metadata; operation admission, grant policy, WSS and Core lease application are real.
"""

import asyncio
from datetime import timedelta
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from nexus_connector_core import (
    CoreError, InstallationCandidate, LaunchIntent, OpenOperation, R4_PREVIEW_REVISION,
    SessionKey, ShutdownPolicy, TurnOperation, build_executor_inventory_snapshot, create_runtime,
    decode_r4_frame, encode_r4_frame, r4_lease_renew_frame,
    r4_submit_intent_hash,
)
from nexus_connector_core.discovery import fingerprint
from nexus_connector_core.journal import open_journal

from okto_nexus.adapters.inbound.http import executor_link
from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.outbound.sqlite.execution_identity import ensure_execution_installation, register_remote_executor
from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from okto_nexus.adapters.outbound.sqlite.execution_tickets import issue_execution_ticket
from okto_nexus.application.execution_admission import submit_execution_operation
from okto_nexus.application.execution_dispatch import reserve_execution_dispatch, begin_execution_send
from okto_nexus.application.execution_intents import resolve_execution_intent
from okto_nexus.application.execution_leases import ExecutionChannel, ExecutionLeaseService, _stamp
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.bootstrap.execution_authority import build_execution_access
from okto_nexus.domain.base import iso_plus
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError


def setup_authority(tmp_path, monkeypatch, *, lease_authority=True,
                    actions=None, max_executions=1, trust_mode=None, candidate=None,
                    subject_permissions=None, subject_comm_scope=None):
    class ManualDispatchFixture:
        def __init__(self, **kwargs):
            pass
        def start(self):
            pass
        async def stop(self):
            pass
    # This fixture isolates lease/dispatch transactions. The public integration
    # test does not use this fixture and exercises the actual socket sender.
    monkeypatch.setattr(executor_link, 'ExecutionDispatchPump', ManualDispatchFixture)
    deps = bootstrap({}, ['--home', str(tmp_path / 'home'), '--feature-harness-integrations', 'true'])
    if trust_mode is not None:
        deps.config.trust_mode = trust_mode
    app = build_app(deps)
    factory = deps.connection_factory
    server_id = ensure_execution_installation(factory).server_id
    now = deps.clock.now_iso()
    adapter_id = candidate.adapter_id if candidate is not None else "codex_app_server"
    app.state.test_agent_keys = {}
    with factory.unit_of_work() as uow:
        for agent in ('operator', 'registrar', 'subject', 'other'):
            uow.connection.execute('INSERT OR IGNORE INTO agents(agent_id,created_at) VALUES (?,?)', (agent, now))
            app.state.test_agent_keys[agent] = app.state.auth.issue_key(uow, agent_id=agent)
        uow.connection.execute('UPDATE agents SET permissions=?,comm_scope=? WHERE agent_id=?',
            (json.dumps(subject_permissions) if subject_permissions is not None else None,
             json.dumps(subject_comm_scope) if subject_comm_scope is not None else None, 'subject'))
        uow.connection.execute("INSERT INTO workspaces(workspace_id,created_at) VALUES ('ws',?)", (now,))
        # This fixture exercises a remote executor; new identities default to local.
        uow.connection.execute(
            "INSERT INTO agent_execution_policies(agent_id,execution_location) VALUES ('subject','remote')")
        uow.connection.execute(
            "INSERT INTO runtime_profiles(profile_id,adapter_id,config,enabled,revision,created_at,updated_at) "
            "VALUES ('profile',?,'{}',1,1,?,?)", (adapter_id, now, now))
        uow.connection.execute(
            "INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,protocol,profile_id,"
            "enabled,activation_state,created_at,updated_at) VALUES "
            "('ep','subject','ws',?,'nxl-r4','profile',1,'approved',?,?)", (adapter_id, now, now))
    registration = register_remote_executor(factory, actor_agent_id='registrar',
                                           connector_id='connector', client_intent_id='register')
    executor_id = registration.executor_id
    if candidate is None:
        binary = tmp_path / 'codex.exe'
        binary.write_bytes(b'Synthetic selected native peer')
        candidate = InstallationCandidate('codex_app_server', str(binary), fingerprint(binary), 'explicit', 'selected')
    snapshot = build_executor_inventory_snapshot([candidate], server_id=server_id,
                executor_id=executor_id, producer_instance_id='peer', publication_sequence=1)
    candidate_ref, revision = snapshot['evidence'][0]['candidate_ref'], snapshot['inventory_revision']
    with factory.unit_of_work() as uow:
        conn = uow.connection
        conn.execute(
            "INSERT INTO execution_workspace_bindings(server_id,workspace_binding_id,executor_id,workspace_id,"
            "realization_handle,revision,status) VALUES (?,'wxb',?,'ws','local-root',1,'READY')", (server_id, executor_id))
        conn.execute(
            "INSERT INTO execution_realizations(server_id,executor_id,realization_ref,local_realization_ref,"
            "subject_agent_id,workspace_binding_id,candidate_ref,inventory_revision,configuration_digest,"
            "local_root_proof_digest,revision,status) VALUES (?,?,'real','local-root','subject','wxb',?,?,'sha256:1','sha256:2',1,'READY')",
            (server_id, executor_id, candidate_ref, revision))
        conn.execute(
            "INSERT INTO execution_bindings(server_id,binding_id,executor_id,endpoint_id,workspace_binding_id,"
            "candidate_ref,inventory_revision,realization_ref,realization_revision,binding_revision) "
            "VALUES (?,'binding',?,'ep','wxb',?,?,'real',1,1)", (server_id, executor_id, candidate_ref, revision))
        conn.execute(
            "INSERT INTO execution_inventory_snapshots(server_id,executor_id,publication_sequence,inventory_revision,"
            "catalog_format,availability_format,snapshot_format,core_version,canonical_projection,received_at,"
            "observation_age_ms,producer_instance_id) VALUES (?,?,1,?,?,?,?,?,?,?,0,'peer')",
            (server_id, executor_id, revision, snapshot['catalog']['format_version'], snapshot['availability']['format_version'],
             snapshot['snapshot_format_version'], snapshot['core_version'], json.dumps(snapshot), now))
        conn.execute("INSERT INTO execution_inventory_current(server_id,executor_id,publication_sequence,inventory_revision) VALUES (?,?,1,?)", (server_id, executor_id, revision))
    fresh = app.state.inventory_fresh_publications
    fresh[(server_id, executor_id)] = (1, time.monotonic(), 0)
    access = build_execution_access(deps)
    operator = RuntimeRequestContext('operator', 'http_loopback', trusted_local_operator=True)
    canonical = access.issue(operator, actor_agent_id='subject', endpoint_id='ep',
        actions=actions if actions is not None else ['open', 'send', 'interrupt', 'close'],
        expires_at=iso_plus(now, 3600), max_executions=max_executions)
    _, revisions, _ = current_agent_revisions(factory, agent_id='subject')
    lane_scopes = {'lane:attach', 'lease:request'} if lease_authority else {'lane:attach'}
    lane_ticket = issue_execution_ticket(factory, server_id=server_id, executor_id=executor_id,
                    binding_id='binding', agent_id='subject', scopes=frozenset(lane_scopes)).ticket
    link_ticket = issue_execution_ticket(factory, server_id=server_id, executor_id=executor_id,
                    binding_id=None, agent_id='registrar').ticket
    info = executor_link.protocol_info()
    monkeypatch.setattr(executor_link, 'protocol_info', lambda: {
        **info, 'remote_execution_ready': True, 'nxl_accepted': [R4_PREVIEW_REVISION]})
    return deps, app, access, operator, canonical, candidate, info, revisions, link_ticket, lane_ticket, server_id, executor_id


def negotiate(ws, info, revisions, lane_ticket, server_id, executor_id, *, binding_id="binding", agent_id="subject", control_capabilities=()):
    base = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, server_id=server_id, executor_id=executor_id)
    ws.send_text(encode_r4_frame(dict(**base, type='hello', link_attempt_id='attempt',
        core_version=info['core_version'], management_revision=info['management_revision'],
        supported_nxl=[R4_PREVIEW_REVISION], snapshot_formats=[info['executor_snapshot_format']], control_capabilities=list(control_capabilities))).decode())
    welcome = ws.receive_json()
    assert welcome['type'] == 'welcome'
    connection = dict(connection_id=welcome['connection_id'], connection_generation=welcome['connection_generation'])
    request = ws.receive_json()
    assert not request['operation_ids'] and not request['session_ids']
    ws.send_text(encode_r4_frame(dict(**base, **connection, type='reconcile.report',
        reconcile_id=request['reconcile_id'], cursor=None, next_cursor=None, complete=True,
        receipts=[], claims=[], stream_watermarks=[], ownership_facts=[])).decode())
    assert ws.receive_json()['recovery_remaining'] is False
    ws.send_text(encode_r4_frame(dict(**base, connection_id=connection['connection_id'],
        expected_connection_generation=connection['connection_generation'], type='binding.attach',
        attach_request_id='attach', binding_id=binding_id, agent_id=agent_id, ticket=lane_ticket,
        credential_epoch=revisions.credential_epoch, authorization_revision=revisions.authorization,
        configuration_revision=revisions.configuration)).decode())
    assert ws.receive_json()['type'] == 'binding.attached'
    return ExecutionChannel(server_id, executor_id, **connection,
                            control_capabilities=tuple(welcome['control_capabilities']))


def admit(deps, app):
    resolution = resolve_execution_intent(deps.connection_factory, actor_agent_id='subject',
        request=dict(client_intent_id='open', intent='runtime.start', binding_id='binding',
                     workspace_binding_id='wxb', new_session=True), remote_ready=True,
        fresh_publications=app.state.inventory_fresh_publications)
    assert resolution['can_submit'], resolution['blockers']
    view, reused = submit_execution_operation(deps.connection_factory, actor_agent_id='subject',
        request={k:resolution[k] for k in ('client_intent_id','operation_id','resolution_revision','intent_hash')},
        remote_ready=True, fresh_publications=app.state.inventory_fresh_publications)
    assert not reused and view['operation_id'] == resolution['operation_id']
    return resolution


def assert_session_input_authority(deps, app, access, scope, expected_grant, channel):
    from dataclasses import replace

    from okto_nexus.application.session_interaction_authority import enqueue_human_input
    from okto_nexus.domain.execution.keys import SessionKey, SessionOwnerGeneration
    from okto_nexus.domain.session_interaction import InputAuthor, InputDeliveryState, InputScope

    auth = app.state.operator_auth
    assert auth.configure('fixture-operator', 'fixture-password', local=True)
    token = auth.login('fixture-operator', 'fixture-password')
    author = InputAuthor(auth.authority_reference(token), 'web')
    factory = deps.connection_factory
    exact = InputScope(SessionKey(scope['server_id'], scope['executor_id'], scope['session_id']),
        SessionOwnerGeneration(scope['session_owner_generation']), scope['binding_id'], scope['workspace_id'],
        scope['workspace_binding_id'], scope['agent_id'])
    tables = ('execution_client_intents', 'execution_operations', 'execution_dispatch_outbox')
    with factory.unit_of_work(write=False) as uow:
        counts = tuple(uow.connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in tables)
    args = dict(factory=factory, access=access, author=author, authority_fence=auth.authority_fence,
                current_capability_revision=lambda uow, scope: 'synthetic-capability',
                client_intent_id='human-input', capability_revision='synthetic-capability', text='Queued input')
    stale = replace(exact, generation=SessionOwnerGeneration(scope['session_owner_generation'] + 1))
    with pytest.raises(OktoNexusError, match='exact session is unavailable'):
        enqueue_human_input(scope=stale, **args)
    with pytest.raises(OktoNexusError, match='capability changed'):
        enqueue_human_input(scope=exact, **{**args, 'capability_revision': 'stale-capability'})
    accepted = enqueue_human_input(scope=exact, **args)
    assert accepted.status is InputDeliveryState.QUEUED
    assert enqueue_human_input(scope=exact, **args) == accepted
    with factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        assert tuple(conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in tables) == counts
        active_grant = conn.execute('SELECT revision,used_executions FROM runtime_execution_grants WHERE grant_id=?',
                                   (expected_grant,)).fetchone()
        stored = conn.execute('SELECT authority_ref,source_grant_id,source_grant_revision FROM session_interaction_inputs'
                              ' WHERE input_id=?', (accepted.input_id,)).fetchone()
        assert tuple(stored) == (author.authority_ref, expected_grant, active_grant['revision'])
        assert active_grant['used_executions'] == 0
    assert_staged_input_respects_shared_pump(deps, app, access, exact, channel)
    assert_interrupt_commits_exact_target_with_barrier(deps, app, access, exact, author, accepted.queue_revision)
    assert enqueue_human_input(scope=exact, **args) == accepted
    auth.logout(token)
    with pytest.raises(OktoNexusError, match='no longer signed in'):
        enqueue_human_input(scope=exact, **args)


def assert_staged_input_respects_shared_pump(deps, app, access, exact, channel):
    from dataclasses import replace

    from nexus_connector_core import CapacityReservation, capacity_reservation_id

    from okto_nexus.adapters.outbound.sqlite.session_interaction import (
        confirm_dispatch_capacity,
        prepare_dispatch_head,
        project_input_receipt,
    )
    from okto_nexus.adapters.outbound.sqlite.session_interaction_queue_controls import set_input_queue_paused
    from okto_nexus.application.execution_dispatch import release_unsent_dispatch
    from okto_nexus.application.execution_domain_delivery import DeliveryTransactionFactory
    from okto_nexus.application.execution_native_facts import stamp
    from okto_nexus.application.runtime_availability import CapacityHost
    from okto_nexus.application.session_interaction_dispatch import admit_held_input, prepare_input_capacity

    context = RuntimeRequestContext('operator', 'operator_session', trusted_local_operator=True)
    factory = deps.connection_factory
    with (pytest.raises(RuntimeError, match='rollback staged fixture'),
          app.state.operator_auth.authority_fence() as resolve, factory.unit_of_work() as uow):
        borrowed = DeliveryTransactionFactory(uow)
        now = stamp(access.clock.now_iso())
        head = prepare_dispatch_head(uow, scope=exact, now=now)
        assert head is not None and head.source_grant is not None
        common = {'actor_agent_id': 'operator', 'context': context, 'access': access,
                  'fresh_publications': app.state.inventory_fresh_publications, 'remote_ready': True}

        def admit_turn(client_id, text):
            resolution = resolve_execution_intent(borrowed, request={
                'client_intent_id': client_id, 'intent': 'turn.submit', 'agent_id': exact.agent_id,
                'binding_id': exact.binding_id, 'workspace_binding_id': exact.workspace_binding_id,
                'session_id': exact.session.session_id, 'text': text,
            }, **common)
            assert resolution['can_submit'], resolution['blockers']
            submit_execution_operation(borrowed, request={name: resolution[name] for name in (
                'client_intent_id', 'operation_id', 'intent_hash', 'resolution_revision')}, **common)
            return resolution

        authority = {'factory': factory, 'access': access, 'resolve_human': resolve, 'scope': exact,
                     'current_capability_revision': lambda uow, scope: 'synthetic-capability'}
        attempt = prepare_input_capacity(uow, host=CapacityHost(channel, None, 'fixture-boot'), **authority)
        request = attempt.request
        held = CapacityReservation(capacity_reservation_id(request), request, 'HELD', 1, 9000, None)
        stale = replace(held, request=replace(request,
            scope=replace(request.scope, connection_generation=channel.connection_generation + 1)))
        input_args = {**authority, 'fresh_publications': app.state.inventory_fresh_publications, 'remote_ready': True}
        uow.connection.execute('SAVEPOINT stale_reservation')
        with pytest.raises(OktoNexusError, match='differs from the prepared capacity request'):
            admit_held_input(uow, reservation=stale, **input_args)
        uow.connection.execute('ROLLBACK TO stale_reservation')
        uow.connection.execute('RELEASE stale_reservation')
        consumption = admit_held_input(uow, reservation=held, **input_args)
        linked = uow.connection.execute('SELECT operation_id,capacity_state FROM session_interaction_inputs WHERE input_id=?',
                                        (head.input_id,)).fetchone()
        assert tuple(linked) == (consumption.turn_operation_id, 'WAITING_CONSUMPTION')
        operation = uow.connection.execute('SELECT intent_hash FROM execution_operations WHERE operation_id=?',
                                           (consumption.turn_operation_id,)).fetchone()
        assert operation['intent_hash'] == consumption.turn_intent_hash
        outbox = uow.connection.execute('SELECT dispatch_state FROM execution_dispatch_outbox WHERE operation_id=?',
                                        (consumption.turn_operation_id,)).fetchone()
        assert outbox['dispatch_state'] == 'WAITING_INTERACTION_CAPACITY'
        assert prepare_dispatch_head(uow, scope=exact, now=now) is None
        admit_turn('fixture-concurrent-r4', 'Concurrent text')
        assert reserve_execution_dispatch(borrowed, server_id=exact.session.server_id,
            executor_id=exact.session.executor_id, remote_ready=True) is None
        confirmed = replace(held, state='CONSUMED', capacity_revision=2, consumption=consumption)
        capacity_args = {'scope': exact, 'operation_id': consumption.turn_operation_id}
        with pytest.raises(OktoNexusError, match='different input capacity claim'):
            confirm_dispatch_capacity(uow, observed=replace(confirmed, reservation_id='other-reservation'), **capacity_args)
        confirm_dispatch_capacity(uow, observed=confirmed, **capacity_args)
        confirm_dispatch_capacity(uow, observed=confirmed, **capacity_args)
        send_reservation = reserve_execution_dispatch(borrowed, server_id=exact.session.server_id,
            executor_id=exact.session.executor_id, remote_ready=True)
        assert send_reservation.operation_id == consumption.turn_operation_id
        assert send_reservation.session_input
        send_args = {'reservation': send_reservation, 'remote_ready': True, 'access': access,
                     'fresh_publications': app.state.inventory_fresh_publications}
        revision = uow.connection.execute('SELECT revision FROM session_interaction_queues').fetchone()[0]
        pause_args = {'scope': exact, 'capability_revision': 'pause', 'verify_authority': lambda: 'pause'}
        paused = set_input_queue_paused(uow, paused=True, expected_queue_revision=revision, **pause_args)
        with pytest.raises(OktoNexusError, match='queue is paused') as blocked:
            begin_execution_send(borrowed, **send_args)
        assert blocked.value.details['transient'] == 'session_input_paused'
        release_unsent_dispatch(borrowed, reservation=send_reservation)
        assert reserve_execution_dispatch(borrowed, server_id=exact.session.server_id,
            executor_id=exact.session.executor_id, remote_ready=True) is None
        set_input_queue_paused(uow, paused=False, expected_queue_revision=paused.queue_revision, **pause_args)
        send_reservation = reserve_execution_dispatch(borrowed, server_id=exact.session.server_id,
            executor_id=exact.session.executor_id, remote_ready=True)
        assert send_reservation.operation_id == consumption.turn_operation_id and send_reservation.attempt_no == 2
        send_args['reservation'] = send_reservation
        with pytest.raises(OktoNexusError, match='input author cannot be verified'):
            begin_execution_send(borrowed, **send_args)
        with pytest.raises(OktoNexusError, match='no longer signed in'):
            begin_execution_send(borrowed, resolve_session_input_human=lambda _: None,
                session_input_capability_revision=input_args['current_capability_revision'], **send_args)
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants').fetchone()[0] == 0
        authorized = begin_execution_send(borrowed, resolve_session_input_human=resolve,
            session_input_capability_revision=input_args['current_capability_revision'], **send_args)
        assert authorized.frame['operation_id'] == consumption.turn_operation_id
        assert uow.connection.execute('SELECT possible_effect FROM session_interaction_inputs WHERE input_id=?',
                                      (head.input_id,)).fetchone()[0] == 1
        with pytest.raises(OktoNexusError, match='reservation changed'):
            begin_execution_send(borrowed, resolve_session_input_human=resolve,
                session_input_capability_revision=input_args['current_capability_revision'], **send_args)
        key = (exact.session.server_id, exact.session.executor_id, consumption.turn_operation_id)
        uow.connection.execute("UPDATE execution_dispatch_outbox SET dispatch_state='DISPATCHED' "
                               "WHERE server_id=? AND executor_id=? AND operation_id=?", key)
        uow.connection.execute("UPDATE execution_operations SET admission_state='DISPATCHED' "
                               "WHERE server_id=? AND executor_id=? AND operation_id=?", key)
        project_input_receipt(uow.connection, operation_key=key, stage='ACCEPTED',
                              possible_effect=True, native_id='fixture-turn')
        assert reserve_execution_dispatch(borrowed, server_id=exact.session.server_id,
            executor_id=exact.session.executor_id, remote_ready=True) is None
        uow.connection.execute("UPDATE execution_operations SET admission_state='RESOLVED_TERMINAL' "
                               "WHERE server_id=? AND executor_id=? AND operation_id=?", key)
        following = reserve_execution_dispatch(borrowed, server_id=exact.session.server_id,
            executor_id=exact.session.executor_id, remote_ready=True)
        assert following and following.operation_id != consumption.turn_operation_id
        raise RuntimeError('rollback staged fixture')


def assert_interrupt_commits_exact_target_with_barrier(deps, app, access, exact, author, queue_revision):
    from contextlib import nullcontext

    from okto_nexus.adapters.outbound.sqlite.session_interaction_queue_controls import (
        is_input_queue_paused,
        set_input_queue_paused,
    )
    from okto_nexus.application.execution_domain_delivery import DeliveryTransactionFactory
    from okto_nexus.application.session_interaction_controls import request_exact_human_interrupt

    with (pytest.raises(RuntimeError, match='rollback control fixture'),
          app.state.operator_auth.authority_fence() as resolve, deps.connection_factory.unit_of_work() as uow):
        borrowed = DeliveryTransactionFactory(uow)
        options = {'factory': borrowed, 'access': access, 'authority_fence': lambda: nullcontext(resolve),
                   'current_interrupt_revision': lambda *_: 'fixture-interrupt', 'scope': exact, 'author': author,
                   'client_intent_id': 'fixture-exact-interrupt', 'capability_revision': 'fixture-interrupt',
                   'expected_queue_revision': queue_revision, 'remote_ready': True,
                   'fresh_publications': app.state.inventory_fresh_publications}
        operation, reused = request_exact_human_interrupt(native_turn_id='fixture-turn', **options)
        operation_id = operation['operation_id']
        assert not reused and is_input_queue_paused(uow.connection, exact.session)
        with pytest.raises(OktoNexusError, match='different content'):
            request_exact_human_interrupt(native_turn_id='replacement-turn', **options)
        reserved = reserve_execution_dispatch(borrowed, server_id=exact.session.server_id,
            executor_id=exact.session.executor_id, remote_ready=True)
        assert reserved.operation_id == operation_id and reserved.session_control
        send = {'reservation': reserved, 'access': access, 'remote_ready': True,
                'fresh_publications': app.state.inventory_fresh_publications}
        with pytest.raises(OktoNexusError, match='interrupt author cannot be verified'):
            begin_execution_send(borrowed, **send)
        with pytest.raises(OktoNexusError, match='no longer signed in'):
            begin_execution_send(borrowed, resolve_session_input_human=lambda _: None,
                session_interrupt_capability_revision=options['current_interrupt_revision'], **send)
        authorized = begin_execution_send(borrowed, resolve_session_input_human=resolve,
            session_interrupt_capability_revision=options['current_interrupt_revision'], **send)
        assert authorized.frame['action'] == 'turn.interrupt' and authorized.frame['expected_turn_id'] == 'fixture-turn'
        set_input_queue_paused(uow, scope=exact, paused=False, expected_queue_revision=queue_revision + 1,
                               capability_revision='fixture-resume', verify_authority=lambda: 'fixture-resume')
        same, reused = request_exact_human_interrupt(native_turn_id='fixture-turn', **options)
        assert reused and same['operation_id'] == operation_id
        assert not is_input_queue_paused(uow.connection, exact.session)
        raise RuntimeError('rollback control fixture')


def test_ns09_02_server_grant_core_application_and_replay(tmp_path, monkeypatch):
    connector = pytest.importorskip('okto_nexus_connector.transport.wss_r4')
    from okto_nexus_connector.transport.https_client import NexusHTTPClient
    from test_vertical_inventory import _NativeFactory
    deps, app, access, operator, canonical, candidate, info, revisions, link_ticket, lane_ticket, server_id, executor_id = setup_authority(tmp_path, monkeypatch)
    path = f'wss://127.0.0.1:8202/v1/runtime/executors/{executor_id}/link'
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(path, headers={'Authorization': f'Bearer {link_ticket}'}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane_ticket, server_id, executor_id)
            resolution = admit(deps, app)
            scope = resolution['scope']
            reservation = reserve_execution_dispatch(deps.connection_factory, server_id=server_id,
                                                       executor_id=executor_id, remote_ready=True)
            from okto_nexus.application.execution_dispatch import AuthorizedOpenBootstrap, release_unsent_dispatch
            authorized = begin_execution_send(deps.connection_factory, reservation=reservation, remote_ready=True,
                                 fresh_publications=app.state.inventory_fresh_publications, access=access)
            assert isinstance(authorized, AuthorizedOpenBootstrap)
            assert authorized.grant_id == canonical['grant_id']
            with deps.connection_factory.unit_of_work(write=False) as uow:
                sent = uow.connection.execute(
                    'SELECT dispatch_state,dispatch_phase,lease_id,lease_serial FROM execution_dispatch_outbox').fetchone()
                assert tuple(sent) == ('SENDING', 'OPEN_AUTHORIZED_PENDING_LEASE', None, None)
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_leases').fetchone()[0] == 0
            with pytest.raises(OktoNexusError, match='reservation changed'):
                begin_execution_send(deps.connection_factory, reservation=reservation, remote_ready=True,
                                     fresh_publications=app.state.inventory_fresh_publications, access=access)
            with pytest.raises(OktoNexusError, match='no longer unsent'):
                release_unsent_dispatch(deps.connection_factory, reservation=reservation)
            class Peer:
                request = None
                async def send(self, raw):
                    frame = decode_r4_frame(raw.encode())
                    if frame['type'] == 'lease.renew':
                        self.request = frame
                    await asyncio.to_thread(ws.send_text, raw)
                async def recv(self):
                    raw = await asyncio.to_thread(ws.receive_text)
                    frame = decode_r4_frame(raw.encode())
                    if frame['type'] == 'lease.granted':
                        with deps.connection_factory.unit_of_work(write=False) as uow:
                            row = uow.connection.execute('SELECT status,applied_at FROM execution_leases ORDER BY lease_serial DESC').fetchone()
                            assert tuple(row) == ('ISSUED', None)
                    return raw
            async def run():
                journal = await open_journal(tmp_path / 'core.db')
                native = _NativeFactory()
                async def environment(_):
                    return {}
                runtime = create_runtime(journal=journal, environment=environment,
                    candidates={candidate.adapter_id:candidate}, workspace_roots={'ws':str(tmp_path)}, native_factory=native)
                peer = Peer()
                state = connector.R4ControlState(server_id, executor_id, channel.connection_id, channel.connection_generation, True)
                try:
                    # The dispatched open is only a bootstrap envelope until
                    # Core has installed the correlated lease.
                    with pytest.raises(CoreError):
                        runtime.r4_operation_context(authorized.frame,
                            connection_id=state.connection_id,
                            connection_generation=state.connection_generation)
                    application = await connector.apply_r4_lease(peer, state, runtime, scope=scope, grant_id=authorized.grant_id)
                    # Same request proves the Server processed the application
                    # without inventing another ACK frame or extending validity.
                    ws.send_text(encode_r4_frame(peer.request).decode())
                    repeated = ws.receive_json()
                    assert repeated['lease_serial'] == 1
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        row = uow.connection.execute('SELECT status,valid_until_server,applied_at FROM execution_leases').fetchone()
                        assert row['status'] == 'ACTIVE' and row['applied_at']
                        original_expiry = row['valid_until_server']
                        session = uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()
                        assert tuple(session) == ('OPEN_PENDING', 'ACTIVE')
                    ws.send_text(encode_r4_frame(peer.request).decode())
                    assert ws.receive_json() == repeated
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        assert uow.connection.execute('SELECT valid_until_server FROM execution_leases').fetchone()[0] == original_expiry
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        dispatched = uow.connection.execute(
                            'SELECT dispatch_phase,lease_id,lease_serial,dispatch_grant_id FROM execution_dispatch_outbox').fetchone()
                        assert tuple(dispatched) == ('LEASE_AUTHORIZED', application.context.r4_authority.lease_id,
                            1, canonical['grant_id'])
                    assert authorized.grant_id == canonical['grant_id']
                    submit = dict(protocol_major=1,contract_revision=R4_PREVIEW_REVISION,type='operation.submit',
                        **authorized.scope,connection_id=authorized.connection_id,
                        connection_generation=authorized.connection_generation,grant_id=authorized.grant_id,
                        operation_id=resolution['operation_id'],action='runtime.open',
                        payload=authorized.semantic_intent['payload'])
                    submit['intent_hash'] = r4_submit_intent_hash(submit)
                    assert submit['intent_hash'] == resolution['intent_hash']
                    context = runtime.r4_operation_context(submit,connection_id=state.connection_id,
                                                           connection_generation=state.connection_generation)
                    prepared = await runtime.prepare(LaunchIntent('subject','ws',candidate.adapter_id), context)
                    opened = await runtime.open(OpenOperation(resolution['operation_id'], scope['session_id'], 'epoch', prepared), context)
                    assert opened.operation_id == resolution['operation_id']
                    ticket = issue_execution_ticket(deps.connection_factory, server_id=server_id,
                        executor_id=executor_id, binding_id='binding', agent_id='subject',
                        scopes=frozenset({'receipt:publish'})).ticket
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as raw:
                        async with NexusHTTPClient('https://127.0.0.1:8202', client=raw) as http:
                            await http.publish_core_open_receipt(ticket, submit_frame=submit,
                                core_receipt=opened, context=context, prepared=prepared,
                                stream_epoch='epoch', receipt_revision=1)
                            with deps.connection_factory.unit_of_work(write=False) as uow:
                                assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions').fetchone()[0] == 'READY'
                            assert_session_input_authority(deps, app, access, scope, canonical['grant_id'], channel)
                            for index in range(2):
                                turn = resolve_execution_intent(deps.connection_factory, actor_agent_id='subject',
                                    request=dict(client_intent_id=f'turn-{index}', intent='turn.submit',
                                        binding_id='binding', workspace_binding_id='wxb', session_id=scope['session_id'], text='Hello'),
                                    remote_ready=True, fresh_publications=app.state.inventory_fresh_publications)
                                assert turn['can_submit'], turn['blockers']
                                submit_execution_operation(deps.connection_factory, actor_agent_id='subject',
                                    request={k:turn[k] for k in ('client_intent_id','operation_id','resolution_revision','intent_hash')},
                                    remote_ready=True, fresh_publications=app.state.inventory_fresh_publications)
                                reserved = reserve_execution_dispatch(deps.connection_factory, server_id=server_id,
                                    executor_id=executor_id, remote_ready=True)
                                def begin_turn():
                                    return begin_execution_send(deps.connection_factory, reservation=reserved,
                                        remote_ready=True, fresh_publications=app.state.inventory_fresh_publications, access=access)
                                if index:
                                    with pytest.raises(OktoNexusError, match='not authorized'):
                                        begin_turn()
                                    continue
                                dispatch = begin_turn()
                                with pytest.raises(OktoNexusError, match='reservation changed'):
                                    begin_turn()
                                turn_frame = {**submit, 'operation_id':turn['operation_id'], 'action':'turn.submit',
                                    'payload':dispatch.semantic_intent['payload'], 'intent_hash':turn['intent_hash']}
                                turn_context = runtime.r4_operation_context(turn_frame, connection_id=state.connection_id,
                                    connection_generation=state.connection_generation)
                                receipt = await runtime.submit(TurnOperation(turn['operation_id'], scope['session_id'], 'Hello'), turn_context)
                                await http.publish_core_turn_receipt(ticket, submit_frame=turn_frame,
                                    core_receipt=receipt, context=turn_context, receipt_revision=1)
                                assert native.native.sent == [('send_turn', turn['operation_id'])]
                            with deps.connection_factory.unit_of_work(write=False) as uow:
                                assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants').fetchone()[0] == 1
                    renewed = await connector.apply_r4_lease(peer, state, runtime, scope=scope, grant_id=canonical['grant_id'], purpose='renew')
                    ws.send_text(encode_r4_frame(peer.request).decode())
                    assert ws.receive_json()['lease_serial'] == 2
                    assert renewed.context.lease_deadline_monotonic > application.context.lease_deadline_monotonic
                    assert (await runtime.persisted_lease(SessionKey(server_id,executor_id,scope['session_id']))).connection_generation == channel.connection_generation
                    access.revoke(operator, grant_id=canonical['grant_id'])
                    ws.send_text(encode_r4_frame(peer.request).decode())
                    assert ws.receive_json()['code'] == 'LEASE_REVALIDATION_REQUIRED'
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        assert uow.connection.execute('SELECT status FROM execution_leases ORDER BY lease_serial DESC').fetchone()[0] == 'REVOKED'
                    assert len(native.native.sent) == 1
                finally:
                    await runtime.shutdown(ShutdownPolicy(0, 0))
                    await journal.aclose()
            asyncio.run(run())


def test_ns09_02_transaction_rollback_scope_and_late_ack(tmp_path, monkeypatch):
    deps, app, access, _, canonical, _, info, revisions, link_ticket, lane_ticket, server_id, executor_id = setup_authority(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor_id}/link',
                headers={'Authorization': f'Bearer {link_ticket}'}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane_ticket, server_id, executor_id)
            scope = admit(deps, app)['scope']
            service = ExecutionLeaseService(factory=deps.connection_factory, access=access,
                fresh_publications=app.state.inventory_fresh_publications, max_duration_ms=1000)
            request = dict(protocol_major=1,contract_revision=R4_PREVIEW_REVISION,type='lease.renew',
                request_id='request',grant_id=canonical['grant_id'],expected_lease_serial=0,scope=scope,
                connection_id=channel.connection_id,connection_generation=channel.connection_generation,purpose='initial')
            with pytest.raises(OktoNexusError):
                service.issue({**request,'scope':{**scope,'agent_id':'registrar'}},channel=channel)
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute("CREATE TRIGGER fail_grant BEFORE INSERT ON execution_leases BEGIN SELECT RAISE(ABORT,'lease fault'); END")
            with pytest.raises(Exception, match='lease fault'):
                service.issue(request, channel=channel)
            with deps.connection_factory.unit_of_work() as uow:
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_leases').fetchone()[0] == 0
                assert uow.connection.execute('SELECT lease_state FROM execution_sessions').fetchone()[0] == 'NONE'
                uow.connection.execute('DROP TRIGGER fail_grant')
            grant = service.issue(request, channel=channel)
            assert service.issue(request, channel=channel) == grant
            with pytest.raises(OktoNexusError):
                service.issue({**request,'request_id':'another'},channel=channel)
            ack = {k:grant[k] for k in ('protocol_major','contract_revision','request_id','lease_id','lease_serial','grant_id','scope')}
            ack.update(type='lease.applied',connection_id=channel.connection_id,
                       connection_generation=channel.connection_generation,application_stage='INSTALLED')
            class LateClock:
                def now_iso(self):
                    return (_stamp(deps.clock.now_iso()) + timedelta(seconds=2)).isoformat()
            access.clock = LateClock()
            with pytest.raises(OktoNexusError):
                service.applied(ack, channel=channel)
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT status,applied_at FROM execution_leases').fetchone()['status'] == 'ISSUED'
                assert uow.connection.execute('SELECT lease_state FROM execution_sessions').fetchone()[0] == 'LEASE_PENDING'


def test_server_lease_serial_race_and_superseded_socket_cannot_ack(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    deps, app, access, _, canonical, _, info, revisions, link_ticket, lane_ticket, server_id, executor_id = setup_authority(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor_id}/link',
                headers={'Authorization': f'Bearer {link_ticket}'}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane_ticket, server_id, executor_id)
            scope = admit(deps, app)['scope']
            service = ExecutionLeaseService(factory=deps.connection_factory, access=access,
                fresh_publications=app.state.inventory_fresh_publications)
            request = dict(protocol_major=1,contract_revision=R4_PREVIEW_REVISION,type='lease.renew',
                request_id='request',grant_id=canonical['grant_id'],expected_lease_serial=0,scope=scope,
                connection_id=channel.connection_id,connection_generation=channel.connection_generation,purpose='initial')
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: service.issue(request,channel=channel), range(2)))
            assert results[0] == results[1]
            grant = results[0]
            ack = {k:grant[k] for k in ('protocol_major','contract_revision','request_id','lease_id','lease_serial','grant_id','scope')}
            ack.update(type='lease.applied',connection_id=channel.connection_id,
                       connection_generation=channel.connection_generation,application_stage='INSTALLED')
            service.applied(ack, channel=channel)
            service.applied(ack, channel=channel)
            renewal = {**request, 'purpose':'renew', 'expected_lease_serial':1}
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute("CREATE TRIGGER fail_renew BEFORE INSERT ON execution_leases BEGIN SELECT RAISE(ABORT,'renewal fault'); END")
            with pytest.raises(Exception, match='renewal fault'):
                service.issue({**renewal,'request_id':'rollback'},channel=channel)
            with deps.connection_factory.unit_of_work() as uow:
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_leases').fetchone()[0] == 1
                assert uow.connection.execute('SELECT lease_state FROM execution_sessions').fetchone()[0] == 'ACTIVE'
                uow.connection.execute('DROP TRIGGER fail_renew')
            def race(name):
                try:
                    return service.issue({**renewal,'request_id':name},channel=channel)
                except OktoNexusError:
                    return None
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(race, ('race-a','race-b')))
            accepted = [r for r in results if r]
            assert len(accepted) == 1 and accepted[0]['lease_serial'] == 2
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute("UPDATE execution_executors SET generation=generation+1,owner_instance_id='new-owner' "
                                       "WHERE server_id=? AND executor_id=?", (server_id,executor_id))
            revoked = {k:accepted[0][k] for k in ('protocol_major','contract_revision','request_id','lease_id','lease_serial','grant_id','scope')}
            revoked.update(type='lease.applied',connection_id=channel.connection_id,
                           connection_generation=channel.connection_generation,application_stage='REVOKED')
            with pytest.raises(OktoNexusError, match='superseded connection'):
                service.applied(revoked,channel=channel)
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert {r[0] for r in uow.connection.execute('SELECT status FROM execution_leases')} == {'SUPERSEDED'}


@pytest.mark.parametrize('change', ['permission','method','credential','grant','ticket','scope'])
def test_canonical_authority_changes_refuse_initial_lease(tmp_path, monkeypatch, change):
    deps, app, access, operator, canonical, _, info, revisions, link_ticket, lane_ticket, server_id, executor_id = setup_authority(tmp_path, monkeypatch, lease_authority=change != 'scope')
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor_id}/link',
                headers={'Authorization': f'Bearer {link_ticket}'}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws,info,revisions,lane_ticket,server_id,executor_id)
            scope = admit(deps,app)['scope']
            if change == 'grant':
                access.revoke(operator,grant_id=canonical['grant_id'])
            elif change == 'scope':
                pass  # The actual attach ticket never included lease:request.
            else:
                with deps.connection_factory.unit_of_work() as uow:
                    if change == 'permission':
                        uow.connection.execute("UPDATE agents SET permissions=? WHERE agent_id='subject'",
                                               (json.dumps({'messages':{'send_direct':False}}),))
                    elif change == 'method':
                        uow.connection.execute("INSERT INTO agent_connection_methods VALUES ('subject','codex_app_server',0)")
                    elif change == 'ticket':
                        uow.connection.execute("UPDATE execution_link_tickets SET revoked_at=? WHERE binding_id='binding'",
                                               (deps.clock.now_iso(),))
                    else:
                        app.state.auth.issue_key(uow,agent_id='subject')
            ws.send_text(encode_r4_frame(dict(protocol_major=1,contract_revision=R4_PREVIEW_REVISION,
                type='lease.renew',request_id='request',grant_id=canonical['grant_id'],expected_lease_serial=0,
                scope=scope,connection_id=channel.connection_id,connection_generation=channel.connection_generation,
                purpose='initial')).decode())
            assert ws.receive_json()['code'] == 'LEASE_REVALIDATION_REQUIRED'
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_leases').fetchone()[0] == 0
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_sessions').fetchone()[0] == 1


@pytest.mark.parametrize('revoke_first', [True, False])
def test_revoked_lease_projection_survives_lane_and_owner_fencing(tmp_path, monkeypatch, revoke_first):
    deps, app, access, operator, canonical, _, info, revisions, link_ticket, lane_ticket, server_id, executor_id = setup_authority(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor_id}/link',
                headers={'Authorization': f'Bearer {link_ticket}'}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane_ticket, server_id, executor_id)
            scope = admit(deps, app)['scope']
            service = ExecutionLeaseService(factory=deps.connection_factory, access=access,
                fresh_publications=app.state.inventory_fresh_publications)
            request = dict(protocol_major=1,contract_revision=R4_PREVIEW_REVISION,type='lease.renew',
                request_id='request',grant_id=canonical['grant_id'],expected_lease_serial=0,scope=scope,
                connection_id=channel.connection_id,connection_generation=channel.connection_generation,purpose='initial')
            service.issue(request, channel=channel)
            if revoke_first:
                access.revoke(operator, grant_id=canonical['grant_id'])
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute("UPDATE execution_control_lanes SET state='DISCONNECTED'")
                uow.connection.execute("UPDATE execution_executors SET control_state='DISCONNECTED',generation=generation+1 "
                                       "WHERE executor_id=?", (executor_id,))
            if not revoke_first:
                access.revoke(operator, grant_id=canonical['grant_id'])
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT lease_state FROM execution_sessions').fetchone()[0] == 'REVOKED'
                assert uow.connection.execute('SELECT status FROM execution_leases').fetchone()[0] == 'REVOKED'
            with pytest.raises(OktoNexusError):
                service.issue(request, channel=channel)


def test_unapplied_lease_requires_reconciliation_before_reconnect(tmp_path, monkeypatch):
    deps, app, access, _, canonical, _, info, revisions, link_ticket, lane_ticket, server_id, executor_id = setup_authority(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor_id}/link',
                headers={'Authorization': f'Bearer {link_ticket}'}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane_ticket, server_id, executor_id)
            scope = admit(deps, app)['scope']
            service = ExecutionLeaseService(factory=deps.connection_factory, access=access,
                fresh_publications=app.state.inventory_fresh_publications)
            request = dict(protocol_major=1,contract_revision=R4_PREVIEW_REVISION,type='lease.renew',
                request_id='request',grant_id=canonical['grant_id'],expected_lease_serial=0,scope=scope,
                connection_id=channel.connection_id,connection_generation=channel.connection_generation,purpose='initial')
            service.issue(request, channel=channel)
            next_channel = ExecutionChannel(server_id, executor_id, 'next-connection', channel.connection_generation + 1)
            # Fixture models an accepted new channel; it does not qualify
            # the still-pending nonempty reconciliation implementation.
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute("UPDATE execution_executors SET generation=?,owner_instance_id=? WHERE executor_id=?",
                    (next_channel.connection_generation, next_channel.connection_id, executor_id))
                uow.connection.execute("UPDATE execution_control_lanes SET connection_id=?,connection_generation=?",
                    (next_channel.connection_id, next_channel.connection_generation))
                uow.connection.execute("UPDATE execution_link_tickets SET bound_connection_id=? WHERE binding_id='binding'",
                    (next_channel.connection_id,))
            with pytest.raises(OktoNexusError, match='unapplied lease requires reconciliation'):
                service.issue({**request, 'request_id':'reconnect', 'purpose':'reconnect', 'expected_lease_serial':1,
                    'connection_id':next_channel.connection_id, 'connection_generation':next_channel.connection_generation},
                    channel=next_channel)
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_leases').fetchone()[0] == 1


def test_compatible_renewal_preserves_applied_authority_until_ack(tmp_path, monkeypatch):
    from okto_nexus.adapters.outbound.sqlite.execution_leases import SqliteExecutionLeaseRepository
    deps, app, access, _, canonical, _, info, revisions, link_ticket, lane_ticket, server_id, executor_id = setup_authority(tmp_path, monkeypatch)
    repository = SqliteExecutionLeaseRepository()
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor_id}/link',
                headers={'Authorization': f'Bearer {link_ticket}'}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane_ticket, server_id, executor_id)
            scope = admit(deps, app)['scope']
            service = ExecutionLeaseService(factory=deps.connection_factory, access=access,
                fresh_publications=app.state.inventory_fresh_publications)
            request = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='lease.renew',
                request_id='initial', grant_id=canonical['grant_id'], expected_lease_serial=0, scope=scope,
                connection_id=channel.connection_id, connection_generation=channel.connection_generation,
                purpose='initial')

            def acknowledge(grant, stage):
                ack = {k:grant[k] for k in ('protocol_major','contract_revision','request_id','lease_id','lease_serial','grant_id','scope')}
                ack.update(type='lease.applied', connection_id=channel.connection_id,
                           connection_generation=channel.connection_generation, application_stage=stage)
                service.applied(ack, channel=channel)

            initial = service.issue(request, channel=channel)
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert repository.effective(uow, scope)['status'] == 'ISSUED'
                assert uow.connection.execute('SELECT lease_state FROM execution_sessions').fetchone()[0] == 'LEASE_PENDING'
            acknowledge(initial, 'INSTALLED')
            renewal = service.issue({**request, 'request_id':'renewal', 'purpose':'renew',
                                     'expected_lease_serial':1}, channel=channel)
            with deps.connection_factory.unit_of_work() as uow:
                conn = uow.connection
                previous = repository.effective(uow, scope)
                assert previous['lease_serial'] == 1 and previous['status'] == 'ACTIVE'
                assert repository.latest(uow, scope)['status'] == 'ISSUED'
                assert conn.execute('SELECT lease_state FROM execution_sessions').fetchone()[0] == 'ACTIVE'
                # Selection cannot extend the old lease deadline.
                deadline = previous['valid_until_server']
                assert repository.effective(uow, scope)['valid_until_server'] == deadline
                # Incompatible grants never borrow the previous authority.
                for field, value in (
                    ('scope_json', '{}'), ('connection_id', 'different'),
                    ('connection_generation', channel.connection_generation + 1),
                    ('grant_id', 'different'), ('source_grant_revision', 'different'),
                    ('allowed_actions_json', '[]'),
                ):
                    conn.execute('SAVEPOINT changed_authority')
                    conn.execute(f'UPDATE execution_leases SET {field}=? WHERE lease_serial=2', (value,))
                    assert repository.effective(uow, scope)['lease_serial'] == 2, field
                    conn.execute('ROLLBACK TO changed_authority')
                    conn.execute('RELEASE changed_authority')
                for status in ('REVOKED', 'SUPERSEDED'):
                    conn.execute('SAVEPOINT unavailable')
                    conn.execute('UPDATE execution_leases SET status=? WHERE lease_serial=1', (status,))
                    assert repository.effective(uow, scope)['lease_serial'] == 2
                    conn.execute('ROLLBACK TO unavailable')
                    conn.execute('RELEASE unavailable')
            acknowledge(renewal, 'RENEWED')
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert repository.effective(uow, scope)['lease_serial'] == 2
                assert repository.effective(uow, scope)['status'] == 'ACTIVE'
                assert uow.connection.execute('SELECT status FROM execution_leases WHERE lease_serial=1').fetchone()[0] == 'SUPERSEDED'
