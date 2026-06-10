"""Phase 2a (application) tests for the inbox read service (ADR 0001).

Exercises ``InboxService`` over the REAL migrated SQLite store and the concrete
delivery repo. Deliveries are seeded directly (Phase 2b wires ``message_create``
to write them); here we verify the read/ack/lease behaviour in isolation:
pull -> in-flight, ack -> history, peek non-destructive, count lanes, history
pagination, at-least-once redelivery on lease expiry, and GLOBAL (cross-workspace)
materialisation of the message body.
"""

from __future__ import annotations

import threading

from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.mcp.tools.inbox import _resolve_lease_ttl, build_service
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteWorkspaceRepo,
)
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from okto_nexus.application.inbox import DEFAULT_INBOX_LEASE_TTL_SECONDS, InboxService
from okto_nexus.application.ports import Repos
from okto_nexus.domain.inbox import DELIVERY_UNREAD, new_delivery_id
from okto_nexus.errors import ErrorCode, OktoNexusError


def make_inbox(factory, clock, lease_ttl=60):
    return InboxService(
        connection_factory=factory,
        deliveries=SqliteMessageDeliveryRepo(clock),
        messages=SqliteMessageRepo(clock),
        agents=SqliteAgentRepo(clock),
        clock=clock,
        lease_ttl_seconds=lease_ttl,
    )


def seed(factory, clock, *, workspace_id, recipient, message_id, sender="sender", body="hello"):
    """Register the recipient + a workspace + a message, and queue one unread delivery."""
    wrepo = SqliteWorkspaceRepo(clock)
    arepo = SqliteAgentRepo(clock)
    mrepo = SqliteMessageRepo(clock)
    drepo = SqliteMessageDeliveryRepo(clock)
    with factory.unit_of_work() as uow:
        wrepo.upsert(uow, workspace_id=workspace_id, root_realpath="/x", last_seen_at=clock.now_iso())
        arepo.upsert(uow, agent_id=recipient)
        mrepo.create(
            uow,
            message_id=message_id,
            workspace_id=workspace_id,
            from_agent_id=sender,
            subject="subj",
            body=body,
        )
        drepo.create(
            uow,
            delivery_id=new_delivery_id(),
            message_id=message_id,
            recipient_agent_id=recipient,
            status=DELIVERY_UNREAD,
            created_at=clock.now_iso(),
        )


# --------------------------------------------------------------------------- #
# pull / ack / count
# --------------------------------------------------------------------------- #
def test_pull_returns_unread_and_marks_in_flight(migrated_factory, fake_clock):
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m1")
    inbox = make_inbox(migrated_factory, fake_clock)

    page = inbox.pull(agent_id="r")
    assert page["count"] == 1
    item = page["messages"][0]
    assert item["message_id"] == "m1"
    assert item["body"] == "hello"  # materialised body
    assert item["status"] == "delivered"
    assert item["lease_expires_at"] is not None

    # Already in-flight -> a second pull yields nothing (no double-delivery).
    assert inbox.pull(agent_id="r")["count"] == 0
    assert inbox.count(agent_id="r") == {"unread": 0, "in_flight": 1, "read": 0}


def test_ack_moves_to_history(migrated_factory, fake_clock):
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m1")
    inbox = make_inbox(migrated_factory, fake_clock)

    inbox.pull(agent_id="r")
    acked = inbox.ack(agent_id="r", message_ids=["m1"])
    assert acked == {"acknowledged": 1}
    assert inbox.count(agent_id="r") == {"unread": 0, "in_flight": 0, "read": 1}

    hist = inbox.history(agent_id="r")
    assert [m["message_id"] for m in hist["messages"]] == ["m1"]
    assert hist["messages"][0]["status"] == "read"
    # Acking again is idempotent (already read -> nothing transitions).
    assert inbox.ack(agent_id="r", message_ids=["m1"]) == {"acknowledged": 0}


def test_peek_is_non_destructive(migrated_factory, fake_clock):
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m1")
    inbox = make_inbox(migrated_factory, fake_clock)

    peeked = inbox.peek(agent_id="r")
    assert peeked["count"] == 1 and peeked["messages"][0]["status"] == "unread"
    # Still unread after peek (peek does not consume).
    assert inbox.count(agent_id="r") == {"unread": 1, "in_flight": 0, "read": 0}


# --------------------------------------------------------------------------- #
# at-least-once: lease expiry redelivers
# --------------------------------------------------------------------------- #
def test_lease_expiry_redelivers_unacked(migrated_factory, fake_clock):
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m1")
    inbox = make_inbox(migrated_factory, fake_clock, lease_ttl=60)

    first = inbox.pull(agent_id="r")  # leased at T0 .. T0+60
    assert first["count"] == 1

    # No ack; advance past the lease -> the next pull expires it and redelivers.
    fake_clock.set_iso("2026-06-07T00:05:00Z")
    again = inbox.pull(agent_id="r")
    assert [m["message_id"] for m in again["messages"]] == ["m1"]

    # But once acked, an expired lease no longer redelivers.
    inbox.ack(agent_id="r", message_ids=["m1"])
    fake_clock.set_iso("2026-06-07T00:10:00Z")
    assert inbox.pull(agent_id="r")["count"] == 0


# --------------------------------------------------------------------------- #
# global (cross-workspace) materialisation
# --------------------------------------------------------------------------- #
def test_inbox_is_global_across_workspaces(migrated_factory, fake_clock):
    # The message lives in workspace 'wsA'; the recipient pulls with NO workspace
    # context and still gets the body (the inbox is global).
    seed(migrated_factory, fake_clock, workspace_id="wsA", recipient="r", message_id="mA", body="from A")
    inbox = make_inbox(migrated_factory, fake_clock)
    page = inbox.pull(agent_id="r")
    assert page["count"] == 1
    assert page["messages"][0]["workspace_id"] == "wsA"
    assert page["messages"][0]["body"] == "from A"


# --------------------------------------------------------------------------- #
# pagination + validation
# --------------------------------------------------------------------------- #
def test_history_pagination(migrated_factory, fake_clock):
    inbox = make_inbox(migrated_factory, fake_clock)
    for i in range(3):
        seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id=f"m{i}")
    inbox.pull(agent_id="r", limit=10)
    inbox.ack(agent_id="r", message_ids=["m0", "m1", "m2"])

    first = inbox.history(agent_id="r", limit=2)
    assert len(first["messages"]) == 2 and first["has_more"] is True
    second = inbox.history(agent_id="r", cursor=first["next_cursor"], limit=2)
    assert len(second["messages"]) == 1 and second["has_more"] is False


def test_pull_requires_agent_id(migrated_factory, fake_clock):
    inbox = make_inbox(migrated_factory, fake_clock)
    for bad in (None, "", "   "):
        with pytest.raises(OktoNexusError) as ei:
            inbox.pull(agent_id=bad)
        assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


def test_pull_clamps_limit(migrated_factory, fake_clock):
    inbox = make_inbox(migrated_factory, fake_clock)
    with pytest.raises(OktoNexusError) as ei:
        inbox.pull(agent_id="r", limit=0)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    # empty inbox, valid limit -> empty page (no error)
    assert inbox.pull(agent_id="r", limit=5) == {"messages": [], "count": 0}


def test_ack_of_foreign_or_unknown_message_is_zero(migrated_factory, fake_clock):
    inbox = make_inbox(migrated_factory, fake_clock)
    # 'r' has no deliveries at all; acking anything transitions nothing.
    assert inbox.ack(agent_id="r", message_ids=["nope"]) == {"acknowledged": 0}


def test_peek_surfaces_both_unread_and_in_flight(migrated_factory, fake_clock):
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m1")
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m2")
    inbox = make_inbox(migrated_factory, fake_clock)
    inbox.pull(agent_id="r", limit=1)  # one -> in-flight, one stays unread
    statuses = sorted(m["status"] for m in inbox.peek(agent_id="r")["messages"])
    assert statuses == ["delivered", "unread"]  # peek exposes both pending lanes


def test_count_sweeps_expired_lease_back_to_unread(migrated_factory, fake_clock):
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m1")
    inbox = make_inbox(migrated_factory, fake_clock, lease_ttl=60)
    inbox.pull(agent_id="r")  # in-flight, leased to T0+60
    assert inbox.count(agent_id="r")["in_flight"] == 1
    # Past the lease, count must report it as unread (redeliverable), not in_flight,
    # so a recipient gating pull on `unread` is not misled into skipping it.
    fake_clock.set_iso("2026-06-07T00:05:00Z")
    assert inbox.count(agent_id="r") == {"unread": 1, "in_flight": 0, "read": 0}


def test_concurrent_pull_delivers_exactly_once(migrated_factory, fake_clock):
    """Two pulls of the same single unread delivery: the conditional UPDATE makes
    exactly one win (no double-delivery)."""
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m1")
    results: list[int] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def worker() -> None:
        inbox = make_inbox(migrated_factory, fake_clock)
        barrier.wait()
        for _ in range(40):  # retry transient WAL busy/snapshot under contention
            try:
                page = inbox.pull(agent_id="r")
                with lock:
                    results.append(page["count"])
                return
            except OktoNexusError as exc:
                if exc.code != ErrorCode.DB_ERROR.value:
                    raise

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # The single message is claimed by exactly one pull; the other gets nothing.
    assert sorted(results) == [0, 1]


# --------------------------------------------------------------------------- #
# tools/inbox.py adapter wiring (env knob + idempotent repo reuse)
# --------------------------------------------------------------------------- #
def test_resolve_lease_ttl_env_parsing():
    assert _resolve_lease_ttl({}) == DEFAULT_INBOX_LEASE_TTL_SECONDS
    assert _resolve_lease_ttl({"OKTO_NEXUS_INBOX_LEASE_TTL_SECONDS": "42"}) == 42
    # blank / non-int / non-positive all fall back to the default.
    for bad in ("", "   ", "abc", "-5", "0"):
        assert (
            _resolve_lease_ttl({"OKTO_NEXUS_INBOX_LEASE_TTL_SECONDS": bad})
            == DEFAULT_INBOX_LEASE_TTL_SECONDS
        )


def test_build_service_reuses_existing_repos(migrated_factory, tmp_config, fake_clock):
    deps = SimpleNamespace(
        connection_factory=migrated_factory,
        clock=fake_clock,
        config=tmp_config,
        repos=Repos(),
    )
    existing = SqliteMessageDeliveryRepo(fake_clock)
    deps.repos.deliveries = existing
    build_service(deps, env={})
    assert deps.repos.deliveries is existing  # reused, not re-instantiated
    assert deps.repos.messages is not None and deps.repos.agents is not None
