"""Ephemeral poll-token control/data-plane contract tests."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from okto_nexus.adapters.inbound.http.app import build_app  # noqa: E402
from okto_nexus.adapters.inbound.mcp.server import bootstrap  # noqa: E402
from okto_nexus.adapters.inbound.mcp.tools.poll_tokens import (  # noqa: E402
    build_service as build_poll_token_service,
)
from okto_nexus.domain.approvals import OPERATOR_AGENT_ID  # noqa: E402
from okto_nexus.domain.poll_tokens import hash_poll_token  # noqa: E402


def _seed_session(deps, *, workspace_id: str = "w" * 64) -> tuple[str, str]:
    session_id = "ses_ept"
    session_secret = "secret-ept"
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id=workspace_id)
        deps.repos.sessions.create(
            uow,
            session_id=session_id,
            agent_id=OPERATOR_AGENT_ID,
            workspace_id=workspace_id,
            status="active",
            session_secret=session_secret,
        )
    return session_id, session_secret


def _issue_token(deps, *, pre_event: bool = False):
    workspace_id = "w" * 64
    session_id, session_secret = _seed_session(deps, workspace_id=workspace_id)
    if pre_event:
        with deps.connection_factory.unit_of_work() as uow:
            deps.event_emitter.emit(
                uow,
                workspace_id=workspace_id,
                stream="workspace",
                type="before.issue",
                payload={"secret": "old"},
            )
    service = build_poll_token_service(deps)
    issued = service.issue(
        actor_agent_id=OPERATOR_AGENT_ID,
        session_id=session_id,
        session_secret=session_secret,
    )
    token = service.authenticate(issued["token"])
    assert token is not None
    return service, issued, token, workspace_id


def test_poll_token_issue_stores_hash_only_and_returns_once(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    _service, issued, token, _workspace_id = _issue_token(deps)

    assert issued["token"].startswith("nxsept_")
    assert issued["token_id"] == token.token_id
    assert issued["base_url"] == "/api/v1"
    assert issued["scope"]["mutations"] is False

    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute(
            "SELECT token_hash FROM ephemeral_poll_tokens WHERE token_id = ?",
            (issued["token_id"],),
        ).fetchone()
    assert row["token_hash"] == hash_poll_token(issued["token"])
    assert row["token_hash"] != issued["token"]


def test_ept_events_are_forward_only_and_summary_projected(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    _service, issued, token, workspace_id = _issue_token(deps, pre_event=True)
    assert token.issue_cursor == 1

    app = build_app(deps)
    headers = {"authorization": f"Bearer {issued['token']}"}
    with TestClient(app) as client:
        too_old = client.get("/api/v1/events?cursor=0", headers=headers)
        assert too_old.status_code == 422
        assert too_old.json()["error"]["code"] == "VALIDATION_ERROR"

        with deps.connection_factory.unit_of_work() as uow:
            event_id = deps.event_emitter.emit(
                uow,
                workspace_id=workspace_id,
                stream="workspace",
                type="message.created",
                actor_agent_id=OPERATOR_AGENT_ID,
                payload={
                    "message_id": "msg_ept",
                    "subject": "do not leak in summary",
                },
            )

        cursor = client.get("/api/v1/events/cursor", headers=headers).json()["data"]
        assert cursor["cursor"] >= token.issue_cursor

        page = client.get(
            f"/api/v1/events?cursor={token.issue_cursor}&filters=type:message.created",
            headers=headers,
        )
        assert page.status_code == 200
        data = page.json()["data"]
        assert [item["event_id"] for item in data["events"]] == [event_id]
        assert "payload" not in data["events"][0]
        assert data["events"][0]["type"] == "message.created"


def test_ept_inbox_count_and_peek_are_envelope_only(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    _service, issued, _token, workspace_id = _issue_token(deps)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.messages.create(
            uow,
            message_id="msg_pending",
            workspace_id=workspace_id,
            from_agent_id="sender",
            subject="pending",
            body="secret body must not be returned by EPT peek",
        )
        deps.repos.deliveries.create(
            uow,
            delivery_id="del_pending",
            message_id="msg_pending",
            recipient_agent_id=OPERATOR_AGENT_ID,
            status="unread",
        )

    app = build_app(deps)
    headers = {"authorization": f"Bearer {issued['token']}"}
    with TestClient(app) as client:
        count = client.get("/api/v1/inbox/count", headers=headers)
        assert count.status_code == 200
        assert count.json()["data"]["unread"] == 1
        assert "handoffs_pending" in count.json()["data"]

        peek = client.get("/api/v1/inbox/peek", headers=headers)
        assert peek.status_code == 200
        item = peek.json()["data"]["messages"][0]
        assert item["message_id"] == "msg_pending"
        assert "body" not in item
        assert "body_preview" not in item
        assert item["body_bytes"] > 0


def test_ept_is_rejected_on_mutating_routes_even_with_loopback_trust(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    _service, issued, _token, _workspace_id = _issue_token(deps)
    app = build_app(deps)
    headers = {"authorization": f"Bearer {issued['token']}"}

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.post("/api/v1/admin/reset", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_FAILED"
