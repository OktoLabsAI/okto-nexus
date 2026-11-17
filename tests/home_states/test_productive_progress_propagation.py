"""Private current-progress transport over synthetic read facts, not native runs."""
import json
import sqlite3
from dataclasses import asdict

import pytest

from okto_nexus.adapters.outbound.sqlite.home import FACTS, FACTS_NATIVE_PROGRESS
from okto_nexus.adapters.outbound.sqlite.home_entries import SqliteHomeEntryRelations
from tests.home_states.test_progress_equivalence import CORRECTED_LEGACY
from tests.home_states.test_projection_batch import authorized, scenario
from tests.ui_simplification.test_entry_relations import link_handoff
from tests.ui_simplification.test_fixtures import fixtures

__all__ = ['scenario']


def seed_progress(s, count=1):
    """Reuse existing admitted scope; extra operations/events are SQL read facts."""
    with s.factory.unit_of_work() as uow:
        c, now = uow.connection, s.clock.now_iso()
        link_handoff(c, now)
        original = c.execute("SELECT * FROM execution_operations WHERE action='turn.submit'").fetchone()
        session = c.execute('SELECT * FROM execution_sessions WHERE server_id=? AND executor_id=? AND session_id=?',
            (original['server_id'], original['executor_id'], original['session_id'])).fetchone()
        epoch = session['stream_epoch']
        sequence = c.execute('SELECT COALESCE(MAX(sequence),0) FROM execution_event_ingress WHERE server_id=? '
            'AND executor_id=? AND session_id=? AND stream_epoch=?',
            (original['server_id'], original['executor_id'], original['session_id'], epoch)).fetchone()[0]
        expected = dict(json.loads(original['expected_revisions_json']), session_owner_generation=session['owner_generation'])
        ids = {f'private-progress-{i:03}' for i in range(count)}
        for i, operation_id in enumerate(sorted(ids), 1):
            fixtures._copy(c, 'execution_operations', original, operation_id=operation_id,
                expected_revisions_json=json.dumps(expected))
            c.execute('INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,stage,possible_effect,retry_safe,received_at) '
                "VALUES(?,?,?,1,?,'SUBMITTED',1,0,?)",
                (original['server_id'], original['executor_id'], operation_id, original['intent_hash'], now))
            c.execute('INSERT INTO execution_domain_deliveries(server_id,executor_id,operation_id,domain_operation_id) '
                "VALUES(?,?,?,'entry-domain')", (original['server_id'], original['executor_id'], operation_id))
            # Deliberately synthetic migrated ingress facts. No provider, grant,
            # canonical frame or execution qualification is manufactured here.
            payload = json.dumps({'operation_id': operation_id, 'payload': {'delivery_phase': 'progress'}})
            c.execute('INSERT INTO execution_event_ingress(server_id,executor_id,session_id,stream_epoch,sequence,event_hash,event_type,payload_json,received_at) '
                "VALUES(?,?,?,?,?,'private-read-fixture','native.event',?,?)",
                (original['server_id'], original['executor_id'], original['session_id'], epoch, sequence+i, payload, now))
        c.execute('UPDATE execution_event_watermarks SET committed_contiguous=?,gap_state=\'none\' WHERE '
            'server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?',
            (sequence+count, original['server_id'], original['executor_id'], original['session_id'], epoch))
        assert c.execute('SELECT changes()').fetchone()[0] == 1
    return ids


def read_relations(s, version=2, queries=None):
    statements = []
    with authorized(s, {'workspace_id': 'ws'}, version) as (uow, scope, server, now, relation, _):
        before = uow.connection.total_changes
        uow.connection.set_trace_callback(statements.append)
        try:
            value = (queries or SqliteHomeEntryRelations()).read(uow, scope=scope, server_id=server,
                now=now, attention_relation=relation, presentation_version=version)
            assert uow.connection.total_changes == before
        finally:
            uow.connection.set_trace_callback(None)
    return value, statements


def test_complete_positive_collection_exceeds_preview_without_new_queries(scenario):
    _, before_sql = read_relations(scenario)
    ids = seed_progress(scenario, 25)
    with authorized(scenario, {'workspace_id': 'ws'}, 2) as (uow, _, _, _, relation, params):
        work = SqliteHomeEntryRelations()._work(uow, params=params, attention_relation=relation)
        parent = next(item for item in work if item['source_ref']['id'] == 'ui-handoff-0')
        assert len(parent['runtime_refs']) == 20
        proofs = [proof for proof in work.native_progress_current if proof['operation_id'] in ids]
        assert {proof['operation_id'] for proof in proofs} == ids
        assert len(proofs) == 25
        assert all('native_progress_current' not in item for item in work)
    current, after_sql = read_relations(scenario)
    own = [row for row in current.harness_blocking if row['family']=='operation' and row['operation_id'] in ids]
    assert len(own) == 25
    assert all(row['productive_progress_current'] is True and row['stage']=='SUBMITTED' for row in own)
    assert len(before_sql) == len(after_sql)
    assert all('native_progress_current' not in json.dumps(asdict(entry)) for entry in current.entries)


def test_legacy_rows_digests_and_public_items_do_not_transport_private_proof(scenario):
    seed_progress(scenario, 25)
    with authorized(scenario, {'workspace_id': 'ws'}, 1) as (uow, _, _, _, relation, params):
        queries = SqliteHomeEntryRelations()
        current = queries._work(uow, params=params, attention_relation=relation)
        # Frozen pre-private-transport query, with the already-qualified R3
        # committed watermark correction; complete JSON includes source revision.
        old = queries._project(uow, relation=CORRECTED_LEGACY, params=params, attention_relation=relation)
        assert current == old
        assert not hasattr(current, 'native_progress_current')
        assert 'FILTER(WHERE observed_running=1)' not in FACTS
        assert 'FILTER(WHERE observed_running=1)' in FACTS_NATIVE_PROGRESS
    legacy, _ = read_relations(scenario, 1)
    assert legacy.harness_blocking is None
    public = scenario.read(section='work', filters={'workspace_id':'ws','state':'all'})
    assert 'native_progress_current' not in json.dumps(public)
    assert 'productive_progress_current' not in json.dumps(public)


@pytest.mark.parametrize('field,value', [('server_id','another-server'),('executor_id','another-executor'),
    ('operation_id','another-operation'),('session_id','another-session'),('workspace_id','another-workspace'),
    ('agent_id','another-agent'),('binding_id','another-binding'),('workspace_binding_id','another-wxb'),
    ('stream_epoch','another-epoch'),('owner_generation',2),('owner_generation',True),('operation_id',None)])
def test_positive_proof_never_crosses_any_exact_scope_member(scenario, monkeypatch, field, value):
    ids = seed_progress(scenario)
    queries = SqliteHomeEntryRelations()
    original = queries._work_results
    def different_scope(*args, **kwargs):
        work, results = original(*args, **kwargs)
        work.native_progress_current = [dict(proof, **{field:value}) for proof in work.native_progress_current]
        return work, results
    monkeypatch.setattr(queries, '_work_results', different_scope)
    current, _ = read_relations(scenario, queries=queries)
    operation = next(row for row in current.harness_blocking if row['family']=='operation' and row['operation_id'] in ids)
    assert operation['stage'] == 'SUBMITTED'
    assert 'productive_progress_current' not in operation


def test_missing_or_unavailable_work_proof_is_unknown_not_negative(scenario, monkeypatch):
    ids = seed_progress(scenario)
    queries = SqliteHomeEntryRelations()
    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError('controlled unavailable Work source')
    monkeypatch.setattr(queries, '_work', unavailable)
    value, _ = read_relations(scenario, queries=queries)
    assert value.source_status['work'] == 'unavailable'
    operation = next(row for row in value.harness_blocking if row['family']=='operation' and row['operation_id'] in ids)
    assert 'productive_progress_current' not in operation
    assert not value.total_is_exact


def test_older_plain_list_query_port_does_not_infer_proof_from_running(scenario, monkeypatch):
    ids = seed_progress(scenario)
    queries = SqliteHomeEntryRelations()
    original = queries._work
    monkeypatch.setattr(queries, '_work', lambda *args, **kwargs: list(original(*args, **kwargs)))
    value, _ = read_relations(scenario, queries=queries)
    assert value.source_status['work'] == 'ready'
    operation = next(row for row in value.harness_blocking if row['family']=='operation' and row['operation_id'] in ids)
    assert 'productive_progress_current' not in operation
