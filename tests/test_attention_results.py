"""Canonical MCP outcomes and correlated SQLite result deduplication."""
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

import test_attention_operations as operations
import test_coordination_passive as passive

sys.path.insert(0, str(Path(__file__).parent / 'execution_r4'))
import test_handoff_business_outcomes as business  # noqa: E402

from okto_nexus.adapters.outbound.sqlite.attention import SqliteAttentionQueries
from okto_nexus.adapters.outbound.sqlite.attention_results import SOURCE_SQL, build_policy
from okto_nexus.application.attention import AttentionService
from okto_nexus.application.attention_results import project
from okto_nexus.bootstrap.execution_authority import build_execution_access
from okto_nexus.domain.attention import occurrence, stamp
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError

observation = passive.observation
qualified_bridge = business.qualified_bridge
qualified_contract = business.qualified_contract
local_setup = business.local_setup
connected_local = business.connected_local
runtime = business.runtime
NOW, LATER = operations.NOW, operations.LATER
OPERATOR = RuntimeRequestContext(None, 'http_loopback', trusted_local_operator=True)


def read(conn, *, workspace_id=None, agent_id=None, now=NOW):
    facts = [json.loads(row['facts']) for row in conn.execute(SOURCE_SQL,
        dict(now=now, workspace_id=workspace_id, agent_id=agent_id))]
    return [item for row in facts for item in project(row, now, {})], facts


def call(env, name, *, actor='reader', **arguments):
    response = passive.read(env, name, dict(workspace_id='workspace', **arguments), actor=actor)
    assert response['ok'], response
    return response['data']


def create(env, *, verifiable=False):
    env.deps.config.feature_verification = True
    result = call(env, 'handoff_create', from_agent_id='reader',
        target=dict(strategy='direct', agent_id='worker'), visibility='eligible', payload='PRIVATE WORK',
        **(dict(acceptance_criteria=['Review evidence'], verify_by={'kind': 'creator'}) if verifiable else {}))
    return result['handoff_id']


def service(env):
    env.deps.config.feature_attention = True
    return AttentionService(factory=env.deps.connection_factory, access=build_execution_access(env.deps),
        queries=SqliteAttentionQueries(), clock=env.deps.clock, config=env.deps.config)


@pytest.mark.parametrize('outcome', ['complete', 'reject', 'verify', 'reject_open'])
def test_real_mcp_terminal_handoff_is_passive_result_and_seen_is_independent(observation, outcome):
    env = observation
    hid = create(env, verifiable=outcome == 'verify')
    if outcome != 'reject_open':
        claim = call(env, 'handoff_claim', actor='worker', agent_id='worker', handoff_id=hid)
        epoch = claim['claim_epoch']
    else:
        epoch = 0
    env.deps.clock.set_iso(LATER)
    action = 'handoff_reject' if outcome.startswith('reject') else 'handoff_complete'
    done = call(env, action, actor='worker', agent_id='worker', handoff_id=hid,
        **(dict(reason='PRIVATE REJECTION') if outcome.startswith('reject') else dict(result='PRIVATE RESULT')),
        **({'claim_epoch': epoch} if epoch else {}))
    if outcome == 'verify':
        assert done['status'] == 'VERIFYING'
        with env.deps.connection_factory.unit_of_work(write=False) as uow:
            assert read(uow.connection)[0] == []
        call(env, 'handoff_verify', agent_id='reader', handoff_id=hid, claim_epoch=epoch, verdict='pass')
    before = passive.snapshot(env.deps)
    attention = service(env)
    view = attention.read(context=OPERATOR, filters={'kind': 'result_unseen'})
    item, = view['items']
    assert item['source_type'] == 'handoff_result' and item['source_id'] == hid
    assert item['resolution'] == 'resolved' and item['active'] is True
    assert item['allowed_actions'] == ['inspect_handoff'] and item['operation_id'] is None
    assert item['executor_id'] is None
    assert item['first_detected_at'] == item['last_changed_at'] == stamp(LATER)
    assert 'PRIVATE' not in json.dumps(view)
    assert passive.snapshot(env.deps) == before
    attention.mark_seen(context=OPERATOR, attention_id=item['attention_id'],
        source_revision=item['source_revision'], preference_revision=0)
    assert attention.read(context=OPERATOR, filters={'kind': 'result_unseen'})['total'] == 0
    history = attention.read(context=OPERATOR, filters={'kind': 'result_unseen', 'state': 'all'})['items'][0]
    assert history['resolution'] == 'resolved' and history['seen_state']['seen'] and not history['active']
    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[0] == (
            'REJECTED' if outcome.startswith('reject') else 'COMPLETED')


def test_open_claimed_verifying_and_cancelled_are_not_manual_terminal_results(observation):
    hid = create(observation)
    with observation.deps.connection_factory.unit_of_work(write=False) as uow:
        assert read(uow.connection)[0] == []
    call(observation, 'handoff_cancel', agent_id='reader', handoff_id=hid, reason='Do not execute')
    with observation.deps.connection_factory.unit_of_work(write=False) as uow:
        assert read(uow.connection)[0] == []
    hid = create(observation, verifiable=True)
    claim = call(observation, 'handoff_claim', actor='worker', agent_id='worker', handoff_id=hid)
    with observation.deps.connection_factory.unit_of_work(write=False) as uow:
        assert read(uow.connection)[0] == []
    call(observation, 'handoff_complete', actor='worker', agent_id='worker', handoff_id=hid,
        claim_epoch=claim['claim_epoch'], result='PRIVATE RESULT')
    with observation.deps.connection_factory.unit_of_work(write=False) as uow:
        assert read(uow.connection)[0] == []


@pytest.fixture
def managed(observation):
    with observation.deps.connection_factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("INSERT INTO workspaces(workspace_id,created_at) VALUES('ws',?)", (NOW,))
        c.execute("INSERT INTO agents(agent_id,created_at) VALUES('creator',?)", (NOW,))
        operations.managed_operation(c)
        c.execute("INSERT INTO execution_domain_deliveries VALUES('s','e','op','domain-op')")
        yield c, observation


def engine(conn, env, *, state='all'):
    return SqliteAttentionQueries().snapshot(SimpleNamespace(connection=conn),
        filters=dict(state=state, seen='all', kind='result_unseen'), now=LATER, config=env.deps.config,
        access=build_execution_access(env.deps), context=OPERATOR)


@pytest.mark.parametrize('first_source', ['handoff', 'execution'])
def test_native_and_handoff_result_share_seen_across_lag_and_partial_retention(managed, first_source):
    c, env = managed
    if first_source == 'execution':
        operations.canonical_result(c, terminal=1)
    else:
        c.execute("UPDATE handoffs SET status='COMPLETED',updated_at=? WHERE handoff_id='h'", (NOW,))
    first, = engine(c, env)['items']
    assert first['source_type'] == 'handoff_result' and first['source_id'] == 'h'
    SqliteAttentionQueries().save_preference(SimpleNamespace(connection=c), attention_id=first['attention_id'],
        seen_at=NOW, snoozed_until=None, expected_revision=0, now=NOW)
    if first_source == 'execution':
        c.execute("UPDATE handoffs SET status='COMPLETED',updated_at=? WHERE handoff_id='h'", (LATER,))
    else:
        operations.canonical_result(c, terminal=1)
    combined = engine(c, env)
    item, = combined['items']
    assert item['attention_id'] == first['attention_id'] and item['seen_state']['seen'] and not item['active']
    assert item['first_detected_at'] == first['first_detected_at']
    assert item['operation_id'] == 'op' and item['allowed_actions'] == ['inspect_handoff', 'inspect_result']
    assert item['executor_id'] == 'e'
    assert engine(c, env, state='active')['total'] == 0
    c.execute('DELETE FROM execution_results')
    retained, = engine(c, env)['items']
    assert retained['attention_id'] == first['attention_id'] and retained['seen_state']['seen']
    assert retained['first_detected_at'] == first['first_detected_at']
    assert retained['allowed_actions'] == ['inspect_handoff'] and retained['operation_id'] is None
    assert retained['executor_id'] is None
    assert engine(c, env, state='active')['total'] == 0


def test_standalone_execution_result_preserves_the_existing_identity_and_metadata(managed):
    c, _ = managed
    c.execute('DELETE FROM execution_domain_deliveries')
    operations.canonical_result(c, terminal=1)
    item, = read(c)[0]
    expected = occurrence(kind='result_unseen', source_type='execution_result', source_id='op',
        episode=['s', 'e', 'stream', 1], source_revision=['stream', 1, 'success'],
        first_detected_at=NOW, last_changed_at=NOW, agent_id='worker', workspace_id='ws',
        session_id='session-op', operation_id='op', executor_id='e', resolution='resolved', active=True, allowed_actions=['inspect_result'])
    assert item == expected


@pytest.mark.parametrize('outcome', ['success', 'failed', 'interrupted'])
def test_native_outcomes_require_terminal_proof_and_do_not_read_contents(managed, outcome):
    c, _ = managed
    operations.canonical_result(c)
    assert read(c)[0] == []
    c.execute('UPDATE execution_results SET terminal_sequence=1,delivery_outcome=?', (outcome,))
    before = list(c.iterdump())
    items, facts = read(c)
    assert len(items) == 1 and items[0]['resolution'] == 'resolved'
    assert facts[0]['native_results'][0]['delivery_outcome'] == outcome
    assert 'SECRET' not in json.dumps(items) + json.dumps(facts)
    assert read(c, now=LATER)[0] == items and list(c.iterdump()) == before
    assert read(c, workspace_id='foreign')[0] == read(c, agent_id='foreign')[0] == []


def test_rework_does_not_assign_an_older_native_result_to_a_new_claim_epoch(managed):
    c, env = managed
    operations.canonical_result(c, terminal=1)
    prior, = read(c)[0]
    SqliteAttentionQueries().save_preference(SimpleNamespace(connection=c), attention_id=prior['attention_id'],
        seen_at=NOW, snoozed_until=None, expected_revision=0, now=NOW)
    c.execute("UPDATE handoffs SET status='VERIFYING' WHERE handoff_id='h'")
    c.execute("UPDATE handoffs SET status='CLAIMED',claim_epoch=2,updated_at=? WHERE handoff_id='h'", (LATER,))
    assert read(c)[0] == [prior]
    c.execute("UPDATE handoffs SET status='COMPLETED',updated_at=? WHERE handoff_id='h'", (LATER,))
    items = engine(c, env)['items']
    assert len(items) == 2 and len({item['attention_id'] for item in items}) == 2
    old = next(item for item in items if item['attention_id'] == prior['attention_id'])
    new = next(item for item in items if item['attention_id'] != prior['attention_id'])
    assert old['operation_id'] == 'op' and old['seen_state']['seen']
    assert new['operation_id'] is None and not new['seen_state']['seen']


def test_handoff_terminal_anchor_rolls_back_and_deletion_cleans_only_its_metadata(observation):
    env = observation
    hid = create(env)
    claim = call(env, 'handoff_claim', actor='worker', agent_id='worker', handoff_id=hid)
    with env.deps.connection_factory.unit_of_work() as uow:
        c = uow.connection
        c.execute('SAVEPOINT terminal')
        c.execute("UPDATE handoffs SET status='COMPLETED',updated_at=? WHERE handoff_id=?", (LATER, hid))
        assert read(c)[0]
        c.execute('ROLLBACK TO terminal')
        c.execute('RELEASE terminal')
        assert read(c)[0] == []
        assert not c.execute("SELECT 1 FROM attention_operation_epochs WHERE source_type='handoff_result'").fetchone()
    call(env, 'handoff_complete', actor='worker', agent_id='worker', handoff_id=hid,
        claim_epoch=claim['claim_epoch'], result='PRIVATE RESULT')
    with env.deps.connection_factory.unit_of_work() as uow:
        c = uow.connection
        c.execute('DELETE FROM handoffs WHERE handoff_id=?', (hid,))
        assert not c.execute("SELECT 1 FROM attention_operation_epochs WHERE source_type='handoff_result'").fetchone()


def test_projection_is_pure_and_result_api_requires_operator(observation):
    env = observation
    hid = create(env)
    call(env, 'handoff_reject', actor='worker', agent_id='worker', handoff_id=hid, reason='PRIVATE REJECTION')
    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        items, facts = read(uow.connection)
    assert build_policy(None, config=None, access=None, context=None, now=NOW) == {}
    assert project(facts[0], LATER, {}) == items
    actor = passive.actor_row(env, 'worker')
    with pytest.raises(OktoNexusError) as error:
        service(env).read(context=RuntimeRequestContext('worker', 'agent_key', credential_binding=actor.api_key_hash))
    assert str(error.value.code) == 'PERMISSION_DENIED'


def test_automatic_handoff_real_canonical_execution_and_mcp_return_share_one_result(runtime):
    """Real automatic admission, receipt/event ingress and MCP; synthetic peer."""
    setup, binding, native = runtime
    deps, _, client, *_ = setup
    _, hid, _ = business.prepare(runtime)
    business.enable_capacity(runtime)
    discovery = business.build_handoff_runtime_candidates(deps)
    attempts = business.build_handoff_runtime_attempts(deps)
    page = discovery.prepare_page(business.lease(runtime, hid), limit=4)
    assert len(page.attempt_ids) == 1
    assert client.portal.call(attempts.reserve, page.attempt_ids[0]).state == 'RESERVED'
    winner = attempts.claim(page.attempt_ids[0])
    client.portal.call(business.build_capacity_admission(deps).consume, winner.operation_id)
    turn = business.current_turn(setup)
    business.wait_receipt(setup, turn)
    cap = business.capability(setup, binding, turn['session_id'], 'mcp')
    business.emit(setup, native, turn, 'PRIVATE AUTOMATIC RESULT')
    deadline = time.monotonic() + 10
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            terminal = uow.connection.execute(
                'SELECT terminal_sequence FROM execution_results WHERE operation_id=?',
                (turn['operation_id'],)).fetchone()
        if terminal and terminal[0] is not None:
            break
        assert time.monotonic() < deadline, 'Canonical terminal result was not projected.'
        time.sleep(.02)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before, = read(uow.connection)[0]
    assert before['source_type'] == 'handoff_result' and before['source_id'] == hid
    with deps.connection_factory.unit_of_work() as uow:
        SqliteAttentionQueries().save_preference(uow, attention_id=before['attention_id'],
            seen_at=deps.clock.now_iso(), snoozed_until=None, expected_revision=0, now=deps.clock.now_iso())
    done, status = business.invoke(setup, cap, 'complete', hid, claim_epoch=1, result='PRIVATE EXPLICIT RESULT')
    assert status == 200 and done['status'] == 'COMPLETED', done
    with deps.connection_factory.unit_of_work(write=False) as uow:
        items, facts = read(uow.connection)
        assert len(items) == 1 and items[0]['attention_id'] == before['attention_id']
        assert items[0]['first_detected_at'] == before['first_detected_at']
        assert len(facts[0]['native_results']) == 1
        assert uow.connection.execute('SELECT seen_at FROM attention_preferences WHERE attention_id=?',
            (before['attention_id'],)).fetchone()[0] is not None
        assert 'PRIVATE' not in json.dumps(items) + json.dumps(facts)
    assert native.opens == 1 and native.native.sent == [('send_turn', turn['operation_id'])]
