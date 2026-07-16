"""Delivery/read receipts (surface revision 8).

``inbox_pull`` emits ``message.delivered`` and ``inbox_ack`` emits
``message.read`` - sender-visible only (``eligible`` + direct target at the
sender), atomic with the lane transition, mirroring at-least-once truthfully
(a redelivery emits again; an idempotent re-ack emits nothing).
"""

from __future__ import annotations

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.inbound.mcp.tools.events import (
    build_service as build_event_service,
)
from okto_nexus.adapters.inbound.mcp.tools.inbox import (
    build_service as build_inbox_service,
)
from okto_nexus.adapters.inbound.mcp.tools.messages import (
    build_service as build_message_service,
)


@pytest.fixture
def bus(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    messages = build_message_service(deps)
    inbox = build_inbox_service(deps)
    events = build_event_service(deps)
    with deps.connection_factory.unit_of_work() as uow:
        for agent_id in ("sender", "receiver", "bystander"):
            deps.repos.agents.upsert(uow, agent_id=agent_id)
    root = str(tmp_path)
    return deps, messages, inbox, events, root


def _events_for(events, root, agent_id, type_):
    page = events.event_get(
        project_root=root,
        agent_id=agent_id,
        stream="workspace",
        filters={"type": type_},
    )
    return page["events"]


def test_pull_emits_sender_only_delivered_receipt(bus):
    _, messages, inbox, events, root = bus
    sent = messages.create_message(
        project_root=root,
        from_agent_id="sender",
        subject="s",
        body="b",
        target={"strategy": "direct", "agent_id": "receiver"},
    )

    # No receipt before the pull.
    assert _events_for(events, root, "sender", "message.delivered") == []

    inbox.pull(agent_id="receiver")

    receipts = _events_for(events, root, "sender", "message.delivered")
    assert len(receipts) == 1
    payload = receipts[0]["payload"]
    assert payload["message_id"] == sent["message_id"]
    assert payload["recipient_agent_id"] == "receiver"
    assert payload["from_agent_id"] == "sender"
    # Sender-only visibility: a bystander never sees the receipt.
    assert _events_for(events, root, "bystander", "message.delivered") == []


def test_ack_emits_read_receipt_once_and_idempotently(bus):
    _, messages, inbox, events, root = bus
    sent = messages.create_message(
        project_root=root,
        from_agent_id="sender",
        subject="s",
        body="b",
        target={"strategy": "direct", "agent_id": "receiver"},
    )
    inbox.pull(agent_id="receiver")

    acked = inbox.ack(agent_id="receiver", message_ids=[sent["message_id"]])
    assert acked == {
        "acknowledged": 1,
        "read_message_ids": [sent["message_id"]],
    }
    receipts = _events_for(events, root, "sender", "message.read")
    assert len(receipts) == 1
    assert receipts[0]["payload"]["message_id"] == sent["message_id"]
    assert _events_for(events, root, "bystander", "message.read") == []

    # Idempotent re-ack: no transition -> NO second receipt.
    again = inbox.ack(agent_id="receiver", message_ids=[sent["message_id"]])
    assert again == {"acknowledged": 0, "read_message_ids": []}
    assert len(_events_for(events, root, "sender", "message.read")) == 1


def test_sender_can_await_read_receipt_with_event_wait(bus):
    _, messages, inbox, events, root = bus
    sent = messages.create_message(
        project_root=root,
        from_agent_id="sender",
        subject="s",
        body="b",
        target={"strategy": "direct", "agent_id": "receiver"},
    )
    inbox.pull(agent_id="receiver")
    inbox.ack(agent_id="receiver", message_ids=[sent["message_id"]])

    # The documented push pattern: targeted wait on the receipt type.
    page = events.event_wait(
        project_root=root,
        agent_id="sender",
        stream="workspace",
        filters={"type": "message.read"},
        timeout_seconds=0,
    )
    assert [e["payload"]["message_id"] for e in page["events"]] == [
        sent["message_id"]
    ]


def test_message_status_and_receipts_agree(bus):
    _, messages, inbox, events, root = bus
    sent = messages.create_message(
        project_root=root,
        from_agent_id="sender",
        subject="s",
        body="b",
        target={"strategy": "direct", "agent_id": "receiver"},
    )
    inbox.pull(agent_id="receiver")
    inbox.ack(agent_id="receiver", message_ids=[sent["message_id"]])

    status = inbox.message_status(message_id=sent["message_id"])
    assert status["deliveries"][0]["status"] == "read"
    assert status["deliveries"][0]["read_at"] is not None
    assert len(_events_for(events, root, "sender", "message.read")) == 1


def test_event_cursor_anchors_a_monitor_at_now(bus):
    deps, messages, inbox, events, root = bus
    # History exists BEFORE the monitor starts...
    messages.create_message(
        project_root=root, from_agent_id="sender", subject="old", body="b",
        target={"strategy": "direct", "agent_id": "receiver"},
    )
    anchor = events.latest_cursor(
        project_root=root, agent_id="bystander", stream="workspace"
    )
    assert anchor > 0

    # ...a monitor anchored at NOW sees only what happens next.
    sent = messages.create_message(
        project_root=root, from_agent_id="sender", subject="new", body="b",
        target={"strategy": "direct", "agent_id": "receiver"},
    )
    page = events.event_get(
        project_root=root, agent_id="sender", stream="workspace",
        cursor=anchor, filters={"type": "message.created"},
    )
    assert [e["payload"]["message_id"] for e in page["events"]] == [
        sent["message_id"]
    ]

    # The anchor honours the events.read permission gate.
    from okto_nexus.errors import ErrorCode, OktoNexusError

    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id="blind")
        deps.repos.agents.set_permissions(
            uow,
            agent_id="blind",
            permissions={"events": {"read": False}},
            preset_id=None,
        )
    with pytest.raises(OktoNexusError) as exc:
        events.latest_cursor(
            project_root=root, agent_id="blind", stream="workspace"
        )
    assert exc.value.code == ErrorCode.PERMISSION_DENIED


# --------------------------------------------------------------------------- #
# Inbox read receipts (surface revision 10, opt-out via inbox_read_receipts)
# --------------------------------------------------------------------------- #
def _send(messages, root, sender, recipient, subject="s", body="b"):
    return messages.create_message(
        project_root=root, from_agent_id=sender, subject=subject, body=body,
        target={"strategy": "direct", "agent_id": recipient},
    )


def test_ack_lands_grouped_receipt_in_sender_inbox(bus):
    _, messages, inbox, _, root = bus
    m1 = _send(messages, root, "sender", "receiver", subject="first")
    m2 = _send(messages, root, "sender", "receiver", subject="second")
    inbox.pull(agent_id="receiver")
    inbox.ack(
        agent_id="receiver", message_ids=[m1["message_id"], m2["message_id"]]
    )

    # ONE grouped notification, kind message.read_receipt, both ids inside.
    assert inbox.count(agent_id="sender")["unread"] == 1
    pulled = inbox.pull(agent_id="sender")["messages"]
    assert len(pulled) == 1
    import json as _json

    body = _json.loads(pulled[0]["body"])
    assert body["kind"] == "message.read_receipt"
    assert body["read_by"] == "receiver"
    assert sorted(body["message_ids"]) == sorted(
        [m1["message_id"], m2["message_id"]]
    )
    assert pulled[0]["from_agent_id"] == "receiver"


def test_receipts_never_generate_receipts(bus):
    _, messages, inbox, _, root = bus
    m = _send(messages, root, "sender", "receiver")
    inbox.pull(agent_id="receiver")
    inbox.ack(agent_id="receiver", message_ids=[m["message_id"]])

    # The sender acks the RECEIPT: terminal - no ping-pong back to receiver.
    receipt = inbox.pull(agent_id="sender")["messages"][0]
    inbox.ack(agent_id="sender", message_ids=[receipt["message_id"]])
    assert inbox.count(agent_id="receiver")["unread"] == 0
    # And no new notification for the sender either.
    assert inbox.count(agent_id="sender")["unread"] == 0


def test_self_send_produces_no_receipt(bus):
    _, messages, inbox, _, root = bus
    m = _send(messages, root, "sender", "sender")
    inbox.pull(agent_id="sender")
    inbox.ack(agent_id="sender", message_ids=[m["message_id"]])
    assert inbox.count(agent_id="sender")["unread"] == 0


def test_opt_out_setting_disables_inbox_receipts(tmp_path):
    deps = bootstrap(
        {}, ["--home", str(tmp_path / "home"), "--inbox-read-receipts", "false"]
    )
    messages = build_message_service(deps)
    inbox = build_inbox_service(deps)
    with deps.connection_factory.unit_of_work() as uow:
        for agent_id in ("sender", "receiver"):
            deps.repos.agents.upsert(uow, agent_id=agent_id)
    root = str(tmp_path)
    m = _send(messages, root, "sender", "receiver")
    inbox.pull(agent_id="receiver")
    acked = inbox.ack(agent_id="receiver", message_ids=[m["message_id"]])
    assert acked["acknowledged"] == 1
    # Opted out: nothing lands in the sender's inbox (the message.read EVENT
    # still fires - the event channel is not part of the opt-out).
    assert inbox.count(agent_id="sender")["unread"] == 0
