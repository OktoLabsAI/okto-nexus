"""Presence tracks ACTIVITY: any authenticated, active verb advances the
session heartbeat, so an agent that coordinates (receives, sends, claims) shows
PRESENT without spamming ``session_heartbeat``.

The gap this closes: presence (the dashboard rollup AND the broadcast audience)
keys on the session ``last_heartbeat_at``, never on the agent ``last_seen_at``
that activity already bumps. So a working agent (e.g. Claude Code parked on its
inbox) decayed to stale right after each turn. Now the credential seam every
sensitive verb funnels through - ``SessionTrustGuard.require`` and the inline
``message_create`` check - stamps the heartbeat on a VERIFIED action, at the
same cost (no extra round-trip), via :func:`advance_session_presence`.

Exercised over the REAL SQLite adapters (``migrated_factory``).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from okto_nexus.adapters.inbound.mcp.tools.inbox import register as register_inbox
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
from okto_nexus.adapters.outbound.sqlite.observability_repo import (
    SqliteObservabilityQueries,
)
from okto_nexus.application.identity import (
    IdentityService,
    SessionTrustGuard,
    advance_session_presence,
)
from okto_nexus.application.messages import MessageService
from okto_nexus.application.observability import ObservabilityService
from okto_nexus.application.ports import Repos
from okto_nexus.config import NexusConfig
from okto_nexus.domain.base import iso_to_epoch
from types import SimpleNamespace


# --------------------------------------------------------------------------- #
# Test doubles & helpers (mirrors test_presence_trust.py)
# --------------------------------------------------------------------------- #
class StubClock:
    """Deterministic, advanceable clock implementing the Clock port."""

    def __init__(self, iso: str = "2026-06-19T00:00:00.000000Z") -> None:
        self._iso = iso

    def now_iso(self) -> str:
        return self._iso

    def now_epoch(self) -> float:
        return iso_to_epoch(self._iso)

    def advance_seconds(self, seconds: float) -> None:
        dt = datetime.fromtimestamp(self.now_epoch() + seconds, tz=timezone.utc)
        self._iso = dt.isoformat(timespec="microseconds").replace("+00:00", "Z")


class FakeEmitter:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self._next = 0

    def emit(self, uow, **kwargs) -> int:
        self._next += 1
        self.events.append({"event_id": self._next, **kwargs})
        return self._next


class FakeServer:
    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def _strict_config(tmp_path) -> NexusConfig:
    return NexusConfig(home_dir=tmp_path / "okto_home", trust_mode="strict")


def make_identity(factory, config, clock) -> IdentityService:
    return IdentityService(
        connection_factory=factory,
        workspaces=SqliteWorkspaceRepo(clock),
        agents=SqliteAgentRepo(clock),
        sessions=SqliteSessionRepo(clock),
        clock=clock,
        config=config,
        event_emitter=FakeEmitter(),
    )


def make_messages(factory, config, clock) -> MessageService:
    return MessageService(
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


def mkproj(tmp_path, name="P"):
    p = tmp_path / name
    p.mkdir()
    return str(p)


def seed(identity, project_root, *agents):
    ws = identity.workspace_resolve(project_root=project_root)["workspace_id"]
    for agent in agents:
        identity.agent_register(agent_id=agent)
    return ws


def _tool_deps(factory, config, clock):
    return SimpleNamespace(
        config=config,
        connection_factory=factory,
        clock=clock,
        repos=Repos(),
        event_emitter=None,
    )


def _session_hb(factory, session_id: str) -> str:
    conn = factory.get_connection()
    try:
        row = conn.execute(
            "SELECT last_heartbeat_at FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()
    return row["last_heartbeat_at"]


def _presence_of(config, clock, hb_at: str) -> str:
    obs = ObservabilityService(SqliteObservabilityQueries(), clock, config)
    return obs.classify_presence(has_active_session=True, last_heartbeat_at=hb_at)


# --------------------------------------------------------------------------- #
# The seam: SessionTrustGuard.require advances the heartbeat on a valid action
# --------------------------------------------------------------------------- #
def test_trust_guard_refreshes_heartbeat_so_stale_agent_reads_present(
    migrated_factory, tmp_path
):
    clock = StubClock()
    config = _strict_config(tmp_path)
    identity = make_identity(migrated_factory, config, clock)
    ws = seed(identity, mkproj(tmp_path), "alice")
    alice = identity.session_open(agent_id="alice", workspace_id=ws)
    sid = alice["session_id"]

    # Let the present window lapse: with the original heartbeat the agent would
    # read stale even though it is about to act.
    clock.advance_seconds(config.session_stale_ttl_seconds + 30)
    stale_hb = _session_hb(migrated_factory, sid)
    assert _presence_of(config, clock, stale_hb) == "stale"

    guard = SessionTrustGuard(
        connection_factory=migrated_factory,
        sessions=SqliteSessionRepo(clock),
        trust_mode="strict",
    )
    guard.require(
        tool="inbox_pull",
        agent_id="alice",
        session_id=sid,
        session_secret=alice["session_secret"],
    )

    fresh_hb = _session_hb(migrated_factory, sid)
    assert iso_to_epoch(fresh_hb) == pytest.approx(clock.now_epoch())
    assert fresh_hb != stale_hb
    assert _presence_of(config, clock, fresh_hb) == "present"


def test_trust_guard_failed_credentials_do_not_stamp_presence(
    migrated_factory, tmp_path
):
    clock = StubClock()
    config = _strict_config(tmp_path)
    identity = make_identity(migrated_factory, config, clock)
    ws = seed(identity, mkproj(tmp_path), "alice")
    alice = identity.session_open(agent_id="alice", workspace_id=ws)
    sid = alice["session_id"]
    clock.advance_seconds(config.session_stale_ttl_seconds + 30)
    before = _session_hb(migrated_factory, sid)

    guard = SessionTrustGuard(
        connection_factory=migrated_factory,
        sessions=SqliteSessionRepo(clock),
        trust_mode="strict",
    )
    from okto_nexus.errors import OktoNexusError

    with pytest.raises(OktoNexusError):
        guard.require(
            tool="inbox_pull",
            agent_id="alice",
            session_id=sid,
            session_secret="forged",
        )
    # A rejected action proves nothing: the heartbeat is untouched (rolled back).
    assert _session_hb(migrated_factory, sid) == before


def test_open_mode_credentialless_action_does_not_stamp_presence(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    identity = make_identity(migrated_factory, tmp_config, clock)  # trust_mode=open
    ws = seed(identity, mkproj(tmp_path), "alice")
    alice = identity.session_open(agent_id="alice", workspace_id=ws)
    sid = alice["session_id"]
    clock.advance_seconds(120)
    before = _session_hb(migrated_factory, sid)

    guard = SessionTrustGuard(
        connection_factory=migrated_factory, sessions=SqliteSessionRepo(clock)
    )  # open default
    guard.require(tool="inbox_pull", agent_id="alice", session_id=sid)  # no secret
    # No session to attribute liveness to without a credential: untouched.
    assert _session_hb(migrated_factory, sid) == before


# --------------------------------------------------------------------------- #
# End-to-end: RECEIVING (inbox_pull) and SENDING keep the agent present
# --------------------------------------------------------------------------- #
def test_inbox_pull_keeps_recipient_present(migrated_factory, tmp_path):
    clock = StubClock()
    config = _strict_config(tmp_path)
    identity = make_identity(migrated_factory, config, clock)
    proj = mkproj(tmp_path)
    ws = seed(identity, proj, "sender", "validator")
    sender = identity.session_open(agent_id="sender", workspace_id=ws)
    validator = identity.session_open(agent_id="validator", workspace_id=ws)

    msg_svc = make_messages(migrated_factory, config, clock)
    msg_svc.create_message(
        project_root=proj,
        from_agent_id="sender",
        subject="please validate",
        body="gate",
        target={"strategy": "direct", "agent_id": "validator"},
        from_session_id=sender["session_id"],
        session_secret=sender["session_secret"],
    )

    # The validator goes quiet long enough to read stale, then RECEIVES.
    clock.advance_seconds(config.session_stale_ttl_seconds + 30)
    vsid = validator["session_id"]
    assert _presence_of(config, clock, _session_hb(migrated_factory, vsid)) == "stale"

    server = FakeServer()
    register_inbox(server, _tool_deps(migrated_factory, config, clock))
    pulled = server.tools["inbox_pull"](
        agent_id="validator",
        session_id=vsid,
        session_secret=validator["session_secret"],
    )
    assert pulled["ok"] is True
    assert [m["body"] for m in pulled["data"]["messages"]] == ["gate"]
    # Receiving updated the status: the validator now reads PRESENT.
    assert _presence_of(config, clock, _session_hb(migrated_factory, vsid)) == "present"


def test_message_send_keeps_sender_present(migrated_factory, tmp_path):
    clock = StubClock()
    config = _strict_config(tmp_path)
    identity = make_identity(migrated_factory, config, clock)
    proj = mkproj(tmp_path)
    ws = seed(identity, proj, "alice", "bob")
    alice = identity.session_open(agent_id="alice", workspace_id=ws)
    identity.session_open(agent_id="bob", workspace_id=ws)
    sid = alice["session_id"]

    clock.advance_seconds(config.session_stale_ttl_seconds + 30)
    assert _presence_of(config, clock, _session_hb(migrated_factory, sid)) == "stale"

    svc = make_messages(migrated_factory, config, clock)
    out = svc.create_message(
        project_root=proj,
        from_agent_id="alice",
        subject="s",
        body="b",
        target={"strategy": "direct", "agent_id": "bob"},
        from_session_id=sid,
        session_secret=alice["session_secret"],
    )
    assert out["recipients"] == ["bob"]
    fresh_hb = _session_hb(migrated_factory, sid)
    assert iso_to_epoch(fresh_hb) == pytest.approx(clock.now_epoch())
    assert _presence_of(config, clock, fresh_hb) == "present"


# --------------------------------------------------------------------------- #
# advance_session_presence is best-effort (never fails the surrounding action)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sid", [None, "", "   ", "ghost-session"])
def test_advance_session_presence_is_best_effort(migrated_factory, sid):
    sessions = SqliteSessionRepo(StubClock())
    with migrated_factory.unit_of_work() as uow:
        advance_session_presence(sessions, uow, session_id=sid)  # never raises
