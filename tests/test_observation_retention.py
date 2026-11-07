"""OBS maintenance uses bounded existing pruning without erasing replay fences."""
from types import SimpleNamespace
import hashlib

import pytest

from okto_nexus.adapters.outbound.sqlite.events_repo import SqliteEventRepo
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo, SqliteSessionRepo, SqliteWorkspaceRepo,
)
from okto_nexus.adapters.outbound.sqlite.messages_repo import SqliteMessageDeliveryRepo, SqliteMessageRepo
from okto_nexus.adapters.outbound.sqlite.observations_repo import SqliteObservationRepo
from okto_nexus.application.retention import AUTO_PRUNE_MAX_BATCHES, RetentionService
from okto_nexus.bootstrap.dependencies import maybe_auto_prune
from okto_nexus.domain.base import iso_plus
from okto_nexus.domain.observations import parse_report, report_hash
from okto_nexus.errors import OktoNexusError


NOW = "2026-11-06T15:00:00.000000Z"
START = iso_plus(NOW, -600)
WORKSPACE = "w" * 64
AGENT = "external_observer"


def clock(at=NOW):
    return SimpleNamespace(now_iso=lambda: at)


def snapshot(factory):
    tables = ("events", "observation_sources", "observation_instances", "observation_heads",
              "observation_tokens", "observation_token_instances", "observation_rate_buckets",
              "observation_installation")
    with factory.unit_of_work(write=False) as uow:
        return {name: [tuple(row) for row in uow.connection.execute(f'SELECT * FROM "{name}" ORDER BY 1')]
                for name in tables}


class TrackingFactory:
    def __init__(self, factory):
        self.factory = factory
        self.writes = []

    def unit_of_work(self, write=True):
        self.writes.append(write)
        return self.factory.unit_of_work(write=write)


class TrackedObservations(SqliteObservationRepo):
    def __init__(self):
        self.cleanups = []
        self.event_batches = []

    def prune(self, uow, *, now, limit=500):
        counts = super().prune(uow, now=now, limit=limit)
        self.cleanups.append((limit, dict(counts)))
        return counts

    def prune_events(self, uow, *, cutoff, max_events=20000, limit=500):
        count = super().prune_events(uow, cutoff=cutoff, max_events=max_events, limit=limit)
        self.event_batches.append((limit, count))
        return count


@pytest.fixture
def store(migrated_factory, tmp_config):
    factory = migrated_factory
    repo = TrackedObservations()
    tmp_config.observation_max_events = 2
    with factory.unit_of_work() as uow:
        SqliteAgentRepo(clock()).upsert(uow, agent_id=AGENT)
        SqliteAgentRepo(clock()).upsert(uow, agent_id="another_observer")
        SqliteWorkspaceRepo(clock()).upsert(uow, workspace_id=WORKSPACE)
        source = repo.create_source(uow, agent_id=AGENT, source_kind="custom",
            workspace_ids=[WORKSPACE], registration_ref="retention_fixture", now=START)
        instance = repo.create_instance(uow, source_id=source["source_id"],
            expected_revision=source["revision"], workspace_id=WORKSPACE,
            external_instance_ref="opaque-instance", now=START)
        tokens = []
        for index in range(5):
            tokens.append(repo.issue_token(uow, source_id=source["source_id"],
                expected_revision=source["revision"],
                token_hash=hashlib.sha256(f"retention-token-{index}".encode()).hexdigest(),
                instance_grants=[dict(observed_instance_id=instance["observed_instance_id"],
                                      generation=instance["generation"])], issuer_agent_id=AGENT,
                now=START, expires_at=iso_plus(NOW, -1 if index < 3 else 300)))
        report = parse_report(dict(schema_version=1, source_id=source["source_id"],
            observed_instance_id=instance["observed_instance_id"], generation=instance["generation"],
            sequence=7, state="idle", evidence="reported", observed_at=START,
            current_completion_ref="opaque-completion"))
        receipt = repo.store_report(uow, report=report.to_dict(), report_hash=report_hash(report),
            source_revision=source["revision"], publisher_token_id=tokens[0]["token_id"],
            received_at=START, valid_until=iso_plus(START, 90))
        repo.revoke_token(uow, source_id=source["source_id"], token_id=tokens[3]["token_id"], now=START)
        # Configured source/actor/installation buckets survive even when full.
        # Separate retired registry entries leave two orphan buckets eligible
        # for maintenance, without altering the registered head's authority.
        assert repo.consume_budget(uow, source_id=source["source_id"], agent_id=AGENT,
                                   cost=1, now=START)["allowed"]
        retired = repo.create_source(uow, agent_id="another_observer", source_kind="custom",
            workspace_ids=[WORKSPACE], registration_ref="retired_fixture", now=START)
        assert repo.consume_budget(uow, source_id=retired["source_id"], agent_id="another_observer",
                                   cost=1, now=START)["allowed"]
        uow.connection.execute("DELETE FROM observation_sources WHERE source_id=?", (retired["source_id"],))
        uow.connection.execute("DELETE FROM agents WHERE agent_id='another_observer'")
    repos = SimpleNamespace(events=SqliteEventRepo(clock()), deliveries=SqliteMessageDeliveryRepo(clock()),
        sessions=SqliteSessionRepo(clock()), messages=SqliteMessageRepo(clock()),
        coordination_requests=None, observations=repo)
    deps = SimpleNamespace(connection_factory=factory, clock=clock(), config=tmp_config, repos=repos)
    return SimpleNamespace(factory=factory, config=tmp_config, repo=repo, deps=deps,
                           source=source, instance=instance, tokens=tokens, receipt=receipt)


def service(store, *, batch_size=500, factory=None, observations=True):
    repos = store.deps.repos
    return RetentionService(connection_factory=factory or store.factory, clock=clock(),
        config=store.config, events=repos.events, deliveries=repos.deliveries,
        sessions=repos.sessions, messages=repos.messages,
        observations=store.repo if observations else None, batch_size=batch_size)


def seed_events(store):
    refs = {}
    with store.factory.unit_of_work() as uow:
        for name, days, kind in (("canonical_old", 40, "message.created"),
                                ("canonical_fresh", 6, "message.created"),
                                ("observation_old", 40, "observation.activity"),
                                ("observation_aged", 8, "observation.activity"),
                                ("observation_cap", 6, "observation.activity"),
                                ("observation_fresh1", 5, "observation.activity"),
                                ("observation_fresh2", 4, "observation.activity")):
            refs[name] = SqliteEventRepo(clock(iso_plus(NOW, -days * 86400))).append(
                uow, workspace_id=WORKSPACE, stream="workspace", type=kind)
    return refs


def event_ids(store):
    with store.factory.unit_of_work(write=False) as uow:
        return {row[0] for row in uow.connection.execute("SELECT event_id FROM events")}


def test_dry_run_is_passive_and_totals_do_not_double_count_shared_event_rows(store):
    refs = seed_events(store)
    before = snapshot(store.factory)
    tracking = TrackingFactory(store.factory)
    dry = service(store, factory=tracking).prune(dry_run=True, vacuum=True)
    assert tracking.writes and not any(tracking.writes)
    assert snapshot(store.factory) == before
    assert dry["tables"]["events"] == {"deleted": 1, "complete": True}
    assert dry["tables"]["observation_events"] == {"deleted": 3, "complete": True}
    assert dry["tables"]["observation_tokens"] == {"deleted": 3, "complete": True}
    assert dry["tables"]["observation_rate_buckets"] == {"deleted": 2, "complete": True}
    assert dry["total_deleted"] == 9 == sum(item["deleted"] for item in dry["tables"].values())
    assert dry["windows_days"]["observation_events"] == 7
    assert dry["row_limits"] == {"observation_events": 2}
    assert dry["vacuum"]["ran"] is False
    actual = service(store).prune()
    assert actual["tables"] == dry["tables"]
    assert actual["total_deleted"] == dry["total_deleted"]
    assert event_ids(store) == {refs[key] for key in ("canonical_fresh", "observation_fresh1", "observation_fresh2")}


def test_disabled_feature_still_maintains_history_and_preserves_registered_head_and_tokens(store):
    assert store.config.feature_observations is False
    with store.factory.unit_of_work(write=False) as uow:
        head = store.repo.get_head(uow, observed_instance_id=store.instance["observed_instance_id"])
    before = snapshot(store.factory)
    report = RetentionService.from_deps(store.deps).prune()
    after = snapshot(store.factory)
    assert report["tables"]["observation_tokens"]["deleted"] == 3
    for name in ("observation_heads", "observation_instances", "observation_sources", "observation_installation"):
        assert after[name] == before[name]
    assert {row[0] for row in after["observation_tokens"]} == {store.tokens[index]["token_id"] for index in (0, 4)}
    with store.factory.unit_of_work(write=False) as uow:
        assert store.repo.get_head(uow, observed_instance_id=store.instance["observed_instance_id"]) == head
        assert store.repo.check_sequence(uow, observed_instance_id=store.instance["observed_instance_id"],
            generation=store.instance["generation"], sequence=7, report_hash=store.receipt["report_hash"]) == store.receipt
        with pytest.raises(OktoNexusError) as error:
            store.repo.check_sequence(uow, observed_instance_id=store.instance["observed_instance_id"],
                generation=store.instance["generation"], sequence=6, report_hash=store.receipt["report_hash"])
        assert error.value.code == "CONFLICT"
    retained_buckets = {row[:2] for row in after["observation_rate_buckets"]}
    assert retained_buckets == {("agent", AGENT), ("source", store.source["source_id"]),
                                ("installation", "singleton")}


def test_pruning_after_rate_reduction_never_refills_an_existing_source_budget(store):
    later = iso_plus(NOW, 20)
    with store.factory.unit_of_work() as uow:
        assert store.repo.consume_budget(uow, source_id=store.source["source_id"],
            agent_id=AGENT, cost=20, now=NOW)["allowed"]
    store.config.observation_source_rate_per_minute = 1
    store.deps.clock = clock(later)
    before = snapshot(store.factory)["observation_rate_buckets"]
    report = RetentionService.from_deps(store.deps).prune()
    assert report["tables"]["observation_rate_buckets"]["deleted"] == 2
    after = snapshot(store.factory)["observation_rate_buckets"]
    current = {("source", store.source["source_id"]), ("agent", AGENT), ("installation", "singleton")}
    assert [row for row in before if row[:2] in current] == after
    rates = {name: (getattr(store.config, f"observation_{name}_rate_per_minute"),
                    getattr(store.config, f"observation_{name}_burst"))
             for name in ("source", "agent", "installation")}
    with store.factory.unit_of_work() as uow:
        refused = store.repo.consume_budget(uow, source_id=store.source["source_id"],
            agent_id=AGENT, cost=1, now=later, rates=rates)
        assert refused["allowed"] is False
        assert refused["retry_after_seconds"] == 40


def test_generic_event_override_cannot_shorten_observation_window(store):
    refs = seed_events(store)
    store.config.observation_max_events = 100
    dry = service(store).prune(events_keep_days=0, dry_run=True)
    actual = service(store).prune(events_keep_days=0)
    assert actual["tables"] == dry["tables"]
    assert actual["tables"]["events"]["deleted"] == 2
    assert actual["tables"]["observation_events"]["deleted"] == 2
    assert event_ids(store) == {refs[key] for key in ("observation_cap", "observation_fresh1", "observation_fresh2")}


def test_per_pass_budget_is_shared_by_tokens_and_buckets_and_can_resume(store):
    seed_events(store)
    first = service(store, batch_size=2).prune(max_batches=1)
    assert first["tables"]["observation_events"] == {"deleted": 2, "complete": False}
    assert first["tables"]["observation_tokens"] == {"deleted": 2, "complete": False}
    assert first["tables"]["observation_rate_buckets"] == {"deleted": 0, "complete": False}
    assert len(store.repo.cleanups) == len(store.repo.event_batches) == 1
    second = service(store, batch_size=2).prune(max_batches=1)
    assert second["tables"]["observation_tokens"] == {"deleted": 1, "complete": True}
    assert second["tables"]["observation_rate_buckets"] == {"deleted": 1, "complete": False}
    final = service(store, batch_size=2).prune()
    assert final["tables"]["observation_rate_buckets"] == {"deleted": 1, "complete": True}
    assert all(sum(counts.values()) <= limit == 2 for limit, counts in store.repo.cleanups)
    assert all(count <= limit == 2 for limit, count in store.repo.event_batches)
    assert first["total_deleted"] + second["total_deleted"] + final["total_deleted"] == 9


@pytest.mark.parametrize("lane", ["cleanup", "events"])
def test_failing_batch_rolls_back_its_deletions_and_does_not_return_success(store, lane):
    seed_events(store)
    before = snapshot(store.factory)

    class FailAfterDeletion(TrackedObservations):
        def prune(self, uow, *, now, limit=500):
            counts = super().prune(uow, now=now, limit=limit)
            if lane == "cleanup":
                raise RuntimeError("injected cleanup persistence failure")
            return counts

        def prune_events(self, uow, *, cutoff, max_events=20000, limit=500):
            count = super().prune_events(uow, cutoff=cutoff, max_events=max_events, limit=limit)
            if lane == "events":
                raise RuntimeError("injected event persistence failure")
            return count

    store.repo = FailAfterDeletion()
    with pytest.raises(RuntimeError, match="injected"):
        service(store).prune()
    after = snapshot(store.factory)
    for name in ("observation_tokens", "observation_rate_buckets", "observation_heads"):
        assert after[name] == before[name]
    if lane == "events":
        assert {row[0] for row in after["events"] if row[3].startswith("observation.")} == {
            row[0] for row in before["events"] if row[3].startswith("observation.")}


def test_startup_uses_existing_batch_budget_for_observation_events(store, capsys):
    count = AUTO_PRUNE_MAX_BATCHES * 500 + 1
    with store.factory.unit_of_work() as uow:
        events = SqliteEventRepo(clock(iso_plus(NOW, -8 * 86400)))
        for _ in range(count):
            events.append(uow, workspace_id=WORKSPACE, stream="workspace", type="observation.activity")
    store.config.auto_prune_on_start = True
    report = maybe_auto_prune(store.deps)
    assert report is not None
    assert report["tables"]["observation_events"] == {"deleted": count - 1, "complete": False}
    assert len(event_ids(store)) == 1
    assert len(store.repo.event_batches) == AUTO_PRUNE_MAX_BATCHES
    assert "auto-prune deleted" in capsys.readouterr().err
    assert service(store).prune()["tables"]["observation_events"] == {"deleted": 1, "complete": True}


def test_custom_retention_batch_cannot_exceed_observation_store_bound(store):
    seed_events(store)
    service(store, batch_size=10000).prune(max_batches=1)
    assert store.repo.cleanups and store.repo.event_batches
    assert {limit for limit, _ in store.repo.cleanups + store.repo.event_batches} == {1000}


def test_existing_event_repo_default_keeps_legacy_semantics_without_obs_lane(store):
    refs = seed_events(store)
    dry = service(store, observations=False).prune(dry_run=True)
    assert dry["tables"]["events"]["deleted"] == 2
    assert "observation_events" not in dry["tables"]
    actual = service(store, observations=False).prune()
    assert actual["total_deleted"] == 2
    assert event_ids(store) == set(refs.values()) - {refs["canonical_old"], refs["observation_old"]}
