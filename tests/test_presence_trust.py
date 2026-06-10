"""Behavioural tests for M6 (presence) and M10 (dual-agent trust).

M6 - three presence notions reconciled into ONE predicate:

* ``IdentityService.list_present`` = active sessions with a heartbeat within
  ``presence_ttl_seconds`` (the SAME predicate the broadcast audience uses);
* a broadcast skips heartbeat-stale agents but the exclusion is EXPLICIT
  (``excluded_stale`` + warning) - an alive-but-busy agent is never dropped
  silently, and a dead session that never called ``session_close`` stops
  receiving broadcasts forever;
* ``session_open``/``session_heartbeat`` opportunistically reap sessions dead
  past ``session_reap_seconds`` (status ``closed``, ``session.reaped`` event).

M10 - confused-deputy mitigation for the cooperative model:

* migration 007 adds ``sessions.session_secret``; ``session_open`` generates,
  persists and returns it (and no read surface leaks it);
* ``NexusConfig.trust_mode`` ('open' default | 'strict') parses fail-closed;
* in strict mode the sensitive verbs (message_create, handoff_claim/complete/
  reject, inbox_pull/ack/extend) require a matching session_id+session_secret;
  in open mode a SUPPLIED credential is still validated (mismatch fails);
* the shared.md renderer redacts the target of non-public handoffs.

Exercised over the REAL SQLite adapters (``migrated_factory``), like the
sibling identity/messages suites.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.mcp.tools.handoff import register as register_handoff
from okto_nexus.adapters.inbound.mcp.tools.inbox import register as register_inbox
from okto_nexus.adapters.outbound.sharedmd.renderer import FileSystemSharedMdRenderer
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
from okto_nexus.application.identity import IdentityService
from okto_nexus.application.messages import MessageService
from okto_nexus.application.ports import Repos
from okto_nexus.application.shared_md import SharedMdView
from okto_nexus.config import (
    DEFAULT_PRESENCE_TTL_SECONDS,
    DEFAULT_SESSION_REAP_SECONDS,
    NexusConfig,
    load_config,
)
from okto_nexus.domain.base import iso_to_epoch
from okto_nexus.domain.models import Handoff
from okto_nexus.errors import ErrorCode, OktoNexusError


# --------------------------------------------------------------------------- #
# Test doubles & helpers
# --------------------------------------------------------------------------- #
class StubClock:
    """Deterministic, advanceable clock implementing the Clock port.

    Emits the CANONICAL fixed-width UTC form (utc_now_iso's shape) so the
    lease-write boundary (``iso_plus``) accepts it - the handoff claim writes
    a lease timestamp.
    """

    def __init__(self, iso: str = "2026-06-07T00:00:00.000000Z") -> None:
        self._iso = iso

    def now_iso(self) -> str:
        return self._iso

    def now_epoch(self) -> float:
        return iso_to_epoch(self._iso)

    def advance_seconds(self, seconds: float) -> None:
        dt = datetime.fromtimestamp(self.now_epoch() + seconds, tz=timezone.utc)
        self._iso = dt.isoformat(timespec="microseconds").replace("+00:00", "Z")


class FakeEmitter:
    """Fake EventEmitter recording every emission."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self._next = 0

    def emit(self, uow, **kwargs) -> int:
        self._next += 1
        self.events.append({"event_id": self._next, **kwargs})
        return self._next


class FakeServer:
    """Captures FastMCP-style ``@server.tool()`` registrations by name."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def make_identity(factory, config, clock, emitter=None) -> IdentityService:
    return IdentityService(
        connection_factory=factory,
        workspaces=SqliteWorkspaceRepo(clock),
        agents=SqliteAgentRepo(clock),
        sessions=SqliteSessionRepo(clock),
        clock=clock,
        config=config,
        event_emitter=emitter,
    )


def make_messages(factory, config, clock, **overrides) -> MessageService:
    kwargs = dict(
        connection_factory=factory,
        channels=SqliteChannelRepo(clock),
        messages=SqliteMessageRepo(clock),
        workspaces=SqliteWorkspaceRepo(clock),
        agents=SqliteAgentRepo(clock),
        sessions=SqliteSessionRepo(clock),
        deliveries=SqliteMessageDeliveryRepo(clock),
        event_emitter=FakeEmitter(),
        clock=clock,
        max_inline_bytes=config.max_inline_bytes,
        presence_ttl_seconds=config.presence_ttl_seconds,
        trust_mode=config.trust_mode,
    )
    kwargs.update(overrides)
    return MessageService(**kwargs)


def mkproj(tmp_path, name="P"):
    p = tmp_path / name
    p.mkdir()
    return str(p)


def seed(identity, project_root, *agents):
    """Resolve the workspace and register the given agents."""
    ws = identity.workspace_resolve(project_root=project_root)["workspace_id"]
    for agent in agents:
        identity.agent_register(agent_id=agent)
    return ws


def count(factory, table: str, where: str = "", params: tuple = ()) -> int:
    conn = factory.get_connection()
    try:
        sql = f"SELECT COUNT(*) FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


# =========================================================================== #
# M6 (1): list_present - ONE presence notion
# =========================================================================== #
def test_list_present_includes_only_fresh_active_sessions(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_identity(migrated_factory, tmp_config, clock)
    ws = seed(svc, mkproj(tmp_path), "alice", "bob", "carol")
    s_alice = svc.session_open(agent_id="alice", workspace_id=ws)["session_id"]
    s_bob = svc.session_open(agent_id="bob", workspace_id=ws)["session_id"]
    s_carol = svc.session_open(agent_id="carol", workspace_id=ws)["session_id"]
    svc.session_close(session_id=s_carol)  # properly closed -> never present

    # Beyond the presence TTL: only the session that heartbeats stays present.
    clock.advance_seconds(tmp_config.presence_ttl_seconds + 1)
    svc.session_heartbeat(session_id=s_bob)

    present = svc.list_present(workspace_id=ws)
    assert [(p["agent_id"], p["session_id"]) for p in present] == [("bob", s_bob)]
    # alice's stored status is STILL 'active' (no reap yet) - presence is the
    # stricter, heartbeat-based notion, not the stored column.
    assert svc.get_session(session_id=s_alice)["status"] in ("active", "stale")
    # No read surface leaks the session secret.
    assert all("session_secret" not in p for p in present)


def test_list_present_requires_workspace(migrated_factory, tmp_config):
    svc = make_identity(migrated_factory, tmp_config, StubClock())
    with pytest.raises(OktoNexusError) as ei:
        svc.list_present(workspace_id=None)
    assert ei.value.code == ErrorCode.WORKSPACE_REQUIRED.value


# =========================================================================== #
# M6 (2): broadcast uses presence; exclusion is EXPLICIT
# =========================================================================== #
def test_broadcast_skips_stale_agent_and_reports_excluded_stale(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    identity = make_identity(migrated_factory, tmp_config, clock)
    proj = mkproj(tmp_path)
    ws = seed(identity, proj, "alice", "bob", "carol")
    identity.session_open(agent_id="alice", workspace_id=ws)
    s_bob = identity.session_open(agent_id="bob", workspace_id=ws)["session_id"]
    identity.session_open(agent_id="carol", workspace_id=ws)

    clock.advance_seconds(tmp_config.presence_ttl_seconds + 1)
    identity.session_heartbeat(session_id=s_bob)  # bob is alive; carol is not

    svc = make_messages(migrated_factory, tmp_config, clock)
    out = svc.create_message(
        project_root=proj, from_agent_id="alice", subject="hi", body="all hands"
    )
    # bob (fresh) receives; carol (stale active session) is excluded EXPLICITLY;
    # alice is the sender (never in excluded_stale, excluded by design).
    assert out["recipients"] == ["bob"]
    assert out["excluded_stale"] == ["carol"]
    assert "warning" in out
    assert "carol" in out["warning"]
    assert str(tmp_config.presence_ttl_seconds) in out["warning"]
    # The exclusion is real: no delivery row accumulates for carol's inbox.
    assert count(
        migrated_factory, "message_deliveries", "recipient_agent_id = ?", ("carol",)
    ) == 0
    assert count(
        migrated_factory, "message_deliveries", "recipient_agent_id = ?", ("bob",)
    ) == 1


def test_broadcast_to_all_stale_audience_is_explicit_not_silent(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    identity = make_identity(migrated_factory, tmp_config, clock)
    proj = mkproj(tmp_path)
    ws = seed(identity, proj, "alice", "carol")
    identity.session_open(agent_id="alice", workspace_id=ws)
    identity.session_open(agent_id="carol", workspace_id=ws)
    clock.advance_seconds(tmp_config.presence_ttl_seconds + 1)

    svc = make_messages(migrated_factory, tmp_config, clock)
    out = svc.create_message(
        project_root=proj,
        from_agent_id="alice",
        subject="hi",
        body="anyone?",
        target={"strategy": "broadcast"},
    )
    assert out["recipients"] == [] and out["delivered_count"] == 0
    assert out["excluded_stale"] == ["carol"]
    # Both halves of the warning: zero matches AND the stale exclusion.
    assert "nobody" in out["warning"]
    assert "carol" in out["warning"]


def test_broadcast_fresh_audience_has_no_excluded_stale_key(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    identity = make_identity(migrated_factory, tmp_config, clock)
    proj = mkproj(tmp_path)
    ws = seed(identity, proj, "alice", "bob")
    identity.session_open(agent_id="alice", workspace_id=ws)
    identity.session_open(agent_id="bob", workspace_id=ws)

    svc = make_messages(migrated_factory, tmp_config, clock)
    out = svc.create_message(
        project_root=proj, from_agent_id="alice", subject="hi", body="hello"
    )
    assert out["recipients"] == ["bob"]
    assert "excluded_stale" not in out
    assert "warning" not in out


def test_dead_session_without_close_stops_accumulating_unread(
    migrated_factory, tmp_config, tmp_path
):
    """THE M6 regression: a crashed agent (no session_close) used to receive
    every broadcast FOREVER; with presence-based audience its unread stops
    growing once the heartbeat goes stale."""
    clock = StubClock()
    identity = make_identity(migrated_factory, tmp_config, clock)
    proj = mkproj(tmp_path)
    ws = seed(identity, proj, "alice", "bob", "ghost")
    identity.session_open(agent_id="alice", workspace_id=ws)
    s_bob = identity.session_open(agent_id="bob", workspace_id=ws)["session_id"]
    identity.session_open(agent_id="ghost", workspace_id=ws)  # then it crashes

    svc = make_messages(migrated_factory, tmp_config, clock)
    svc.create_message(project_root=proj, from_agent_id="alice", subject="1", body="x")
    ghost_deliveries = count(
        migrated_factory, "message_deliveries", "recipient_agent_id = ?", ("ghost",)
    )
    assert ghost_deliveries == 1  # still fresh: it legitimately received one

    clock.advance_seconds(tmp_config.presence_ttl_seconds + 1)
    identity.session_heartbeat(session_id=s_bob)
    for i in range(3):
        svc.create_message(
            project_root=proj, from_agent_id="alice", subject=f"n{i}", body="x"
        )
    # ghost's backlog did NOT grow; bob kept receiving.
    assert count(
        migrated_factory, "message_deliveries", "recipient_agent_id = ?", ("ghost",)
    ) == 1
    assert count(
        migrated_factory, "message_deliveries", "recipient_agent_id = ?", ("bob",)
    ) == 4


# =========================================================================== #
# M6 (3): opportunistic reaper on session_heartbeat / session_open
# =========================================================================== #
def test_heartbeat_reaps_sessions_dead_past_reap_window(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    emitter = FakeEmitter()
    svc = make_identity(migrated_factory, tmp_config, clock, emitter=emitter)
    ws = seed(svc, mkproj(tmp_path), "alice", "ghost")
    s_dead = svc.session_open(agent_id="ghost", workspace_id=ws)["session_id"]
    s_live = svc.session_open(agent_id="alice", workspace_id=ws)["session_id"]

    clock.advance_seconds(tmp_config.session_reap_seconds + 1)
    svc.session_heartbeat(session_id=s_live)

    dead = svc.get_session(session_id=s_dead)
    assert dead["status"] == "closed"
    # The freshly heartbeated session is never reaped.
    assert svc.get_session(session_id=s_live)["status"] == "active"
    reaped = [e for e in emitter.events if e["type"] == "session.reaped"]
    assert len(reaped) == 1
    assert reaped[0]["payload"]["session_id"] == s_dead
    assert reaped[0]["payload"]["reason"] == "stale"


def test_session_open_reaps_dead_sessions_of_the_workspace(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_identity(migrated_factory, tmp_config, clock)
    ws = seed(svc, mkproj(tmp_path), "alice", "ghost")
    s_dead = svc.session_open(agent_id="ghost", workspace_id=ws)["session_id"]

    clock.advance_seconds(tmp_config.session_reap_seconds + 1)
    opened = svc.session_open(agent_id="alice", workspace_id=ws)

    assert svc.get_session(session_id=s_dead)["status"] == "closed"
    assert svc.get_session(session_id=opened["session_id"])["status"] == "active"


def test_reaper_leaves_recent_sessions_alone(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_identity(migrated_factory, tmp_config, clock)
    ws = seed(svc, mkproj(tmp_path), "alice", "bob")
    s_idle = svc.session_open(agent_id="bob", workspace_id=ws)["session_id"]
    s_live = svc.session_open(agent_id="alice", workspace_id=ws)["session_id"]

    # Stale (beyond presence TTL) but NOT dead (within the reap window).
    clock.advance_seconds(tmp_config.presence_ttl_seconds + 1)
    svc.session_heartbeat(session_id=s_live)
    assert svc.get_session(session_id=s_idle)["status"] == "stale"  # NOT closed
    assert count(migrated_factory, "sessions", "status = 'closed'") == 0


# =========================================================================== #
# M10 (1): migration 007 + session_open returns a persisted secret
# =========================================================================== #
def test_migration_007_adds_session_secret_column_idempotently(migrated_factory):
    from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner

    conn = migrated_factory.get_connection()
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
        versions = {
            r[0]
            for r in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
    finally:
        conn.close()
    assert "session_secret" in cols
    assert 7 in versions  # the column is attributable to migration 007
    assert MigrationRunner(migrated_factory).apply() == []  # idempotent re-run


def test_session_open_returns_persisted_unique_secret_and_no_read_leak(
    migrated_factory, tmp_config, tmp_path
):
    svc = make_identity(migrated_factory, tmp_config, StubClock())
    ws = seed(svc, mkproj(tmp_path), "alice")
    s1 = svc.session_open(agent_id="alice", workspace_id=ws)
    s2 = svc.session_open(agent_id="alice", workspace_id=ws)

    assert s1["session_secret"] and s2["session_secret"]
    assert s1["session_secret"] != s2["session_secret"]  # per-session, random

    conn = migrated_factory.get_connection()
    try:
        row = conn.execute(
            "SELECT session_secret FROM sessions WHERE session_id = ?",
            (s1["session_id"],),
        ).fetchone()
    finally:
        conn.close()
    assert row["session_secret"] == s1["session_secret"]  # persisted as returned

    # The secret is returned ONLY by session_open: no other read leaks it.
    assert "session_secret" not in svc.get_session(session_id=s1["session_id"])
    assert all("session_secret" not in s for s in svc.list_sessions(workspace_id=ws))


# =========================================================================== #
# M10 (2): trust_mode config knob parses fail-closed
# =========================================================================== #
def test_trust_mode_defaults_open_and_parses_env_and_cli():
    assert load_config({}).trust_mode == "open"
    assert NexusConfig().trust_mode == "open"
    assert load_config({"OKTO_NEXUS_TRUST_MODE": "strict"}).trust_mode == "strict"
    assert load_config({"OKTO_NEXUS_TRUST_MODE": " STRICT "}).trust_mode == "strict"
    # CLI > env precedence.
    cfg = load_config({"OKTO_NEXUS_TRUST_MODE": "strict"}, ["--trust-mode", "open"])
    assert cfg.trust_mode == "open"


@pytest.mark.parametrize("bad", ["", "  ", "paranoid", "1", "true"])
def test_trust_mode_invalid_value_is_a_startup_error(bad):
    with pytest.raises(OktoNexusError) as ei:
        load_config({"OKTO_NEXUS_TRUST_MODE": bad})
    assert ei.value.code == ErrorCode.CONFIG_ERROR.value
    assert "trust_mode" in ei.value.message


@pytest.mark.parametrize(
    "env_var,field,default",
    [
        (
            "OKTO_NEXUS_PRESENCE_TTL_SECONDS",
            "presence_ttl_seconds",
            DEFAULT_PRESENCE_TTL_SECONDS,
        ),
        (
            "OKTO_NEXUS_SESSION_REAP_SECONDS",
            "session_reap_seconds",
            DEFAULT_SESSION_REAP_SECONDS,
        ),
    ],
)
def test_presence_and_reap_knobs_parse_fail_closed(env_var, field, default):
    assert getattr(load_config({}), field) == default
    assert getattr(load_config({env_var: "42"}), field) == 42
    with pytest.raises(OktoNexusError) as ei:
        load_config({env_var: "0"})
    assert ei.value.code == ErrorCode.CONFIG_ERROR.value


# =========================================================================== #
# M10 (3): strict mode gates message_create (service level)
# =========================================================================== #
def _strict_config(tmp_path) -> NexusConfig:
    return NexusConfig(home_dir=tmp_path / "okto_home", trust_mode="strict")


def test_strict_message_create_requires_credentials_and_rolls_back(
    migrated_factory, tmp_path
):
    clock = StubClock()
    config = _strict_config(tmp_path)
    identity = make_identity(migrated_factory, config, clock)
    proj = mkproj(tmp_path)
    seed(identity, proj, "alice", "bob")

    svc = make_messages(migrated_factory, config, clock)
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(
            project_root=proj,
            from_agent_id="alice",
            subject="s",
            body="b",
            target={"strategy": "direct", "agent_id": "bob"},
        )
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert "session_open" in ei.value.message  # prescriptive: names the fix
    assert "strict" in ei.value.message
    # Fail-closed: NOTHING persisted (not even the workspace upsert).
    assert count(migrated_factory, "messages") == 0
    assert count(migrated_factory, "message_deliveries") == 0


def test_strict_message_create_rejects_wrong_and_foreign_credentials(
    migrated_factory, tmp_path
):
    clock = StubClock()
    config = _strict_config(tmp_path)
    identity = make_identity(migrated_factory, config, clock)
    proj = mkproj(tmp_path)
    ws = seed(identity, proj, "alice", "bob")
    alice = identity.session_open(agent_id="alice", workspace_id=ws)
    bob = identity.session_open(agent_id="bob", workspace_id=ws)

    svc = make_messages(migrated_factory, config, clock)
    base = dict(
        project_root=proj,
        from_agent_id="alice",
        subject="s",
        body="b",
        target={"strategy": "direct", "agent_id": "bob"},
    )
    # Wrong secret -> NOT_OWNER, nothing persisted.
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(
            **base, from_session_id=alice["session_id"], session_secret="forged"
        )
    assert ei.value.code == ErrorCode.NOT_OWNER.value
    # Another agent's (valid) credentials -> NOT_OWNER: bob's secret cannot
    # publish as alice (the exact confused-deputy of M10).
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(
            **base,
            from_session_id=bob["session_id"],
            session_secret=bob["session_secret"],
        )
    assert ei.value.code == ErrorCode.NOT_OWNER.value
    # Unknown session -> NOT_FOUND.
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(**base, from_session_id="ghost", session_secret="x")
    assert ei.value.code == ErrorCode.NOT_FOUND.value
    assert count(migrated_factory, "messages") == 0

    # Valid pair -> the message goes through.
    out = svc.create_message(
        **base,
        from_session_id=alice["session_id"],
        session_secret=alice["session_secret"],
    )
    assert out["recipients"] == ["bob"]
    assert count(migrated_factory, "messages") == 1


def test_strict_message_create_rejects_closed_session_credentials(
    migrated_factory, tmp_path
):
    clock = StubClock()
    config = _strict_config(tmp_path)
    identity = make_identity(migrated_factory, config, clock)
    proj = mkproj(tmp_path)
    ws = seed(identity, proj, "alice", "bob")
    alice = identity.session_open(agent_id="alice", workspace_id=ws)
    identity.session_close(session_id=alice["session_id"])

    svc = make_messages(migrated_factory, config, clock)
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(
            project_root=proj,
            from_agent_id="alice",
            subject="s",
            body="b",
            target={"strategy": "direct", "agent_id": "bob"},
            from_session_id=alice["session_id"],
            session_secret=alice["session_secret"],
        )
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert "closed" in ei.value.message


def test_open_mode_validates_supplied_credentials_never_ignores(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    identity = make_identity(migrated_factory, tmp_config, clock)
    proj = mkproj(tmp_path)
    ws = seed(identity, proj, "alice", "bob")
    alice = identity.session_open(agent_id="alice", workspace_id=ws)

    svc = make_messages(migrated_factory, tmp_config, clock)  # trust_mode=open
    base = dict(
        project_root=proj,
        from_agent_id="alice",
        subject="s",
        body="b",
        target={"strategy": "direct", "agent_id": "bob"},
    )
    # No credentials: legacy behaviour still works.
    assert svc.create_message(**base)["recipients"] == ["bob"]
    # A WRONG supplied secret fails even in open mode.
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(
            **base, from_session_id=alice["session_id"], session_secret="forged"
        )
    assert ei.value.code == ErrorCode.NOT_OWNER.value
    # A secret without its session_id is a usage error, not silently dropped.
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(**base, session_secret=alice["session_secret"])
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    # The CORRECT pair passes.
    out = svc.create_message(
        **base,
        from_session_id=alice["session_id"],
        session_secret=alice["session_secret"],
    )
    assert out["recipients"] == ["bob"]


# =========================================================================== #
# M10 (3): strict mode gates the handoff verbs (tool level)
# =========================================================================== #
def _tool_deps(factory, config, clock):
    return SimpleNamespace(
        config=config,
        connection_factory=factory,
        clock=clock,
        repos=Repos(),
        event_emitter=None,
    )


def test_strict_handoff_claim_complete_reject_require_credentials(
    migrated_factory, tmp_path
):
    clock = StubClock()
    config = _strict_config(tmp_path)
    identity = make_identity(migrated_factory, config, clock)
    proj = mkproj(tmp_path)
    ws = seed(identity, proj, "creator", "worker")
    worker = identity.session_open(agent_id="worker", workspace_id=ws)

    server = FakeServer()
    register_handoff(server, _tool_deps(migrated_factory, config, clock))
    created = server.tools["handoff_create"](
        project_root=proj,
        from_agent_id="creator",
        target={"strategy": "broadcast"},
        visibility="public",
    )
    assert created["ok"] is True
    hid = created["data"]["handoff_id"]

    # Without credentials every sensitive verb refuses, prescriptively.
    for tool in ("handoff_claim", "handoff_complete", "handoff_reject"):
        res = server.tools[tool](project_root=proj, handoff_id=hid, agent_id="worker")
        assert res["ok"] is False, tool
        assert res["error"]["code"] == "VALIDATION_ERROR", tool
        assert "session_open" in res["error"]["message"], tool

    # A forged secret is NOT_OWNER (the claim never reaches the service).
    forged = server.tools["handoff_claim"](
        project_root=proj,
        handoff_id=hid,
        agent_id="worker",
        session_id=worker["session_id"],
        session_secret="forged",
    )
    assert forged["ok"] is False and forged["error"]["code"] == "NOT_OWNER"
    assert count(migrated_factory, "handoffs", "status = 'CLAIMED'") == 0

    # Valid credentials: the full claim -> complete flow proceeds.
    claimed = server.tools["handoff_claim"](
        project_root=proj,
        handoff_id=hid,
        agent_id="worker",
        session_id=worker["session_id"],
        session_secret=worker["session_secret"],
    )
    assert claimed["ok"] is True and claimed["data"]["claimed_by"] == "worker"
    completed = server.tools["handoff_complete"](
        project_root=proj,
        handoff_id=hid,
        agent_id="worker",
        session_id=worker["session_id"],
        session_secret=worker["session_secret"],
    )
    assert completed["ok"] is True


def test_open_mode_handoff_claim_validates_supplied_secret(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    identity = make_identity(migrated_factory, tmp_config, clock)
    proj = mkproj(tmp_path)
    ws = seed(identity, proj, "creator", "worker")
    worker = identity.session_open(agent_id="worker", workspace_id=ws)

    server = FakeServer()
    register_handoff(server, _tool_deps(migrated_factory, tmp_config, clock))
    hid = server.tools["handoff_create"](
        project_root=proj,
        from_agent_id="creator",
        target={"strategy": "broadcast"},
        visibility="public",
    )["data"]["handoff_id"]

    # Open mode: a wrong supplied secret fails (never ignored)...
    res = server.tools["handoff_claim"](
        project_root=proj,
        handoff_id=hid,
        agent_id="worker",
        session_id=worker["session_id"],
        session_secret="forged",
    )
    assert res["ok"] is False and res["error"]["code"] == "NOT_OWNER"
    # ...while the credential-less legacy call still works.
    res = server.tools["handoff_claim"](
        project_root=proj, handoff_id=hid, agent_id="worker"
    )
    assert res["ok"] is True


# =========================================================================== #
# M10 (3): strict mode gates inbox_pull / inbox_ack / inbox_extend (tool level)
# =========================================================================== #
def test_strict_inbox_pull_ack_extend_require_credentials(
    migrated_factory, tmp_path, fake_clock
):
    config = _strict_config(tmp_path)
    identity = make_identity(migrated_factory, config, fake_clock)
    proj = mkproj(tmp_path)
    ws = seed(identity, proj, "sender", "validator")
    sender = identity.session_open(agent_id="sender", workspace_id=ws)
    validator = identity.session_open(agent_id="validator", workspace_id=ws)

    msg_svc = make_messages(migrated_factory, config, fake_clock)
    msg = msg_svc.create_message(
        project_root=proj,
        from_agent_id="sender",
        subject="please validate",
        body="gate",
        target={"strategy": "direct", "agent_id": "validator"},
        from_session_id=sender["session_id"],
        session_secret=sender["session_secret"],
    )

    server = FakeServer()
    register_inbox(server, _tool_deps(migrated_factory, config, fake_clock))

    # An unauthenticated actor cannot suppress the validator's unread (the M10
    # attack): pull/ack/extend all refuse without credentials.
    for tool, kwargs in (
        ("inbox_pull", {}),
        ("inbox_ack", {"message_ids": [msg["message_id"]]}),
        ("inbox_extend", {"message_ids": [msg["message_id"]], "extend_seconds": 60}),
    ):
        res = server.tools[tool](agent_id="validator", **kwargs)
        assert res["ok"] is False, tool
        assert res["error"]["code"] == "VALIDATION_ERROR", tool
        assert "session_open" in res["error"]["message"], tool
    # The unread is intact - nothing was leased or acknowledged.
    assert server.tools["inbox_count"](agent_id="validator")["data"]["unread"] == 1

    # The validator itself, with its own credentials, completes the flow.
    creds = dict(
        session_id=validator["session_id"],
        session_secret=validator["session_secret"],
    )
    pulled = server.tools["inbox_pull"](agent_id="validator", **creds)
    assert pulled["ok"] is True
    assert [m["body"] for m in pulled["data"]["messages"]] == ["gate"]
    extended = server.tools["inbox_extend"](
        agent_id="validator",
        message_ids=[msg["message_id"]],
        extend_seconds=120,
        **creds,
    )
    assert extended["ok"] is True
    acked = server.tools["inbox_ack"](
        agent_id="validator", message_ids=[msg["message_id"]], **creds
    )
    assert acked["ok"] is True and acked["data"]["acknowledged"] == 1


# =========================================================================== #
# M10 (4): shared.md redacts non-public handoff targets
# =========================================================================== #
WS = "a" * 64


def _render(tmp_path, handoffs) -> str:
    renderer = FileSystemSharedMdRenderer(home_dir=tmp_path / "home")
    view = SharedMdView(workspace_id=WS, limit_events=50, handoffs=handoffs)
    result = renderer.render(view=view)
    from pathlib import Path

    return Path(result.path).read_text(encoding="utf-8")


def test_shared_md_redacts_target_of_non_public_handoffs(tmp_path):
    secret_target = '{"strategy":"direct","agent_id":"validator-7"}'
    handoffs = [
        Handoff(
            "ho-private", WS, "open", "2026-06-07T00:00:00Z",
            target=secret_target, visibility="private",
        ),
        Handoff(
            "ho-eligible", WS, "open", "2026-06-07T00:01:00Z",
            target=secret_target, visibility="eligible",
        ),
        # Unset visibility is redacted too (fail-safe: only PUBLIC renders raw).
        Handoff(
            "ho-unset", WS, "open", "2026-06-07T00:02:00Z",
            target=secret_target, visibility=None,
        ),
    ]
    text = _render(tmp_path, handoffs)
    assert "validator-7" not in text  # the private payload/target never leaks
    assert text.count("[private]") == 3
    # The handoff rows themselves are still listed (existence is not secret).
    for hid in ("ho-private", "ho-eligible", "ho-unset"):
        assert hid in text


def test_shared_md_renders_public_handoff_target_raw(tmp_path):
    handoffs = [
        Handoff(
            "ho-public", WS, "open", "2026-06-07T00:00:00Z",
            target='{"strategy":"capability","capability":"ocr"}',
            visibility="public",
        ),
    ]
    text = _render(tmp_path, handoffs)
    assert '"capability":"ocr"' in text  # public stays informative
    assert "[private]" not in text
