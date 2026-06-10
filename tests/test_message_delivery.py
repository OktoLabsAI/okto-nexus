"""Phase 2b tests: message_create resolves recipients and fans out to inboxes.

Exercises the DELIVERING ``MessageService`` (deliveries + sessions wired) over
the real migrated store: the recipient-resolution audience rules (global registry
for directed/capability/role; workspace participants for broadcast), the critique
rules (direct->unknown = NOT_FOUND; group zero-match = warning, never silent), the
sender exclusion, the end-to-end create -> InboxService.pull flow, and the
sender-side ``message_status`` view of each recipient's delivery cycle.
"""

from __future__ import annotations

import inspect

import pytest

from okto_nexus.adapters.outbound.sqlite.events_repo import (
    SqliteEventEmitter,
    SqliteEventRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteSessionRepo,
    SqliteWorkspaceRepo,
)
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteChannelRepo,
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from okto_nexus.application.inbox import InboxService
from okto_nexus.application.messages import MessageService
from okto_nexus.domain.base import new_id
from okto_nexus.domain.ids import resolve_realpath, resolve_workspace_id
from okto_nexus.errors import ErrorCode, OktoNexusError


def make_service(factory, clock) -> MessageService:
    return MessageService(
        connection_factory=factory,
        channels=SqliteChannelRepo(clock),
        messages=SqliteMessageRepo(clock),
        workspaces=SqliteWorkspaceRepo(clock),
        agents=SqliteAgentRepo(clock),
        sessions=SqliteSessionRepo(clock),
        deliveries=SqliteMessageDeliveryRepo(clock),
        event_emitter=SqliteEventEmitter(SqliteEventRepo(clock)),
        clock=clock,
        max_inline_bytes=65536,
    )


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


def make_inbox(factory, clock) -> InboxService:
    return InboxService(
        connection_factory=_compat(factory),
        deliveries=SqliteMessageDeliveryRepo(clock),
        messages=SqliteMessageRepo(clock),
        agents=SqliteAgentRepo(clock),
        clock=clock,
    )


def mkproj(tmp_path, name="P"):
    p = tmp_path / name
    p.mkdir()
    return str(p)


def register(factory, clock, agent_id, *, role=None, capabilities=None):
    arepo = SqliteAgentRepo(clock)
    with factory.unit_of_work() as uow:
        arepo.upsert(uow, agent_id=agent_id, role=role, capabilities=capabilities)


def open_session(factory, clock, agent_id, project_root):
    """Register presence: upsert the workspace + an active session for the agent."""
    wrepo = SqliteWorkspaceRepo(clock)
    srepo = SqliteSessionRepo(clock)
    ws = resolve_workspace_id(project_root)
    with factory.unit_of_work() as uow:
        wrepo.upsert(
            uow,
            workspace_id=ws,
            root_realpath=resolve_realpath(project_root),
            last_seen_at=clock.now_iso(),
        )
        srepo.create(
            uow,
            session_id=new_id("ses"),
            agent_id=agent_id,
            workspace_id=ws,
            status="active",
        )


def count(factory, table):
    conn = factory.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# direct
# --------------------------------------------------------------------------- #
def test_direct_to_registered_then_pull(migrated_factory, fake_clock, tmp_path):
    register(migrated_factory, fake_clock, "bob")
    svc = make_service(migrated_factory, fake_clock)
    proj = mkproj(tmp_path)

    out = svc.create_message(
        project_root=proj,
        from_agent_id="alice",
        subject="hi",
        body="ping",
        target={"strategy": "direct", "agent_id": "bob"},
    )
    assert out["recipients"] == ["bob"]
    assert out["delivered_count"] == 1
    assert "warning" not in out

    # End-to-end: bob pulls his global inbox and gets the body.
    inbox = make_inbox(migrated_factory, fake_clock)
    page = inbox.pull(agent_id="bob")
    assert [m["body"] for m in page["messages"]] == ["ping"]


def test_direct_unknown_agent_is_not_found_and_rolls_back(migrated_factory, fake_clock, tmp_path):
    svc = make_service(migrated_factory, fake_clock)
    proj = mkproj(tmp_path)
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(
            project_root=proj,
            from_agent_id="alice",
            subject="hi",
            body="ping",
            target={"strategy": "direct", "agent_id": "ghost"},
        )
    assert ei.value.code == ErrorCode.NOT_FOUND.value
    # WHOLE uow rolled back: not even the workspace upsert (the first write) leaks.
    assert count(migrated_factory, "messages") == 0
    assert count(migrated_factory, "message_deliveries") == 0
    assert count(migrated_factory, "workspaces") == 0


# --------------------------------------------------------------------------- #
# broadcast -> workspace participants (sender excluded)
# --------------------------------------------------------------------------- #
def test_broadcast_delivers_to_workspace_participants_excluding_sender(
    migrated_factory, fake_clock, tmp_path
):
    proj = mkproj(tmp_path)
    for a in ("alice", "bob", "carol"):
        register(migrated_factory, fake_clock, a)
    # alice (sender) and bob are present in this workspace; carol is not.
    open_session(migrated_factory, fake_clock, "alice", proj)
    open_session(migrated_factory, fake_clock, "bob", proj)

    svc = make_service(migrated_factory, fake_clock)
    out = svc.create_message(
        project_root=proj, from_agent_id="alice", subject="announce", body="hello all"
    )
    # bob receives; alice (sender) excluded; carol (not present) excluded.
    assert out["recipients"] == ["bob"]
    assert out["delivered_count"] == 1


def test_broadcast_to_empty_workspace_warns(migrated_factory, fake_clock, tmp_path):
    proj = mkproj(tmp_path)
    register(migrated_factory, fake_clock, "alice")
    open_session(migrated_factory, fake_clock, "alice", proj)  # only the sender present
    svc = make_service(migrated_factory, fake_clock)
    out = svc.create_message(
        project_root=proj, from_agent_id="alice", subject="hi", body="anyone?"
    )
    assert out["recipients"] == []
    assert out["delivered_count"] == 0
    assert "warning" in out
    # The message row still exists (observable via the log); just nobody got it.
    assert count(migrated_factory, "messages") == 1


# --------------------------------------------------------------------------- #
# capability / role -> global registry
# --------------------------------------------------------------------------- #
def test_capability_delivers_to_global_holders(migrated_factory, fake_clock, tmp_path):
    proj = mkproj(tmp_path)
    register(migrated_factory, fake_clock, "alice")
    register(migrated_factory, fake_clock, "w1", capabilities=["ocr", "pdf"])
    register(migrated_factory, fake_clock, "w2", capabilities={"ocr": True})
    register(migrated_factory, fake_clock, "w3", capabilities=["xml"])
    svc = make_service(migrated_factory, fake_clock)

    out = svc.create_message(
        project_root=proj,
        from_agent_id="alice",
        subject="ocr please",
        body="scan.png",
        target={"strategy": "capability", "capability": "ocr"},
    )
    assert out["recipients"] == ["w1", "w2"]  # global; w3 (xml) excluded


def test_capability_zero_match_warns_not_errors(migrated_factory, fake_clock, tmp_path):
    proj = mkproj(tmp_path)
    register(migrated_factory, fake_clock, "alice")
    svc = make_service(migrated_factory, fake_clock)
    out = svc.create_message(
        project_root=proj,
        from_agent_id="alice",
        subject="x",
        body="y",
        target={"strategy": "capability", "capability": "telepathy"},
    )
    assert out["recipients"] == [] and "warning" in out


def test_role_delivers_to_global_holders(migrated_factory, fake_clock, tmp_path):
    proj = mkproj(tmp_path)
    register(migrated_factory, fake_clock, "alice")
    register(migrated_factory, fake_clock, "v1", role="validator")
    register(migrated_factory, fake_clock, "v2", role="validator")
    register(migrated_factory, fake_clock, "w1", role="worker")
    svc = make_service(migrated_factory, fake_clock)
    out = svc.create_message(
        project_root=proj,
        from_agent_id="alice",
        subject="review",
        body="pr",
        target={"strategy": "role", "role": "validator"},
    )
    assert out["recipients"] == ["v1", "v2"]


# --------------------------------------------------------------------------- #
# durable fan-out + sender-exclusion asymmetry + mixed + unsafe-target rejection
# --------------------------------------------------------------------------- #
def test_multi_recipient_fanout_persists_and_each_pulls(migrated_factory, fake_clock, tmp_path):
    proj = mkproj(tmp_path)
    register(migrated_factory, fake_clock, "alice")
    register(migrated_factory, fake_clock, "w1", capabilities=["ocr"])
    register(migrated_factory, fake_clock, "w2", capabilities=["ocr"])
    svc = make_service(migrated_factory, fake_clock)
    out = svc.create_message(
        project_root=proj,
        from_agent_id="alice",
        subject="ocr",
        body="scan",
        target={"strategy": "capability", "capability": "ocr"},
    )
    assert out["recipients"] == ["w1", "w2"] and out["delivered_count"] == 2
    # DURABLE effect (not just the resolved list): one delivery row per recipient...
    assert count(migrated_factory, "message_deliveries") == 2
    # ...and each recipient independently pulls the body from its own inbox.
    inbox = make_inbox(migrated_factory, fake_clock)
    assert [m["body"] for m in inbox.pull(agent_id="w1")["messages"]] == ["scan"]
    assert [m["body"] for m in inbox.pull(agent_id="w2")["messages"]] == ["scan"]


def test_group_excludes_sender_even_when_eligible(migrated_factory, fake_clock, tmp_path):
    proj = mkproj(tmp_path)
    register(migrated_factory, fake_clock, "alice", capabilities=["ocr"])  # sender HAS it
    register(migrated_factory, fake_clock, "w1", capabilities=["ocr"])
    svc = make_service(migrated_factory, fake_clock)
    out = svc.create_message(
        project_root=proj,
        from_agent_id="alice",
        subject="ocr",
        body="b",
        target={"strategy": "capability", "capability": "ocr"},
    )
    assert out["recipients"] == ["w1"]  # alice excluded despite being eligible


def test_direct_to_self_delivers(migrated_factory, fake_clock, tmp_path):
    proj = mkproj(tmp_path)
    register(migrated_factory, fake_clock, "alice")
    svc = make_service(migrated_factory, fake_clock)
    out = svc.create_message(
        project_root=proj,
        from_agent_id="alice",
        subject="note",
        body="self",
        target={"strategy": "direct", "agent_id": "alice"},
    )
    assert out["recipients"] == ["alice"] and out["delivered_count"] == 1
    inbox = make_inbox(migrated_factory, fake_clock)
    assert [m["body"] for m in inbox.pull(agent_id="alice")["messages"]] == ["self"]


def test_mixed_resolves_global_union(migrated_factory, fake_clock, tmp_path):
    proj = mkproj(tmp_path)
    register(migrated_factory, fake_clock, "alice")
    register(migrated_factory, fake_clock, "v1", role="validator")
    register(migrated_factory, fake_clock, "w1", capabilities=["ocr"])
    register(migrated_factory, fake_clock, "x1")  # matches neither sub-rule
    svc = make_service(migrated_factory, fake_clock)
    out = svc.create_message(
        project_root=proj,
        from_agent_id="alice",
        subject="s",
        body="b",
        target={
            "strategy": "mixed",
            "rules": [
                {"strategy": "role", "role": "validator"},
                {"strategy": "capability", "capability": "ocr"},
            ],
        },
    )
    assert out["recipients"] == ["v1", "w1"]


def test_direct_with_fallback_rejected_for_messages(migrated_factory, fake_clock, tmp_path):
    proj = mkproj(tmp_path)
    register(migrated_factory, fake_clock, "bob")
    svc = make_service(migrated_factory, fake_clock)
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(
            project_root=proj,
            from_agent_id="alice",
            subject="s",
            body="b",
            target={"strategy": "direct_with_fallback", "agent_id": "bob", "fallback_after_seconds": 0},
        )
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert count(migrated_factory, "messages") == 0  # rejected before any write


def test_broadcast_nested_in_mixed_rejected(migrated_factory, fake_clock, tmp_path):
    proj = mkproj(tmp_path)
    register(migrated_factory, fake_clock, "alice")
    svc = make_service(migrated_factory, fake_clock)
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(
            project_root=proj,
            from_agent_id="alice",
            subject="s",
            body="b",
            target={
                "strategy": "mixed",
                "rules": [{"strategy": "role", "role": "x"}, {"strategy": "broadcast"}],
            },
        )
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# message_status: the sender's end-to-end view of each recipient's cycle
# --------------------------------------------------------------------------- #
def test_message_status_tracks_each_recipient_independently(
    migrated_factory, fake_clock, tmp_path
):
    """After a fan-out send, message_status shows the per-recipient lanes as
    they diverge: one recipient acks, the other lets its lease expire."""
    proj = mkproj(tmp_path)
    register(migrated_factory, fake_clock, "alice")
    register(migrated_factory, fake_clock, "w1", capabilities=["ocr"])
    register(migrated_factory, fake_clock, "w2", capabilities=["ocr"])
    svc = make_service(migrated_factory, fake_clock)
    out = svc.create_message(
        project_root=proj,
        from_agent_id="alice",
        subject="ocr",
        body="scan",
        target={"strategy": "capability", "capability": "ocr"},
    )
    mid = out["message_id"]
    inbox = make_inbox(migrated_factory, fake_clock)

    def by_recipient():
        status = inbox.message_status(message_id=mid)
        assert status["message_id"] == mid and status["count"] == 2
        return {d["recipient"]: d for d in status["deliveries"]}

    # Freshly sent: both queued, never claimed.
    state = by_recipient()
    assert state["w1"] == {"recipient": "w1", "status": "unread", "attempts": 0, "read_at": None}
    assert state["w2"] == {"recipient": "w2", "status": "unread", "attempts": 0, "read_at": None}

    # w1 pulls and acks; w2 pulls but goes silent.
    inbox.pull(agent_id="w1")
    inbox.ack(agent_id="w1", message_ids=[mid])
    inbox.pull(agent_id="w2")
    state = by_recipient()
    assert state["w1"]["status"] == "read" and state["w1"]["read_at"] is not None
    assert state["w2"] == {"recipient": "w2", "status": "delivered", "attempts": 1, "read_at": None}

    # w2's lease (default 300s) elapses: the sender sees it as redeliverable
    # again - NOT silently stuck in 'delivered'.
    fake_clock.set_iso("2026-06-07T01:00:00Z")
    state = by_recipient()
    assert state["w1"]["status"] == "read"  # history is unaffected by time
    assert state["w2"] == {"recipient": "w2", "status": "unread", "attempts": 1, "read_at": None}
