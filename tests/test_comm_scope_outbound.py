"""Outbound communication-scope enforcement on message sends (F1 / C4).

The sender's operator-set ``comm_scope.outbound`` tag selector filters WHO a
message may reach, on top of target resolution:

* a *directed* send to an agent outside the scope is ``PERMISSION_DENIED``
  with an OPAQUE message (AC6) - the selector and the target's tags never
  leak, and nothing persists (no message row, no delivery, no event);
* a *group* send (role / capability / broadcast / mixed) silently loses
  nobody: out-of-scope agents are dropped from the fan-out, counted in
  ``filtered_by_audience`` and surfaced in an explicit ``warning`` (AC7);
* a sender WITHOUT a scope behaves exactly as before (default-allow), and an
  unknown direct target stays ``NOT_FOUND`` regardless of the scope.

Exercised through the real application service over the real SQLite adapters
(``bootstrap`` deps), mirroring ``test_permissions.py``.
"""

from __future__ import annotations

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.inbound.mcp.tools.messages import (
    build_service as build_message_service,
)
from okto_nexus.domain.base import new_id
from okto_nexus.domain.ids import resolve_realpath, resolve_workspace_id
from okto_nexus.errors import ErrorCode, OktoNexusError

SCOPE_CORE = {"outbound": {"team": ["core"]}}


@pytest.fixture
def deps(tmp_path):
    return bootstrap({}, ["--home", str(tmp_path / "home")])


def _register(deps, agent_id: str, *, role=None, tags=None, comm_scope=None):
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id=agent_id, role=role)
        if tags is not None:
            deps.repos.agents.set_tags(uow, agent_id=agent_id, tags=tags)
        if comm_scope is not None:
            deps.repos.agents.set_comm_scope(
                uow, agent_id=agent_id, comm_scope=comm_scope
            )


def _open_session(deps, agent_id: str, project_root: str) -> None:
    """Give the agent a FRESH active session so broadcasts consider it present."""
    ws = resolve_workspace_id(project_root)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(
            uow,
            workspace_id=ws,
            root_realpath=resolve_realpath(project_root),
            last_seen_at=deps.clock.now_iso(),
        )
        deps.repos.sessions.create(
            uow,
            session_id=new_id("ses"),
            agent_id=agent_id,
            workspace_id=ws,
            status="active",
        )


def _count(deps, table: str) -> int:
    conn = deps.connection_factory.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# AC6 - directed sends
# --------------------------------------------------------------------------- #
def test_direct_within_outbound_scope_delivers(deps, tmp_path):
    service = build_message_service(deps)
    _register(deps, "shy", comm_scope=SCOPE_CORE)
    _register(deps, "bob", tags={"team": ["core"]})

    out = service.create_message(
        project_root=str(tmp_path),
        from_agent_id="shy",
        subject="s",
        body="b",
        target={"strategy": "direct", "agent_id": "bob"},
    )
    assert out["recipients"] == ["bob"]
    assert out["delivered_count"] == 1
    assert "filtered_by_audience" not in out
    assert "warning" not in out


def test_direct_blocked_by_outbound_scope_is_opaque_permission_denied(deps, tmp_path):
    service = build_message_service(deps)
    _register(deps, "shy", comm_scope=SCOPE_CORE)
    _register(deps, "eve", tags={"team": ["research"]})

    with pytest.raises(OktoNexusError) as exc:
        service.create_message(
            project_root=str(tmp_path),
            from_agent_id="shy",
            subject="s",
            body="b",
            target={"strategy": "direct", "agent_id": "eve"},
        )
    assert exc.value.code == ErrorCode.PERMISSION_DENIED
    # OPAQUE (AC6): the denial names the mechanism, never the selector's
    # keys/values nor the target's tags.
    assert exc.value.details == {"required_permission": "comm_scope.outbound"}
    text = exc.value.message
    for secret in ("team", "core", "research"):
        assert secret not in text
    # Fail-closed rollback: nothing persisted.
    assert _count(deps, "messages") == 0
    assert _count(deps, "message_deliveries") == 0
    assert _count(deps, "events") == 0


def test_direct_blocked_when_target_has_no_tags(deps, tmp_path):
    # A tagless agent can never satisfy a require-selector (absent key -> no
    # match) - the fail-closed default.
    service = build_message_service(deps)
    _register(deps, "shy", comm_scope=SCOPE_CORE)
    _register(deps, "untagged")

    with pytest.raises(OktoNexusError) as exc:
        service.create_message(
            project_root=str(tmp_path),
            from_agent_id="shy",
            subject="s",
            body="b",
            target={"strategy": "direct", "agent_id": "untagged"},
        )
    assert exc.value.code == ErrorCode.PERMISSION_DENIED


def test_unknown_direct_target_stays_not_found_with_scope(deps, tmp_path):
    service = build_message_service(deps)
    _register(deps, "shy", comm_scope=SCOPE_CORE)

    with pytest.raises(OktoNexusError) as exc:
        service.create_message(
            project_root=str(tmp_path),
            from_agent_id="shy",
            subject="s",
            body="b",
            target={"strategy": "direct", "agent_id": "ghost"},
        )
    assert exc.value.code == ErrorCode.NOT_FOUND


# --------------------------------------------------------------------------- #
# AC7 - group fan-outs filter, count and warn
# --------------------------------------------------------------------------- #
def test_role_fanout_filters_by_outbound_scope_with_warning(deps, tmp_path):
    service = build_message_service(deps)
    _register(deps, "shy", comm_scope=SCOPE_CORE)
    _register(deps, "bob", role="worker", tags={"team": ["core"]})
    _register(deps, "eve", role="worker", tags={"team": ["research"]})

    out = service.create_message(
        project_root=str(tmp_path),
        from_agent_id="shy",
        subject="s",
        body="b",
        target={"strategy": "role", "role": "worker"},
    )
    assert out["recipients"] == ["bob"]
    assert out["delivered_count"] == 1
    assert out["filtered_by_audience"] == 1
    assert "comm_scope.outbound" in out["warning"]
    # Exactly one delivery row - the filtered agent got nothing.
    assert _count(deps, "message_deliveries") == 1


def test_role_fanout_all_filtered_delivers_to_nobody(deps, tmp_path):
    service = build_message_service(deps)
    _register(deps, "shy", comm_scope=SCOPE_CORE)
    _register(deps, "eve", role="worker", tags={"team": ["research"]})

    out = service.create_message(
        project_root=str(tmp_path),
        from_agent_id="shy",
        subject="s",
        body="b",
        target={"strategy": "role", "role": "worker"},
    )
    assert out["recipients"] == []
    assert out["delivered_count"] == 0
    assert out["filtered_by_audience"] == 1
    assert "delivered to nobody" in out["warning"]
    # The message itself persists (a zero-recipient group send is legal).
    assert _count(deps, "messages") == 1
    assert _count(deps, "message_deliveries") == 0


def test_mixed_target_drops_blocked_direct_rule_and_warns(deps, tmp_path):
    # ``mixed`` is a GROUP strategy: a nested direct rule pointing outside the
    # scope is dropped (counted + warned), never an opaque hard denial.
    service = build_message_service(deps)
    _register(deps, "shy", comm_scope=SCOPE_CORE)
    _register(deps, "bob", role="worker", tags={"team": ["core"]})
    _register(deps, "eve", tags={"team": ["research"]})

    out = service.create_message(
        project_root=str(tmp_path),
        from_agent_id="shy",
        subject="s",
        body="b",
        target={
            "strategy": "mixed",
            "rules": [
                {"strategy": "direct", "agent_id": "eve"},
                {"strategy": "role", "role": "worker"},
            ],
        },
    )
    assert out["recipients"] == ["bob"]
    assert out["filtered_by_audience"] == 1


def test_broadcast_filters_present_agents_by_outbound_scope(deps, tmp_path):
    service = build_message_service(deps)
    root = str(tmp_path)
    _register(deps, "shy", comm_scope=SCOPE_CORE)
    _register(deps, "bob", tags={"team": ["core"]})
    _register(deps, "eve", tags={"team": ["research"]})
    _open_session(deps, "bob", root)
    _open_session(deps, "eve", root)

    out = service.create_message(
        project_root=root, from_agent_id="shy", subject="s", body="b"
    )
    assert out["recipients"] == ["bob"]
    assert out["filtered_by_audience"] == 1
    assert "comm_scope.outbound" in out["warning"]


# --------------------------------------------------------------------------- #
# No scope -> unchanged behaviour
# --------------------------------------------------------------------------- #
def test_sender_without_scope_reaches_everyone(deps, tmp_path):
    service = build_message_service(deps)
    _register(deps, "open")
    _register(deps, "bob", role="worker", tags={"team": ["core"]})
    _register(deps, "eve", role="worker", tags={"team": ["research"]})

    out = service.create_message(
        project_root=str(tmp_path),
        from_agent_id="open",
        subject="s",
        body="b",
        target={"strategy": "role", "role": "worker"},
    )
    assert out["recipients"] == ["bob", "eve"]
    assert "filtered_by_audience" not in out
    assert "warning" not in out


def test_scope_reset_to_none_restores_default_allow(deps, tmp_path):
    service = build_message_service(deps)
    _register(deps, "shy", comm_scope=SCOPE_CORE)
    _register(deps, "eve", tags={"team": ["research"]})

    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.set_comm_scope(uow, agent_id="shy", comm_scope=None)

    out = service.create_message(
        project_root=str(tmp_path),
        from_agent_id="shy",
        subject="s",
        body="b",
        target={"strategy": "direct", "agent_id": "eve"},
    )
    assert out["recipients"] == ["eve"]
