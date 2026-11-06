"""Whole-engine batch reads across distinct actors and cooperative time limits."""
import json
from types import SimpleNamespace

import pytest

import test_attention_api as api
from okto_nexus.adapters.outbound.sqlite import attention as query_module
from okto_nexus.application import attention_authority
from okto_nexus.domain.attention import normalize_filters
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError


OPERATOR = RuntimeRequestContext('operator', 'http_loopback', trusted_local_operator=True)
attention_env = api.attention_env


def seed(env, start, end):
    """Schema-valid source metadata; this is a batch-read test, not admission proof."""
    deps, now = env.deps, env.clock.now_iso()
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        for index in range(start, end):
            actor = 'batch-actor-' + str(index)
            workspace = 'attention-one' if index % 2 == 0 else 'attention-two'
            deps.repos.agents.upsert(uow, agent_id=actor)
            conn.execute("INSERT INTO runtime_profiles(profile_id,adapter_id,config,created_at,updated_at) "
                "VALUES(?,'batch-fixture','{}',?,?)", (actor, now, now))
            conn.execute("INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,protocol,profile_id,created_at,updated_at) "
                "VALUES(?,?,?,'batch-fixture','nxl-r4',?,?,?)", (actor, actor, workspace, actor, now, now))
            deps.repos.messages.create(uow, message_id=actor, workspace_id=workspace, from_agent_id='operator',
                body='PRIVATE-BATCH-BODY', target=json.dumps(dict(strategy='direct', agent_id=actor)), created_at=now)
            deps.repos.deliveries.create(uow, delivery_id=actor, message_id=actor,
                recipient_agent_id=actor, status='parked', created_at=now)
            conn.execute("INSERT INTO handoffs(handoff_id,workspace_id,from_agent_id,target,status,claimed_by,claim_epoch,created_at,updated_at,result) "
                "VALUES(?,?,'operator',?,'COMPLETED',?,1,?,?,'PRIVATE-BATCH-RESULT')",
                (actor, workspace, json.dumps(dict(strategy='direct', agent_id=actor)), actor, now, now))
            deps.approvals.intercept(uow, workspace_id=workspace, agent_id=actor, action='message_create',
                policy_id='batch-fixture', kwargs=dict(body='PRIVATE-APPROVAL-BODY'))


def read(env, **filters):
    service = env.app.state.attention
    statements = []
    with service.factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        before = conn.total_changes
        conn.set_trace_callback(statements.append)
        try:
            result = service.queries.snapshot(uow, filters=normalize_filters(filters), now=env.clock.now_iso(),
                config=env.deps.config, access=service.access, context=OPERATOR, limit=200)
        finally:
            conn.set_trace_callback(None)
        assert conn.total_changes == before
    queries = [statement for statement in statements if statement.lstrip().upper().startswith(('SELECT', 'WITH'))]
    assert not any(statement.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE')) for statement in statements)
    return result, queries


def test_full_engine_query_count_is_constant_across_distinct_agents_and_source_families(attention_env):
    env = attention_env
    seed(env, 0, 1)
    single, single_queries = read(env)
    assert single['total'] == 3
    seed(env, 1, 40)
    many, many_queries = read(env)
    assert many['total'] == len(many['items']) == 120
    assert len(many_queries) == len(single_queries)
    assert len({item['attention_id'] for item in many['items']}) == 120
    assert {item['kind'] for item in many['items']} == {'delivery_parked', 'approval_pending', 'result_unseen'}
    assert 'PRIVATE-' not in json.dumps(many)
    scoped, scoped_queries = read(env, workspace_id='attention-one', agent_id='batch-actor-18')
    assert scoped['total'] == 3 and len(scoped_queries) == len(single_queries)
    assert all(item['workspace_id'] == 'attention-one' and item['agent_id'] == 'batch-actor-18' for item in scoped['items'])


def test_budget_expiring_in_python_graph_preparation_aborts_and_connection_recovers(attention_env, monkeypatch):
    env = attention_env
    seed(env, 0, 2)
    clock = [0.0]
    original = attention_authority.prepare_graph
    reached = []

    def expired_graph(rows, *, check_budget=None):
        reached.append(len(rows['agents']))
        clock[0] = 6.0
        return original(rows, check_budget=check_budget)

    # Advance only after the SQL facts have been loaded; no sleep or empty
    # repository fault stands in for interruption during Python processing.
    monkeypatch.setattr(query_module, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(attention_authority, 'prepare_graph', expired_graph)
    with pytest.raises(OktoNexusError) as error:
        read(env)
    assert reached and error.value.code == 'ATTENTION_QUERY_BUDGET'
    monkeypatch.setattr(attention_authority, 'prepare_graph', original)
    recovered, _ = read(env)
    assert recovered['total'] == 6


def test_kind_filter_avoids_unrelated_authority_graph_and_preserves_exact_counts(attention_env, monkeypatch):
    env = attention_env
    seed(env, 0, 4)

    def unrelated_graph(*args, **kwargs):
        raise AssertionError('A parked-delivery query must not prepare execution authority.')

    monkeypatch.setattr(attention_authority, 'prepare_graph', unrelated_graph)
    result, statements = read(env, kind='delivery_parked')
    assert result['total'] == len(result['items']) == 4
    assert all(item['kind'] == 'delivery_parked' for item in result['items'])
    assert not any('FROM execution_session_capabilities' in statement for statement in statements)
