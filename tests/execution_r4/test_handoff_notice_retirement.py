"""Backlog retirement shares the actual sender fence, not an ACK heuristic."""
import json
from pathlib import Path

import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable
from test_agent_recovery_isolation import eventually
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.adapters.outbound.sqlite.execution_pending_cancellation import SqlitePendingExecutionCancellation
from okto_nexus.adapters.outbound.sqlite.handoff_notice_retirement import SqliteHandoffNoticeRetirement
from okto_nexus.adapters.outbound.sqlite.handoff_runtime_schedule import SqliteHandoffScheduleRepository
from okto_nexus.adapters.outbound.sqlite.messages_repo import SqliteMessageDeliveryRepo
from okto_nexus.config import NexusConfig
from okto_nexus.bootstrap.resource_pool import one_shot_pool


def retirement():
    return SqliteHandoffNoticeRetirement(cancellations=SqlitePendingExecutionCancellation(),
        inbox=SqliteMessageDeliveryRepo(), schedule=SqliteHandoffScheduleRepository(), pool_factory=one_shot_pool)


@pytest.fixture
def backlog(tmp_path):
    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path))
    MigrationRunner(factory).apply()
    now = '2026-01-01T00:00:00Z'
    with factory.unit_of_work() as uow:
        c = uow.connection
        c.execute('INSERT INTO workspaces(workspace_id,created_at) VALUES(?,?)', ('w', now))
        c.execute('INSERT INTO agents(agent_id,created_at) VALUES(?,?)', ('a', now))
        c.execute('INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,protocol,created_at,updated_at) '
                  'VALUES(?,?,?,?,?,?,?)', ('e', 'a', 'w', 'fixture', 'nxl-r4', now, now))
        for name, state, route in [('a-uncertain', 'OUTCOME_UNKNOWN', 'legacy_admitted'),
                ('b-safe', 'PENDING', 'legacy_admitted'), ('c-direct', 'PENDING', 'conversation'),
                ('d-old-attempt', 'PENDING', 'legacy_admitted')]:
            c.execute('INSERT INTO handoffs(handoff_id,workspace_id,target,status,created_at) VALUES(?,?,?,?,?)',
                      (name, 'w', json.dumps(dict(strategy='broadcast')), 'OPEN', now))
            c.execute('INSERT INTO messages(message_id,workspace_id,from_agent_id,body,created_at) VALUES(?,?,?,?,?)',
                      (name, 'w', 'a', '{}', now))
            c.execute('INSERT INTO message_deliveries(delivery_id,message_id,recipient_agent_id,status,created_at) VALUES(?,?,?,?,?)',
                      (name, name, 'a', 'unread', now))
            c.execute('INSERT INTO runtime_handoff_notifications VALUES(?,?,?,?,?,?)',
                      (name, name, 'a', 'handoff.created', 'guard', route))
            c.execute('INSERT INTO delivery_outbox(operation_id,delivery_id,message_id,workspace_id,actor_agent_id,'
                'credential_binding,recipient_agent_id,endpoint_id,endpoint_revision,envelope,request_hash,'
                'authorization_revision,root_operation_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (name, name, name, 'w', 'a', 'bound', 'a', 'e', 1, '{}', 'hash', 'auth', name, state, now, now))
            c.execute("UPDATE message_deliveries SET consumer_kind='push',consumer_operation_id=? WHERE delivery_id=?", (name, name))
        c.execute("UPDATE delivery_outbox SET attempt_count=1,attempt_id='lost-history' WHERE operation_id='d-old-attempt'")
    return factory


def test_rotation_restart_preserves_uncertain_history_and_only_releases_owned_inbox(backlog):
    with backlog.unit_of_work() as uow:
        before = dict(uow.connection.execute("SELECT * FROM delivery_outbox WHERE operation_id='a-uncertain'").fetchone())
        assert retirement().retire_page(uow, now=10, limit=1) == 0
    # A new scanner resumes the durable cursor past an unresolved first row.
    with backlog.unit_of_work() as uow:
        assert retirement().retire_page(uow, now=11, limit=1) == 1
        assert dict(uow.connection.execute("SELECT * FROM delivery_outbox WHERE operation_id='a-uncertain'").fetchone()) == before
        assert uow.connection.execute("SELECT status,consumer_kind,read_at FROM message_deliveries WHERE delivery_id='b-safe'").fetchone()[:] == ('unread', None, None)
        assert uow.connection.execute('SELECT actor_kind,previous_state FROM runtime_handoff_notice_retirements').fetchone()[:] == ('system_migration', 'PENDING')
        assert uow.connection.execute('SELECT handoff_id FROM handoff_runtime_schedule').fetchone()[0] == 'b-safe'
    for _ in range(4):
        with backlog.unit_of_work() as uow:
            assert retirement().retire_page(uow, now=12, limit=1) == 0
    with backlog.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM runtime_handoff_notice_retirements').fetchone()[0] == 1
        assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()


def test_retirement_is_atomic_and_does_not_steal_mcp_ack(backlog):
    with backlog.unit_of_work() as uow:
        uow.connection.execute("UPDATE message_deliveries SET consumer_kind='pull',consumer_operation_id=NULL,status='read' WHERE delivery_id='b-safe'")
    with pytest.raises(RuntimeError):
        with backlog.unit_of_work() as uow:
            assert retirement().retire_page(uow, now=10, limit=20) == 1
            raise RuntimeError('crash before commit')
    with backlog.unit_of_work() as uow:
        assert uow.connection.execute('SELECT count(*) FROM runtime_handoff_notice_retirements').fetchone()[0] == 0
        assert retirement().retire_page(uow, now=11, limit=20) == 1
        assert uow.connection.execute("SELECT status,consumer_kind FROM message_deliveries WHERE delivery_id='b-safe'").fetchone()[:] == ('read', 'pull')


def test_queued_one_shot_notice_is_removed_without_disturbing_earlier_capacity(backlog):
    with backlog.unit_of_work() as uow:
        pool = one_shot_pool(uow.connection)
        args = dict(pool_id='a', host_id='host', caller_id='a', request_hash='hash',
                    configuration='config', host_limit=1, now=10)
        assert pool.admit(request_id='ordinary-earlier', **args).state == 'ADMITTED'
        assert pool.admit(request_id='b-safe', **args).state == 'QUEUED'
        uow.connection.execute("UPDATE delivery_outbox SET status='ACCEPTED' WHERE operation_id='b-safe'")
        assert retirement().retire_page(uow, now=11, limit=32) == 1
        assert pool.request('ordinary-earlier').state == 'ADMITTED'
        assert pool.request('b-safe').state == 'CANCELLED'
        assert pool.request('b-safe').outcome['error']['possible_effect'] is False
        assert not uow.connection.execute('SELECT * FROM execution_operations').fetchall()


def create_notice(setup, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    _, _, client, headers, *_, root = setup
    client.headers['host'] = '127.0.0.1:8000'
    result = tool(client, headers['operator']['Authorization'].removeprefix('Bearer '), 'handoff_create',
        dict(project_root=str(root), from_agent_id='operator', target=dict(strategy='direct', agent_id='subject'),
             visibility='eligible', payload='private work'))
    assert result['ok'], result
    return result['data']['handoff_id']


def mark_old_broadcast(uow, handoff_id):
    # Reproduce the persisted pre-upgrade route after ordinary real admission.
    uow.connection.execute('UPDATE handoffs SET target=? WHERE handoff_id=?', ('{"strategy":"broadcast"}', handoff_id))
    uow.connection.execute("UPDATE runtime_handoff_notifications SET runtime_route='legacy_admitted' WHERE handoff_id=?", (handoff_id,))


@pytest.mark.parametrize('one_shot', [False, True])
def test_retirement_wins_reserved_send_race_without_model_or_broken_lane(connected_local, monkeypatch, one_shot):
    setup, binding, native = connected_local
    enable(setup, binding)
    if one_shot:
        from test_sender_sessions import configure
        configure(setup, binding, 'one_shot')
    deps, app, client, *_ = setup
    lock = app.state.embedded_dispatch_owner.pump.send_lock
    client.portal.call(lock.acquire)
    try:
        handoff_id = create_notice(setup, monkeypatch)
        def reserved():
            with deps.connection_factory.unit_of_work(write=False) as uow:
                return uow.connection.execute("SELECT count(*) FROM execution_dispatch_outbox WHERE dispatch_state='RESERVED'").fetchone()[0] == 1
        eventually(reserved)
        with deps.connection_factory.unit_of_work() as uow:
            mark_old_broadcast(uow, handoff_id)
            if not one_shot:
                # NONE ACK is not proof: a turn past its durable send fence
                # remains untouched even before the first receipt arrives.
                c = uow.connection
                for state in ('SENDING', 'RECONCILING'):
                    c.execute('SAVEPOINT uncertain_turn')
                    c.execute("INSERT INTO execution_dispatch_outbox(server_id,executor_id,operation_id,dispatch_state) "
                        "SELECT server_id,executor_id,operation_id,? FROM execution_operations WHERE action='turn.submit'", (state,))
                    assert retirement().retire_page(uow, now=10, limit=32) == 0
                    assert c.execute('SELECT count(*) FROM runtime_handoff_notice_retirements').fetchone()[0] == 0
                    c.execute('ROLLBACK TO uncertain_turn')
                    c.execute('RELEASE uncertain_turn')
            assert retirement().retire_page(uow, now=10, limit=32) == 1
            assert uow.connection.execute("SELECT count(*) FROM execution_domain_deliveries m JOIN execution_dispatch_outbox x "
                "USING(server_id,executor_id,operation_id) WHERE x.dispatch_state<>'RESOLVED_TERMINAL'").fetchone()[0] == 0
            assert uow.connection.execute('SELECT count(*) FROM execution_receipts').fetchone()[0] == 0
    finally:
        client.portal.call(lock.release)
    if one_shot:
        from test_one_shot_runtime import wait_until, query
        wait_until(setup, lambda: not query(setup, 'SELECT * FROM one_shot_slots'))
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT state FROM one_shot_calls').fetchone()[0] == 'CANCELLED'
            assert uow.connection.execute('SELECT count(*) FROM one_shot_slots').fetchone()[0] == 0
            assert uow.connection.execute('SELECT count(*) FROM messages').fetchone()[0] == 1
        assert not native.native.sent  # An independent pool opening may finish, then close.
    else:
        assert native.opens == 0
    previous_opens = native.opens
    if one_shot:
        from test_canonical_delivery import send
        assert send(setup, monkeypatch)['ok']
        eventually(lambda: native.opens == previous_opens + 1 and len(native.native.sent) == 1)
    else:
        next_open = admit(setup, binding, 'after-notice-retirement', 'runtime.start', new_session=True)
        wait_receipt(setup, next_open)
    assert native.opens == previous_opens + 1 and app.state.embedded_dispatch_owner.pump.error is None
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status,reason FROM delivery_outbox WHERE operation_id IN '
            '(SELECT operation_id FROM runtime_handoff_notice_retirements)').fetchone()[:] == ('CANCELLED', 'competitive_notice_before_send')
        assert uow.connection.execute('SELECT count(*) FROM runtime_results').fetchone()[0] == 0


def test_submitted_notice_is_not_reclassified_or_replayed(connected_local, monkeypatch):
    setup, binding, native = connected_local
    enable(setup, binding)
    deps = setup[0]
    handoff_id = create_notice(setup, monkeypatch)
    def submitted():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return uow.connection.execute("SELECT count(*) FROM execution_receipts r JOIN execution_operations p "
                "USING(server_id,executor_id,operation_id) WHERE r.stage='SUBMITTED' AND p.action='turn.submit'").fetchone()[0] > 0
    eventually(submitted)
    with deps.connection_factory.unit_of_work() as uow:
        mark_old_broadcast(uow, handoff_id)
        before = tuple(uow.connection.execute('SELECT * FROM delivery_outbox').fetchone())
        assert retirement().retire_page(uow, now=10, limit=32) == 0
        assert tuple(uow.connection.execute('SELECT * FROM delivery_outbox').fetchone()) == before
        assert uow.connection.execute('SELECT runtime_route FROM runtime_handoff_notifications').fetchone()[0] == 'legacy_admitted'
    assert native.opens == 1 and len(native.native.sent) == 1


def test_opened_provider_is_preserved_but_unsent_initial_notice_is_retired(connected_local, monkeypatch):
    from okto_nexus.application import execution_initial_turns
    setup, binding, native = connected_local
    deps = setup[0]
    enable(setup, binding)
    release = execution_initial_turns.release_ready_initial_turns
    monkeypatch.setattr(execution_initial_turns, 'release_ready_initial_turns', lambda *a, **k: None)
    handoff_id = create_notice(setup, monkeypatch)
    def ready():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return uow.connection.execute("SELECT count(*) FROM execution_sessions WHERE lifecycle_state='READY' AND lease_state='ACTIVE'").fetchone()[0] == 1
    eventually(ready)
    with deps.connection_factory.unit_of_work() as uow:
        c = uow.connection
        opening = tuple(c.execute("SELECT * FROM execution_dispatch_outbox x JOIN execution_operations p "
            "USING(server_id,executor_id,operation_id) WHERE p.action='runtime.open'").fetchone())
        mark_old_broadcast(uow, handoff_id)
        assert retirement().retire_page(uow, now=10, limit=32) == 1
        assert tuple(c.execute("SELECT * FROM execution_dispatch_outbox x JOIN execution_operations p "
            "USING(server_id,executor_id,operation_id) WHERE p.action='runtime.open'").fetchone()) == opening
        assert c.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()[:] == ('READY', 'ACTIVE')
        from okto_nexus.application.execution_domain_delivery import project_delivery_receipt
        opened = c.execute("SELECT server_id,executor_id,operation_id FROM execution_operations WHERE action='runtime.open'").fetchone()
        project_delivery_receipt(c, **dict(opened), action='runtime.open', stage='FAILED')
        assert c.execute('SELECT status FROM delivery_outbox').fetchone()[0] == 'CANCELLED'
    monkeypatch.setattr(execution_initial_turns, 'release_ready_initial_turns', release)
    from test_canonical_delivery import send
    assert send(setup, monkeypatch)['ok']
    eventually(lambda: native.native is not None and len(native.native.sent) == 1)
    assert native.opens == 1  # Existing provider remains reusable, no old notice prompt.
