"""Conversation read-model (chat panel): pair filter, bodies, peers aggregate.

The dashboard chat is server-paginated newest-first: /messages gains
``peer`` (the pair's conversation, both directions), ``undelivered`` (sends
that fanned out to nobody) and ``include_body`` (full body for markdown
rendering, instead of the bounded preview); /conversations/peers is the
O(peers) aggregate behind the searchable peer picker.
"""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from okto_nexus.adapters.inbound.http.app import build_app  # noqa: E402
from okto_nexus.adapters.inbound.mcp.server import bootstrap  # noqa: E402
from okto_nexus.adapters.inbound.mcp.tools.messages import (  # noqa: E402
    build_service as build_message_service,
)

LONG_BODY = "# Title\n\n" + ("lorem ipsum " * 40) + "\n\n- a\n- b\n"


@pytest.fixture
def seeded(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    messages = build_message_service(deps)
    with deps.connection_factory.unit_of_work() as uow:
        for agent_id in ("alice", "bob", "carol"):
            deps.repos.agents.upsert(uow, agent_id=agent_id)
    root = str(tmp_path)
    # 12 alice<->bob messages (both directions), 1 alice->carol, 1 failed send.
    for i in range(6):
        messages.create_message(
            project_root=root, from_agent_id="alice", subject=f"a{i}",
            body=LONG_BODY,
            target={"strategy": "direct", "agent_id": "bob"},
        )
        messages.create_message(
            project_root=root, from_agent_id="bob", subject=f"b{i}", body="ok",
            target={"strategy": "direct", "agent_id": "alice"},
        )
    messages.create_message(
        project_root=root, from_agent_id="alice", subject="side", body="hi",
        target={"strategy": "direct", "agent_id": "carol"},
    )
    messages.create_message(
        project_root=root, from_agent_id="alice", subject="lost", body="void",
        target={"strategy": "role", "role": "nobody-has-this"},
    )
    app = build_app(deps)
    with TestClient(app, client=("127.0.0.1", 50200)) as client:
        yield client


def test_peer_filter_paginates_the_pair_newest_first(seeded):
    client = seeded
    page1 = client.get(
        "/api/v1/messages?agent=alice&peer=bob&page=1&page_size=10"
    ).json()["data"]
    assert page1["total"] == 12  # both directions, never carol nor the failure
    assert len(page1["items"]) == 10
    stamps = [m["created_at"] for m in page1["items"]]
    assert stamps == sorted(stamps, reverse=True)  # newest first

    page2 = client.get(
        "/api/v1/messages?agent=alice&peer=bob&page=2&page_size=10"
    ).json()["data"]
    assert len(page2["items"]) == 2
    # No overlap between pages (lazy "Load more" never duplicates).
    ids1 = {m["message_id"] for m in page1["items"]}
    ids2 = {m["message_id"] for m in page2["items"]}
    assert not (ids1 & ids2)

    # peer without agent is a 422 (a conversation is a pair).
    assert client.get("/api/v1/messages?peer=bob").status_code == 422


def test_include_body_returns_the_full_text(seeded):
    client = seeded
    trimmed = client.get(
        "/api/v1/messages?agent=alice&peer=bob&page_size=1"
    ).json()["data"]["items"][0]
    assert "body" not in trimmed
    assert len(trimmed["preview"]) <= 160

    full = client.get(
        "/api/v1/messages?agent=alice&peer=bob&page_size=2&include_body=true"
    ).json()["data"]["items"]
    bodies = [m["body"] for m in full]
    assert LONG_BODY in bodies  # untruncated, markdown intact


def test_undelivered_filter_is_the_failed_tab(seeded):
    client = seeded
    data = client.get(
        "/api/v1/messages?agent=alice&undelivered=true&include_body=true"
    ).json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["subject"] == "lost"
    assert data["items"][0]["deliveries"] == []


def test_conversation_peers_aggregate(seeded):
    client = seeded
    data = client.get("/api/v1/conversations/peers?agent=alice").json()["data"]
    by_peer = {p["peer"]: p for p in data["items"]}
    assert set(by_peer) == {"bob", "carol"}
    assert by_peer["bob"]["count"] == 12
    assert by_peer["carol"]["count"] == 1
    assert data["failed_count"] == 1
    # Sorted by most recent activity.
    assert data["items"] == sorted(
        data["items"], key=lambda p: p["last_at"], reverse=True
    )


def test_from_to_agent_filters_are_independent_and_combinable(seeded):
    """Directional DE/PARA filters: from_agent (sender), to_agent (recipient),
    each independent of the OR-combined ``agent`` and AND-combinable together."""
    client = seeded

    # from_agent: everything alice SENT (6 -> bob, 1 -> carol, 1 failed = 8).
    sent = client.get("/api/v1/messages?from_agent=alice").json()["data"]
    assert sent["total"] == 8
    assert {m["from_agent_id"] for m in sent["items"]} == {"alice"}

    # to_agent: everything bob RECEIVED (only the 6 from alice).
    recv = client.get("/api/v1/messages?to_agent=bob").json()["data"]
    assert recv["total"] == 6
    assert all(
        any(d["recipient_agent_id"] == "bob" for d in m["deliveries"])
        for m in recv["items"]
    )

    # Combined (AND): alice -> bob only (the 6-message side of the pair).
    pair = client.get(
        "/api/v1/messages?from_agent=alice&to_agent=bob"
    ).json()["data"]
    assert pair["total"] == 6
    assert {m["from_agent_id"] for m in pair["items"]} == {"alice"}

    # to_agent=carol resolves the single alice->carol side message.
    carol = client.get("/api/v1/messages?to_agent=carol").json()["data"]
    assert carol["total"] == 1
    assert carol["items"][0]["subject"] == "side"
