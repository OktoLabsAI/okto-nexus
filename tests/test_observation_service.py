"""Admission, isolation and transaction evidence against the real SQLite store."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
import json
from types import SimpleNamespace

import pytest

from okto_nexus.application.observations import ObservationService
from okto_nexus.application.runtime_access import RuntimeAccessService
from okto_nexus.bootstrap.dependencies import build_repos
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError


OPERATOR = RuntimeRequestContext(None, 'http_loopback', trusted_local_operator=True)
FLAGS = {'observations': {'manage_self': True, 'publish': True}}


@pytest.fixture
def obs(migrated_factory, tmp_config, fake_clock):
    tmp_config.feature_observations = True
    repos, emitter = build_repos(fake_clock, tmp_config)
    deps = SimpleNamespace(connection_factory=migrated_factory, config=tmp_config,
                           clock=fake_clock, repos=repos, event_emitter=emitter)
    access = RuntimeAccessService(connection_factory=migrated_factory, agents=repos.agents,
        endpoints=None, grants=None, config=tmp_config, clock=fake_clock)
    service = ObservationService(deps=deps, access=access)
    with migrated_factory.unit_of_work() as uow:
        for name in ('alice', 'bob'):
            repos.agents.upsert(uow, agent_id=name)
            uow.connection.execute('UPDATE agents SET api_key_hash=?,permissions=? WHERE agent_id=?',
                                   (name + '-key', json.dumps(FLAGS), name))
        for workspace in ('ws', 'other'):
            repos.workspaces.upsert(uow, workspace_id=workspace)
    source = service.create_source(context=OPERATOR, body=dict(agent_id='alice',
        source_kind='custom', workspace_ids=['ws'], registration_ref='registration-1'))['source']
    instance = service.create_instance(context=OPERATOR, source_id=source['source_id'], body=dict(
        expected_revision=source['revision'], workspace_id='ws', external_instance_ref='occupant-1'))['instance']
    token = service.issue_token(context=OPERATOR, source_id=source['source_id'], body=dict(
        expected_revision=source['revision'], instance_grants=[dict(
            observed_instance_id=instance['observed_instance_id'], generation=instance['generation'])]))
    return SimpleNamespace(service=service, factory=migrated_factory, config=tmp_config,
        clock=fake_clock, repos=repos, source=source, instance=instance, token=token['token'],
        credential=token['credential'])


def report(obs, **changes):
    return dict(dict(schema_version=1, source_id=obs.source['source_id'],
        observed_instance_id=obs.instance['observed_instance_id'], generation=obs.instance['generation'],
        sequence=1, state='working', evidence='reported', observed_at=obs.clock.now_iso()), **changes)


def publish(obs, **changes):
    return obs.service.publish(token=obs.token, payload=report(obs, **changes))['receipts'][0]


def advance(obs, seconds):
    now = datetime.fromisoformat(obs.clock.now_iso().replace('Z', '+00:00')) + timedelta(seconds=seconds)
    obs.clock.set_iso(now.isoformat(timespec='microseconds').replace('+00:00', 'Z'))


def snapshot(obs, *, auxiliary=False):
    with obs.factory.unit_of_work(write=False) as uow:
        names = [row[0] for row in uow.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {name: sorted((tuple(row) for row in uow.connection.execute('SELECT * FROM "' + name + '"')), key=repr)
                for name in names if auxiliary or not name.startswith('observation_') and name != 'events'}


def events(obs):
    with obs.factory.unit_of_work(write=False) as uow:
        return [dict(row) for row in uow.connection.execute("SELECT * FROM events WHERE type GLOB 'observation.*'")]


def test_publish_changes_no_coordination_presence_or_capacity(obs):
    before = snapshot(obs)
    publish(obs, state='blocked', reason_code='external_input_required')
    publish(obs, sequence=2, state='idle', current_completion_ref='completion-1')
    assert snapshot(obs) == before
    assert [row['type'] for row in events(obs)] == ['observation.activity', 'observation.completion']
    assert all(row['visibility'] == 'private' for row in events(obs))
    assert all(json.loads(row['target']) == {'strategy': 'direct', 'agent_id': 'alice'} for row in events(obs))


def test_replay_after_ttl_and_policy_change_returns_exact_receipt(obs):
    data = report(obs)
    first = obs.service.publish(token=obs.token, payload=data)['receipts'][0]
    advance(obs, 120)
    obs.config.observation_max_valid_for_seconds = 10
    replay = obs.service.publish(token=obs.token, payload=data)['receipts'][0]
    assert replay == dict(first, replayed=True)
    assert len(events(obs)) == 1
    projected = obs.service.read(context=OPERATOR)['items'][0]
    assert projected['freshness'] == 'stale' and projected['activity_state'] == 'unknown'
    assert projected['last_report']['valid_until'] == first['valid_until']


@pytest.mark.parametrize('changes', [{'state': 'idle'}, {'sequence': 1}])
def test_conflicting_or_old_sequence_cannot_overwrite(obs, changes):
    publish(obs, sequence=2)
    before = snapshot(obs, auxiliary=True)
    with pytest.raises(OktoNexusError, match='CONFLICT'):
        publish(obs, **changes)
    assert snapshot(obs, auxiliary=True) == before


def test_same_sequence_different_hash_conflicts(obs):
    publish(obs)
    with pytest.raises(OktoNexusError, match='CONFLICT'):
        publish(obs, state='blocked')


@pytest.mark.parametrize('change', [
    "UPDATE agents SET is_active=0 WHERE agent_id='alice'",
    "UPDATE agents SET api_key_hash='rotated' WHERE agent_id='alice'",
    "UPDATE agents SET permissions=NULL WHERE agent_id='alice'",
])
def test_revocation_precedes_exact_replay_and_historical_state_unavailable(obs, change):
    data = report(obs)
    obs.service.publish(token=obs.token, payload=data)
    with obs.factory.unit_of_work() as uow:
        uow.connection.execute(change)
    with pytest.raises(OktoNexusError, match='PERMISSION_DENIED'):
        obs.service.publish(token=obs.token, payload=data)
    assert obs.service.read(context=OPERATOR)['items'][0]['freshness'] == 'unavailable'


def test_revoke_token_hides_current_state_without_erasing_history(obs):
    publish(obs)
    obs.service.revoke_token(context=OPERATOR, source_id=obs.source['source_id'], token_id=obs.credential['token_id'])
    item = obs.service.read(context=OPERATOR)['items'][0]
    assert item['freshness'] == 'unavailable' and item['last_report']['state'] == 'working'
    with pytest.raises(OktoNexusError, match='PERMISSION_DENIED'):
        publish(obs)


def test_generation_rotation_requires_new_exact_grant(obs):
    publish(obs)
    rotated = obs.service.rotate_instance(context=OPERATOR, source_id=obs.source['source_id'],
        observed_instance_id=obs.instance['observed_instance_id'], body=dict(
            expected_revision=obs.source['revision'], expected_generation=obs.instance['generation']))['instance']
    assert rotated['generation'] > obs.instance['generation']
    for generation in (obs.instance['generation'], rotated['generation']):
        with pytest.raises(OktoNexusError, match='CONFLICT|PERMISSION_DENIED'):
            publish(obs, generation=generation, sequence=2)
    with pytest.raises(OktoNexusError, match='CONFLICT'):
        obs.service.issue_token(context=OPERATOR, source_id=obs.source['source_id'], body=dict(
            expected_revision=obs.source['revision'], instance_grants=[dict(
                observed_instance_id=obs.instance['observed_instance_id'], generation=obs.instance['generation'])]))


def test_source_registration_idempotency_does_not_grant_permission(obs):
    same = obs.service.create_source(context=OPERATOR, body=dict(agent_id='alice', source_kind='custom',
        workspace_ids=['ws'], registration_ref='registration-1'))['source']
    assert same == obs.source
    with pytest.raises(OktoNexusError, match='CONFLICT'):
        obs.service.create_source(context=OPERATOR, body=dict(agent_id='alice', source_kind='custom',
            workspace_ids=['other'], registration_ref='registration-1'))
    with obs.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET permissions=NULL WHERE agent_id='bob'")
    source = obs.service.create_source(context=OPERATOR, body=dict(agent_id='bob', source_kind='hook',
        workspace_ids=['ws'], registration_ref='bob-registration'))['source']
    instance = obs.service.create_instance(context=OPERATOR, source_id=source['source_id'], body=dict(
        expected_revision=1, workspace_id='ws', external_instance_ref='bob-occupant'))['instance']
    with pytest.raises(OktoNexusError, match='PERMISSION_DENIED'):
        obs.service.issue_token(context=OPERATOR, source_id=source['source_id'], body=dict(
            expected_revision=1, instance_grants=[dict(observed_instance_id=instance['observed_instance_id'],
                generation=instance['generation'])]))


def test_canonical_self_management_requires_current_key_and_explicit_approval(obs):
    alice = RuntimeRequestContext('alice', 'agent_key', credential_binding='alice-key')
    bob = RuntimeRequestContext('bob', 'agent_key', credential_binding='bob-key')
    assert obs.service.get_source(context=alice, source_id=obs.source['source_id'])['source'] == obs.source
    with pytest.raises(OktoNexusError, match='NOT_FOUND'):
        obs.service.get_source(context=bob, source_id=obs.source['source_id'])
    with pytest.raises(OktoNexusError, match='PERMISSION_DENIED'):
        obs.service.get_source(context=replace(alice, credential_binding='stale-key'), source_id=obs.source['source_id'])
    with pytest.raises(OktoNexusError, match='PERMISSION_DENIED'):
        obs.service.create_source(context=alice, body=dict(agent_id='alice', source_kind='custom',
            workspace_ids=['other'], registration_ref='self-expanded'))
    with pytest.raises(OktoNexusError, match='PERMISSION_DENIED|WORKSPACE|VALIDATION'):
        obs.service.create_instance(context=alice, source_id=obs.source['source_id'], body=dict(
            expected_revision=1, workspace_id='other', external_instance_ref='outside'))


def test_disabled_feature_keeps_historical_reads_passive(obs):
    publish(obs)
    obs.config.feature_observations = False
    before = snapshot(obs, auxiliary=True)
    for _ in range(3):
        assert obs.service.read(context=OPERATOR)['items'][0]['freshness'] == 'unavailable'
    with pytest.raises(OktoNexusError, match='FEATURE_DISABLED'):
        publish(obs, sequence=2)
    assert snapshot(obs, auxiliary=True) == before


def test_idle_without_reference_never_invents_completion(obs):
    publish(obs, state='idle')
    publish(obs, state='idle', sequence=2, reason_code='external_completion')
    assert all(row['type'] != 'observation.completion' for row in events(obs))


def test_continuity_coalesces_but_blocked_and_completion_survive(obs):
    publish(obs)
    for sequence in range(2, 5):
        publish(obs, sequence=sequence)
    publish(obs, sequence=5, state='blocked')
    publish(obs, sequence=6, state='idle', current_completion_ref='done1')
    publish(obs, sequence=7, state='idle')
    publish(obs, sequence=8, state='idle', current_completion_ref='done1')
    assert [item['type'] for item in events(obs)] == [
        'observation.activity', 'observation.activity', 'observation.completion']


def test_atomic_batch_failure_rolls_back_head_quota_and_event(obs):
    before = snapshot(obs, auxiliary=True)
    with pytest.raises(OktoNexusError):
        obs.service.publish(token=obs.token, payload={'reports': [report(obs),
            report(obs, observed_instance_id='unauthorized')]})
    assert snapshot(obs, auxiliary=True) == before


@pytest.mark.parametrize('offset', [-91, 31])
def test_backlog_and_future_reports_are_rejected_without_writes(obs, offset):
    observed = datetime.fromisoformat(obs.clock.now_iso().replace('Z', '+00:00')) + timedelta(seconds=offset)
    before = snapshot(obs, auxiliary=True)
    with pytest.raises(OktoNexusError, match='VALIDATION_ERROR'):
        publish(obs, observed_at=observed.isoformat())
    assert snapshot(obs, auxiliary=True) == before


def test_event_failure_rolls_back_head_and_quota(obs, monkeypatch):
    before = snapshot(obs, auxiliary=True)
    def fail(*args, **kwargs):
        raise OSError('simulated disk full')
    monkeypatch.setattr(obs.service.events, 'emit', fail)
    with pytest.raises(OSError, match='disk full'):
        publish(obs)
    assert snapshot(obs, auxiliary=True) == before


def test_commit_failure_returns_no_receipt_and_rolls_back(obs, monkeypatch):
    from okto_nexus.adapters.outbound.sqlite.connection import SqliteUnitOfWork
    before = snapshot(obs, auxiliary=True)
    original = SqliteUnitOfWork.commit
    def fail(self):
        if self._write:
            raise OSError('simulated commit failure')
        return original(self)
    with monkeypatch.context() as patch:
        patch.setattr(SqliteUnitOfWork, 'commit', fail)
        with pytest.raises(OSError, match='commit failure'):
            publish(obs)
    assert snapshot(obs, auxiliary=True) == before


def test_concurrent_identical_publish_has_one_event_and_original_receipt(obs):
    data = report(obs)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: obs.service.publish(token=obs.token, payload=data)['receipts'][0], range(8)))
    assert sum(not item['replayed'] for item in results) == 1
    assert len({(item['received_at'], item['valid_until'], item['report_hash']) for item in results}) == 1
    assert len(events(obs)) == 1


def test_ingress_is_bounded_before_writer_and_refills(obs):
    from contextlib import ExitStack
    from okto_nexus.application.observation_ingress import ObservationIngress
    elapsed = [0.0]
    guard = ObservationIngress(obs.config, capacity=2, timer=lambda: elapsed[0])
    with ExitStack() as stack:
        stack.enter_context(guard.enter())
        stack.enter_context(guard.enter())
        with pytest.raises(OktoNexusError, match='OBSERVATION_BUSY'):
            with guard.enter():
                pytest.fail('queue overflow admitted')
    guard.available = 0
    with pytest.raises(OktoNexusError, match='QUOTA_EXCEEDED'):
        with guard.enter():
            pytest.fail('ingress quota ignored')
    elapsed[0] = 60
    with guard.enter():
        pass


def test_independent_instances_and_source_continuity_remain_distinct(obs):
    publish(obs, state='blocked')
    advance(obs, 120)
    second = obs.service.create_instance(context=OPERATOR, source_id=obs.source['source_id'], body=dict(
        expected_revision=1, workspace_id='ws', external_instance_ref='occupant-2'))['instance']
    token = obs.service.issue_token(context=OPERATOR, source_id=obs.source['source_id'], body=dict(
        expected_revision=1, instance_grants=[dict(observed_instance_id=second['observed_instance_id'],
                                                  generation=second['generation'])]))['token']
    obs.service.publish(token=token, payload=report(obs, observed_instance_id=second['observed_instance_id'],
        generation=second['generation'], state='idle', current_completion_ref='second-done'))
    items = {item['observed_instance_id']: item for item in obs.service.read(context=OPERATOR)['items']}
    assert items[obs.instance['observed_instance_id']]['freshness'] == 'stale'
    assert items[second['observed_instance_id']]['activity_state'] == 'idle'
    assert all(item['source_continuity'] == 'recent' for item in items.values())
    assert all(item['canonical_session_ref'] is None for item in items.values())


def test_batch_100_and_late_validation_failure_are_atomic(obs):
    obs.config.observation_source_burst = 1024
    obs.config.observation_agent_burst = 512
    advance(obs, 300)
    instances = [obs.instance]
    for number in range(99):
        instances.append(obs.service.create_instance(context=OPERATOR, source_id=obs.source['source_id'],
            body=dict(expected_revision=1, workspace_id='ws', external_instance_ref=f'batch-{number}'))['instance'])
    token = obs.service.issue_token(context=OPERATOR, source_id=obs.source['source_id'], body=dict(
        expected_revision=1, instance_grants=[dict(observed_instance_id=item['observed_instance_id'],
            generation=item['generation']) for item in instances]))['token']
    values = [report(obs, observed_instance_id=item['observed_instance_id'], generation=item['generation'])
              for item in instances]
    before = snapshot(obs, auxiliary=True)
    future = datetime.fromisoformat(obs.clock.now_iso().replace('Z', '+00:00')) + timedelta(seconds=31)
    with pytest.raises(OktoNexusError, match='VALIDATION_ERROR'):
        obs.service.publish(token=token, payload={'reports': [values[0], dict(values[1], observed_at=future.isoformat())]})
    assert snapshot(obs, auxiliary=True) == before
    result = obs.service.publish(token=token, payload={'reports': values})
    assert len(result['receipts']) == len(events(obs)) == 100
    assert len(obs.service.read(context=OPERATOR, limit=200)['items']) == 100
