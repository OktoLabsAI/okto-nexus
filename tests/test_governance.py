"""Tests for R-I2: governance policies - deny rules + quotas (spec ffef15bf).

Covers scenarios TS1..TS9 over the REAL bootstrap (migrated temp SQLite home)
through the shared tool registry (the same registration path both MCP
transports mount) plus the REST surface via TestClient.

Gating contract (decision D4 of spec a9a2c856, inherited as the program's
canonical pattern):

* flag ON  - ``enforce()`` runs PRE-persistence inside the write path's own
  UoW: categorical deny -> ``POLICY_DENIED`` (REST 403), violated quota ->
  ``QUOTA_EXCEEDED`` (REST 429); the denial rolls the whole write back and
  ``governance.denied`` is emitted in a SEPARATE best-effort UoW (BR6).
* flag OFF - accept-and-ignore TOTAL: no policy read, no counting, no event;
  staged policies are dormant and responses are byte-identical to a
  policy-free bus (BR4: CRUD still works so the operator configures BEFORE
  enabling).
* the flag is read LIVE on every call: a settings PATCH applies to the very
  next call, no restart (D6).

NOTE (TS9): the scenario text mentions HTTP 400 for invalid policy forms; the
canonical REST mapping of ``VALIDATION_ERROR`` across the whole surface is
422, so 422 is asserted here (divergence declared in the C5 validation).
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap, register_tools
from okto_nexus.application.governance import (
    GovernanceService,
    message_action_for,
)
from okto_nexus.domain.governance import (
    Policy,
    Subject,
    applicable_policies,
    decide,
    validate_policy_form,
)
from okto_nexus.domain.policy import (
    PolicyVersion,
    audience_permits,
    combined_governance_verdict,
    resolve_effective_sources,
    validate_agent_bindings,
)
from okto_nexus.errors import ErrorCode, OktoNexusError


# --------------------------------------------------------------------------- #
# Harness (the e2e pattern of test_trace.py: real bootstrap + tool registry)
# --------------------------------------------------------------------------- #
class FakeServer:
    """Captures FastMCP-style ``@server.tool()`` registrations by name."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            if inspect.iscoroutinefunction(fn):

                @functools.wraps(fn)
                def _sync(*a, **k):
                    return asyncio.run(fn(*a, **k))

                self.tools[fn.__name__] = _sync
            else:
                self.tools[fn.__name__] = fn
            return fn

        return deco


def _ok(env: dict) -> dict:
    assert env["ok"] is True, f"expected ok envelope, got: {env}"
    return env["data"]


def _err(env: dict, code: str) -> dict:
    assert env["ok"] is False, f"expected error envelope, got: {env}"
    assert env["error"]["code"] == code, env["error"]
    return env["error"]


def make_env(tmp_path):
    """Real bootstrap in a temp home + two registered agents + a workspace.

    Enforcement is always-on and binding-driven now (spec 80624c1a, D-FLAG):
    there is no feature flag. A freshly bootstrapped agent holds NO bindings, so
    every write path behaves policy-free until a policy is attached with
    :func:`_attach` (BR2 zero-regression).
    """
    env = {"OKTO_NEXUS_HOME": str(tmp_path / "home")}
    deps = bootstrap(env, [])
    server = FakeServer()
    register_tools(server, deps)
    tools = server.tools
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    root = str(project)
    _ok(tools["workspace_resolve"](project_root=root))
    _ok(tools["agent_register"](agent_id="alpha", role="builder"))
    _ok(tools["agent_register"](agent_id="beta", role="reviewer"))
    return deps, tools, root


def _gov(deps) -> GovernanceService:
    """The service exactly as the tool modules wire it (binding-driven)."""
    return GovernanceService(
        connection_factory=deps.connection_factory,
        governance=deps.repos.governance,
        clock=deps.clock,
        config=deps.config,
        agents=deps.repos.agents,
        capability_catalog=deps.repos.capability_catalog,
        event_emitter=deps.event_emitter,
        policies=deps.repos.policies,
        policy_bindings=deps.repos.policy_bindings,
    )


def _rule(action, limit_kind, *, limit_value=None, window=None) -> dict:
    """One subject-less governance rule for an inline binding."""
    rule: dict = {"action": action, "limit_kind": limit_kind}
    if limit_value is not None:
        rule["limit_value"] = limit_value
    if window is not None:
        rule["window"] = window
    return rule


def _attach(deps, agent_id, *, audience=None, governance=(), extra=()):
    """Overwrite ``agent_id``'s bindings with ONE inline binding (audience +
    governance) - the migration path's shape - plus any ``extra`` bindings
    (e.g. globals) appended after it. This is how a policy comes to BITE an
    agent now: enforcement composes the actor's bindings, so attaching is the
    only way to turn a rule on (D-FLAG: the binding is the new staging)."""
    bindings = validate_agent_bindings(
        [{"source": "inline", "audience": audience, "governance": list(governance)}]
        + list(extra)
    )
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.policy_bindings.replace(uow, agent_id=agent_id, bindings=bindings)


def _count(deps, table: str) -> int:
    conn = deps.connection_factory.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def _denied_events(deps) -> list[dict]:
    conn = deps.connection_factory.get_connection()
    try:
        rows = conn.execute(
            "SELECT payload FROM events WHERE type = 'governance.denied' "
            "ORDER BY event_id"
        ).fetchall()
        return [json.loads(row["payload"]) for row in rows]
    finally:
        conn.close()


def _direct(agent_id: str) -> dict:
    return {"strategy": "direct", "agent_id": agent_id}


def _policy(created_at: str, policy_id: str, **overrides) -> Policy:
    """Compact Policy factory for the pure-domain tests."""
    fields = {
        "subject_kind": "star",
        "subject_value": "*",
        "action": "message_create",
        "limit_kind": "deny",
        "limit_value": None,
        "window": None,
        "enabled": True,
    }
    fields.update(overrides)
    return Policy(policy_id=policy_id, created_at=created_at, **fields)


ALPHA = Subject(agent_id="alpha", role="builder", capabilities=frozenset({"ocr"}))


# --------------------------------------------------------------------------- #
# TS1 - pure evaluator: form validation, matching, deny-overrides (T1)
# --------------------------------------------------------------------------- #
def test_validate_policy_form_normalises_happy_paths():
    deny = validate_policy_form(
        subject_kind=" Agent ",
        subject_value=" alpha ",
        action=" MESSAGE_CREATE ",
        limit_kind="DENY",
    )
    assert deny == {
        "subject_kind": "agent",
        "subject_value": "alpha",
        "action": "message_create",
        "limit_kind": "deny",
        "limit_value": None,
        "window": None,
    }
    # star needs no subject_value and stores the canonical "*".
    star = validate_policy_form(
        subject_kind="star", action="broadcast", limit_kind="deny"
    )
    assert star["subject_value"] == "*"
    quota = validate_policy_form(
        subject_kind="role",
        subject_value="builder",
        action="handoff_create",
        limit_kind="max_count",
        limit_value=5,
        window="24h",
    )
    assert quota["limit_value"] == 5 and quota["window"] == "24h"
    # max_bytes / max_open_handoffs take a limit but never a window.
    bytes_form = validate_policy_form(
        subject_kind="star",
        action="artifact_put",
        limit_kind="max_bytes",
        limit_value=1024,
    )
    assert bytes_form["window"] is None


@pytest.mark.parametrize(
    "kwargs",
    [
        # vocabulary violations (BR1 - fail-closed)
        {"subject_kind": "team", "action": "message_create", "limit_kind": "deny"},
        {"subject_kind": "star", "action": "message_delete", "limit_kind": "deny"},
        {"subject_kind": "star", "action": "broadcast", "limit_kind": "throttle"},
        # subject_value required for non-star kinds
        {"subject_kind": "agent", "action": "broadcast", "limit_kind": "deny"},
        {
            "subject_kind": "role",
            "subject_value": "   ",
            "action": "broadcast",
            "limit_kind": "deny",
        },
        # window: required for max_count, forbidden elsewhere
        {
            "subject_kind": "star",
            "action": "broadcast",
            "limit_kind": "max_count",
            "limit_value": 5,
        },
        {
            "subject_kind": "star",
            "action": "broadcast",
            "limit_kind": "max_count",
            "limit_value": 5,
            "window": "7d",
        },
        {
            "subject_kind": "star",
            "action": "broadcast",
            "limit_kind": "deny",
            "window": "1h",
        },
        # limit_value: forbidden for deny, positive int for quotas
        {
            "subject_kind": "star",
            "action": "broadcast",
            "limit_kind": "deny",
            "limit_value": 1,
        },
        {
            "subject_kind": "star",
            "action": "broadcast",
            "limit_kind": "max_bytes",
            "limit_value": 0,
        },
        {
            "subject_kind": "star",
            "action": "broadcast",
            "limit_kind": "max_bytes",
            "limit_value": True,
        },
        {
            "subject_kind": "star",
            "action": "broadcast",
            "limit_kind": "max_bytes",
            "limit_value": "10",
        },
        {
            "subject_kind": "star",
            "action": "handoff_create",
            "limit_kind": "max_open_handoffs",
        },
    ],
)
def test_validate_policy_form_fail_closed(kwargs):
    with pytest.raises(OktoNexusError) as ei:
        validate_policy_form(**kwargs)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


def test_subject_matching_matrix():
    cases = [
        ({"subject_kind": "agent", "subject_value": "alpha"}, True),
        ({"subject_kind": "agent", "subject_value": "beta"}, False),
        ({"subject_kind": "role", "subject_value": "builder"}, True),
        ({"subject_kind": "role", "subject_value": "reviewer"}, False),
        ({"subject_kind": "capability", "subject_value": "ocr"}, True),
        ({"subject_kind": "capability", "subject_value": "tts"}, False),
        ({"subject_kind": "star", "subject_value": "*"}, True),
    ]
    for overrides, expected in cases:
        policy = _policy("2026-01-01T00:00:00Z", "pol_x", **overrides)
        matched = applicable_policies([policy], ALPHA, "message_create")
        assert bool(matched) is expected, overrides
    # A role policy never matches an agent without a role.
    role_policy = _policy(
        "2026-01-01T00:00:00Z", "pol_r", subject_kind="role", subject_value="builder"
    )
    assert not applicable_policies(
        [role_policy], Subject(agent_id="x"), "message_create"
    )


def test_action_hierarchy_message_create_covers_broadcast():
    mc = _policy("2026-01-01T00:00:00Z", "pol_mc", action="message_create")
    bc = _policy("2026-01-01T00:00:00Z", "pol_bc", action="broadcast")
    # message_create covers BOTH plain sends and broadcasts (BR2)...
    assert applicable_policies([mc], ALPHA, "message_create") == [mc]
    assert applicable_policies([mc], ALPHA, "broadcast") == [mc]
    # ...while broadcast covers only broadcast-strategy sends.
    assert applicable_policies([bc], ALPHA, "broadcast") == [bc]
    assert applicable_policies([bc], ALPHA, "message_create") == []


def test_message_action_classifier():
    assert message_action_for({"strategy": "broadcast"}) == "broadcast"
    assert (
        message_action_for({"strategy": "direct", "agent_id": "b"}) == "message_create"
    )
    # target-less AND channel-less fans out to everyone -> broadcast reach.
    assert message_action_for(None, None) == "broadcast"
    # a channel post without a target is a plain message_create.
    assert message_action_for(None, "ch_1") == "message_create"


def test_applicable_policies_skips_disabled_and_orders_deterministically():
    older = _policy("2026-01-01T00:00:00Z", "pol_b")
    newer = _policy("2026-01-02T00:00:00Z", "pol_a")
    tie = _policy("2026-01-01T00:00:00Z", "pol_a")
    disabled = _policy("2025-01-01T00:00:00Z", "pol_off", enabled=False)
    ordered = applicable_policies(
        [newer, older, tie, disabled], ALPHA, "message_create"
    )
    assert [p.policy_id for p in ordered] == ["pol_a", "pol_b", "pol_a"]
    assert ordered[0].created_at == "2026-01-01T00:00:00Z"


def test_decide_deny_overrides_and_quota_semantics():
    deny = _policy("2026-01-02T00:00:00Z", "pol_deny")
    count = _policy(
        "2026-01-01T00:00:00Z",
        "pol_count",
        limit_kind="max_count",
        limit_value=2,
        window="1h",
    )
    size = _policy(
        "2026-01-01T00:00:00Z", "pol_bytes", limit_kind="max_bytes", limit_value=10
    )
    # Deny beats a violated quota even when the quota sorts first.
    verdict = decide(
        applicable_policies([count, deny], ALPHA, "message_create"),
        size_bytes=0,
        usage={"pol_count": 99},
    )
    assert verdict is not None and verdict.policy.policy_id == "pol_deny"
    assert verdict.current is None
    # Counts violate at current >= limit (the NEXT action would exceed).
    assert decide([count], size_bytes=0, usage={"pol_count": 1}) is None
    at_limit = decide([count], size_bytes=0, usage={"pol_count": 2})
    assert at_limit is not None and at_limit.current == 2
    # max_bytes: the EXACT limit passes; one byte over violates (BR3).
    assert decide([size], size_bytes=10, usage={}) is None
    over = decide([size], size_bytes=11, usage={})
    assert over is not None and over.current == 11
    # A missing usage entry is a programming error - never fail-open.
    with pytest.raises(KeyError):
        decide([count], size_bytes=0, usage={})


# --------------------------------------------------------------------------- #
# TS2 - categorical deny on the message path: rollback + audit (T2)
# --------------------------------------------------------------------------- #
def test_ts2_message_deny_rolls_back_and_audits(tmp_path):
    deps, tools, root = make_env(tmp_path)
    # A deny rule attached to alpha (the binding is the subject now).
    _attach(deps, "alpha", governance=[_rule("message_create", "deny")])
    env = tools["message_create"](
        project_root=root,
        from_agent_id="alpha",
        subject="hi",
        body="blocked",
        target=_direct("beta"),
    )
    err = _err(env, "POLICY_DENIED")
    # The winning rule reports its provenance as <source label>#r<index>.
    assert err["details"]["policy_id"] == "inline#r0"
    assert err["details"]["action"] == "message_create"
    assert err["details"]["limit_kind"] == "deny"
    # The whole write rolled back: no message row, no delivery.
    assert _count(deps, "messages") == 0
    assert _count(deps, "message_deliveries") == 0
    # ...but the audit event was committed in its own UoW (BR6).
    denied = _denied_events(deps)
    assert len(denied) == 1
    assert denied[0]["policy_id"] == "inline#r0"
    assert denied[0]["agent_id"] == "alpha"
    # The binding is agent-scoped: beta has none, so it still sends.
    _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="beta",
            subject="hi",
            body="allowed",
            target=_direct("alpha"),
        )
    )
    assert _count(deps, "messages") == 1


def test_ts2_broadcast_deny_spares_direct_sends(tmp_path):
    deps, tools, root = make_env(tmp_path)
    # A broadcast deny attached to BOTH agents (the old "star" reach).
    for who in ("alpha", "beta"):
        _attach(deps, who, governance=[_rule("broadcast", "deny")])
    # Direct send passes: broadcast rules never cover it (BR2).
    _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="d",
            body="direct ok",
            target=_direct("beta"),
        )
    )
    # The explicit broadcast strategy is denied for EVERY agent (star).
    env = tools["message_create"](
        project_root=root,
        from_agent_id="beta",
        subject="b",
        body="fan-out",
        target={"strategy": "broadcast"},
    )
    _err(env, "POLICY_DENIED")
    assert _count(deps, "messages") == 1


# --------------------------------------------------------------------------- #
# TS3 - deny on the handoff and artifact paths (T2)
# --------------------------------------------------------------------------- #
def test_ts3_handoff_deny_by_role(tmp_path):
    deps, tools, root = make_env(tmp_path)
    # A handoff_create deny attached to alpha (the builder).
    _attach(deps, "alpha", governance=[_rule("handoff_create", "deny")])
    env = tools["handoff_create"](
        project_root=root,
        from_agent_id="alpha",
        target=_direct("beta"),
        visibility="public",
        payload="take over",
    )
    err = _err(env, "POLICY_DENIED")
    assert err["details"]["policy_id"] == "inline#r0"
    assert _count(deps, "handoffs") == 0
    # beta has no binding and creates normally.
    _ok(
        tools["handoff_create"](
            project_root=root,
            from_agent_id="beta",
            target=_direct("alpha"),
            visibility="public",
            payload="reviewer can",
        )
    )
    assert _count(deps, "handoffs") == 1


def test_ts3_artifact_put_deny_needs_an_attached_identity(tmp_path):
    deps, tools, root = make_env(tmp_path)
    # A deny attached to alpha bites alpha's artifact_put (checked here at the
    # service level - the cooperative stdio tool carries no identity to attach).
    _attach(deps, "alpha", governance=[_rule("artifact_put", "deny")])
    with pytest.raises(OktoNexusError) as ei:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            _gov(deps).enforce(uow, agent_id="alpha", action="artifact_put")
    assert ei.value.code == ErrorCode.POLICY_DENIED.value
    # The identityless stdio caller holds NO bindings, so it is never governed
    # (D-FLAG: governance is per-attachment; nothing attaches to a non-identity).
    _ok(
        tools["artifact_put"](
            project_root=root, artifact_type="text", name="n", content="body"
        )
    )
    assert _count(deps, "artifacts") == 1


# --------------------------------------------------------------------------- #
# TS4 - max_count / max_bytes quotas (T3)
# --------------------------------------------------------------------------- #
def test_ts4_max_count_denies_third_send_and_is_per_agent(tmp_path):
    deps, tools, root = make_env(tmp_path)
    _attach(
        deps,
        "alpha",
        governance=[_rule("message_create", "max_count", limit_value=2, window="1h")],
    )
    for i in range(2):
        _ok(
            tools["message_create"](
                project_root=root,
                from_agent_id="alpha",
                subject=f"m{i}",
                body="ok",
                target=_direct("beta"),
            )
        )
    env = tools["message_create"](
        project_root=root,
        from_agent_id="alpha",
        subject="m2",
        body="third",
        target=_direct("beta"),
    )
    err = _err(env, "QUOTA_EXCEEDED")
    assert err["details"] == {
        "policy_id": "inline#r0",
        "action": "message_create",
        "limit_kind": "max_count",
        "limit": 2,
        "window": "1h",
        "current": 2,
    }
    # Consumption is per agent (BR3): beta's own budget is untouched.
    _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="beta",
            subject="b0",
            body="fresh budget",
            target=_direct("alpha"),
        )
    )
    assert _count(deps, "messages") == 3
    # The denial was audited with the quota context, never the body (BR5/BR6).
    denied = _denied_events(deps)
    assert len(denied) == 1
    assert denied[0]["error_code"] == "QUOTA_EXCEEDED"
    assert denied[0]["current"] == 2
    assert "subject" not in denied[0] and "body" not in denied[0]


def test_ts4_max_bytes_exact_limit_passes(tmp_path):
    deps, tools, root = make_env(tmp_path)
    _attach(
        deps,
        "alpha",
        governance=[_rule("message_create", "max_bytes", limit_value=16)],
    )
    # Exactly 16 UTF-8 bytes: the exact limit PASSES (BR3).
    _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="fits",
            body="x" * 16,
            target=_direct("beta"),
        )
    )
    env = tools["message_create"](
        project_root=root,
        from_agent_id="alpha",
        subject="over",
        body="x" * 17,
        target=_direct("beta"),
    )
    err = _err(env, "QUOTA_EXCEEDED")
    assert err["details"]["limit"] == 16
    assert err["details"]["current"] == 17
    assert "window" not in err["details"]


def test_ts4_count_consumption_is_global_across_workspaces(tmp_path):
    deps, tools, root = make_env(tmp_path)
    _attach(
        deps,
        "alpha",
        governance=[_rule("message_create", "max_count", limit_value=2, window="1h")],
    )
    project2 = tmp_path / "project2"
    project2.mkdir(exist_ok=True)
    root2 = str(project2)
    _ok(tools["workspace_resolve"](project_root=root2))
    # One send in EACH workspace exhausts the GLOBAL per-agent budget (BR3:
    # policies are global, consumption is counted across workspaces).
    for send_root in (root, root2):
        _ok(
            tools["message_create"](
                project_root=send_root,
                from_agent_id="alpha",
                subject="s",
                body="b",
                target=_direct("beta"),
            )
        )
    env = tools["message_create"](
        project_root=root,
        from_agent_id="alpha",
        subject="s",
        body="third anywhere",
        target=_direct("beta"),
    )
    err = _err(env, "QUOTA_EXCEEDED")
    assert err["details"]["current"] == 2


def test_ts4_window_expiry_frees_the_budget(tmp_path):
    from okto_nexus.domain.base import iso_plus

    deps, tools, root = make_env(tmp_path)
    _attach(
        deps,
        "alpha",
        governance=[_rule("message_create", "max_count", limit_value=1, window="1h")],
    )
    _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="s",
            body="b",
            target=_direct("beta"),
        )
    )

    class FixedClock:
        def __init__(self, iso: str) -> None:
            self._iso = iso

        def now_iso(self) -> str:
            return self._iso

    def enforce_at(clock) -> None:
        service = GovernanceService(
            connection_factory=deps.connection_factory,
            governance=deps.repos.governance,
            clock=clock,
            config=deps.config,
            agents=deps.repos.agents,
            capability_catalog=deps.repos.capability_catalog,
            event_emitter=deps.event_emitter,
            policies=deps.repos.policies,
            policy_bindings=deps.repos.policy_bindings,
        )
        with deps.connection_factory.unit_of_work(write=False) as uow:
            service.enforce(uow, agent_id="alpha", action="message_create")

    # Inside the window the budget is spent...
    with pytest.raises(OktoNexusError) as ei:
        enforce_at(deps.clock)
    assert ei.value.code == ErrorCode.QUOTA_EXCEEDED.value
    # ...two hours later the on-demand COUNT no longer sees the send: the
    # sliding window freed the budget (windows are derived, never a counter).
    enforce_at(FixedClock(iso_plus(deps.clock.now_iso(), 7200.0)))


# --------------------------------------------------------------------------- #
# TS5 - max_open_handoffs releases on terminal status (T3)
# --------------------------------------------------------------------------- #
def test_ts5_max_open_handoffs_frees_after_terminal(tmp_path):
    deps, tools, root = make_env(tmp_path)
    _attach(
        deps,
        "alpha",
        governance=[_rule("handoff_create", "max_open_handoffs", limit_value=1)],
    )
    first = _ok(
        tools["handoff_create"](
            project_root=root,
            from_agent_id="alpha",
            target=_direct("beta"),
            visibility="public",
            payload="one",
        )
    )
    env = tools["handoff_create"](
        project_root=root,
        from_agent_id="alpha",
        target=_direct("beta"),
        visibility="public",
        payload="two",
    )
    err = _err(env, "QUOTA_EXCEEDED")
    assert err["details"]["limit_kind"] == "max_open_handoffs"
    assert err["details"]["current"] == 1
    # Cancelling moves the handoff to a TERMINAL status; the slot frees up.
    _ok(
        tools["handoff_cancel"](
            project_root=root,
            handoff_id=first["handoff_id"],
            agent_id="alpha",
        )
    )
    _ok(
        tools["handoff_create"](
            project_root=root,
            from_agent_id="alpha",
            target=_direct("beta"),
            visibility="public",
            payload="three",
        )
    )


# --------------------------------------------------------------------------- #
# TS6 - enforcement is binding-driven; no binding = zero-regression (T4)
# --------------------------------------------------------------------------- #
def test_ts6_unbound_agents_are_never_governed(tmp_path):
    deps, tools, root = make_env(tmp_path)
    # No binding is attached to anyone: every write path behaves policy-free,
    # byte-identical to a pre-policy bus (BR2/BR9). There is no feature flag -
    # the ABSENCE of a binding IS the "off" state (D-FLAG).
    _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="s",
            body="way past any byte budget",
            target=_direct("beta"),
        )
    )
    _ok(
        tools["handoff_create"](
            project_root=root,
            from_agent_id="alpha",
            target=_direct("beta"),
            visibility="public",
            payload="p",
        )
    )
    _ok(
        tools["artifact_put"](
            project_root=root, artifact_type="text", name="n", content="body"
        )
    )
    assert _denied_events(deps) == []


def test_ts6_binding_existence_toggles_enforcement_live(tmp_path):
    deps, tools, root = make_env(tmp_path)
    send = lambda: tools["message_create"](  # noqa: E731 - tiny local retry helper
        project_root=root,
        from_agent_id="alpha",
        subject="s",
        body="b",
        target=_direct("beta"),
    )
    # Nothing attached yet: the send passes.
    _ok(send())
    # Attaching an inline deny bites the very NEXT call - no restart: each write
    # path composes the actor's bindings LIVE (D-FLAG: the binding replaced the
    # feature flag as the staging switch).
    _attach(deps, "alpha", governance=[_rule("message_create", "deny")])
    _err(send(), "POLICY_DENIED")
    # Detaching (replace with an empty binding set) frees it again next call.
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.policy_bindings.replace(uow, agent_id="alpha", bindings=[])
    _ok(send())
    assert _count(deps, "messages") == 2


# --------------------------------------------------------------------------- #
# TS7 - agent_whoami: conditional caller-scoped governance block (T5)
# --------------------------------------------------------------------------- #
def test_ts7_whoami_governance_block_gated_and_scoped(tmp_path):
    from okto_nexus.adapters.inbound.http.identity_ctx import current_agent

    deps, tools, root = make_env(tmp_path)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        alpha = deps.repos.agents.get(uow, "alpha")
        beta = deps.repos.agents.get(uow, "beta")

    token = current_agent.set(alpha)
    try:
        # No binding: the block is ABSENT, byte-identical to the pre-policy view.
        baseline = _ok(tools["agent_whoami"]())
        assert "governance" not in baseline
        # Attaching a governance rule surfaces the compact block (FR11), keyed by
        # the effective source label ("inline" for an inline binding) and NEVER
        # exposing the audience selector contents.
        _attach(
            deps,
            "alpha",
            governance=[
                _rule("message_create", "max_count", limit_value=5, window="24h")
            ],
        )
        on = _ok(tools["agent_whoami"]())
        assert on["governance"] == [
            {
                "policy_id": "inline",
                "action": "message_create",
                "limit_kind": "max_count",
                "limit": 5,
                "window": "24h",
            }
        ]
    finally:
        current_agent.reset(token)

    # beta holds no binding: no block at all (BR2 - the no-binding surface stays
    # byte-identical to today's whoami).
    token = current_agent.set(beta)
    try:
        beta_view = _ok(tools["agent_whoami"]())
        assert "governance" not in beta_view
    finally:
        current_agent.reset(token)


# --------------------------------------------------------------------------- #
# TS8 - governance.denied is best-effort and never masks the caller's error (T6)
# --------------------------------------------------------------------------- #
def test_ts8_broken_emitter_never_masks_the_denial(tmp_path):
    deps, _tools, root = make_env(tmp_path)

    class ExplodingEmitter:
        def emit(self, *args, **kwargs):
            raise RuntimeError("audit sink down")

    gov = GovernanceService(
        connection_factory=deps.connection_factory,
        governance=deps.repos.governance,
        clock=deps.clock,
        config=deps.config,
        agents=deps.repos.agents,
        capability_catalog=deps.repos.capability_catalog,
        event_emitter=ExplodingEmitter(),
    )
    denial = OktoNexusError(
        ErrorCode.POLICY_DENIED,
        "denied",
        {"policy_id": "pol_x", "action": "message_create", "limit_kind": "deny"},
    )
    with pytest.raises(OktoNexusError) as ei:
        with gov.guard(workspace_id="ws_1", agent_id="alpha"):
            raise denial
    # The ORIGINAL error propagates unchanged; the emitter crash is swallowed.
    assert ei.value is denial
    assert _denied_events(deps) == []


def test_ts8_non_denial_errors_emit_nothing(tmp_path):
    deps, _tools, root = make_env(tmp_path)
    gov = _gov(deps)
    with pytest.raises(OktoNexusError):
        with gov.guard(workspace_id="ws_1", agent_id="alpha"):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "bad input", {})
    assert _denied_events(deps) == []


def test_ts8_denied_payload_shape(tmp_path):
    deps, tools, root = make_env(tmp_path)
    _attach(deps, "alpha", governance=[_rule("message_create", "deny")])
    _err(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="secret subject",
            body="secret body",
            target=_direct("beta"),
        ),
        "POLICY_DENIED",
    )
    denied = _denied_events(deps)
    assert len(denied) == 1
    assert denied[0] == {
        "policy_id": "inline#r0",
        "action": "message_create",
        "agent_id": "alpha",
        "error_code": "POLICY_DENIED",
        "limit_kind": "deny",
    }


# --------------------------------------------------------------------------- #
# TS9 - REST CRUD + HTTP status mapping (T5)
# --------------------------------------------------------------------------- #
@pytest.fixture()
def rest_client(tmp_path):
    from fastapi.testclient import TestClient

    from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
    from okto_nexus.application.auth import AgentKeyAuthService

    deps = bootstrap({"OKTO_NEXUS_HOME": str(tmp_path / "home")}, [])
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    _, operator_key = ensure_operator_key(deps, auth)
    app = build_app(deps)
    with TestClient(app) as client:
        client.headers.update({"x-api-key": operator_key})
        yield client, deps


def test_ts9_rest_crud_lifecycle(rest_client):
    client, _deps = rest_client
    reg = client.post("/api/v1/agents", json={"agent_id": "alpha", "role": "builder"})
    assert reg.status_code == 200, reg.text

    assert client.get("/api/v1/governance/policies").json()["data"]["items"] == []

    created = client.post(
        "/api/v1/governance/policies",
        json={
            "subject_kind": "agent",
            "subject_value": "alpha",
            "action": "message_create",
            "limit_kind": "deny",
        },
    )
    assert created.status_code == 200, created.text
    policy = created.json()["data"]
    assert policy["policy_id"].startswith("pol_") and policy["enabled"] is True

    patched = client.patch(
        f"/api/v1/governance/policies/{policy['policy_id']}",
        json={"enabled": False},
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["enabled"] is False
    # Disabled policies stay listed (the operator re-enables from the table).
    items = client.get("/api/v1/governance/policies").json()["data"]["items"]
    assert len(items) == 1 and items[0]["enabled"] is False

    deleted = client.delete(f"/api/v1/governance/policies/{policy['policy_id']}")
    assert deleted.status_code == 200 and deleted.json()["data"]["deleted"] is True
    assert client.get("/api/v1/governance/policies").json()["data"]["items"] == []


def test_ts9_rest_validation_is_fail_closed(rest_client):
    client, _deps = rest_client
    # NOTE: VALIDATION_ERROR maps to 422 across the whole REST surface (the
    # TS9 text said 400; divergence declared at C5 validation).
    bad_forms = [
        {"subject_kind": "team", "action": "message_create", "limit_kind": "deny"},
        {
            "subject_kind": "star",
            "action": "broadcast",
            "limit_kind": "max_count",
            "limit_value": 5,
        },
        {
            "subject_kind": "star",
            "action": "broadcast",
            "limit_kind": "max_bytes",
            "limit_value": 0,
        },
        # unknown top-level field (fail-closed body parsing)
        {
            "subject_kind": "star",
            "action": "broadcast",
            "limit_kind": "deny",
            "workspace_id": "x",
        },
        # existence checks (AC7): unregistered agent / capability
        {
            "subject_kind": "agent",
            "subject_value": "ghost",
            "action": "message_create",
            "limit_kind": "deny",
        },
        {
            "subject_kind": "capability",
            "subject_value": "ghost",
            "action": "message_create",
            "limit_kind": "deny",
        },
    ]
    for body in bad_forms:
        resp = client.post("/api/v1/governance/policies", json=body)
        assert resp.status_code == 422, (body, resp.text)
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    # A capability subject works once the name is in the catalogue.
    assert client.post("/api/v1/capabilities", json={"name": "ocr"}).status_code == 200
    ok = client.post(
        "/api/v1/governance/policies",
        json={
            "subject_kind": "capability",
            "subject_value": "ocr",
            "action": "message_create",
            "limit_kind": "deny",
        },
    )
    assert ok.status_code == 200, ok.text
    # Unknown policy ids are 404, not 422.
    missing = client.patch(
        "/api/v1/governance/policies/pol_missing", json={"enabled": True}
    )
    assert missing.status_code == 404
    assert client.delete("/api/v1/governance/policies/pol_missing").status_code == 404


def test_rest_status_mapping_for_denials_preserves_details():
    from okto_nexus.adapters.inbound.http.routes import _map_error

    denied = _map_error(
        OktoNexusError(
            ErrorCode.POLICY_DENIED,
            "denied",
            {"policy_id": "p", "action": "a", "limit_kind": "deny"},
        )
    )
    assert denied.status_code == 403
    quota = _map_error(
        OktoNexusError(
            ErrorCode.QUOTA_EXCEEDED,
            "quota",
            {
                "policy_id": "p",
                "action": "a",
                "limit_kind": "max_count",
                "limit": 2,
                "window": "1h",
                "current": 2,
            },
        )
    )
    assert quota.status_code == 429
    body = json.loads(quota.body)
    # details survive the HTTP mapping - stdio/HTTP parity for agents.
    assert body["error"]["details"]["current"] == 2
    assert body["error"]["details"]["window"] == "1h"


# --------------------------------------------------------------------------- #
# TS10 - agent_whoami.effective_policies names WHICH policies apply as
# <policy_id>@<version>, without leaking the audience selector (spec 80624c1a,
# AC10/FR11). The label is the audit handle a GLOBAL binding resolves to; the
# comm_scope value it references stays operator-private.
# --------------------------------------------------------------------------- #
def test_ts10_whoami_effective_policies_names_globals_without_leaking_audience(
    tmp_path,
):
    from okto_nexus.adapters.inbound.http.identity_ctx import current_agent
    from okto_nexus.application.policy_catalog import PolicyCatalogService

    deps, tools, root = make_env(tmp_path)
    catalog = PolicyCatalogService(
        connection_factory=deps.connection_factory,
        policies=deps.repos.policies,
        policy_bindings=deps.repos.policy_bindings,
        agents=deps.repos.agents,
    )
    # A named, published global policy whose only content is a SECRET audience
    # selector (no governance rules) - so the whoami block can only come from the
    # effective_policies label, never the audience.
    header = catalog.create(name="reachability", description=None)
    pid = header["policy_id"]
    catalog.publish_version(
        policy_id=pid,
        audience={"outbound": {"team": ["backend-secret"]}},
        governance=None,
    )
    # Attach it to alpha as a GLOBAL latest reference (version resolves to 1).
    bindings = validate_agent_bindings(
        [{"source": "global", "policy_id": pid, "mode": "latest"}]
    )
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.policy_bindings.replace(uow, agent_id="alpha", bindings=bindings)
        alpha = deps.repos.agents.get(uow, "alpha")

    token = current_agent.set(alpha)
    try:
        view = _ok(tools["agent_whoami"]())
    finally:
        current_agent.reset(token)

    # effective_policies NAMES the applying policy as <policy_id>@<version> ...
    assert view["effective_policies"] == [f"{pid}@1"]
    # ... and NEITHER the audience selector value nor its envelope keys leak
    # (comm_scope stays operator-private) ...
    dump = json.dumps(view)
    assert "backend-secret" not in dump
    assert "comm_scope" not in view and "audience" not in view
    # ... and an audience-only policy carries no rules, so there is no
    # governance block (that block only surfaces deny/quota/require rules).
    assert "governance" not in view

    # An agent with NO binding stays byte-identical to the pre-policy surface:
    # the field is ABSENT, not an empty list (BR2 zero-regression).
    with deps.connection_factory.unit_of_work(write=False) as uow:
        beta = deps.repos.agents.get(uow, "beta")
    token = current_agent.set(beta)
    try:
        beta_view = _ok(tools["agent_whoami"]())
    finally:
        current_agent.reset(token)
    assert "effective_policies" not in beta_view


# --------------------------------------------------------------------------- #
# TS1 - full zero-regression: an UNBOUND agent is policy-free on EVERY path and
# the stream a second agent reads hides nothing (T1)
# --------------------------------------------------------------------------- #
def test_ts1_unbound_agent_is_full_zero_regression_across_paths(tmp_path):
    """TS1 (spec 80624c1a): an agent with NO bindings is policy-free on every
    write path (direct + broadcast message, handoff, artifact), and a second,
    unbound agent reading the workspace stream sees the activity in full - the
    read-path leaks nothing. Attaching is the ONLY thing that turns a policy on
    (BR2/BR9)."""
    deps, tools, root = make_env(tmp_path)
    _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="s",
            body="direct body well past any imaginable byte budget",
            target=_direct("beta"),
        )
    )
    _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="s",
            body="broadcast body",
            target={"strategy": "broadcast"},
        )
    )
    _ok(
        tools["handoff_create"](
            project_root=root,
            from_agent_id="alpha",
            target=_direct("beta"),
            visibility="public",
            payload="p",
        )
    )
    _ok(
        tools["artifact_put"](
            project_root=root, artifact_type="text", name="n", content="body"
        )
    )
    # Nothing was denied on ANY path.
    assert _denied_events(deps) == []
    # A second, unbound agent reads the workspace stream and sees it all -
    # audience is unrestricted, the read-path hides nothing (both the direct and
    # the broadcast message, plus the public artifact, are visible).
    page = _ok(
        tools["event_get"](project_root=root, agent_id="beta", stream="workspace")
    )
    types = [e["type"] for e in page["events"]]
    assert types.count("message.created") >= 2
    assert "artifact.created" in types


# --------------------------------------------------------------------------- #
# TS4 - effective audience is the AND intersection of N sources (T2)
# --------------------------------------------------------------------------- #
def test_ts4_effective_audience_is_and_intersection_of_sources(tmp_path):
    """TS4 (spec 80624c1a): resolving 2 global bindings + 1 inline yields three
    effective sources whose combined audience is the AND intersection; a target
    failing ANY source is excluded, and adding a 4th source can only NARROW -
    it never re-includes a previously-excluded target."""
    g1 = PolicyVersion(
        "pol_g1", 1, {"outbound": {"team": ["backend"]}}, (), "2026-01-01T00:00:00Z"
    )
    g2 = PolicyVersion(
        "pol_g2", 1, {"outbound": {"tier": ["gold"]}}, (), "2026-01-02T00:00:00Z"
    )
    bindings = [
        {"source": "global", "policy_id": "pol_g1", "mode": "latest"},
        {"source": "global", "policy_id": "pol_g2", "mode": "latest"},
        {"source": "inline", "audience": {"outbound": {"region": ["us"]}}},
    ]
    sources = resolve_effective_sources(bindings, {"pol_g1": [g1], "pol_g2": [g2]})
    # Three sources; the inline one sorts FIRST (published_at "").
    assert [s.label for s in sources] == ["inline", "pol_g1@1", "pol_g2@1"]

    full = {"team": ["backend"], "tier": ["gold"], "region": ["us"]}
    assert audience_permits(sources, "outbound", full) is True
    # Failing ANY single source excludes the target (AND).
    assert (
        audience_permits(sources, "outbound", {"team": ["backend"], "region": ["us"]})
        is False  # fails g2 (no gold tier)
    )
    assert (
        audience_permits(sources, "outbound", {"team": ["backend"], "tier": ["gold"]})
        is False  # fails the inline source (no us region)
    )

    # Adding a 4th source can only narrow: a target that passed all three now
    # fails the new leg, and a target already excluded stays excluded.
    g3 = PolicyVersion(
        "pol_g3", 1, {"outbound": {"clearance": ["high"]}}, (), "2026-01-03T00:00:00Z"
    )
    sources4 = resolve_effective_sources(
        bindings + [{"source": "global", "policy_id": "pol_g3", "mode": "latest"}],
        {"pol_g1": [g1], "pol_g2": [g2], "pol_g3": [g3]},
    )
    assert audience_permits(sources4, "outbound", full) is False  # excluded by g3
    assert (
        audience_permits(sources4, "outbound", {"team": ["backend"], "region": ["us"]})
        is False  # still excluded
    )
    # Only a target satisfying ALL FOUR passes - the 4th never re-includes.
    assert (
        audience_permits(sources4, "outbound", {**full, "clearance": ["high"]}) is True
    )


# --------------------------------------------------------------------------- #
# TS5 - deny beats quota; the first violated quota (deterministic order) reports
# its policy_id@version (T3)
# --------------------------------------------------------------------------- #
def test_ts5_deny_beats_quota_then_first_violated_quota_reports_label(tmp_path):
    """TS5 (spec 80624c1a): with a deny and two concurrent max_count quotas for
    the same action, the composed verdict is the DENY (deny overrides). Remove
    the deny and the FIRST violated quota in (published_at, policy_id, version,
    rule_index) order wins, and the verdict names it as policy_id@version."""
    rule_deny = {
        "action": "message_create",
        "limit_kind": "deny",
        "limit_value": None,
        "window": None,
    }
    rule_q = lambda limit: {  # noqa: E731 - tiny local quota factory
        "action": "message_create",
        "limit_kind": "max_count",
        "limit_value": limit,
        "window": "1h",
    }
    q1 = PolicyVersion("pol_q1", 1, None, (rule_q(2),), "2026-01-01T00:00:00Z")
    q2 = PolicyVersion("pol_q2", 1, None, (rule_q(5),), "2026-01-02T00:00:00Z")
    deny = PolicyVersion("pol_deny", 1, None, (rule_deny,), "2026-01-03T00:00:00Z")
    versions = {"pol_q1": [q1], "pol_q2": [q2], "pol_deny": [deny]}
    g = lambda pid: {"source": "global", "policy_id": pid, "mode": "latest"}  # noqa: E731
    # Both quotas are OVER their limit (their single rule is index 0).
    usage = {"pol_q1@1#r0": 5, "pol_q2@1#r0": 6}

    # With the deny present, deny wins even though the quotas sort first.
    with_deny = resolve_effective_sources(
        [g("pol_q1"), g("pol_q2"), g("pol_deny")], versions
    )
    verdict = combined_governance_verdict(
        with_deny, action="message_create", size_bytes=0, usage=usage
    )
    assert verdict is not None
    assert verdict.policy.limit_kind == "deny"
    assert verdict.current is None  # a categorical deny has no count

    # Remove the deny: the FIRST violated quota in order (q1, published earlier)
    # wins, and its synthetic id carries the policy_id@version label.
    no_deny = resolve_effective_sources([g("pol_q1"), g("pol_q2")], versions)
    quota_verdict = combined_governance_verdict(
        no_deny, action="message_create", size_bytes=0, usage=usage
    )
    assert quota_verdict is not None
    assert quota_verdict.policy.limit_kind == "max_count"
    assert quota_verdict.policy.policy_id.startswith("pol_q1@1")
    assert quota_verdict.current == 5
