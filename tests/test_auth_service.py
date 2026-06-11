"""AgentKeyAuthService: issue/rotate/revoke + cached resolution (spec S1, C2).

Unit tests over a fake ``AgentRepo`` (call-counting) plus an integration pass
over the real SQLite adapter. Cover: plaintext returned exactly once and only
the hash persisted; uniform ``None`` for missing/malformed/unknown/revoked;
the malformed pre-filter skipping storage entirely; positive-hit caching with
TTL expiry; SYNCHRONOUS invalidation on rotation/revocation; negative results
never cached; ``last_seen_at`` touch on the read path; NOT_FOUND when issuing
for an unregistered agent; AuthProvider protocol conformance.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.application.ports import AuthProvider
from okto_nexus.domain.base import iso_to_epoch
from okto_nexus.domain.keys import hash_api_key, is_well_formed_api_key
from okto_nexus.domain.models import Agent
from okto_nexus.errors import ErrorCode, OktoNexusError


class StubClock:
    def __init__(self, iso: str = "2026-06-10T00:00:00Z") -> None:
        self._iso = iso

    def now_iso(self) -> str:
        return self._iso

    def now_epoch(self) -> float:
        return iso_to_epoch(self._iso)

    def advance_seconds(self, seconds: float) -> None:
        dt = datetime.fromtimestamp(self.now_epoch() + seconds, tz=timezone.utc)
        self._iso = dt.isoformat().replace("+00:00", "Z")


class FakeAgentRepo:
    """In-memory AgentRepo recording lookup/touch traffic."""

    def __init__(self) -> None:
        self.rows: dict[str, Agent] = {}
        self.lookups = 0
        self.touches: list[str] = []

    def upsert(self, uow, *, agent_id, role=None, capabilities=None, metadata=None):
        agent = self.rows.get(agent_id) or Agent(
            agent_id=agent_id, created_at="2026-06-10T00:00:00Z"
        )
        if role is not None:
            agent.role = role
        self.rows[agent_id] = agent
        return agent

    def get(self, uow, agent_id):
        return self.rows.get(agent_id)

    def list(self, uow):
        return list(self.rows.values())

    def touch(self, uow, *, agent_id, at=None):
        if agent_id not in self.rows:
            return False
        self.rows[agent_id].last_seen_at = at or "touched"
        self.touches.append(agent_id)
        return True

    def get_active_by_key_hash(self, uow, *, api_key_hash):
        self.lookups += 1
        for agent in self.rows.values():
            if agent.api_key_hash == api_key_hash and agent.is_active:
                return agent
        return None

    def set_key_hash(self, uow, *, agent_id, api_key_hash):
        if agent_id not in self.rows:
            return False
        self.rows[agent_id].api_key_hash = api_key_hash
        return True

    def set_active(self, uow, *, agent_id, is_active):
        if agent_id not in self.rows:
            return False
        self.rows[agent_id].is_active = is_active
        return True

    def list_without_key(self, uow):
        return [a for a in self.rows.values() if a.api_key_hash is None]


@pytest.fixture
def fake_repo() -> FakeAgentRepo:
    repo = FakeAgentRepo()
    repo.upsert(None, agent_id="researcher", role="analyst")
    return repo


@pytest.fixture
def clock() -> StubClock:
    return StubClock()


@pytest.fixture
def service(fake_repo: FakeAgentRepo, clock: StubClock) -> AgentKeyAuthService:
    return AgentKeyAuthService(fake_repo, clock)


def test_service_satisfies_auth_provider_protocol(service):
    assert isinstance(service, AuthProvider)


def test_issue_key_returns_wellformed_plaintext_and_stores_only_hash(
    service, fake_repo
):
    key = service.issue_key(None, agent_id="researcher")
    assert is_well_formed_api_key(key)
    stored = fake_repo.rows["researcher"].api_key_hash
    assert stored == hash_api_key(key)
    assert key not in (stored or "")  # plaintext never equals what is stored


def test_issue_key_for_unknown_agent_raises_not_found(service):
    with pytest.raises(OktoNexusError) as excinfo:
        service.issue_key(None, agent_id="ghost")
    assert excinfo.value.code == ErrorCode.NOT_FOUND


@pytest.mark.parametrize("bad", [None, "", "garbage", "nxs_short", "dash_" + "a" * 48])
def test_resolve_malformed_returns_none_without_storage_lookup(service, fake_repo, bad):
    assert service.resolve(None, bad) is None
    assert fake_repo.lookups == 0  # pre-filter short-circuits storage


def test_resolve_unknown_and_revoked_are_uniform_none(service, fake_repo):
    key = service.issue_key(None, agent_id="researcher")
    unknown = "nxs_" + "0" * 48
    assert service.resolve(None, unknown) is None

    service.set_active(None, agent_id="researcher", is_active=False)
    assert service.resolve(None, key) is None  # revoked == unknown


def test_resolve_caches_positive_hits_within_ttl(service, fake_repo, clock):
    key = service.issue_key(None, agent_id="researcher")
    assert service.resolve(None, key) is not None
    assert service.resolve(None, key) is not None
    assert fake_repo.lookups == 1  # second hit served from cache

    clock.advance_seconds(61)  # past DEFAULT_CACHE_TTL_SECONDS
    assert service.resolve(None, key) is not None
    assert fake_repo.lookups == 2  # TTL expired -> storage consulted again


def test_resolve_touches_last_seen_on_every_success(service, fake_repo):
    key = service.issue_key(None, agent_id="researcher")
    service.resolve(None, key)
    service.resolve(None, key)  # cached, still touches
    assert fake_repo.touches == ["researcher", "researcher"]


def test_rotation_invalidates_previous_key_synchronously(service, fake_repo):
    first = service.issue_key(None, agent_id="researcher")
    assert service.resolve(None, first) is not None  # primes the cache

    second = service.issue_key(None, agent_id="researcher")
    assert service.resolve(None, first) is None  # old key dead immediately
    resolved = service.resolve(None, second)
    assert resolved is not None and resolved.agent_id == "researcher"


def test_revocation_invalidates_cache_synchronously(service, fake_repo, clock):
    key = service.issue_key(None, agent_id="researcher")
    assert service.resolve(None, key) is not None  # primes the cache

    # Within the TTL window the cache would still answer - revocation must
    # drop the entry in the same call, not wait for expiry.
    service.set_active(None, agent_id="researcher", is_active=True)  # no-op flip
    service.set_active(None, agent_id="researcher", is_active=False)
    assert service.resolve(None, key) is None


def test_negative_results_are_not_cached(service, fake_repo):
    key = "nxs_" + "f" * 48
    assert service.resolve(None, key) is None
    lookups_before = fake_repo.lookups

    # The key gets issued "concurrently" (simulated by wiring the hash in).
    fake_repo.set_key_hash(None, agent_id="researcher", api_key_hash=hash_api_key(key))
    resolved = service.resolve(None, key)
    assert resolved is not None and resolved.agent_id == "researcher"
    assert fake_repo.lookups == lookups_before + 1


# --------------------------------------------------------------------------- #
# Integration: service over the real SQLite adapter
# --------------------------------------------------------------------------- #
def test_end_to_end_over_sqlite(migrated_factory, clock):
    repo = SqliteAgentRepo()
    service = AgentKeyAuthService(repo, clock)
    with migrated_factory.unit_of_work() as uow:
        repo.upsert(uow, agent_id="sql-agent")
        key = service.issue_key(uow, agent_id="sql-agent")

        resolved = service.resolve(uow, key)
        assert resolved is not None and resolved.agent_id == "sql-agent"

        rotated = service.issue_key(uow, agent_id="sql-agent")
        assert service.resolve(uow, key) is None
        assert service.resolve(uow, rotated) is not None

        assert service.set_active(uow, agent_id="sql-agent", is_active=False)
        assert service.resolve(uow, rotated) is None
