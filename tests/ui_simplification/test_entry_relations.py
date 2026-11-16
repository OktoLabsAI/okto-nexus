"""UI-017/018 full SQLite inputs, no route/wiring or paging claims."""
from contextlib import contextmanager
import json
import sqlite3

import pytest

from okto_nexus.adapters.outbound.sqlite.home_entries import SqliteHomeEntryRelations
from okto_nexus.domain.attention import normalize_filters, occurrence
from okto_nexus.domain.home import filters as home_filters
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError
from .test_fixtures import fixtures


@pytest.fixture
def scenario(tmp_path):
    with fixtures.scenario(tmp_path / 'entries') as value:
        yield value


@contextmanager
def projected(s, filters=None, queries=None, context=None):
    service = s.app.state.home
    scope = home_filters(filters)
    with s.factory.unit_of_work(write=False) as uow:
        server, now, config = service._basis(uow, context or s.operator, scope)
        with service.attention.queries._relation(uow, filters=normalize_filters({'state': 'all'}),
                now=now, config=config, access=service.access, context=s.operator,
                source_scope={'workspace_id': scope.get('workspace_id')}) as relation:
            yield (queries or SqliteHomeEntryRelations()).read(uow, scope=scope,
                server_id=server, now=now, attention_relation=relation)


def copy_session(c, original, session_id):
    opening = c.execute('SELECT * FROM execution_operations WHERE operation_id=?',
                        (original['open_operation_id'],)).fetchone()
    operation_id = session_id + '-open'
    scope = dict(json.loads(opening['expected_revisions_json']), session_id=session_id)
    fixtures._copy(c, 'execution_operations', opening, operation_id=operation_id,
                   session_id=session_id, expected_revisions_json=json.dumps(scope))
    fixtures._copy(c, 'execution_sessions', original, session_id=session_id, open_operation_id=operation_id)


def link_handoff(c, now):
    c.execute("INSERT INTO delivery_outbox(operation_id,delivery_id,message_id,workspace_id,actor_agent_id,credential_binding,recipient_agent_id,endpoint_id,endpoint_revision,envelope,request_hash,authorization_revision,root_operation_id,created_at,updated_at) VALUES('entry-domain','ui-delivery-0','ui-message-0','ws','subject','fixture','B','ep',1,'{}','fixture','fixture','entry-domain',?,?)", (now, now))
    grant = c.execute('SELECT grant_id FROM runtime_execution_grants LIMIT 1').fetchone()[0]
    c.execute("UPDATE handoffs SET claim_epoch=1 WHERE handoff_id='ui-handoff-0'")
    c.execute("INSERT INTO runtime_handoff_bindings(handoff_id,claim_epoch,operation_id,grant_id,grant_revision,actor_agent_id,idempotency_key,request_hash,created_at) VALUES('ui-handoff-0',1,'entry-domain',?,1,'subject','entry-synthetic','fixture',?)", (grant, now))


def test_logical_work_identity_sessions_results_and_receiver_are_preserved(scenario):
    s = scenario
    expected = {i['id'] for i in s.read(section='work', filters={'state': 'all'}, limit=100)['items']}
    with projected(s) as value:
        assert value.total_is_exact
        assert {e.id for e in value.entries if e.kind == 'work'} == expected
        assert len(value.entries) == len(expected)  # no second results/technical list
        assert not [e for e in value.entries if e.kind in ('session', 'connection')]
        assert {ref.session_id for e in value.entries for ref in e.sessions} == set(s.sessions)
        success = next(e for e in value.entries if e.source_ref['id'] == 'ui-success')
        assert len(success.results) == 1 and success.results[0]['cleanup_state'] == 'pending'
        question = next(e for e in value.entries if e.display_state == 'awaiting_operator')
        assert question.attention
        assert question.sessions[0].session_id == s.sessions[0]
        assert question.connection.binding_id == 'binding'
        assert not next(e for e in value.entries if e.source_ref['id'] == 'ui-unassigned').sessions
        ids = {e.source_ref['id']: e.id for e in value.entries}
        assert ids['ui-handoff-0'] != ids['ui-handoff-1']


def test_uncovered_session_and_idle_connection_have_exact_context(scenario):
    s = scenario
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        session = c.execute("SELECT * FROM execution_sessions WHERE session_id=?", (s.sessions[1],)).fetchone()
        copy_session(c, session, 'entry-no-turn')
        endpoint = c.execute("SELECT * FROM agent_endpoints WHERE endpoint_id='ui-ep-2'").fetchone()
        fixtures._copy(c, 'agent_endpoints', endpoint, endpoint_id='entry-idle-endpoint')
        binding = c.execute("SELECT * FROM execution_bindings WHERE binding_id='ui-binding-2'").fetchone()
        fixtures._copy(c, 'execution_bindings', binding, binding_id='entry-idle-binding', endpoint_id='entry-idle-endpoint')
    with projected(s) as value:
        session = next(e for e in value.entries if e.kind == 'session')
        connection = next(e for e in value.entries if e.kind == 'connection')
        assert session.target['session_id'] == 'entry-no-turn'
        assert 'operation_id' not in session.target
        assert session.connection.binding_id == 'ui-binding-2'
        assert session.connection.workspace_binding_id == 'wxb'
        assert connection.connection.binding_id == 'entry-idle-binding'
        assert connection.display_state == 'configured'
        assert session.group_id != connection.group_id


def test_more_than_hundred_rows_and_twenty_runtime_refs_are_not_truncated(scenario):
    s = scenario
    with s.factory.unit_of_work() as uow:
        c, now = uow.connection, s.clock.now_iso()
        handoff = c.execute("SELECT * FROM handoffs WHERE handoff_id='ui-unassigned'").fetchone()
        for i in range(125):
            fixtures._copy(c, 'handoffs', handoff, handoff_id=f'entry-bulk-{i:03}')
        original = c.execute("SELECT * FROM execution_operations WHERE action='turn.submit' LIMIT 1").fetchone()
        original_session = c.execute("SELECT * FROM execution_sessions WHERE session_id=?", (s.sessions[0],)).fetchone()
        # Same logical handoff, >20 exact runtime sessions. These are read facts,
        # not grants or native executions. Link schema follows canonical columns.
        link_handoff(c, now)
        for i in range(25):
            sid, op = f'entry-many-session-{i}', f'entry-many-operation-{i}'
            copy_session(c, original_session, sid)
            fixtures._copy(c, 'execution_operations', original, operation_id=op, session_id=sid)
            c.execute("INSERT INTO execution_domain_deliveries(server_id,executor_id,operation_id,domain_operation_id) VALUES(?,?,?,'entry-domain')",
                      (s.connections[0].server_id, s.connections[0].executor_id, op))
    with projected(s) as value:
        assert value.total_is_exact
        assert len([e for e in value.entries if e.source_ref['id'].startswith('entry-bulk-')]) == 125
        parent = next(e for e in value.entries if e.source_ref['id'] == 'ui-handoff-0')
        assert len(parent.sessions) == 25
        assert len({r.session_id for r in parent.sessions}) == 25
        assert not [e for e in value.entries if e.kind == 'session']


def test_partial_source_remains_unknown_and_other_sources_survive(scenario, monkeypatch):
    queries = SqliteHomeEntryRelations()
    monkeypatch.setattr(queries, '_results', lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError('controlled source failure')))
    with projected(scenario, queries=queries) as value:
        assert value.source_status['results'] == 'unavailable'
        assert value.source_status['work'] == 'ready'
        assert value.total is None and not value.total_is_exact
        assert value.entries


def test_existing_operator_authorization_runs_before_relation(scenario, monkeypatch):
    queries = SqliteHomeEntryRelations()
    monkeypatch.setattr(queries, 'read', lambda *a, **k: pytest.fail('must authorize first'))
    with pytest.raises(OktoNexusError) as error:
        with projected(scenario, queries=queries, context=RuntimeRequestContext(None, 'http_agent')):
            pytest.fail('unauthorized')
    assert error.value.code == 'PERMISSION_DENIED'


def test_global_and_orphan_occurrences_keep_scope_and_recipient(scenario, monkeypatch):
    s = scenario
    queries = SqliteHomeEntryRelations()
    original = queries._attention
    server = occurrence(kind='runtime_recovery_attention', source_type='execution_operation',
        source_id='server-own-source', episode='server', source_revision=1,
        first_detected_at=s.clock.now_iso(), last_changed_at=s.clock.now_iso())
    # Canonical occurrence builder, injected at the query port: fixture fact,
    # not evidence that a real Server incident was produced by this execution.
    orphan = occurrence(kind='question_waiting_for_agent', source_type='execution_native_request',
        source_id='orphan-native-request', episode='own-orphan', source_revision=1,
        first_detected_at=s.clock.now_iso(), last_changed_at=s.clock.now_iso(),
        agent_id='B', workspace_id='ws')
    monkeypatch.setattr(queries, '_attention', lambda *a, **k: original(*a, **k) + [server, orphan])
    with projected(s, queries=queries) as value:
        assert value.server_attention == [server]
        item = next(e for e in value.entries if e.source_ref['id'] == orphan['source_id'])
        assert item.display_state == 'awaiting_agent' and item.attention[0]['allowed_actions'] == []
        assert not [e for e in value.entries if e.source_ref['id'] == server['source_id']]


def test_missing_attention_is_unknown_not_zero(scenario):
    s = scenario
    with s.factory.unit_of_work(write=False) as uow:
        server, now, _ = s.app.state.home._basis(uow, s.operator, home_filters(None))
        value = SqliteHomeEntryRelations().read(uow, scope={}, server_id=server, now=now, attention_relation=None)
    assert value.source_status['attention'] == 'unavailable'
    assert value.total is None and value.entries


def test_sender_filter_keeps_receiver_question_and_results(scenario):
    s = scenario
    with projected(s) as full:
        question = next(e for e in full.entries if e.display_state == 'awaiting_operator')
        receiver_facts = question.attention
        success = next(e for e in full.entries if e.source_ref['id'] == 'ui-success')
        assert success.results
    with projected(s, {'agent_id': 'operator'}) as selected:
        same = next(e for e in selected.entries if e.id == question.id)
        assert same.attention == receiver_facts
        result = next(e for e in selected.entries if e.id == success.id)
        assert result.results == success.results
        assert not [e for e in selected.entries if e.source_ref['id'].startswith('ui-handoff-')]


def test_resource_budget_never_returns_exact_prefix(scenario, monkeypatch):
    queries = SqliteHomeEntryRelations()
    monkeypatch.setattr(queries, 'MAX_RELATION_ROWS', 2)
    with projected(scenario, queries=queries) as value:
        assert value.source_status['work'] == 'unavailable'
        assert value.total is None and not value.total_is_exact
        assert not [e for e in value.entries if e.activity]


def test_projection_is_read_only_and_secret_free(scenario):
    s = scenario
    with s.factory.unit_of_work(write=False) as uow:
        before = uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0]
    with projected(s) as value:
        from dataclasses import asdict
        payload = json.dumps(asdict(value))
        assert 'private-marker' not in payload and 'cas_token' not in payload
    with s.factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == before


def test_historical_session_never_uses_new_binding_context(scenario):
    s = scenario
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        s.deps.repos.workspaces.upsert(uow, workspace_id='entry-other-workspace')
        original = c.execute("SELECT * FROM execution_workspace_bindings WHERE workspace_binding_id='wxb'").fetchone()
        fixtures._copy(c, 'execution_workspace_bindings', original,
            workspace_binding_id='entry-new-wxb', workspace_id='entry-other-workspace')
        c.execute("UPDATE execution_bindings SET workspace_binding_id='entry-new-wxb' WHERE binding_id='ui-binding-2'")
        c.execute("UPDATE agent_endpoints SET workspace_id='entry-other-workspace' WHERE endpoint_id='ui-ep-2'")
    with projected(s, {'workspace_id': 'ws'}) as value:
        historic = next(e for e in value.entries if e.source_ref['id'] == 'ui-success')
        assert historic.sessions[0].workspace_binding_id == 'wxb'
        assert historic.sessions[0].binding_id == 'ui-binding-2'
        assert historic.sessions[0].workspace_id == 'ws'
        assert historic.connection is None  # current context is a different tuple
        assert not [e for e in value.entries if e.workspace_id == 'entry-other-workspace']


def test_old_claim_result_stays_orphan_instead_of_enriching_new_claim(scenario):
    s = scenario
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        link_handoff(c, s.clock.now_iso())
        c.execute("INSERT INTO execution_domain_deliveries(server_id,executor_id,operation_id,domain_operation_id) VALUES(?,?,'ui-success','entry-domain')",
                  (s.connections[0].server_id, s.connections[0].executor_id))
        c.execute("UPDATE handoffs SET claim_epoch=2 WHERE handoff_id='ui-handoff-0'")
    with projected(s) as value:
        current = next(e for e in value.entries if e.source_ref['id'] == 'ui-handoff-0')
        assert not current.results
        orphan = next(e for e in value.entries if e.results)
        assert orphan.results[0]['verification_state'] == 'historical_claim'
        assert orphan.sessions[0].session_id == s.sessions[1]
        assert orphan.connection.binding_id == 'ui-binding-2'
        assert not [e for e in value.entries if e.kind == 'session']


def test_permission_error_is_never_downgraded_to_partial(scenario, monkeypatch):
    queries = SqliteHomeEntryRelations()
    def denied(*args, **kwargs):
        raise OktoNexusError('PERMISSION_DENIED', 'controlled authorization refusal', {})
    monkeypatch.setattr(queries, '_results', denied)
    with pytest.raises(OktoNexusError) as error:
        with projected(scenario, queries=queries):
            pytest.fail('must refuse')
    assert error.value.code == 'PERMISSION_DENIED'
