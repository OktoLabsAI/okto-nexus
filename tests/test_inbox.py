"""Phase 1 (schema + domain) tests for the message inbox model (ADR 0001).

Covers the pure recipient-resolution and status vocabulary in
``okto_nexus.domain.inbox`` (reusing the routing eligibility predicate), the new
``target_strategy`` helper, the ``MessageDelivery`` model, and that migration
``005`` materialises the ``message_deliveries`` table. No application/adapter
behaviour yet (that is Phase 2+).
"""

from __future__ import annotations

import sqlite3

import pytest

from okto_nexus.domain.inbox import (
    DELIVERY_DELIVERED,
    DELIVERY_PARKED,
    DELIVERY_READ,
    DELIVERY_STATUSES,
    DELIVERY_UNREAD,
    assert_deliverable_message_target,
    new_delivery_id,
    requires_known_recipient,
    requires_workspace_audience,
    resolve_recipients,
)
from okto_nexus.domain.models import MessageDelivery
from okto_nexus.domain.routing import RoutingAgent, target_strategy
from okto_nexus.errors import ErrorCode, OktoNexusError

NOW = "2026-06-07T00:00:00Z"


def _agent(agent_id, role=None, capabilities=None):
    return RoutingAgent(
        agent_id=agent_id,
        workspace_id="ws-irrelevant",  # resolution is workspace-agnostic
        role=role,
        capabilities=capabilities,
    )


# --------------------------------------------------------------------------- #
# Status vocabulary + ids + model
# --------------------------------------------------------------------------- #
def test_delivery_status_vocabulary():
    assert DELIVERY_STATUSES == {
        DELIVERY_UNREAD,
        DELIVERY_DELIVERED,
        DELIVERY_READ,
        DELIVERY_PARKED,
    }
    assert (DELIVERY_UNREAD, DELIVERY_DELIVERED, DELIVERY_READ, DELIVERY_PARKED) == (
        "unread",
        "delivered",
        "read",
        "parked",
    )


def test_new_delivery_id_prefixed_and_unique():
    a, b = new_delivery_id(), new_delivery_id()
    assert a.startswith("del_") and b.startswith("del_")
    assert a != b


def test_message_delivery_model_defaults():
    d = MessageDelivery(
        delivery_id="del_1",
        message_id="msg_1",
        recipient_agent_id="a",
        status=DELIVERY_UNREAD,
        created_at=NOW,
    )
    assert d.delivered_at is None and d.lease_expires_at is None and d.read_at is None


# --------------------------------------------------------------------------- #
# target_strategy
# --------------------------------------------------------------------------- #
def test_target_strategy_none_for_absent_target():
    assert target_strategy(None) is None
    assert target_strategy("") is None
    assert target_strategy("   ") is None


def test_target_strategy_normalizes():
    assert target_strategy({"strategy": "Direct"}) == "direct"
    assert target_strategy({"strategy": "direct-with-fallback"}) == "direct_with_fallback"
    assert target_strategy({"kind": "broadcast"}) == "broadcast"


def test_target_strategy_rejects_missing_and_unknown():
    with pytest.raises(OktoNexusError) as missing:
        target_strategy({"agent_id": "a"})  # no strategy/kind discriminator
    assert missing.value.code == ErrorCode.VALIDATION_ERROR.value
    with pytest.raises(OktoNexusError) as unknown:
        target_strategy({"strategy": "telepathy"})
    assert unknown.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# resolve_recipients — per strategy
# --------------------------------------------------------------------------- #
def test_resolve_direct_hits_named_agent_only():
    candidates = [_agent("a"), _agent("b"), _agent("c")]
    target = {"strategy": "direct", "agent_id": "b"}
    assert resolve_recipients(target, candidates, now=NOW) == frozenset({"b"})


def test_resolve_direct_unknown_agent_is_empty():
    candidates = [_agent("a"), _agent("b")]
    target = {"strategy": "direct", "agent_id": "ghost"}
    assert resolve_recipients(target, candidates, now=NOW) == frozenset()


def test_resolve_capability_string_and_list_any_of():
    candidates = [
        _agent("a", capabilities=["ocr", "pdf"]),
        _agent("b", capabilities={"pdf": True}),
        _agent("c", capabilities=["ocr"]),
        _agent("d", capabilities=["xml"]),  # holds neither ocr nor pdf
    ]
    # string membership
    assert resolve_recipients(
        {"strategy": "capability", "capability": "ocr"}, candidates, now=NOW
    ) == frozenset({"a", "c"})
    # list = any-of (genuine union): c matches via ocr, b via pdf; d (xml-only)
    # is excluded — a single-element list could not demonstrate the OR.
    assert resolve_recipients(
        {"strategy": "capability", "capability": ["ocr", "pdf"]}, candidates, now=NOW
    ) == frozenset({"a", "b", "c"})


def test_resolve_accepts_plain_dict_candidate():
    candidates = [{"agent_id": "x", "role": "worker"}, {"agent_id": "y", "role": "validator"}]
    assert resolve_recipients(
        {"strategy": "role", "role": "worker"}, candidates, now=NOW
    ) == frozenset({"x"})


def test_resolve_role_exact_case_sensitive():
    candidates = [_agent("a", role="validator"), _agent("b", role="Validator"), _agent("c", role="worker")]
    assert resolve_recipients(
        {"strategy": "role", "role": "validator"}, candidates, now=NOW
    ) == frozenset({"a"})  # case-sensitive: 'Validator' excluded


def test_resolve_broadcast_hits_all_candidates():
    candidates = [_agent("a"), _agent("b"), _agent("c")]
    assert resolve_recipients(
        {"strategy": "broadcast"}, candidates, now=NOW
    ) == frozenset({"a", "b", "c"})
    # absent target == broadcast semantics
    assert resolve_recipients(None, candidates, now=NOW) == frozenset({"a", "b", "c"})


def test_resolve_mixed_is_union():
    candidates = [_agent("a", role="worker"), _agent("b", capabilities=["ocr"]), _agent("c")]
    target = {
        "strategy": "mixed",
        "rules": [
            {"strategy": "role", "role": "worker"},
            {"strategy": "capability", "capability": "ocr"},
        ],
    }
    assert resolve_recipients(target, candidates, now=NOW) == frozenset({"a", "b"})


def test_resolve_direct_with_fallback_at_send_is_direct_only_when_delayed():
    candidates = [_agent("a"), _agent("b"), _agent("c")]
    # positive delay: at send (created_at == now) the fallback has NOT elapsed.
    delayed = {
        "strategy": "direct_with_fallback",
        "agent_id": "a",
        "fallback_after_seconds": 60,
    }
    assert resolve_recipients(delayed, candidates, now=NOW) == frozenset({"a"})
    # zero delay: fallback (default broadcast) fires immediately -> everyone.
    immediate = {
        "strategy": "direct_with_fallback",
        "agent_id": "a",
        "fallback_after_seconds": 0,
    }
    assert resolve_recipients(immediate, candidates, now=NOW) == frozenset({"a", "b", "c"})


def test_resolve_malformed_target_raises():
    with pytest.raises(OktoNexusError) as ei:
        resolve_recipients({"strategy": "telepathy"}, [_agent("a")], now=NOW)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


def test_resolve_validates_target_even_with_empty_candidates():
    # A malformed target must raise regardless of candidate count (the schema is
    # validated up front, not as a side effect of iterating candidates).
    with pytest.raises(OktoNexusError) as unknown:
        resolve_recipients({"strategy": "telepathy"}, [], now=NOW)
    assert unknown.value.code == ErrorCode.VALIDATION_ERROR.value
    with pytest.raises(OktoNexusError) as missing_field:
        resolve_recipients({"strategy": "direct"}, [], now=NOW)  # missing agent_id
    assert missing_field.value.code == ErrorCode.VALIDATION_ERROR.value
    # A well-formed group target with no candidates is simply empty (not an error).
    assert resolve_recipients({"strategy": "broadcast"}, [], now=NOW) == frozenset()


# --------------------------------------------------------------------------- #
# requires_known_recipient
# --------------------------------------------------------------------------- #
def test_requires_workspace_audience():
    # broadcast / no-target -> bounded to the workspace's participants.
    assert requires_workspace_audience(None) is True
    assert requires_workspace_audience({"strategy": "broadcast"}) is True
    # everything else resolves against the global registry.
    for glob in (
        {"strategy": "direct", "agent_id": "a"},
        {"strategy": "capability", "capability": "ocr"},
        {"strategy": "role", "role": "x"},
        {"strategy": "mixed", "rules": [{"strategy": "role", "role": "x"}]},
    ):
        assert requires_workspace_audience(glob) is False


# --------------------------------------------------------------------------- #
# assert_deliverable_message_target
# --------------------------------------------------------------------------- #
def test_assert_rejects_direct_with_fallback():
    with pytest.raises(OktoNexusError) as ei:
        assert_deliverable_message_target(
            {"strategy": "direct_with_fallback", "agent_id": "a", "fallback_after_seconds": 0}
        )
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


def test_assert_rejects_broadcast_nested_in_mixed():
    target = {
        "strategy": "mixed",
        "rules": [{"strategy": "role", "role": "x"}, {"strategy": "broadcast"}],
    }
    with pytest.raises(OktoNexusError) as ei:
        assert_deliverable_message_target(target)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    # also via a JSON-string target (the _mixed_rules coercion path)
    import json as _json

    with pytest.raises(OktoNexusError):
        assert_deliverable_message_target(_json.dumps(target))


def test_assert_allows_safe_targets():
    for safe in (
        None,
        {"strategy": "broadcast"},
        {"strategy": "direct", "agent_id": "a"},
        {"strategy": "capability", "capability": "ocr"},
        {"strategy": "role", "role": "x"},
        {"strategy": "mixed", "rules": [
            {"strategy": "role", "role": "x"},
            {"strategy": "capability", "capability": "ocr"},
        ]},
    ):
        assert_deliverable_message_target(safe)  # no raise


def test_requires_known_recipient_only_for_directed():
    assert requires_known_recipient({"strategy": "direct", "agent_id": "a"}) is True
    assert requires_known_recipient(
        {"strategy": "direct_with_fallback", "agent_id": "a", "fallback_after_seconds": 5}
    ) is True
    for group in (
        None,
        {"strategy": "broadcast"},
        {"strategy": "capability", "capability": "ocr"},
        {"strategy": "role", "role": "worker"},
        {"strategy": "mixed", "rules": [{"strategy": "broadcast"}]},
    ):
        assert requires_known_recipient(group) is False


# --------------------------------------------------------------------------- #
# Migration 005 — schema materialised
# --------------------------------------------------------------------------- #
def test_migration_005_creates_message_deliveries(migrated_factory):
    conn = migrated_factory.get_connection()
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "message_deliveries" in tables

        cols = {r[1] for r in conn.execute("PRAGMA table_info(message_deliveries)").fetchall()}
        # 005's columns are all present (later migrations may add more - 006
        # adds `attempts` - so this is a superset check, not equality).
        assert cols >= {
            "delivery_id",
            "message_id",
            "recipient_agent_id",
            "status",
            "delivered_at",
            "lease_expires_at",
            "read_at",
            "created_at",
        }

        indexes = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='message_deliveries'"
            ).fetchall()
        }
        assert {"idx_deliveries_inbox", "idx_deliveries_lease"} <= indexes

        # 005 is recorded in the ledger.
        versions = {
            r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        assert 5 in versions
    finally:
        conn.close()


def test_migration_005_enforces_one_delivery_per_message_recipient(migrated_factory):
    """The UNIQUE(message_id, recipient_agent_id) invariant is actually enforced."""
    conn = migrated_factory.get_connection()
    try:
        conn.execute("INSERT INTO workspaces (workspace_id, created_at) VALUES ('ws1', ?)", (NOW,))
        conn.execute("INSERT INTO agents (agent_id, created_at) VALUES ('a', ?)", (NOW,))
        conn.execute(
            "INSERT INTO messages (message_id, workspace_id, from_agent_id, created_at) "
            "VALUES ('m1', 'ws1', 'a', ?)",
            (NOW,),
        )
        conn.execute(
            "INSERT INTO message_deliveries "
            "(delivery_id, message_id, recipient_agent_id, status, created_at) "
            "VALUES ('d1', 'm1', 'a', 'unread', ?)",
            (NOW,),
        )
        # A second delivery for the SAME (message, recipient) must be rejected.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO message_deliveries "
                "(delivery_id, message_id, recipient_agent_id, status, created_at) "
                "VALUES ('d2', 'm1', 'a', 'unread', ?)",
                (NOW,),
            )
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Migration 006 — delivery hardening (attempts counter + history keyset index)
# --------------------------------------------------------------------------- #
def test_migration_006_adds_attempts_defaulting_to_zero(migrated_factory):
    """A delivery inserted WITHOUT attempts gets 0 (NOT NULL DEFAULT 0)."""
    conn = migrated_factory.get_connection()
    try:
        conn.execute(
            "INSERT INTO workspaces (workspace_id, created_at) VALUES ('ws1', ?)", (NOW,)
        )
        conn.execute("INSERT INTO agents (agent_id, created_at) VALUES ('a', ?)", (NOW,))
        conn.execute(
            "INSERT INTO messages (message_id, workspace_id, from_agent_id, created_at) "
            "VALUES ('m1', 'ws1', 'a', ?)",
            (NOW,),
        )
        # Pre-006-style insert (no attempts column named) must still work...
        conn.execute(
            "INSERT INTO message_deliveries "
            "(delivery_id, message_id, recipient_agent_id, status, created_at) "
            "VALUES ('d1', 'm1', 'a', 'unread', ?)",
            (NOW,),
        )
        # ...and read back as 0, never NULL.
        row = conn.execute(
            "SELECT attempts FROM message_deliveries WHERE delivery_id = 'd1'"
        ).fetchone()
        assert row["attempts"] == 0
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE message_deliveries SET attempts = NULL WHERE delivery_id = 'd1'"
            )
    finally:
        conn.close()


def test_migration_006_recorded_and_history_index_present(migrated_factory):
    conn = migrated_factory.get_connection()
    try:
        indexes = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='message_deliveries'"
            ).fetchall()
        }
        assert "idx_deliveries_history" in indexes
        versions = {
            r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        assert 6 in versions
    finally:
        conn.close()
