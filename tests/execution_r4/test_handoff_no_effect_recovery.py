"""Only exact no-effect and physical-release proof reopens managed work."""
import json
import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.outbound.sqlite.handoff_runtime_candidates import SqliteHandoffCandidateRepository
from okto_nexus.adapters.outbound.sqlite.handoff_runtime_schedule import SqliteHandoffScheduleRepository
from okto_nexus.adapters.outbound.sqlite.migrations import _split_statements, _default_migrations_dir
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.application.handoff_runtime_scheduler import HandoffScheduleLease
from okto_nexus.application.handoff_runtime_candidates import HandoffCandidateDiscovery
from okto_nexus.config import NexusConfig


def evidence():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE handoffs(handoff_id,workspace_id,claim_epoch,status,claimed_by,target);
        CREATE TABLE runtime_handoff_bindings(handoff_id,claim_epoch,operation_id);
        CREATE TABLE delivery_outbox(operation_id,status,reconciliation_id,external_completed_at);
        CREATE TABLE handoff_runtime_attempts(attempt_id,workspace_id,handoff_id,agent_id,
            claim_generation,operation_id,state,active,disposition,reason,updated_at);
        CREATE TABLE one_shot_calls(call_id,state,outcome_json);
        CREATE TABLE execution_capacity_admissions(domain_operation_id,server_id,executor_id,session_id,state);
        CREATE TABLE execution_sessions(server_id,executor_id,session_id,lifecycle_state,lease_state);
        CREATE TABLE execution_domain_deliveries(domain_operation_id,server_id,executor_id,operation_id);
        CREATE TABLE execution_operations(server_id,executor_id,operation_id,action);
        CREATE TABLE execution_receipts(server_id,executor_id,operation_id,receipt_revision,
            stage,possible_effect,retry_safe,error_code);
        CREATE TABLE execution_dispatch_outbox(server_id,executor_id,operation_id,dispatch_state,last_error);
        CREATE TABLE runtime_results(operation_id);
        CREATE TABLE runtime_work_outcomes(operation_id);
        CREATE TABLE agent_endpoints(agent_id,workspace_id,protocol,enabled,activation_state);
        CREATE TABLE handoff_runtime_no_effect_retries(handoff_id,agent_id,failure_count,
            retry_after,last_operation_id,updated_at,PRIMARY KEY(handoff_id,agent_id));
        CREATE TABLE handoff_runtime_schedule(handoff_id,claim_generation,workspace_id,state,due_at,
            wake_revision DEFAULT 0,PRIMARY KEY(handoff_id,claim_generation));
        CREATE TABLE handoff_runtime_schedule_scan(singleton,handoff_cursor,attempt_cursor);
        INSERT INTO handoff_runtime_schedule_scan VALUES(1,0,0);
    ''')
    migration = _default_migrations_dir() / '151_handoff_no_effect_recovery.sql'
    view = next(s for s in _split_statements(migration.read_text(encoding='utf-8'))
                if s.startswith('CREATE VIEW handoff_runtime_proved_no_effect'))
    conn.execute(view)
    conn.execute("INSERT INTO handoffs VALUES('handoff','workspace',1,'CLAIMED','pi',?)",
                 (json.dumps({'strategy':'broadcast'}),))
    conn.execute("INSERT INTO runtime_handoff_bindings VALUES('handoff',1,'call')")
    conn.execute("INSERT INTO delivery_outbox VALUES('call','FAILED_FINAL',NULL,NULL)")
    conn.execute("INSERT INTO handoff_runtime_attempts VALUES('attempt','workspace','handoff','pi',0,"
                 "'call','CLAIM_COMMITTED',1,'ACQUIRE',NULL,'now')")
    conn.execute("INSERT INTO one_shot_calls VALUES('call','FAILED',?)", (json.dumps({
        'error': {'execution_started': False, 'possible_effect': False, 'retry_safe': True}}),))
    conn.execute("INSERT INTO execution_capacity_admissions VALUES('call','server','host','session','CONSUMED')")
    conn.execute("INSERT INTO execution_sessions VALUES('server','host','session','CLOSED','CLOSED')")
    conn.execute("INSERT INTO execution_domain_deliveries VALUES('call','server','host','open')")
    conn.execute("INSERT INTO execution_domain_deliveries VALUES('call','server','host','turn')")
    conn.execute("INSERT INTO execution_operations VALUES('server','host','open','runtime.open')")
    conn.execute("INSERT INTO execution_operations VALUES('server','host','turn','turn.submit')")
    conn.execute("INSERT INTO execution_receipts VALUES('server','host','open',1,'FAILED',0,1,'PRE_EXECUTION_FENCED')")
    conn.execute("INSERT INTO execution_dispatch_outbox VALUES('server','host','turn','RESOLVED_TERMINAL',?)",
                 (json.dumps({'code':'INITIAL_OPEN_FAILED','possible_effect':False}),))
    for agent in ('pi','claude'):
        conn.execute("INSERT INTO agent_endpoints VALUES(?,'workspace','nxl-r4',1,'approved')", (agent,))
    return conn


def lease():
    return HandoffScheduleLease('handoff','workspace',1,'token',0,0,'')


def test_migration_preserves_schema_integrity_and_history_indexes(tmp_path):
    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path))
    assert MigrationRunner(factory).apply()[-1] == 151
    with factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        assert conn.execute('PRAGMA foreign_key_check').fetchone() is None
        indexes = {row['name'] for row in conn.execute("PRAGMA index_list('handoff_runtime_attempts')")}
        assert {'handoff_runtime_attempts_candidate','handoff_runtime_attempts_pending',
                'handoff_runtime_attempts_agent_history','handoff_runtime_attempts_recent'} <= indexes
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='view' "
            "AND name='handoff_runtime_proved_no_effect'").fetchone() is not None


def test_proved_failure_is_scheduled_once_and_cools_only_failed_agent():
    with evidence() as conn:
        uow = SimpleNamespace(connection=conn)
        schedule = SqliteHandoffScheduleRepository()
        assert schedule.sweep(uow, now=1000, limit=4) == (1, 0)
        assert conn.execute('SELECT state,claim_generation FROM handoff_runtime_schedule').fetchone()[:] == ('PENDING',1)
        repo = SqliteHandoffCandidateRepository(attempts=None, availability=None, pool_factory=None)
        proof = repo.proved_no_effect(uow, lease())
        assert (proof['operation_id'],proof['agent_id'],proof['error_code']) == (
            'call','pi','PRE_EXECUTION_FENCED')
        repo.retire_no_effect(uow, proof, now_iso='2026-10-18T00:00:00Z', now_epoch=1000)
        assert conn.execute('SELECT state,active,disposition FROM handoff_runtime_attempts').fetchone()[:] == (
            'FAILED_NO_EFFECT',0,'RELEASE')
        conn.execute("UPDATE handoffs SET status='OPEN',claimed_by=NULL")
        agents,_,_ = repo.agents_page(uow, lease(), allow_new=True, limit=4, now_epoch=1001)
        assert agents == ('claude',)
        agents,_,_ = repo.agents_page(uow, lease(), allow_new=True, limit=4, now_epoch=1015)
        assert set(agents) == {'pi','claude'}


def test_discovery_reopens_proved_claim_and_retires_original_attempt_atomically():
    with evidence() as conn:
        conn.commit()

        class Factory:
            @contextmanager
            def unit_of_work(self):
                conn.execute('BEGIN IMMEDIATE')
                try:
                    yield SimpleNamespace(connection=conn)
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise

        class Handoffs:
            _clock = SimpleNamespace(now_iso=lambda: '2026-10-18T00:00:00Z')

            def __init__(self):
                self._handoffs = self

            def get(self, uow, *, workspace_id, handoff_id):
                row = uow.connection.execute('SELECT * FROM handoffs WHERE workspace_id=? AND handoff_id=?',
                    (workspace_id,handoff_id)).fetchone()
                return SimpleNamespace(**dict(row)) if row else None

            def _reopen_runtime_claim(self, uow, *, operation, handoff_id, claim_epoch,
                                      reason, reconciliation_id, actor_agent_id):
                assert operation['operation_id'] == 'call' and claim_epoch == 1
                assert reason == 'PRE_EXECUTION_FENCED' and reconciliation_id is actor_agent_id is None
                assert uow.connection.execute("UPDATE handoffs SET status='OPEN',claimed_by=NULL "
                    "WHERE handoff_id=? AND claim_epoch=? AND status='CLAIMED'",
                    (handoff_id,claim_epoch)).rowcount == 1

        repo = SqliteHandoffCandidateRepository(attempts=None,availability=None,pool_factory=None)
        discovery = HandoffCandidateDiscovery(factory=Factory(),repository=repo,
            attempts=None,handoffs=Handoffs(),acquisition_enabled=False)
        assert discovery.prepare_page(lease(),limit=4).settled
        assert conn.execute('SELECT status,claimed_by FROM handoffs').fetchone()[:] == ('OPEN',None)
        assert conn.execute('SELECT state,active FROM handoff_runtime_attempts').fetchone()[:] == (
            'FAILED_NO_EFFECT',0)
        assert conn.execute('SELECT failure_count FROM handoff_runtime_no_effect_retries').fetchone()[0] == 1


@pytest.mark.parametrize('change', ['core_effect','lease_active','turn_started','call_effect','terminal'])
def test_missing_or_uncertain_proof_never_schedules_recovery(change):
    with evidence() as conn:
        if change == 'call_effect':
            conn.execute('UPDATE one_shot_calls SET outcome_json=?', (json.dumps({
                'error': {'execution_started': True, 'possible_effect': True, 'retry_safe': False}}),))
        else:
            conn.execute({
                'core_effect': 'UPDATE execution_receipts SET possible_effect=1',
                'lease_active': "UPDATE execution_sessions SET lease_state='ACTIVE'",
                'turn_started': "INSERT INTO execution_receipts VALUES('server','host','turn',1,'SUBMITTED',1,0,NULL)",
                'terminal': "UPDATE handoffs SET status='COMPLETED'",
            }[change])
        uow = SimpleNamespace(connection=conn)
        assert SqliteHandoffCandidateRepository(attempts=None,availability=None,
            pool_factory=None).proved_no_effect(uow,lease()) is None
        assert SqliteHandoffScheduleRepository().sweep(uow,now=1000,limit=4) == (0,0)
        assert conn.execute('SELECT count(*) FROM handoff_runtime_schedule').fetchone()[0] == 0
