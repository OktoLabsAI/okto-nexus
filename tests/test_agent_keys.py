"""Agent API keys: domain primitives + migration 009 + repo surface (spec S1, C1).

Covers the key format/hash helpers (pure domain), the 009 schema (columns,
backfill defaults, partial UNIQUE index) and the new ``SqliteAgentRepo``
methods: resolve-by-hash with the uniform active filter, set/replace hash
(immediate invalidation), the revocation switch, and the `issue-keys` view.
"""

from __future__ import annotations

import hashlib

import pytest

from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.domain.keys import (
    API_KEY_PREFIX,
    generate_api_key,
    hash_api_key,
    is_well_formed_api_key,
)
from okto_nexus.errors import ErrorCode, OktoNexusError


# --------------------------------------------------------------------------- #
# Domain primitives (pure)
# --------------------------------------------------------------------------- #
def test_generate_api_key_format_and_uniqueness():
    keys = {generate_api_key() for _ in range(64)}
    assert len(keys) == 64  # secrets-backed: collisions would be a bug
    for key in keys:
        assert key.startswith(API_KEY_PREFIX)
        token = key[len(API_KEY_PREFIX) :]
        assert len(token) == 48
        assert set(token) <= set("0123456789abcdef")
        assert is_well_formed_api_key(key)


def test_hash_api_key_is_lowercase_hex_sha256():
    key = "nxs_" + "ab" * 24
    expected = hashlib.sha256(key.encode("utf-8")).hexdigest().lower()
    assert hash_api_key(key) == expected
    assert len(hash_api_key(key)) == 64


@pytest.mark.parametrize(
    "value",
    [
        "",
        "nxs_",
        "nxs_short",
        "dash_" + "a" * 48,  # Pulse prefix, not ours
        "nxs_" + "g" * 48,  # non-hex
        "nxs_" + "a" * 47,
        "nxs_" + "a" * 49,
        "NXS_" + "a" * 48,  # prefix is case-sensitive
    ],
)
def test_is_well_formed_api_key_rejects(value):
    assert not is_well_formed_api_key(value)


# --------------------------------------------------------------------------- #
# Migration 009 schema
# --------------------------------------------------------------------------- #
def test_migration_009_columns_and_backfill_defaults(migrated_factory):
    with migrated_factory.unit_of_work() as uow:
        cols = {
            row["name"]: row
            for row in uow.connection.execute("PRAGMA table_info(agents)")
        }
        assert "api_key_hash" in cols
        assert "is_active" in cols

        # A row inserted without the new columns gets the backfill defaults:
        # no key yet (NULL) and active (1).
        repo = SqliteAgentRepo()
        agent = repo.upsert(uow, agent_id="legacy-v1")
        assert agent.api_key_hash is None
        assert agent.is_active is True


def test_migration_009_unique_index_rejects_duplicate_hash(migrated_factory):
    repo = SqliteAgentRepo()
    duplicated = hash_api_key(generate_api_key())
    with migrated_factory.unit_of_work() as uow:
        repo.upsert(uow, agent_id="a1")
        repo.upsert(uow, agent_id="a2")
        assert repo.set_key_hash(uow, agent_id="a1", api_key_hash=duplicated)
        with pytest.raises(OktoNexusError) as excinfo:
            repo.set_key_hash(uow, agent_id="a2", api_key_hash=duplicated)
        assert excinfo.value.code == ErrorCode.DB_ERROR


# --------------------------------------------------------------------------- #
# Repo surface
# --------------------------------------------------------------------------- #
def test_resolve_by_hash_requires_active_and_is_uniform(migrated_factory):
    repo = SqliteAgentRepo()
    key = generate_api_key()
    key_hash = hash_api_key(key)
    with migrated_factory.unit_of_work() as uow:
        repo.upsert(uow, agent_id="researcher", role="analyst")
        assert repo.set_key_hash(uow, agent_id="researcher", api_key_hash=key_hash)

        found = repo.get_active_by_key_hash(uow, api_key_hash=key_hash)
        assert found is not None and found.agent_id == "researcher"
        assert found.api_key_hash == key_hash

        # Unknown hash and revoked agent are indistinguishable: both None.
        assert (
            repo.get_active_by_key_hash(
                uow, api_key_hash=hash_api_key(generate_api_key())
            )
            is None
        )
        assert repo.set_active(uow, agent_id="researcher", is_active=False)
        assert repo.get_active_by_key_hash(uow, api_key_hash=key_hash) is None

        # Re-activation restores resolution with the SAME hash.
        assert repo.set_active(uow, agent_id="researcher", is_active=True)
        assert repo.get_active_by_key_hash(uow, api_key_hash=key_hash) is not None


def test_set_key_hash_replacement_invalidates_previous(migrated_factory):
    repo = SqliteAgentRepo()
    first = hash_api_key(generate_api_key())
    second = hash_api_key(generate_api_key())
    with migrated_factory.unit_of_work() as uow:
        repo.upsert(uow, agent_id="rotator")
        repo.set_key_hash(uow, agent_id="rotator", api_key_hash=first)
        repo.set_key_hash(uow, agent_id="rotator", api_key_hash=second)

        assert repo.get_active_by_key_hash(uow, api_key_hash=first) is None
        resolved = repo.get_active_by_key_hash(uow, api_key_hash=second)
        assert resolved is not None and resolved.agent_id == "rotator"


def test_set_methods_return_false_for_unknown_agent(migrated_factory):
    repo = SqliteAgentRepo()
    with migrated_factory.unit_of_work() as uow:
        assert not repo.set_key_hash(
            uow, agent_id="ghost", api_key_hash=hash_api_key(generate_api_key())
        )
        assert not repo.set_active(uow, agent_id="ghost", is_active=False)


def test_list_without_key_is_additive_view(migrated_factory):
    repo = SqliteAgentRepo()
    with migrated_factory.unit_of_work() as uow:
        repo.upsert(uow, agent_id="keyless-1")
        repo.upsert(uow, agent_id="keyless-2")
        repo.upsert(uow, agent_id="keyed")
        repo.set_key_hash(
            uow, agent_id="keyed", api_key_hash=hash_api_key(generate_api_key())
        )

        pending = repo.list_without_key(uow)
        assert [a.agent_id for a in pending] == ["keyless-1", "keyless-2"]

        # Upsert (register/update) never clears an existing hash.
        repo.upsert(uow, agent_id="keyed", role="executor")
        refreshed = repo.get(uow, "keyed")
        assert refreshed is not None and refreshed.api_key_hash is not None
