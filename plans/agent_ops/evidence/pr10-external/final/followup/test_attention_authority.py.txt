"""Authority attention reads real admitted work without sending or mutating it."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent / 'execution_r4'))
import test_native_decisions as native_fixtures  # noqa: E402
import test_canonical_relay as relay_fixtures  # noqa: E402

from okto_nexus.adapters.outbound.sqlite.attention_authority import SOURCE_SQL, build_policy
from okto_nexus.application.attention_authority import project
from okto_nexus.application.execution_binding_proposals import _agent_guard
from okto_nexus.application.execution_domain_delivery import DeliveryTransactionFactory
from okto_nexus.application.execution_native_facts import stamp
from okto_nexus.errors import OktoNexusError
from okto_nexus.bootstrap.execution_authority import build_execution_access
from okto_nexus.domain.runtime_context import RuntimeRequestContext

decision_state = native_fixtures.decision_state
opening = native_fixtures.opening
relay_pair = relay_fixtures.relay_pair
connected_local = relay_fixtures.connected_local
local_setup = relay_fixtures.local_setup
qualified_contract = relay_fixtures.qualified_contract
qualified_bridge = relay_fixtures.qualified_bridge


@pytest.fixture(autouse=True)
def isolated_inventory(monkeypatch):
    from okto_nexus.bootstrap import embedded_inventory
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', lambda **_: SimpleNamespace(candidates=()))


def read(uow, deps, *, now=None, workspace_id=None, agent_id=None):
    now = now or deps.clock.now_iso()
    context = RuntimeRequestContext('operator', 'http_loopback', trusted_local_operator=True)
    policy = build_policy(uow, config=deps.config, access=build_execution_access(deps), context=context, now=now)
    facts = [json.loads(row['facts']) for row in uow.connection.execute(SOURCE_SQL,
        dict(now=now, workspace_id=workspace_id, agent_id=agent_id))]
    return facts, policy, now


def items(uow, deps, **kwargs):
    facts, policy, now = read(uow, deps, **kwargs)
    return [item for row in facts for item in project(row, now, policy)]


def publish_policy(deps, values, now):
    """Canonical persisted fixture; HTTP ownership/publication has its own suite."""
    from okto_nexus.application.server_effective_policy import publish_effective_policy
    with deps.connection_factory.unit_of_work() as uow:
        snapshot = publish_effective_policy(uow, values=values, now=now)
    for key, value in values.items():
        setattr(deps.config, key, value)
    return snapshot


def attention_service(deps, now):
    from fake_clock import FakeClock
    from okto_nexus.application.attention import AttentionService
    from okto_nexus.adapters.outbound.sqlite.attention import SqliteAttentionQueries
    return AttentionService(factory=deps.connection_factory, access=build_execution_access(deps),
        queries=SqliteAttentionQueries(), clock=FakeClock(iso=now), config=deps.config)


@pytest.fixture
def queued_message(tmp_path, monkeypatch, request):
    from test_ns09 import setup_authority, negotiate
    from test_mcp_session_capabilities import rpc, envelope
    handoff_mode = getattr(request, 'param', None) == 'handoff'
    notice_mode = getattr(request, 'param', None) == 'notice'
    required_native = getattr(request, 'param', None) == 'required_native'
    state = setup_authority(tmp_path, monkeypatch, max_executions=10)
    deps, app, _, _, _, _, info, revisions, link, lane, server, executor = state
    if required_native:
        deps.config.feature_hitl = True
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy=?", ('none' if handoff_mode else 'conversation',))
        if required_native:
            uow.connection.execute("UPDATE runtime_profiles SET config=?", (json.dumps(
                dict(required_native_requests=['item/commandExecution/requestApproval'])),))
    from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
    from okto_nexus.adapters.outbound.sqlite.execution_tickets import issue_execution_ticket
    _, revisions, _ = current_agent_revisions(deps.connection_factory, agent_id='subject')
    lane = issue_execution_ticket(deps.connection_factory, server_id=server, executor_id=executor,
        binding_id='binding', agent_id='subject', scopes=frozenset({'lane:attach', 'lease:request'})).ticket
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor}/link',
                headers={'Authorization': 'Bearer ' + link}, subprotocols=['nxl.v1']) as websocket:
            negotiate(websocket, info, revisions, lane, server, executor)
            if notice_mode:
                result = envelope(rpc((deps, app), app.state.test_agent_keys['operator'], 'handoff_create',
                    dict(workspace_id='ws', from_agent_id='operator', visibility='eligible', payload='Private notice body',
                        target=dict(strategy='direct', agent_id='subject'))))
                assert result['ok'], result
                deadline = time.monotonic() + 15
                while True:
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        if uow.connection.execute('SELECT 1 FROM delivery_outbox d JOIN runtime_handoff_notifications n USING(message_id)').fetchone():
                            break
                    assert time.monotonic() < deadline, 'No canonical notice was admitted'
                    deps.runtime_dispatcher.scan_once()
                    time.sleep(.02)
            elif handoff_mode:
                granted = state[2].issue(state[3], actor_agent_id='operator', endpoint_id='ep',
                    actions=['execute_work'], expires_at=None, max_executions=1)
                created = envelope(rpc((deps, app), app.state.test_agent_keys['operator'], 'handoff_create',
                    dict(workspace_id='ws', from_agent_id='operator', visibility='eligible', payload='Private handoff body',
                        target=dict(strategy='direct', agent_id='subject'))))
                assert created['ok'], created
                result = envelope(rpc((deps, app), app.state.test_agent_keys['operator'], 'handoff_claim',
                    dict(workspace_id='ws', handoff_id=created['data']['handoff_id'], agent_id='subject',
                        runtime_endpoint_id='ep', execution_grant_id=granted['grant_id'], idempotency_key='attention-work')))
                assert result['ok'], result
            else:
                result = envelope(rpc((deps, app), app.state.test_agent_keys['operator'], 'message_create',
                    dict(workspace_id='ws', from_agent_id='operator', subject='Private attention subject',
                        body='Private attention message body', target=dict(strategy='direct', agent_id='subject'))))
                assert result['ok'], result
                assert result['data']['runtime_operations']
            yield deps, app


def test_healthy_admitted_work_and_native_question_have_no_authority_incident(decision_state):
    deps, _, _ = decision_state
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = list(uow.connection.iterdump())
        facts, policy, now = read(uow, deps)
        assert {row['family'] for row in facts} == {'native', 'dispatch'}
        assert [item for row in facts for item in project(row, now, policy)] == []
        assert before == list(uow.connection.iterdump())


def test_revoked_grant_blocks_pending_turn_and_native_request_without_leaking_content(decision_state, monkeypatch):
    deps, _, _ = decision_state
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at='2026-01-01T00:00:00Z'")
        facts, policy, now = read(uow, deps)
        before = list(uow.connection.iterdump())
        with monkeypatch.context() as pure:
            pure.setattr(deps.connection_factory, 'unit_of_work', lambda **_: pytest.fail('projection performed SQL'))
            pure.setattr(deps.clock, 'now_iso', lambda: pytest.fail('projection read wall clock'))
            result = [item for row in deepcopy(facts) for item in project(row, now, policy)]
        assert len(result) == 2
        assert {item['source_type'] for item in result} == {'execution_operation', 'execution_native_request'}
        assert all(item['kind'] == 'execution_authority_blocking' and item['category'] == 'action_required' for item in result)
        assert all(secret not in json.dumps(result) for secret in ('private-marker', 'api_key_hash', 'credential_binding', 'source_guard_digest'))
        assert before == list(uow.connection.iterdump())


@pytest.mark.parametrize('key', ['feature_harness_integrations', 'feature_hitl'])
def test_effective_policy_same_clock_recurrence_does_not_inherit_seen_or_snooze(decision_state, key):
    deps, _, _ = decision_state
    now = deps.clock.now_iso()
    publish_policy(deps, dict(feature_harness_integrations=True, feature_hitl=True), now)
    service = attention_service(deps, now)
    context = RuntimeRequestContext('operator', 'http_loopback', trusted_local_operator=True)
    def observed():
        return service.read(context=context, filters=dict(kind='execution_authority_blocking', state='all'))['items']
    assert observed() == []
    first_policy = publish_policy(deps, {key: False}, now)
    first = observed()
    assert first and all(stamp(item['first_detected_at']) == stamp(now) for item in first)
    item = first[0]
    marked = service.mark_seen(context=context, attention_id=item['attention_id'],
        source_revision=item['source_revision'], preference_revision=0)['item']
    service.snooze(context=context, attention_id=item['attention_id'], source_revision=item['source_revision'],
        preference_revision=marked['seen_state']['revision'], until=(stamp(now) + timedelta(hours=1)).isoformat())
    retained = next(row for row in observed() if row['attention_id'] == item['attention_id'])
    assert retained['seen_state']['seen'] and retained['seen_state']['snoozed']
    publish_policy(deps, {key: True}, now)
    assert observed() == []
    final_policy = publish_policy(deps, {key: False}, now)
    final = observed()
    assert final_policy[key]['generation'] == first_policy[key]['generation'] + 2
    assert final_policy[key]['changed_at'] == first_policy[key]['changed_at']
    assert {row['attention_id'] for row in first}.isdisjoint(row['attention_id'] for row in final)
    assert {row['source_revision'] for row in first}.isdisjoint(row['source_revision'] for row in final)
    assert all(row['seen_state'] == dict(seen=False, seen_at=None, snoozed=False, snoozed_until=None, revision=0) for row in final)
    assert all(stamp(row['first_detected_at']) == stamp(now) for row in final)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = list(uow.connection.iterdump())
        facts, policy, now = read(uow, deps)
        [project(row, now, policy) for row in facts]
        assert before == list(uow.connection.iterdump())
    assert publish_policy(deps, {key: False}, now) == final_policy
    assert observed() == final


@pytest.mark.parametrize('key', ['feature_harness_integrations', 'feature_hitl'])
def test_effective_policy_toggle_does_not_renew_independent_grant_revocation(decision_state, key):
    deps, _, _ = decision_state
    now = deps.clock.now_iso()
    publish_policy(deps, dict(feature_harness_integrations=True, feature_hitl=True), now)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE runtime_execution_grants SET revoked_at=?', (now,))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        first = items(uow, deps, now=now)
    assert len(first) == 2
    for value in (False, True, False):
        publish_policy(deps, {key: value}, now)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert items(uow, deps, now=now) == first


def test_effective_policy_wal_snapshot_keeps_values_and_generations_together(decision_state):
    deps, _, _ = decision_state
    now = deps.clock.now_iso()
    publish_policy(deps, dict(feature_harness_integrations=True, feature_hitl=True), now)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        facts, initial, _ = read(uow, deps, now=now)
        assert [item for row in facts for item in project(row, now, initial)] == []
        with ThreadPoolExecutor(max_workers=1) as pool:
            changed = pool.submit(publish_policy, deps, dict(feature_harness_integrations=False, feature_hitl=False), now).result(timeout=10)
        assert deps.config.feature_harness_integrations is False and deps.config.feature_hitl is False
        before = list(uow.connection.iterdump())
        facts, policy, _ = read(uow, deps, now=now)
        assert policy['effective_policy'] == initial['effective_policy']
        assert policy['feature_harness_integrations'] is True and policy['feature_hitl'] is True
        assert [item for row in facts for item in project(row, now, policy)] == []
        assert before == list(uow.connection.iterdump())
    with deps.connection_factory.unit_of_work(write=False) as uow:
        facts, policy, _ = read(uow, deps, now=now)
        assert policy['feature_harness_integrations'] is False and policy['feature_hitl'] is False
        assert all(policy['effective_policy'][key]['generation'] == value['generation'] for key, value in changed.items())
        assert len([item for row in facts for item in project(row, now, policy)]) == 2


def test_effective_hitl_policy_blocks_pending_native_dispatch_and_native_actions(decision_state):
    from okto_nexus.application.attention_native import project as native_project
    from okto_nexus.application.execution_native_decisions import validate_native_dispatch
    deps, _, _ = decision_state
    now = deps.clock.now_iso()
    publish_policy(deps, dict(feature_harness_integrations=True, feature_hitl=True), now)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        facts, policy, _ = read(uow, deps, now=now)
        native = next(row['native'] for row in facts if row['family'] == 'native')
        initial, = native_project(native, now, policy)
        assert 'decide_native' in initial['allowed_actions']
    publish_policy(deps, {'feature_hitl': False}, now)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        _, policy, _ = read(uow, deps, now=now)
        disabled, = native_project(native, now, policy)
        assert disabled['allowed_actions'] == ['inspect_approval']
        assert disabled['category'] == 'watch'
    publish_policy(deps, {'feature_hitl': True}, now)
    accepted = native_fixtures.post(decision_state)
    assert accepted.status_code == 202, accepted.text
    publish_policy(deps, {'feature_hitl': False}, now)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        result, = items(uow, deps, now=now)
        operation = uow.connection.execute("SELECT * FROM execution_operations WHERE action='approval.decide'").fetchone()
        assert result['operation_id'] == operation['operation_id']
        with pytest.raises(OktoNexusError, match='Native decision dispatch is disabled'):
            validate_native_dispatch(uow, operation=operation, semantic=json.loads(operation['semantic_payload']), access=build_execution_access(deps))


@pytest.mark.parametrize('queued_message,key', [('message', 'feature_harness_integrations'),
    ('required_native', 'feature_hitl'), ('handoff', 'feature_harness_integrations'),
    ('handoff', 'feature_hitl')], indirect=['queued_message'])
def test_effective_policy_delivery_and_handoff_recurrence(queued_message, key):
    from okto_nexus.adapters.inbound.mcp.tools.handoff import build_service
    deps, _ = queued_message
    now = deps.clock.now_iso()
    baseline = {name: getattr(deps.config, name) for name in ('feature_harness_integrations', 'feature_hitl')}
    publish_policy(deps, baseline, now)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert items(uow, deps, now=now) == []
    publish_policy(deps, {key: not baseline[key]}, now)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        first = items(uow, deps, now=now)
        assert first and all(stamp(item['first_detected_at']) == stamp(now) for item in first)
        if uow.connection.execute('SELECT 1 FROM runtime_handoff_bindings').fetchone():
            work = dict(uow.connection.execute('SELECT * FROM delivery_outbox').fetchone())
            service = build_service(deps, register_approval_executor=False)
            with pytest.raises(OktoNexusError):
                service.runtime_work.revalidate(uow, operation=work)
    publish_policy(deps, {key: baseline[key]}, now)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert items(uow, deps, now=now) == []
    publish_policy(deps, {key: not baseline[key]}, now)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        final = items(uow, deps, now=now)
        assert len(final) == len(first)
        assert {item['attention_id'] for item in first}.isdisjoint(item['attention_id'] for item in final)
        assert all(stamp(item['first_detected_at']) == stamp(now) for item in final)


def test_native_authority_mutations_match_canonical_live_predicates(decision_state):
    deps, _, _ = decision_state
    cases = [
        ('grant revoked', "UPDATE runtime_execution_grants SET revoked_at='2000-01-01T00:00:00Z'", False),
        ('grant expired', "UPDATE runtime_execution_grants SET no_expiry=0,expires_at='2000-01-01T00:00:00Z'", False),
        ('grant actions', "UPDATE runtime_execution_grants SET actions='[\"open\"]'", False),
        ('inactive actor', "UPDATE agents SET is_active=0 WHERE agent_id='subject'", False),
        ('credential rotated', "UPDATE agents SET api_key_hash='rotated' WHERE agent_id='subject'", False),
        ('permission', "UPDATE agents SET permissions='{\"messages\":{\"send_direct\":false}}' WHERE agent_id='subject'", True),
        ('endpoint disabled', "UPDATE agent_endpoints SET enabled=0", False),
        ('endpoint approval', "UPDATE agent_endpoints SET activation_state='pending'", False),
        ('profile disabled', "UPDATE runtime_profiles SET enabled=0", True),
        ('profile changed', "UPDATE runtime_profiles SET revision=revision+1", True),
        ('native response disabled', "UPDATE runtime_profiles SET config=json_set(config,'$.disabled_capabilities',json('[\"approvals\"]'))", True),
        ('runtime disabled', "UPDATE runtime_policy_defaults SET runtime_enabled=0", True),
        ('execution location', "UPDATE agent_execution_policies SET execution_location='local' WHERE agent_id='subject'", True),
        ('scope authorization', "UPDATE execution_agent_revisions SET authorization_revision=authorization_revision+1", False),
        ('binding revision', "UPDATE execution_bindings SET binding_revision=binding_revision+1", False),
        ('executor revoked', "UPDATE execution_executors SET revoked_at='2000-01-01T00:00:00Z'", False),
    ]
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        for label, sql, refresh in cases:
            conn.execute('SAVEPOINT mutation')
            try:
                conn.execute(sql)
                if refresh:
                    conn.execute('UPDATE execution_client_intents SET source_guard_digest=?', (_agent_guard(conn, 'subject'),))
                facts, policy, now = read(uow, deps)
                native = next(row for row in facts if row['family'] == 'native')
                request = conn.execute('SELECT * FROM execution_native_requests').fetchone()
                with pytest.raises(OktoNexusError):
                    deps.native_decisions._live(uow, request, json.loads(request['operational_frame_json']))
                assert len(project(native, now, policy)) == 1, label
            finally:
                conn.execute('ROLLBACK TO mutation')
                conn.execute('RELEASE mutation')


def test_queued_turn_denials_match_real_begin_send_boundary(decision_state, opening):
    from okto_nexus.application.execution_dispatch import reserve_execution_dispatch, begin_execution_send
    from okto_nexus.adapters.outbound.sqlite.execution_receipts import append_execution_receipt
    from okto_nexus.adapters.outbound.sqlite.execution_tickets import issue_execution_ticket, verify_execution_ticket
    from nexus_connector_core import R4_PREVIEW_REVISION
    deps, app, _ = decision_state
    channel, resolved = opening[5:7]
    issued = issue_execution_ticket(deps.connection_factory, server_id=channel.server_id, executor_id=channel.executor_id,
        binding_id='binding', agent_id='subject', scopes=frozenset({'receipt:publish'}))
    principal = verify_execution_ticket(deps.connection_factory, ticket=issued.ticket, server_id=channel.server_id,
        executor_id=channel.executor_id, binding_id='binding', scope='receipt:publish')
    append_execution_receipt(deps.connection_factory, principal=principal, frame=dict(protocol_major=1,
        contract_revision=R4_PREVIEW_REVISION, type='operation.receipt', server_id=channel.server_id,
        executor_id=channel.executor_id, binding_id='binding', agent_id='subject', session_id=resolved['scope']['session_id'],
        operation_id=resolved['operation_id'], intent_hash=resolved['intent_hash'], connection_id=channel.connection_id,
        connection_generation=channel.connection_generation, receipt_revision=1, stage='SUBMITTED',
        native_id='synthetic-attention-peer', possible_effect=True, retry_safe=False))
    with deps.connection_factory.unit_of_work() as uow:
        factory = DeliveryTransactionFactory(uow)
        work = uow.connection.execute("SELECT * FROM execution_operations WHERE action='turn.submit'").fetchone()
        reservation = reserve_execution_dispatch(factory, server_id=work['server_id'], executor_id=work['executor_id'], remote_ready=True)
        assert reservation is not None
        for sql in (
            "UPDATE runtime_execution_grants SET unlimited_actions=0,used_executions=max_executions",
            "UPDATE runtime_execution_grants SET revoked_at='2000-01-01T00:00:00Z'",
            "UPDATE runtime_profiles SET enabled=0",
            "UPDATE agents SET api_key_hash='rotated' WHERE agent_id='subject'",
            "UPDATE runtime_policy_defaults SET runtime_enabled=0",
        ):
            uow.connection.execute('SAVEPOINT mutation')
            try:
                uow.connection.execute(sql)
                facts, policy, now = read(uow, deps)
                pending = next(row for row in facts if row['family'] == 'dispatch')
                assert len(project(pending, now, policy)) == 1, sql
                with pytest.raises(OktoNexusError):
                    begin_execution_send(factory, reservation=reservation, remote_ready=True,
                        fresh_publications=app.state.inventory_fresh_publications, access=build_execution_access(deps))
                assert uow.connection.execute('SELECT dispatch_state FROM execution_dispatch_outbox WHERE operation_id=?',
                    (work['operation_id'],)).fetchone()[0] == 'RESERVED'
            finally:
                uow.connection.execute('ROLLBACK TO mutation')
                uow.connection.execute('RELEASE mutation')


def test_offline_recovery_inventory_wait_and_lease_renewal_are_not_authority_denials(decision_state):
    deps, app, _ = decision_state
    with deps.connection_factory.unit_of_work() as uow:
        for sql in (
            "UPDATE execution_executors SET control_state='DISCONNECTED'",
            "UPDATE execution_control_lanes SET state='DISCONNECTED'",
            "UPDATE execution_leases SET valid_until_server='2000-01-01T00:00:00Z'",
            "UPDATE execution_leases SET status='ISSUED',applied_at=NULL",
            "UPDATE execution_sessions SET lease_state='LEASE_PENDING'",
            "INSERT INTO execution_agent_recovery(server_id,executor_id,agent_id,generation,state,updated_at) SELECT server_id,executor_id,'subject',generation,'RECOVERING','2000-01-01T00:00:00Z' FROM execution_executors",
        ):
            uow.connection.execute('SAVEPOINT availability')
            try:
                uow.connection.execute(sql)
                assert items(uow, deps) == [], sql
            finally:
                uow.connection.execute('ROLLBACK TO availability')
                uow.connection.execute('RELEASE availability')
        app.state.inventory_fresh_publications.clear()
        assert items(uow, deps) == []


def test_exhausted_budget_blocks_new_turn_but_not_response_to_existing_native_request(decision_state):
    deps, _, _ = decision_state
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE runtime_execution_grants SET unlimited_actions=0,used_executions=max_executions')
        result = items(uow, deps)
        assert len(result) == 1 and result[0]['source_type'] == 'execution_operation'
        request = uow.connection.execute('SELECT * FROM execution_native_requests').fetchone()
        deps.native_decisions._live(uow, request, json.loads(request['operational_frame_json']))


def test_approved_native_decision_is_one_pending_authority_unit(decision_state):
    deps, _, _ = decision_state
    response = native_fixtures.post(decision_state)
    assert response.status_code == 202, response.text
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at='2000-01-01T00:00:00Z'")
        facts, policy, now = read(uow, deps)
        assert not any(row['family'] == 'native' for row in facts)
        pending = [row for row in facts if row['family'] == 'dispatch' and row['work']['action'] == 'approval.decide']
        assert len(pending) == 1 and len(project(pending[0], now, policy)) == 1


def test_episode_stability_rollback_and_reentry_ignore_retry_and_observation_timestamps(decision_state):
    deps, _, _ = decision_state
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        conn.execute("UPDATE runtime_profiles SET enabled=0")
        first = items(uow, deps)
        conn.execute("UPDATE agent_endpoints SET updated_at='2099-01-01',last_observed_at='2099-01-01'")
        conn.execute("UPDATE runtime_profiles SET updated_at='2099-01-01'")
        conn.execute('UPDATE execution_dispatch_outbox SET attempt_no=attempt_no+1')
        assert items(uow, deps) == first
        conn.execute('SAVEPOINT authority')
        conn.execute('UPDATE runtime_profiles SET enabled=1')
        assert items(uow, deps) == []
        conn.execute('UPDATE runtime_profiles SET enabled=0')
        aborted = items(uow, deps)
        assert {row['attention_id'] for row in aborted}.isdisjoint(row['attention_id'] for row in first)
        conn.execute('ROLLBACK TO authority')
        conn.execute('RELEASE authority')
        assert items(uow, deps) == first


def test_scope_filters_and_terminal_or_expired_work_do_not_report_authority(decision_state):
    deps, _, _ = decision_state
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at='2000-01-01T00:00:00Z'")
        assert len(items(uow, deps)) == 2
        assert items(uow, deps, workspace_id='foreign') == []
        assert items(uow, deps, agent_id='foreign') == []
        uow.connection.execute("UPDATE execution_dispatch_outbox SET dispatch_state='DISPATCHED' WHERE dispatch_state='PENDING'")
        uow.connection.execute("UPDATE execution_native_requests SET expires_at='2000-01-01T00:00:00Z'")
        assert items(uow, deps) == []


def test_managed_message_uses_canonical_sender_audience_permissions_and_policy(queued_message):
    deps, _ = queued_message
    from okto_nexus.adapters.inbound.mcp.tools.messages import build_service
    service = build_service(deps)
    cases = [
        ('sender retired', "UPDATE agents SET is_active=0 WHERE agent_id='operator'"),
        ('sender credential', "UPDATE agents SET api_key_hash='rotated' WHERE agent_id='operator'"),
        ('sender permission', "UPDATE agents SET permissions='{\"messages\":{\"send_direct\":false}}' WHERE agent_id='operator'"),
        ('recipient retired', "UPDATE agents SET is_active=0 WHERE agent_id='subject'"),
        ('audience', "UPDATE agents SET comm_scope='{\"inbound\":{\"team\":[\"blocked\"]}}' WHERE agent_id='subject'"),
        ('endpoint revision', "UPDATE agent_endpoints SET revision=revision+1"),
        ('profile revision', "UPDATE runtime_profiles SET revision=revision+1"),
        ('method disabled', "INSERT INTO agent_connection_methods(agent_id,method,enabled) VALUES('subject','codex_app_server',0)"),
        ('policy revision', "INSERT INTO agent_policy_bindings(agent_id,position,source,audience,governance,created_at) VALUES('operator',0,'inline',NULL,'[]','2026-01-01T00:00:00Z')"),
    ]
    access = build_execution_access(deps)
    with deps.connection_factory.unit_of_work() as uow:
        operation = dict(uow.connection.execute('SELECT * FROM delivery_outbox').fetchone())
        assert items(uow, deps) == []
        for label, sql in cases:
            uow.connection.execute('SAVEPOINT message_case')
            try:
                uow.connection.execute(sql)
                result = items(uow, deps)
                assert result, label
                with pytest.raises(OktoNexusError):
                    access.validate_domain_delivery(uow, operation)
                assert all(secret not in json.dumps(result) for secret in ('Private attention', 'credential_binding', 'api_key_hash'))
            finally:
                uow.connection.execute('ROLLBACK TO message_case')
                uow.connection.execute('RELEASE message_case')
        # Both production metadata authority checks still accept the source.
        service.revalidate_runtime_delivery(uow, operation)
        access.validate_domain_delivery(uow, operation)


@pytest.mark.parametrize('keep_agents', [True, False])
def test_reset_discards_authority_tombstones_but_preserves_retained_config_counters(migrated_factory, keep_agents):
    from okto_nexus.application.database_reset import clear_operational_history
    with migrated_factory.unit_of_work() as uow:
        conn = uow.connection
        conn.execute("INSERT INTO agents(agent_id,created_at) VALUES('retained','2026-01-01T00:00:00Z')")
        conn.execute("INSERT INTO agents(agent_id,created_at) VALUES('removed','2026-01-01T00:00:00Z')")
        conn.execute("UPDATE agents SET is_active=0 WHERE agent_id='retained'")
        conn.execute("DELETE FROM agents WHERE agent_id='removed'")
        old = tuple(conn.execute("SELECT episode,first_detected_at,last_changed_at FROM attention_operation_epochs "
            "WHERE source_type='authority_agents' AND source_id=json_array('retained')").fetchone())
        assert conn.execute("SELECT count(*) FROM attention_operation_epochs WHERE state='deleted' AND source_type LIKE 'authority_%'").fetchone()[0] == 1
        clear_operational_history(conn, keep_agents=keep_agents)
        assert conn.execute("SELECT count(*) FROM attention_operation_epochs WHERE state='deleted' AND source_type LIKE 'authority_%'").fetchone()[0] == 0
        row = conn.execute("SELECT episode,first_detected_at,last_changed_at FROM attention_operation_epochs "
            "WHERE source_type='authority_agents' AND source_id=json_array('retained')").fetchone()
        assert tuple(row) == old if keep_agents else row is None


def test_migration_161_to_162_backfills_metadata_only_and_never_changes_161(conn_factory, tmp_path):
    from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
    from okto_nexus.adapters.outbound.sqlite.attention_authority import ANCHOR_SCHEMA_SQL
    from importlib.resources import files
    import hashlib
    source = files('okto_nexus').joinpath('migrations')
    previous = tmp_path / 'previous'
    previous.mkdir()
    digest = hashlib.sha256((source / '161_attention_preferences.sql').read_bytes()).hexdigest()
    for path in source.iterdir():
        if path.name.endswith('.sql') and int(path.name.split('_')[0]) <= 161:
            (previous / path.name).write_bytes(path.read_bytes())
    MigrationRunner(conn_factory, previous).apply()
    with conn_factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO agents(agent_id,api_key_hash,metadata,created_at) VALUES('retained','private-key-digest','{\"private\":true}','2026-01-01T00:00:00Z')")
    assert MigrationRunner(conn_factory).apply() == [162, 163, 164, 165]
    with conn_factory.unit_of_work(write=False) as uow:
        anchor = dict(uow.connection.execute("SELECT * FROM attention_operation_epochs WHERE source_type='authority_agents'").fetchone())
        assert anchor['episode'] == 1 and anchor['state'] == 'present'
        assert 'private' not in json.dumps(anchor)
    assert hashlib.sha256((source / '161_attention_preferences.sql').read_bytes()).hexdigest() == digest
    assert ANCHOR_SCHEMA_SQL in (source / '162_attention_authority_epochs.sql').read_text(encoding='utf-8')


@pytest.mark.parametrize('queued_message', ['handoff'], indirect=True)
def test_handoff_current_authority_budget_and_legacy_preference_identity(queued_message):
    from okto_nexus.domain.attention import digest
    from okto_nexus.adapters.inbound.mcp.tools.handoff import build_service
    deps, _ = queued_message
    service = build_service(deps, register_approval_executor=False)
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        work = dict(conn.execute('SELECT * FROM delivery_outbox').fetchone())
        binding = conn.execute('SELECT * FROM runtime_handoff_bindings').fetchone()
        grant = conn.execute('SELECT * FROM runtime_execution_grants WHERE grant_id=?', (binding['grant_id'],)).fetchone()
        assert grant['used_executions'] == grant['max_executions'] == 1
        # The work grant was consumed at admission; deferred revalidation does
        # not charge it again or mistake that consumed budget for revocation.
        service.runtime_work.revalidate(uow, operation=work)
        assert items(uow, deps) == []
        conn.execute("UPDATE runtime_execution_grants SET revoked_at='2026-01-01T00:00:00Z' WHERE grant_id=?", (binding['grant_id'],))
        first, = items(uow, deps)
        old_episode = [binding['grant_id'], binding['grant_revision'], work['endpoint_revision'], work['profile_revision']]
        assert first['attention_id'] == 'att_' + digest([1, 'execution_authority_blocking', 'delivery_operation', work['operation_id'], old_episode])
        assert first['source_type'] == 'delivery_operation'
        with pytest.raises(OktoNexusError):
            service.runtime_work.revalidate(uow, operation=work)
        conn.execute("UPDATE delivery_outbox SET updated_at='2099-01-01',attempt_count=attempt_count+1")
        assert items(uow, deps) == [first]
        from okto_nexus.application.server_effective_policy import publish_effective_policy
        # Legacy grant revocation is still the cause. Global toggles must not
        # replace its v161 identity or alter viewing CAS material.
        for value in (True, False, True):
            publish_effective_policy(uow, values=dict(feature_harness_integrations=value, feature_hitl=value), now=deps.clock.now_iso())
            assert items(uow, deps) == [first]


@pytest.mark.parametrize('change', ['responder_key', 'opening_grant', 'opening_initiator'])
def test_native_decision_revalidates_responder_and_original_opening_authority(decision_state, change):
    deps, _, _ = decision_state
    if change == 'opening_initiator':
        # Recorded delegated initiation is a fixture precondition; its guard
        # is produced by the same canonical helper used by native admission.
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE execution_operations SET actor_agent_id='operator' WHERE action='runtime.open'")
            uow.connection.execute("UPDATE execution_client_intents SET actor_agent_id='operator',actor_guard_digest=? "
                "WHERE operation_id IN(SELECT operation_id FROM execution_operations WHERE action='runtime.open')",
                ('local-operator:' + _agent_guard(uow.connection, 'operator'),))
    accepted = native_fixtures.post(decision_state)
    assert accepted.status_code == 202, accepted.text
    with deps.connection_factory.unit_of_work() as uow:
        if change == 'opening_grant':
            uow.connection.execute("UPDATE runtime_execution_grants SET actions='[\"send\",\"interrupt\",\"close\"]',revision=revision+1")
        elif change == 'opening_initiator':
            uow.connection.execute("UPDATE execution_client_intents SET actor_guard_digest='local-operator:changed' "
                "WHERE operation_id IN(SELECT operation_id FROM execution_operations WHERE action='runtime.open')")
        else:
            uow.connection.execute("UPDATE agents SET api_key_hash='rotated' WHERE agent_id='operator'")
        facts, policy, now = read(uow, deps)
        pending = next(row for row in facts if row['family'] == 'dispatch' and row['work']['action'] == 'approval.decide')
        projected, = project(pending, now, policy)
        assert projected['executor_id'] == pending['work']['executor_id']
        from okto_nexus.application.execution_native_decisions import validate_native_dispatch
        operation = uow.connection.execute("SELECT * FROM execution_operations WHERE action='approval.decide'").fetchone()
        with pytest.raises(OktoNexusError):
            validate_native_dispatch(uow, operation=operation, semantic=json.loads(operation['semantic_payload']), access=build_execution_access(deps))


def test_expiration_without_write_uses_last_eligible_grant_deadline(queued_message):
    deps, _ = queued_message
    now = deps.clock.now_iso()
    deadline = (stamp(now) + timedelta(seconds=60)).isoformat()
    last_deadline = (stamp(now) + timedelta(seconds=120)).isoformat()
    access = build_execution_access(deps)
    context = RuntimeRequestContext('operator', 'http_loopback', trusted_local_operator=True)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE runtime_execution_grants SET no_expiry=0,expires_at=?', (deadline,))
    access.issue(context, actor_agent_id='subject', endpoint_id='ep', actions=['open', 'send'],
        expires_at=last_deadline, max_executions=10)
    access.issue(context, actor_agent_id='other', endpoint_id='ep', actions=['open', 'send'],
        expires_at=(stamp(now) + timedelta(seconds=600)).isoformat(), max_executions=10)
    with deps.connection_factory.unit_of_work() as uow:
        assert items(uow, deps, now=(stamp(now) + timedelta(seconds=59)).isoformat()) == []
        assert items(uow, deps, now=(stamp(now) + timedelta(seconds=61)).isoformat()) == []
        result = items(uow, deps, now=(stamp(now) + timedelta(seconds=121)).isoformat())
        assert result
        assert all(stamp(item['first_detected_at']) == stamp(last_deadline) for item in result)
        assert items(uow, deps, now=(stamp(now) + timedelta(seconds=180)).isoformat()) == result
        uow.connection.execute("UPDATE runtime_execution_grants SET revision=revision+1 WHERE actor_agent_id='other'")
        assert items(uow, deps, now=(stamp(now) + timedelta(seconds=180)).isoformat()) == result


def test_content_guardrail_denial_is_distinct_from_authority_revocation(queued_message):
    from test_guardrails import _add_guardrail
    deps, _ = queued_message
    with deps.connection_factory.unit_of_work() as uow:
        _add_guardrail(uow, guardrail_id='authority-content-boundary',
            evaluator_config={'kind': 'keyword_blocklist', 'keywords': ['Private attention']})
        operation = dict(uow.connection.execute('SELECT * FROM delivery_outbox').fetchone())
        with pytest.raises(OktoNexusError) as error:
            build_execution_access(deps).validate_domain_delivery(uow, operation)
        assert str(error.value.code) == 'GUARDRAIL_DENIED'
        assert items(uow, deps) == []


def test_pending_relay_rechecks_original_actor_and_ancestor_configuration(relay_pair, monkeypatch):
    from okto_nexus.application import execution_dispatch_pump
    setup, first, _, _, native_factory = relay_pair
    deps = setup[0]
    observer_setup = relay_fixtures.create_agent(setup, 'observer')
    _, third, _ = relay_fixtures.connect_local(observer_setup, agent_id='observer')
    setup[1].state.embedded_dispatch_owner.native_factory = native_factory
    deps.config.max_relay_depth = 1
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='conversation',public_config=? WHERE endpoint_id=?",
            (json.dumps(dict(relay_results=True)), third['endpoint_id']))
        uow.connection.execute('UPDATE agent_endpoints SET public_config=? WHERE endpoint_id=?',
            (json.dumps(dict(relay_results=True, notify_target=dict(strategy='direct', agent_id='observer'))), first['endpoint_id']))
    held, release = threading.Event(), threading.Event()
    original = execution_dispatch_pump.begin_execution_send
    def hold_relay(factory, **kwargs):
        reservation = kwargs['reservation']
        with factory.unit_of_work(write=False) as uow:
            relay = uow.connection.execute('SELECT d.source_result_id FROM execution_domain_deliveries x '
                'JOIN delivery_outbox d ON d.operation_id=x.domain_operation_id WHERE x.server_id=? '
                'AND x.executor_id=? AND x.operation_id=?',
                (reservation.server_id, reservation.executor_id, reservation.operation_id)).fetchone()
        if relay and relay[0] and not held.is_set():
            held.set()
            assert release.wait(30), 'The test did not release its reserved relay'
        return original(factory, **kwargs)
    monkeypatch.setattr(execution_dispatch_pump, 'begin_execution_send', hold_relay)
    try:
        result = relay_fixtures.send(setup, monkeypatch)
        assert result['ok'], result
        assert held.wait(20), 'No real canonical relay reached its deferred-send fence'
        with deps.connection_factory.unit_of_work() as uow:
            relay = dict(uow.connection.execute('SELECT * FROM delivery_outbox WHERE source_result_id IS NOT NULL').fetchone())
            assert relay['actor_agent_id'] == 'caller' and relay['recipient_agent_id'] == 'observer'
            assert items(uow, deps) == []
            build_execution_access(deps).validate_domain_delivery(uow, relay)
            for sql, values in (
                ("UPDATE agents SET api_key_hash='rotated' WHERE agent_id='caller'", ()),
                ("UPDATE agent_endpoints SET public_config=json_set(public_config,'$.relay_results',json('false')) WHERE endpoint_id=?", (first['endpoint_id'],)),
                ("INSERT INTO agent_policy_bindings(agent_id,position,source,audience,governance,created_at) VALUES('caller',0,'inline',NULL,'[]','2026-01-01T00:00:00Z')", ()),
            ):
                uow.connection.execute('SAVEPOINT relay_change')
                try:
                    uow.connection.execute(sql, values)
                    assert items(uow, deps), sql
                    with pytest.raises(OktoNexusError):
                        build_execution_access(deps).validate_domain_delivery(uow, relay)
                finally:
                    uow.connection.execute('ROLLBACK TO relay_change')
                    uow.connection.execute('RELEASE relay_change')
    finally:
        release.set()


@pytest.mark.parametrize('queued_message', ['notice'], indirect=True)
def test_pending_handoff_notice_rechecks_governance_audience(queued_message):
    deps, _ = queued_message
    with deps.connection_factory.unit_of_work() as uow:
        operation = dict(uow.connection.execute('SELECT d.* FROM delivery_outbox d JOIN runtime_handoff_notifications n USING(message_id)').fetchone())
        assert items(uow, deps) == []
        build_execution_access(deps).validate_domain_delivery(uow, operation)
        uow.connection.execute('SAVEPOINT obsolete_notice')
        uow.connection.execute("UPDATE handoffs SET status='CLAIMED',claimed_by='subject'")
        uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at='2000-01-01T00:00:00Z'")
        assert items(uow, deps) == []  # Availability notice already retired by a claim.
        uow.connection.execute('ROLLBACK TO obsolete_notice')
        uow.connection.execute('RELEASE obsolete_notice')
        uow.connection.execute("INSERT INTO agent_policy_bindings(agent_id,position,source,audience,governance,created_at) "
            "VALUES('operator',0,'inline',?,'[]','2026-01-01T00:00:00Z')", (json.dumps({'outbound': {'team': ['unavailable']}}),))
        with pytest.raises(OktoNexusError):
            build_execution_access(deps).validate_domain_delivery(uow, operation)
        assert items(uow, deps)
