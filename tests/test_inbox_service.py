"""Application tests for the inbox queue service (ADR 0001, M4+M8 hardening).

Exercises ``InboxService`` over the REAL migrated SQLite store and the concrete
delivery repo. Deliveries are seeded directly (``message_create`` wires them in
the messages slice); here we verify the queue behaviour in isolation:

* pull -> in-flight under a caller-tunable lease; ack -> history;
* peek / count / history are 100% READ-ONLY (no row changes, no commits) and
  project the effective lane of lease-expired in-flight rows;
* pull's claim is recipient-scoped: it re-claims the recipient's own expired
  leases and never touches other recipients' rows;
* poison deliveries park (dead-letter) after the max claim attempts and stop
  reoccupying the head of the batch;
* inbox_extend renews in-flight leases atomically with precise errors;
* history pagination is keyset (no duplicates under interleaved acks);
* message_status gives the sender the per-recipient delivery cycle.
"""

from __future__ import annotations

import inspect
import threading

from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.mcp.tools.inbox import build_service, register
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteWorkspaceRepo,
)
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from okto_nexus.application.inbox import (
    DEFAULT_INBOX_LEASE_TTL_SECONDS,
    DEFAULT_MAX_DELIVERY_ATTEMPTS,
    InboxService,
)
from okto_nexus.application.ports import Repos
from okto_nexus.domain.inbox import DELIVERY_UNREAD, new_delivery_id
from okto_nexus.errors import ErrorCode, OktoNexusError


def _compat(factory):
    """Tolerate a ConnectionFactory whose ``unit_of_work`` does not yet accept
    ``write=`` (the parameter lands in a parallel wave); returns the factory
    untouched (fully transparent) once the parameter exists."""
    if "write" in inspect.signature(factory.unit_of_work).parameters:
        return factory

    class _WriteParamShim:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def unit_of_work(self, write=True):
            return self._inner.unit_of_work()

    return _WriteParamShim(factory)


def make_inbox(factory, clock, lease_ttl=60):
    return InboxService(
        connection_factory=_compat(factory),
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


def _deliveries_snapshot(factory):
    """Every column of every delivery row, in rowid order (write detector)."""
    conn = factory.get_connection()
    try:
        return [
            tuple(r)
            for r in conn.execute(
                "SELECT * FROM message_deliveries ORDER BY rowid"
            ).fetchall()
        ]
    finally:
        conn.close()


def _delivery_row(factory, message_id):
    conn = factory.get_connection()
    try:
        return conn.execute(
            "SELECT status, attempts, delivered_at, lease_expires_at "
            "FROM message_deliveries WHERE message_id = ?",
            (message_id,),
        ).fetchone()
    finally:
        conn.close()


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

    # No ack; advance past the lease -> the next pull re-claims and redelivers.
    fake_clock.set_iso("2026-06-07T00:05:00.000000Z")
    again = inbox.pull(agent_id="r")
    assert [m["message_id"] for m in again["messages"]] == ["m1"]

    # But once acked, an expired lease no longer redelivers.
    inbox.ack(agent_id="r", message_ids=["m1"])
    fake_clock.set_iso("2026-06-07T00:10:00.000000Z")
    assert inbox.pull(agent_id="r")["count"] == 0


# --------------------------------------------------------------------------- #
# M4: peek/count/history are 100% READ-ONLY
# --------------------------------------------------------------------------- #
def test_peek_count_history_write_nothing_even_with_expired_leases(
    migrated_factory, fake_clock
):
    """The read paths change NO row (asserted on every column of every row) and
    commit NO write (asserted via PRAGMA data_version from an observer
    connection), even when an expired lease must be presented as unread."""
    for mid in ("m1", "m2", "m3"):
        seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id=mid)
    inbox = make_inbox(migrated_factory, fake_clock, lease_ttl=60)
    inbox.pull(agent_id="r", limit=2)        # m1, m2 in-flight
    inbox.ack(agent_id="r", message_ids=["m2"])  # m2 read
    fake_clock.set_iso("2026-06-07T00:05:00.000000Z")   # m1's lease expired

    before = _deliveries_snapshot(migrated_factory)
    observer = migrated_factory.get_connection()
    try:
        dv_before = observer.execute("PRAGMA data_version").fetchone()[0]

        peeked = inbox.peek(agent_id="r")
        counts = inbox.count(agent_id="r")
        hist = inbox.history(agent_id="r")

        dv_after = observer.execute("PRAGMA data_version").fetchone()[0]
    finally:
        observer.close()

    # Effective lanes: the expired in-flight m1 reads as unread (lease cleared
    # in the projection), m3 is unread, m2 is history.
    by_id = {m["message_id"]: m for m in peeked["messages"]}
    assert set(by_id) == {"m1", "m3"}
    assert by_id["m1"]["status"] == "unread"
    assert by_id["m1"]["lease_expires_at"] is None
    assert counts == {"unread": 2, "in_flight": 0, "read": 1}
    assert [m["message_id"] for m in hist["messages"]] == ["m2"]

    # ...and NOTHING was written: identical rows, no committed transaction.
    assert _deliveries_snapshot(migrated_factory) == before
    assert dv_after == dv_before


def test_reads_use_readonly_uow_and_mutations_use_write_uow(
    migrated_factory, fake_clock
):
    """The service asks the factory for a READ transaction on every polling
    path (write=False) and a WRITE one only for pull/ack/extend - the port
    contract that keeps polling off the WAL writer lock."""
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m1")

    class RecordingFactory:
        def __init__(self, inner):
            self._inner = inner
            self.write_flags = []

        def unit_of_work(self, write=True):
            self.write_flags.append(write)
            return self._inner.unit_of_work()

        def get_connection(self):
            return self._inner.get_connection()

    recording = RecordingFactory(migrated_factory)
    inbox = InboxService(
        connection_factory=recording,
        deliveries=SqliteMessageDeliveryRepo(fake_clock),
        messages=SqliteMessageRepo(fake_clock),
        agents=SqliteAgentRepo(fake_clock),
        clock=fake_clock,
        lease_ttl_seconds=60,
    )

    inbox.peek(agent_id="r")
    inbox.count(agent_id="r")
    inbox.history(agent_id="r")
    inbox.message_status(message_id="m1")
    assert recording.write_flags == [False, False, False, False]

    recording.write_flags.clear()
    inbox.pull(agent_id="r")
    inbox.extend(agent_id="r", message_ids=["m1"], extend_seconds=120)
    inbox.ack(agent_id="r", message_ids=["m1"])
    assert recording.write_flags == [True, True, True]


# --------------------------------------------------------------------------- #
# M4: pull's claim is recipient-scoped
# --------------------------------------------------------------------------- #
def test_pull_reclaims_own_expired_and_never_touches_other_recipients(
    migrated_factory, fake_clock
):
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r1", message_id="m1")
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r2", message_id="m2")
    inbox = make_inbox(migrated_factory, fake_clock, lease_ttl=60)
    inbox.pull(agent_id="r1")
    r2_lease = inbox.pull(agent_id="r2")["messages"][0]["lease_expires_at"]

    fake_clock.set_iso("2026-06-07T00:05:00.000000Z")  # both leases are now expired
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r1", message_id="m3")

    # ONE claim covers r1's expired redelivery AND r1's fresh unread message...
    page = inbox.pull(agent_id="r1", limit=10)
    assert [m["message_id"] for m in page["messages"]] == ["m1", "m3"]

    # ...while r2's expired delivery is PHYSICALLY untouched (no global sweep):
    # still 'delivered' carrying its original elapsed lease until r2 pulls.
    row = _delivery_row(migrated_factory, "m2")
    assert (row["status"], row["lease_expires_at"]) == ("delivered", r2_lease)

    # r2 still redelivers it on r2's own pull.
    assert [m["message_id"] for m in inbox.pull(agent_id="r2")["messages"]] == ["m2"]


def test_concurrent_pull_delivers_exactly_once(migrated_factory, fake_clock):
    """Two simultaneous pulls of the same single unread delivery: the
    single-statement, recipient-scoped claim makes exactly one win (no
    double-delivery and no compensatory retries)."""
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m1")
    results: list[int] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def worker() -> None:
        inbox = make_inbox(migrated_factory, fake_clock)
        barrier.wait()
        page = inbox.pull(agent_id="r")
        with lock:
            results.append(page["count"])

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # The single message is claimed by exactly one pull; the other gets nothing.
    assert sorted(results) == [0, 1]


# --------------------------------------------------------------------------- #
# M8: caller-tunable lease (pull lease_seconds)
# --------------------------------------------------------------------------- #
def test_pull_lease_seconds_sets_and_clamps_the_lease(migrated_factory, fake_clock):
    for mid in ("m1", "m2", "m3"):
        seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id=mid)
    inbox = make_inbox(migrated_factory, fake_clock, lease_ttl=60)

    chosen = inbox.pull(agent_id="r", limit=1, lease_seconds=120)
    assert chosen["messages"][0]["lease_expires_at"] == "2026-06-07T00:02:00.000000Z"

    too_low = inbox.pull(agent_id="r", limit=1, lease_seconds=1)  # clamped to 10
    assert too_low["messages"][0]["lease_expires_at"] == "2026-06-07T00:00:10.000000Z"

    too_high = inbox.pull(agent_id="r", limit=1, lease_seconds=999_999)  # to 3600
    assert too_high["messages"][0]["lease_expires_at"] == "2026-06-07T01:00:00.000000Z"


def test_pull_lease_seconds_default_and_validation(migrated_factory, fake_clock):
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m1")
    inbox = make_inbox(migrated_factory, fake_clock, lease_ttl=60)
    # Omitted -> the service default applies (60s here).
    page = inbox.pull(agent_id="r")
    assert page["messages"][0]["lease_expires_at"] == "2026-06-07T00:01:00.000000Z"
    for bad in ("soon", True, 12.5):
        with pytest.raises(OktoNexusError) as ei:
            inbox.pull(agent_id="r", lease_seconds=bad)
        assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# M8: poison deliveries park after the max claim attempts (DLQ)
# --------------------------------------------------------------------------- #
def test_poison_delivery_parks_after_max_attempts_and_frees_the_head(
    migrated_factory, fake_clock
):
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m1")
    inbox = make_inbox(migrated_factory, fake_clock, lease_ttl=10)

    # m1 is claimed (never acked) the maximum number of times.
    for i in range(DEFAULT_MAX_DELIVERY_ATTEMPTS):
        fake_clock.set_iso(f"2026-06-07T00:0{i}:00.000000Z")
        assert [m["message_id"] for m in inbox.pull(agent_id="r")["messages"]] == ["m1"]

    # A healthy message arrives behind the poison one.
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m2")

    # The next claim PARKS m1 instead of redelivering it - and the same pull
    # still delivers m2 (the poison message no longer occupies the head).
    fake_clock.set_iso("2026-06-07T00:05:00.000000Z")
    page = inbox.pull(agent_id="r", limit=10)
    assert [m["message_id"] for m in page["messages"]] == ["m2"]

    row = _delivery_row(migrated_factory, "m1")
    assert row["status"] == "parked"
    assert row["attempts"] == DEFAULT_MAX_DELIVERY_ATTEMPTS
    assert row["delivered_at"] is None and row["lease_expires_at"] is None

    # Parked never comes back: later pulls redeliver only the healthy message.
    fake_clock.set_iso("2026-06-07T00:20:00.000000Z")
    assert [m["message_id"] for m in inbox.pull(agent_id="r")["messages"]] == ["m2"]
    assert _delivery_row(migrated_factory, "m1")["status"] == "parked"

    # Parked is excluded from count and from the default peek...
    assert inbox.count(agent_id="r") == {"unread": 0, "in_flight": 1, "read": 0}
    assert [m["message_id"] for m in inbox.peek(agent_id="r")["messages"]] == ["m2"]
    # ...but inspectable on demand.
    with_parked = inbox.peek(agent_id="r", include_parked=True)
    statuses = {m["message_id"]: m["status"] for m in with_parked["messages"]}
    assert statuses == {"m1": "parked", "m2": "delivered"}


def test_peek_include_parked_must_be_boolean(migrated_factory, fake_clock):
    inbox = make_inbox(migrated_factory, fake_clock)
    with pytest.raises(OktoNexusError) as ei:
        inbox.peek(agent_id="r", include_parked="yes")
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# peek is envelope-only (body_preview/body_bytes); pull/history keep the body
# --------------------------------------------------------------------------- #
def test_peek_is_envelope_only_pull_and_history_return_full_body(
    migrated_factory, fake_clock
):
    """peek is the TRIAGE path: it must not materialise full bodies (worst case
    ~50 x 64KB per call), only a bounded preview + the full UTF-8 size so the
    recipient can decide whether an inbox_pull is worth it. pull (consumption)
    and history (explicit content read) keep the integral body."""
    long_body = ("x" * 250) + "ção"  # > 200 chars, multibyte tail
    seed(
        migrated_factory,
        fake_clock,
        workspace_id="ws",
        recipient="r",
        message_id="m1",
        body=long_body,
    )
    inbox = make_inbox(migrated_factory, fake_clock)

    item = inbox.peek(agent_id="r")["messages"][0]
    assert "body" not in item
    assert item["body_preview"] == long_body[:200]
    assert len(item["body_preview"]) == 200
    assert item["body_bytes"] == len(long_body.encode("utf-8"))
    # The triage envelope survives: who / subject / when / delivery state.
    assert item["from_agent_id"] == "sender"
    assert item["subject"] == "subj"
    assert item["status"] == "unread"
    assert item["created_at"] is not None

    # pull materialises the FULL body (and no preview fields).
    pulled = inbox.pull(agent_id="r")["messages"][0]
    assert pulled["body"] == long_body
    assert "body_preview" not in pulled and "body_bytes" not in pulled

    # history keeps the full body too.
    inbox.ack(agent_id="r", message_ids=["m1"])
    hist = inbox.history(agent_id="r")["messages"][0]
    assert hist["body"] == long_body
    assert "body_preview" not in hist and "body_bytes" not in hist


def test_peek_short_body_previews_whole_body(migrated_factory, fake_clock):
    seed(
        migrated_factory,
        fake_clock,
        workspace_id="ws",
        recipient="r",
        message_id="m1",
        body="oi",
    )
    inbox = make_inbox(migrated_factory, fake_clock)
    item = inbox.peek(agent_id="r")["messages"][0]
    assert "body" not in item
    assert item["body_preview"] == "oi"
    assert item["body_bytes"] == 2


def test_peek_include_bodies_opts_into_full_body_and_validates(
    migrated_factory, fake_clock
):
    long_body = "y" * 300
    seed(
        migrated_factory,
        fake_clock,
        workspace_id="ws",
        recipient="r",
        message_id="m1",
        body=long_body,
    )
    inbox = make_inbox(migrated_factory, fake_clock)

    item = inbox.peek(agent_id="r", include_bodies=True)["messages"][0]
    assert item["body"] == long_body
    assert "body_preview" not in item and "body_bytes" not in item

    with pytest.raises(OktoNexusError) as ei:
        inbox.peek(agent_id="r", include_bodies="yes")
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# M8: inbox_extend renews in-flight leases
# --------------------------------------------------------------------------- #
def test_extend_renews_lease_and_prevents_redelivery(migrated_factory, fake_clock):
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m1")
    inbox = make_inbox(migrated_factory, fake_clock, lease_ttl=60)
    inbox.pull(agent_id="r")  # leased to 00:01:00

    fake_clock.set_iso("2026-06-07T00:00:30.000000Z")
    out = inbox.extend(agent_id="r", message_ids=["m1"], extend_seconds=600)
    assert out == {"extended": 1, "lease_expires_at": "2026-06-07T00:10:30.000000Z"}

    # Past the ORIGINAL lease the message is still in flight (not redelivered).
    fake_clock.set_iso("2026-06-07T00:02:00.000000Z")
    assert inbox.pull(agent_id="r")["count"] == 0
    assert inbox.count(agent_id="r") == {"unread": 0, "in_flight": 1, "read": 0}

    # Once the EXTENDED lease elapses, at-least-once redelivery resumes.
    fake_clock.set_iso("2026-06-07T00:15:00.000000Z")
    assert [m["message_id"] for m in inbox.pull(agent_id="r")["messages"]] == ["m1"]


def test_extend_seconds_clamped(migrated_factory, fake_clock):
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m1")
    inbox = make_inbox(migrated_factory, fake_clock, lease_ttl=60)
    inbox.pull(agent_id="r")
    out = inbox.extend(agent_id="r", message_ids=["m1"], extend_seconds=999_999)
    assert out["lease_expires_at"] == "2026-06-07T01:00:00.000000Z"  # clamped to 3600


def test_extend_fails_precisely_per_lane_and_extends_nothing(
    migrated_factory, fake_clock
):
    for mid in ("m1", "m2", "m3"):
        seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id=mid)
    inbox = make_inbox(migrated_factory, fake_clock, lease_ttl=60)
    inbox.pull(agent_id="r", limit=2)            # m1, m2 in-flight
    inbox.ack(agent_id="r", message_ids=["m2"])  # m2 read; m3 still unread
    m1_lease_before = _delivery_row(migrated_factory, "m1")["lease_expires_at"]

    # Unknown message -> NOT_FOUND naming the offender.
    with pytest.raises(OktoNexusError) as unknown:
        inbox.extend(agent_id="r", message_ids=["ghost"], extend_seconds=60)
    assert unknown.value.code == ErrorCode.NOT_FOUND.value
    assert unknown.value.details["not_in_flight"][0]["message_id"] == "ghost"

    # Mixed batch: m1 IS in-flight but m3 was never pulled -> the call fails
    # with a per-message reason AND m1's lease is left unchanged (atomic).
    with pytest.raises(OktoNexusError) as mixed:
        inbox.extend(agent_id="r", message_ids=["m1", "m3"], extend_seconds=600)
    assert mixed.value.code == ErrorCode.INVALID_TRANSITION.value
    problems = {p["message_id"]: p for p in mixed.value.details["not_in_flight"]}
    assert set(problems) == {"m3"}
    assert "inbox_pull" in problems["m3"]["reason"]
    assert _delivery_row(migrated_factory, "m1")["lease_expires_at"] == m1_lease_before

    # Already acknowledged -> precise reason.
    with pytest.raises(OktoNexusError) as read_err:
        inbox.extend(agent_id="r", message_ids=["m2"], extend_seconds=60)
    assert read_err.value.code == ErrorCode.INVALID_TRANSITION.value
    assert "acknowledged" in read_err.value.details["not_in_flight"][0]["reason"]

    # Expired lease -> redeliverable, not extendable.
    fake_clock.set_iso("2026-06-07T00:05:00.000000Z")
    with pytest.raises(OktoNexusError) as expired:
        inbox.extend(agent_id="r", message_ids=["m1"], extend_seconds=60)
    assert expired.value.code == ErrorCode.INVALID_TRANSITION.value
    assert "expired" in expired.value.details["not_in_flight"][0]["reason"]

    # Validation: empty ids / non-integer seconds.
    for bad_ids in (None, [], ["  "]):
        with pytest.raises(OktoNexusError) as no_ids:
            inbox.extend(agent_id="r", message_ids=bad_ids, extend_seconds=60)
        assert no_ids.value.code == ErrorCode.VALIDATION_ERROR.value
    with pytest.raises(OktoNexusError) as bad_secs:
        inbox.extend(agent_id="r", message_ids=["m1"], extend_seconds=None)
    assert bad_secs.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# M8: keyset history pagination (stable under interleaved acks)
# --------------------------------------------------------------------------- #
def test_history_keyset_pages_do_not_duplicate_under_interleaved_acks(
    migrated_factory, fake_clock
):
    for i in range(5):
        seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id=f"m{i}")
    inbox = make_inbox(migrated_factory, fake_clock)
    inbox.pull(agent_id="r", limit=10)
    inbox.ack(agent_id="r", message_ids=["m0", "m1", "m2"])  # read_at = T0

    first = inbox.history(agent_id="r", limit=2)
    assert len(first["messages"]) == 2 and first["has_more"] is True
    page1 = {m["message_id"] for m in first["messages"]}

    # Between pages, NEWER acks land (with OFFSET pagination they would shift
    # page-1 items down into page 2 and duplicate them).
    fake_clock.set_iso("2026-06-07T00:01:00.000000Z")
    inbox.ack(agent_id="r", message_ids=["m3", "m4"])

    second = inbox.history(agent_id="r", cursor=first["next_cursor"], limit=2)
    page2 = {m["message_id"] for m in second["messages"]}
    assert not page1 & page2  # NO duplicates across the page boundary
    # The cursor keeps walking the ORIGINAL snapshot's remainder.
    assert page1 | page2 == {"m0", "m1", "m2"}
    assert len(page2) == 1
    assert second["has_more"] is False and second["next_cursor"] is None

    # A fresh first page sees the newly acked messages first (newest-first).
    fresh = inbox.history(agent_id="r", limit=2)
    assert {m["message_id"] for m in fresh["messages"]} == {"m3", "m4"}


def test_history_pagination_walks_all_pages(migrated_factory, fake_clock):
    inbox = make_inbox(migrated_factory, fake_clock)
    for i in range(3):
        seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id=f"m{i}")
    inbox.pull(agent_id="r", limit=10)
    inbox.ack(agent_id="r", message_ids=["m0", "m1", "m2"])

    first = inbox.history(agent_id="r", limit=2)
    assert len(first["messages"]) == 2 and first["has_more"] is True
    second = inbox.history(agent_id="r", cursor=first["next_cursor"], limit=2)
    assert len(second["messages"]) == 1 and second["has_more"] is False
    seen = [m["message_id"] for m in first["messages"] + second["messages"]]
    assert sorted(seen) == ["m0", "m1", "m2"]  # complete, no repeats


def test_history_rejects_foreign_cursor(migrated_factory, fake_clock):
    inbox = make_inbox(migrated_factory, fake_clock)
    for bad in ("3", "not-a-cursor", 7, "~", "x~"):
        with pytest.raises(OktoNexusError) as ei:
            inbox.history(agent_id="r", cursor=bad)
        assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
        assert "next_cursor" in ei.value.message  # prescriptive: where to get one


# --------------------------------------------------------------------------- #
# M8: message_status — the sender's view of the delivery cycle
# --------------------------------------------------------------------------- #
def test_message_status_reflects_the_delivery_cycle(migrated_factory, fake_clock):
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m1")
    inbox = make_inbox(migrated_factory, fake_clock, lease_ttl=60)

    def status():
        out = inbox.message_status(message_id="m1")
        assert out["message_id"] == "m1" and out["count"] == 1
        return out["deliveries"][0]

    assert status() == {"recipient": "r", "status": "unread", "attempts": 0, "read_at": None}

    inbox.pull(agent_id="r")
    assert status() == {"recipient": "r", "status": "delivered", "attempts": 1, "read_at": None}

    # Lease elapses unacked: the sender sees it as redeliverable again.
    fake_clock.set_iso("2026-06-07T00:05:00.000000Z")
    assert status() == {"recipient": "r", "status": "unread", "attempts": 1, "read_at": None}

    inbox.pull(agent_id="r")
    inbox.ack(agent_id="r", message_ids=["m1"])
    final = status()
    assert (final["status"], final["attempts"]) == ("read", 2)
    assert final["read_at"] == "2026-06-07T00:05:00.000000Z"


def test_message_status_unknown_message_is_not_found(migrated_factory, fake_clock):
    inbox = make_inbox(migrated_factory, fake_clock)
    with pytest.raises(OktoNexusError) as ei:
        inbox.message_status(message_id="ghost")
    assert ei.value.code == ErrorCode.NOT_FOUND.value
    assert "message_create" in ei.value.message  # prescriptive
    for bad in (None, "", "  "):
        with pytest.raises(OktoNexusError) as bad_id:
            inbox.message_status(message_id=bad)
        assert bad_id.value.code == ErrorCode.VALIDATION_ERROR.value


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
# validation
# --------------------------------------------------------------------------- #
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


def test_count_reports_expired_lease_as_unread(migrated_factory, fake_clock):
    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m1")
    inbox = make_inbox(migrated_factory, fake_clock, lease_ttl=60)
    inbox.pull(agent_id="r")  # in-flight, leased to T0+60
    assert inbox.count(agent_id="r")["in_flight"] == 1
    # Past the lease, count must report it as unread (redeliverable), not in_flight,
    # so a recipient gating pull on `unread` is not misled into skipping it.
    fake_clock.set_iso("2026-06-07T00:05:00.000000Z")
    assert inbox.count(agent_id="r") == {"unread": 1, "in_flight": 0, "read": 0}


# --------------------------------------------------------------------------- #
# tools/inbox.py adapter wiring (env knob + idempotent repo reuse + new tools)
# --------------------------------------------------------------------------- #
class FakeServer:
    """Captures FastMCP-style ``@server.tool()`` registrations by name."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def test_build_service_lease_ttl_comes_from_config(
    migrated_factory, tmp_config, fake_clock
):
    # The knob moved into NexusConfig (fail-closed parse at load_config time);
    # the adapter must read the configured value, not os.environ.
    assert tmp_config.inbox_lease_ttl_seconds == DEFAULT_INBOX_LEASE_TTL_SECONDS
    tmp_config.inbox_lease_ttl_seconds = 42
    deps = SimpleNamespace(
        connection_factory=migrated_factory,
        clock=fake_clock,
        config=tmp_config,
        repos=Repos(),
    )
    svc = build_service(deps)
    assert svc._lease_ttl == 42


def test_build_service_reuses_existing_repos(migrated_factory, tmp_config, fake_clock):
    deps = SimpleNamespace(
        connection_factory=migrated_factory,
        clock=fake_clock,
        config=tmp_config,
        repos=Repos(),
    )
    existing = SqliteMessageDeliveryRepo(fake_clock)
    deps.repos.deliveries = existing
    build_service(deps)
    assert deps.repos.deliveries is existing  # reused, not re-instantiated
    assert deps.repos.messages is not None and deps.repos.agents is not None


def test_register_exposes_queue_tools_and_envelopes_errors(
    migrated_factory, tmp_config, fake_clock
):
    deps = SimpleNamespace(
        connection_factory=_compat(migrated_factory),
        clock=fake_clock,
        config=tmp_config,
        repos=Repos(),
    )
    server = FakeServer()
    register(server, deps)
    expected = {
        "inbox_pull", "inbox_ack", "inbox_extend", "inbox_peek",
        "inbox_count", "inbox_history", "message_status",
    }
    assert expected <= set(server.tools)

    # Errors surface as actionable envelopes (never exceptions).
    env = server.tools["message_status"](message_id="ghost")
    assert env["ok"] is False and env["error"]["code"] == "NOT_FOUND"
    assert "message_create" in env["error"]["message"]

    seed(migrated_factory, fake_clock, workspace_id="ws", recipient="r", message_id="m1")
    env2 = server.tools["inbox_extend"](agent_id="r", message_ids="m1", extend_seconds=60)
    assert env2["ok"] is False and env2["error"]["code"] == "INVALID_TRANSITION"
    assert env2["error"]["details"]["not_in_flight"][0]["message_id"] == "m1"

    # Happy path: pull with a custom lease, then renew it through the tool.
    pulled = server.tools["inbox_pull"](agent_id="r", lease_seconds=120)
    assert pulled["ok"] is True and pulled["data"]["count"] == 1
    env3 = server.tools["inbox_extend"](agent_id="r", message_ids="m1", extend_seconds=600)
    assert env3["ok"] is True and env3["data"]["extended"] == 1

    # include_parked is plumbed through the tool surface.
    env4 = server.tools["inbox_peek"](agent_id="r", include_parked=True)
    assert env4["ok"] is True and env4["data"]["count"] == 1


def test_inbox_peek_tool_is_envelope_only_with_include_bodies_opt_in(
    migrated_factory, tmp_config, fake_clock
):
    deps = SimpleNamespace(
        connection_factory=_compat(migrated_factory),
        clock=fake_clock,
        config=tmp_config,
        repos=Repos(),
    )
    server = FakeServer()
    register(server, deps)
    body = "B" * 250
    seed(
        migrated_factory,
        fake_clock,
        workspace_id="ws",
        recipient="r",
        message_id="m1",
        body=body,
    )

    # Default: envelope-only projection through the MCP tool.
    env = server.tools["inbox_peek"](agent_id="r")
    assert env["ok"] is True
    item = env["data"]["messages"][0]
    assert "body" not in item
    assert item["body_preview"] == "B" * 200
    assert item["body_bytes"] == 250

    # Opt-in: include_bodies=true returns the full body without consuming.
    env_full = server.tools["inbox_peek"](agent_id="r", include_bodies=True)
    assert env_full["ok"] is True
    assert env_full["data"]["messages"][0]["body"] == body
    # ...and the message is STILL unread (peek never consumes).
    assert server.tools["inbox_count"](agent_id="r")["data"]["unread"] == 1
