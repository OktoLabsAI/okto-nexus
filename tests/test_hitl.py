"""Tests for R-I3: HITL approvals + operator steering (spec 2948b2a2).

Covers scenarios TS1..TS10 + TS12 over the REAL bootstrap (migrated temp
SQLite home) through the shared tool registry (the same registration path both
MCP transports mount) plus the REST surface via TestClient - the exact harness
of test_governance.py.

Gating contract (decision D4 of spec a9a2c856, the program's canonical
pattern, refined by 2948b2a2 BR6; governance is now binding-driven, spec
80624c1a D-FLAG):

* interception requires an ATTACHED require_approval rule (via a binding) AND
  feature_hitl ON (read LIVE): ``enforce()`` returns no verdict when the actor
  has no binding, and a matching ``ApprovalRequired`` verdict is dropped with
  hitl OFF - responses stay byte-identical to a policy-free bus.
* queue reads and DECISIONS are ungated: a pendency created while ON stays
  decidable after the flag flips OFF.
* verdict precedence is deny > quota > require_approval (BR8): only an action
  that would have PASSED is intercepted.

Declared drifts (validated at C2/C5): the ``pending_approval`` envelope is a
tool RESPONSE and is never projected - what survives every projection profile
is the ``approval_id`` promoted from approval.* event payloads (asserted in
TS12 here); ``VALIDATION_ERROR`` maps to HTTP 422 across the whole REST
surface (the TS texts occasionally said 400).
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap, register_tools
from okto_nexus.application.governance import GovernanceService
from okto_nexus.domain.governance import (
    ApprovalRequired,
    Policy,
    Subject,
    Violation,
    applicable_policies,
    decide,
    validate_policy_form,
)
from okto_nexus.domain.policy import validate_agent_bindings
from okto_nexus.errors import ErrorCode, OktoNexusError


# --------------------------------------------------------------------------- #
# Harness (identical shape to test_governance.py)
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


def make_env(tmp_path, *, feature_hitl: bool = False):
    """Real bootstrap in a temp home + two registered agents + a workspace.

    Enforcement is binding-driven now (spec 80624c1a, D-FLAG): there is no
    feature_governance flag - a rule only bites once ATTACHED via :func:`_attach`.
    ``feature_hitl`` still gates whether a matching require_approval verdict is
    PROMOTED to an interception (spec 2948b2a2 BR6), read live.
    """
    env = {"OKTO_NEXUS_HOME": str(tmp_path / "home")}
    if feature_hitl:
        env["OKTO_NEXUS_FEATURE_HITL"] = "true"
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


def _attach(deps, agent_id, *, audience=None, governance=()):
    """Overwrite ``agent_id``'s bindings with ONE inline binding (the migration
    path's shape). Attaching is how a policy comes to BITE an agent now:
    enforcement composes the actor's bindings (D-FLAG replaced the flag). Each
    effective rule's synthetic id is ``inline#r<index-in-governance>``.
    """
    bindings = validate_agent_bindings(
        [{"source": "inline", "audience": audience, "governance": list(governance)}]
    )
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.policy_bindings.replace(uow, agent_id=agent_id, bindings=bindings)


def _require_approval_policy(deps, *, action: str = "message_create") -> dict:
    """Attach a single inline require_approval rule to alpha (the sender in every
    HITL scenario). The effective rule's synthetic id is ``inline#r0``, so that
    is what the interception envelope / approval.requested report as policy_id.
    """
    _attach(deps, "alpha", governance=[_rule(action, "require_approval")])
    return {"policy_id": "inline#r0"}


def _count(deps, table: str) -> int:
    conn = deps.connection_factory.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def _events(deps, event_type: str) -> list[dict]:
    conn = deps.connection_factory.get_connection()
    try:
        rows = conn.execute(
            "SELECT payload FROM events WHERE type = ? ORDER BY event_id",
            (event_type,),
        ).fetchall()
        return [json.loads(row["payload"]) for row in rows]
    finally:
        conn.close()


def _message_rows(deps) -> list:
    conn = deps.connection_factory.get_connection()
    try:
        return conn.execute(
            "SELECT from_agent_id, subject, body, channel_id, target "
            "FROM messages ORDER BY message_id"
        ).fetchall()
    finally:
        conn.close()


def _direct(agent_id: str) -> dict:
    return {"strategy": "direct", "agent_id": agent_id}


def _ws_id(tools, root: str) -> str:
    return _ok(tools["workspace_resolve"](project_root=root))["workspace_id"]


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


def _client(deps):
    """Operator-authenticated TestClient over the SAME deps (use via ``with``)."""
    from fastapi.testclient import TestClient

    from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
    from okto_nexus.application.auth import AgentKeyAuthService

    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    issued = ensure_operator_key(deps, auth)
    assert issued is not None, "expected the cold-start operator key"
    _, operator_key = issued
    client = TestClient(build_app(deps))
    client.headers.update({"x-api-key": operator_key})
    return client


def _issue_key(deps, agent_id: str) -> str:
    from okto_nexus.application.auth import AgentKeyAuthService

    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    with deps.connection_factory.unit_of_work() as uow:
        return auth.issue_key(uow, agent_id=agent_id)


# --------------------------------------------------------------------------- #
# TS1 - pure grammar + three-stage verdict (T1)
# --------------------------------------------------------------------------- #
def test_validate_policy_form_require_approval_happy_paths():
    # Binary and parameterless (FR1): no limit_value, no window, for BOTH
    # interceptable actions.
    for action in ("message_create", "handoff_create"):
        form = validate_policy_form(
            subject_kind="star", action=action, limit_kind="require_approval"
        )
        assert form["limit_kind"] == "require_approval"
        assert form["limit_value"] is None
        assert form["window"] is None


@pytest.mark.parametrize(
    "kwargs",
    [
        # parameterless: any limit_value / window is fail-closed
        {
            "subject_kind": "star",
            "action": "message_create",
            "limit_kind": "require_approval",
            "limit_value": 1,
        },
        {
            "subject_kind": "star",
            "action": "message_create",
            "limit_kind": "require_approval",
            "window": "1h",
        },
        # V1 keeps artifact_put out, and the broadcast hierarchy is reached
        # via message_create (FR1) - naming either action is fail-closed.
        {
            "subject_kind": "star",
            "action": "artifact_put",
            "limit_kind": "require_approval",
        },
        {
            "subject_kind": "star",
            "action": "broadcast",
            "limit_kind": "require_approval",
        },
    ],
)
def test_validate_policy_form_require_approval_fail_closed(kwargs):
    with pytest.raises(OktoNexusError) as ei:
        validate_policy_form(**kwargs)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


def test_decide_three_stage_verdict_and_precedence():
    deny = _policy("2026-01-03T00:00:00Z", "pol_deny")
    quota = _policy(
        "2026-01-02T00:00:00Z",
        "pol_quota",
        limit_kind="max_count",
        limit_value=1,
        window="1h",
    )
    ra_tie = _policy("2026-01-01T00:00:00Z", "pol_ra_a", limit_kind="require_approval")
    ra_old = _policy("2026-01-01T00:00:00Z", "pol_ra_b", limit_kind="require_approval")
    ra_new = _policy("2026-01-02T00:00:00Z", "pol_ra_c", limit_kind="require_approval")

    # Stage 1: a categorical deny beats everything, even though the
    # require_approval policies sort FIRST in (created_at, policy_id) order.
    everything = applicable_policies(
        [deny, quota, ra_new, ra_old, ra_tie], ALPHA, "message_create"
    )
    verdict = decide(everything, size_bytes=0, usage={"pol_quota": 99})
    assert isinstance(verdict, Violation)
    assert verdict.policy.policy_id == "pol_deny"

    # Stage 2: a VIOLATED quota still beats require_approval (BR8).
    no_deny = applicable_policies(
        [quota, ra_new, ra_old, ra_tie], ALPHA, "message_create"
    )
    verdict = decide(no_deny, size_bytes=0, usage={"pol_quota": 1})
    assert isinstance(verdict, Violation)
    assert verdict.policy.policy_id == "pol_quota"

    # Stage 3: only an action that would have PASSED is intercepted, and the
    # FIRST matching require_approval in (created_at, policy_id) order wins -
    # pol_ra_a beats pol_ra_b on the id tiebreak and pol_ra_c on created_at.
    verdict = decide(no_deny, size_bytes=0, usage={"pol_quota": 0})
    assert isinstance(verdict, ApprovalRequired)
    assert verdict.policy.policy_id == "pol_ra_a"

    # No require_approval in play -> plain allow stays None.
    quota_only = applicable_policies([quota], ALPHA, "message_create")
    assert decide(quota_only, size_bytes=0, usage={"pol_quota": 0}) is None
    assert decide([], size_bytes=0, usage={}) is None


# --------------------------------------------------------------------------- #
# TS2 - message interception: pending envelope, zero side effects (T2)
# --------------------------------------------------------------------------- #
def test_ts2_message_interception_returns_pending_and_persists_nothing(tmp_path):
    deps, tools, root = make_env(tmp_path, feature_hitl=True)
    pol = _require_approval_policy(deps)
    env = tools["message_create"](
        project_root=root,
        from_agent_id="alpha",
        subject="classified subject",
        body="classified body",
        target=_direct("beta"),
    )
    data = _ok(env)
    assert data["status"] == "pending_approval"
    approval_id = data["approval_id"]
    assert approval_id.startswith("apr_")
    assert data["action"] == "message_create"
    assert data["policy_id"] == pol["policy_id"]
    assert data["watch"] == {
        "stream": "workspace",
        "types": ["approval.granted", "approval.denied"],
        "approval_id": approval_id,
    }
    # feature_trace is OFF: no correlator key sneaks into the envelope.
    assert "trace_id" not in data

    # NOTHING executed: no message row, no delivery (beta's inbox is empty).
    assert _count(deps, "messages") == 0
    assert _count(deps, "message_deliveries") == 0
    assert _events(deps, "message.created") == []

    # approval.requested committed in the SAME UoW as the row (BR1), with
    # routing metadata ONLY - the exact-dict assert proves no subject/body.
    requested = _events(deps, "approval.requested")
    assert requested == [
        {
            "approval_id": approval_id,
            "action": "message_create",
            "agent_id": "alpha",
            "policy_id": pol["policy_id"],
        }
    ]

    # The persisted payload is COMPLETE and re-executable (BR1): resolved
    # project_root, full content, target echo - and never session secrets.
    assert _count(deps, "approvals") == 1
    detail = deps.approvals.get_approval(approval_id=approval_id)
    payload = detail["request_payload"]
    assert payload["kind"] == "message_create"
    kwargs = payload["kwargs"]
    assert kwargs["from_agent_id"] == "alpha"
    assert kwargs["subject"] == "classified subject"
    assert kwargs["body"] == "classified body"
    assert kwargs["target"] == {"strategy": "direct", "agent_id": "beta"}
    with deps.connection_factory.unit_of_work(write=False) as uow:
        ws = deps.repos.workspaces.get(uow, detail["workspace_id"])
    assert kwargs["project_root"] == ws.root_realpath
    assert "session_secret" not in kwargs
    assert "from_session_id" not in kwargs


# --------------------------------------------------------------------------- #
# TS3 - handoff interception; pendencies consume NO open-handoff budget (T2)
# --------------------------------------------------------------------------- #
def test_ts3_handoff_interception_and_open_quota_untouched(tmp_path):
    deps, tools, root = make_env(tmp_path, feature_hitl=True)
    # Both rules live in the SAME inline binding on alpha: the require_approval
    # only fires once the max_open_handoffs quota passes (verdict precedence).
    _attach(
        deps,
        "alpha",
        governance=[
            _rule("handoff_create", "require_approval"),
            _rule("handoff_create", "max_open_handoffs", limit_value=1),
        ],
    )

    def attempt(payload: str) -> dict:
        return tools["handoff_create"](
            project_root=root,
            from_agent_id="alpha",
            target=_direct("beta"),
            visibility="public",
            payload=payload,
        )

    first = _ok(attempt("one"))
    assert first["status"] == "pending_approval"
    assert first["action"] == "handoff_create"
    assert _count(deps, "handoffs") == 0
    assert _events(deps, "handoff.created") == []
    assert len(_events(deps, "approval.requested")) == 1

    # A pending interception holds NO open handoff: the max_open_handoffs
    # budget (limit 1) is untouched, so the second attempt passes the quota
    # stage and is intercepted again - never QUOTA_EXCEEDED.
    second = _ok(attempt("two"))
    assert second["status"] == "pending_approval"
    assert second["approval_id"] != first["approval_id"]
    assert _count(deps, "approvals") == 2
    assert _count(deps, "handoffs") == 0


# --------------------------------------------------------------------------- #
# TS4 - approve re-executes the persisted action verbatim (T3)
# --------------------------------------------------------------------------- #
def test_ts4_approve_executes_verbatim_as_the_original_sender(tmp_path):
    deps, tools, root = make_env(tmp_path, feature_hitl=True)
    _require_approval_policy(deps)
    pending = _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="plan",
            body="ship it",
            target=_direct("beta"),
        )
    )
    approval_id = pending["approval_id"]

    with _client(deps) as client:
        resp = client.post(
            f"/api/v1/approvals/{approval_id}/decision", json={"decision": "approve"}
        )
        assert resp.status_code == 200, resp.text
        result = resp.json()["data"]
    assert result["status"] == "approved"
    assert result["decided_by"] == "operator"
    message_id = result["executed_result"]["message_id"]
    assert message_id

    # The message exists verbatim, authored by ALPHA (never the operator),
    # with its delivery fanned out to beta.
    rows = _message_rows(deps)
    assert len(rows) == 1
    assert rows[0]["from_agent_id"] == "alpha"
    assert rows[0]["subject"] == "plan"
    assert rows[0]["body"] == "ship it"
    assert _count(deps, "message_deliveries") == 1
    assert len(_events(deps, "message.created")) == 1

    # approval.granted: metadata only (BR5), attributed to the decider.
    granted = _events(deps, "approval.granted")
    assert len(granted) == 1
    assert granted[0]["approval_id"] == approval_id
    assert granted[0]["decided_by"] == "operator"
    assert granted[0]["agent_id"] == "alpha"
    assert "subject" not in granted[0] and "body" not in granted[0]

    # The row became a receipt: approved + executed_result, payload intact.
    detail = deps.approvals.get_approval(approval_id=approval_id)
    assert detail["status"] == "approved"
    assert detail["decided_by"] == "operator"
    assert detail["decided_at"] is not None
    assert detail["executed_result"]["message_id"] == message_id
    assert detail["request_payload"]["kwargs"]["body"] == "ship it"

    # Structural equivalence: an IDENTICAL send without interception (flag
    # OFF) produces a row equal on every non-volatile column.
    deps.config.feature_hitl = False
    _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="plan",
            body="ship it",
            target=_direct("beta"),
        )
    )
    rows = _message_rows(deps)
    assert len(rows) == 2
    assert tuple(rows[0]) == tuple(rows[1])


# --------------------------------------------------------------------------- #
# TS5 - reject notifies the requester; nothing is ever executed (T3)
# --------------------------------------------------------------------------- #
def test_ts5_reject_with_and_without_justification(tmp_path):
    deps, tools, root = make_env(tmp_path, feature_hitl=True)
    _require_approval_policy(deps)

    def intercept(body: str) -> str:
        pending = _ok(
            tools["message_create"](
                project_root=root,
                from_agent_id="alpha",
                subject="s",
                body=body,
                target=_direct("beta"),
            )
        )
        return pending["approval_id"]

    first = intercept("attempt one")
    second = intercept("attempt two")

    with _client(deps) as client:
        with_just = client.post(
            f"/api/v1/approvals/{first}/decision",
            json={"decision": "reject", "justification": "too risky today"},
        )
        assert with_just.status_code == 200, with_just.text
        data = with_just.json()["data"]
        assert data["status"] == "rejected"
        assert data["justification"] == "too risky today"
        assert data["notified"] is True
        without_just = client.post(
            f"/api/v1/approvals/{second}/decision", json={"decision": "reject"}
        )
        assert without_just.status_code == 200, without_just.text
        data2 = without_just.json()["data"]
        assert data2["status"] == "rejected"
        assert "justification" not in data2
        assert data2["notified"] is True

    # The ONLY messages on the bus are the two operator->alpha notifications
    # (FR5) - the intercepted sends themselves never executed.
    rows = _message_rows(deps)
    assert len(rows) == 2
    assert {row["from_agent_id"] for row in rows} == {"operator"}
    by_subject = {row["subject"]: row for row in rows}
    first_note = by_subject[f"Approval {first}: message_create rejected"]
    assert "too risky today" in first_note["body"]
    second_note = by_subject[f"Approval {second}: message_create rejected"]
    assert "No justification provided" in second_note["body"]

    # approval.denied for both; the rows are closed but NEVER deleted (BR1).
    denied = _events(deps, "approval.denied")
    assert {event["approval_id"] for event in denied} == {first, second}
    ws = _ws_id(tools, root)
    rejected = deps.approvals.list_approvals(workspace_id=ws, status="rejected")
    assert {item["approval_id"] for item in rejected} == {first, second}
    assert deps.approvals.list_approvals(workspace_id=ws, status="pending") == []


# --------------------------------------------------------------------------- #
# TS6 - precedence end-to-end: deny/quota win; first require_approval (T4)
# --------------------------------------------------------------------------- #
def test_ts6_deny_and_quota_beat_interception(tmp_path):
    deps, tools, root = make_env(tmp_path, feature_hitl=True)

    def send(body: str) -> dict:
        return tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="s",
            body=body,
            target=_direct("beta"),
        )

    ra = _rule("message_create", "require_approval")
    # A deny composed ALONGSIDE the require_approval (rule index 1) wins over the
    # interception (BR8) and files nothing - creation order is moot.
    _attach(deps, "alpha", governance=[ra, _rule("message_create", "deny")])
    err = _err(send("b"), "POLICY_DENIED")
    assert err["details"]["policy_id"] == "inline#r1"
    assert _count(deps, "approvals") == 0

    # Swap the deny for a byte quota: the VIOLATED quota also wins over the
    # interception (BR8) and still files nothing.
    _attach(
        deps,
        "alpha",
        governance=[ra, _rule("message_create", "max_bytes", limit_value=4)],
    )
    err = _err(send("way past four bytes"), "QUOTA_EXCEEDED")
    assert err["details"]["policy_id"] == "inline#r1"
    assert _count(deps, "approvals") == 0
    assert _events(deps, "approval.requested") == []

    # With the quota gone the SAME send is finally intercepted.
    _attach(deps, "alpha", governance=[ra])
    assert _ok(send("b"))["status"] == "pending_approval"


def test_ts6_first_require_approval_policy_is_reported(tmp_path):
    deps, tools, root = make_env(tmp_path, feature_hitl=True)
    # Two require_approval rules in the inline binding: the FIRST in effective
    # order (rule index, then decide()'s deterministic tiebreak) is reported.
    _attach(
        deps,
        "alpha",
        governance=[
            _rule("message_create", "require_approval"),
            _rule("message_create", "require_approval"),
        ],
    )
    pending = _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="s",
            body="b",
            target=_direct("beta"),
        )
    )
    assert pending["status"] == "pending_approval"
    # Deterministic attribution: the FIRST matching rule (inline#r0), exactly as
    # decide() promises over the (source, rule_index) ordering.
    assert pending["policy_id"] == "inline#r0"


# --------------------------------------------------------------------------- #
# TS8 - negatives: double decision, revert-on-gate-failure, 404/422 (T4)
# --------------------------------------------------------------------------- #
def _intercept_message(tools, root: str, body: str) -> str:
    pending = _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="s",
            body=body,
            target=_direct("beta"),
        )
    )
    assert pending["status"] == "pending_approval"
    return pending["approval_id"]


def test_ts8_double_decision_conflicts_in_both_orders(tmp_path):
    deps, tools, root = make_env(tmp_path, feature_hitl=True)
    _require_approval_policy(deps)
    first = _intercept_message(tools, root, "one")
    second = _intercept_message(tools, root, "two")

    with _client(deps) as client:
        # approve then reject -> the FIRST decision is final (AC6).
        ok = client.post(
            f"/api/v1/approvals/{first}/decision", json={"decision": "approve"}
        )
        assert ok.status_code == 200, ok.text
        conflict = client.post(
            f"/api/v1/approvals/{first}/decision", json={"decision": "reject"}
        )
        assert conflict.status_code == 409, conflict.text
        details = conflict.json()["error"]["details"]
        assert details["status"] == "approved"
        assert details["decided_by"] == "operator"

        # reject then approve -> same guarantee in the other order.
        ok = client.post(
            f"/api/v1/approvals/{second}/decision", json={"decision": "reject"}
        )
        assert ok.status_code == 200, ok.text
        conflict = client.post(
            f"/api/v1/approvals/{second}/decision", json={"decision": "approve"}
        )
        assert conflict.status_code == 409, conflict.text
        assert conflict.json()["error"]["details"]["status"] == "rejected"

        # unknown id -> 404; unknown decision token -> fail-closed 422.
        missing = client.post(
            "/api/v1/approvals/apr_missing/decision", json={"decision": "approve"}
        )
        assert missing.status_code == 404
        third = _intercept_message(tools, root, "three")
        bad = client.post(
            f"/api/v1/approvals/{third}/decision", json={"decision": "maybe"}
        )
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "VALIDATION_ERROR"
    # The bad token decided NOTHING: the row is still pending.
    assert deps.approvals.get_approval(approval_id=third)["status"] == "pending"


def test_ts8_gate_failure_on_approve_reverts_to_pending(tmp_path):
    deps, tools, root = make_env(tmp_path, feature_hitl=True)
    ra = _rule("message_create", "require_approval")
    _attach(deps, "alpha", governance=[ra])
    approval_id = _intercept_message(tools, root, "blocked later")
    # A deny composed AFTER the interception: re-execution runs with EVERY
    # other gate live (BR2), so the approve surfaces the gate's REAL error.
    _attach(deps, "alpha", governance=[ra, _rule("message_create", "deny")])

    with _client(deps) as client:
        blocked = client.post(
            f"/api/v1/approvals/{approval_id}/decision", json={"decision": "approve"}
        )
        assert blocked.status_code == 403, blocked.text
        assert blocked.json()["error"]["code"] == "POLICY_DENIED"
        # Honest revert (BR3): approved must only describe a CONSUMED
        # execution, so the row went back to pending and stays decidable.
        assert deps.approvals.get_approval(approval_id=approval_id)["status"] == (
            "pending"
        )
        assert _count(deps, "messages") == 0

        # Detaching the deny (keeping require_approval) frees the retry; the
        # re-execution bypasses re-interception (BR2 one-shot).
        _attach(deps, "alpha", governance=[ra])
        retry = client.post(
            f"/api/v1/approvals/{approval_id}/decision", json={"decision": "approve"}
        )
        assert retry.status_code == 200, retry.text
        assert retry.json()["data"]["status"] == "approved"
    assert _count(deps, "messages") == 1


# --------------------------------------------------------------------------- #
# TS7 - D4 gating: flag OFF is invisible; live flip; decidable with OFF (T5)
# --------------------------------------------------------------------------- #
#: Volatile keys masked before the byte-identity comparison - ids/timestamps
#: differ per send by construction, everything else must match exactly.
_VOLATILE_KEYS = frozenset(
    {"message_id", "created_at", "delivered_at", "delivery_id", "event_id"}
)


def _mask_volatile(value):
    if isinstance(value, dict):
        return {
            key: ("?" if key in _VOLATILE_KEYS else _mask_volatile(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_mask_volatile(item) for item in value]
    return value


def test_ts7_flag_off_accept_and_ignore_and_live_flip(tmp_path):
    deps, tools, root = make_env(tmp_path, feature_hitl=False)

    def send() -> dict:
        return tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="s",
            body="b",
            target=_direct("beta"),
        )

    # Baseline BEFORE any policy exists == a policy-free bus.
    baseline = _ok(send())
    _require_approval_policy(deps)

    # hitl OFF: the ApprovalRequired verdict is dropped inside enforce()
    # (D4 accept-and-ignore) - the response is byte-identical to the
    # baseline once the per-send volatile ids are masked.
    with_policy = _ok(send())
    assert json.dumps(_mask_volatile(with_policy), sort_keys=True) == json.dumps(
        _mask_volatile(baseline), sort_keys=True
    )
    assert _count(deps, "approvals") == 0
    assert _events(deps, "approval.requested") == []
    assert _count(deps, "messages") == 2

    # Live flip (D6): a settings PATCH mutates the shared config in place -
    # the VERY NEXT send is intercepted, no restart.
    deps.config.feature_hitl = True
    pending = _ok(send())
    assert pending["status"] == "pending_approval"
    assert _count(deps, "messages") == 2

    # A pendency created while ON stays decidable with the flag OFF (BR6):
    # only the interception is gated, never the queue or the decision.
    deps.config.feature_hitl = False
    result = deps.approvals.decide(
        approval_id=pending["approval_id"], decision="approve", decided_by="operator"
    )
    assert result["status"] == "approved"
    assert result["executed_result"]["message_id"]
    assert _count(deps, "messages") == 3


# --------------------------------------------------------------------------- #
# TS9 - operator identity: seeding, reservation, steering, cold-start (T6)
# --------------------------------------------------------------------------- #
def test_ts9_operator_seeded_once_and_name_reserved(tmp_path):
    deps, tools, root = make_env(tmp_path)
    # bootstrap seeded the identity; a SECOND bootstrap on the same home is
    # create-if-missing: still exactly one row, role untouched (FR6/BR4).
    deps2 = bootstrap({"OKTO_NEXUS_HOME": str(tmp_path / "home")}, [])
    conn = deps2.connection_factory.get_connection()
    try:
        rows = conn.execute(
            "SELECT agent_id, role FROM agents WHERE agent_id = 'operator'"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0]["role"] == "operator"

    # Reserved on the public registration path, every spelling (BR4).
    for name in ("operator", "Operator", " OPERATOR "):
        err = _err(tools["agent_register"](agent_id=name), "VALIDATION_ERROR")
        assert err["details"]["reserved"] == "operator"


def test_ts9_steering_is_operator_only_and_unprivileged(tmp_path):
    deps, tools, root = make_env(tmp_path)
    ws = _ws_id(tools, root)

    with _client(deps) as client:
        # The reserved name is fail-closed over REST registration too.
        reserved = client.post(
            "/api/v1/agents", json={"agent_id": "Operator", "role": "x"}
        )
        assert reserved.status_code == 422

        # Authenticated operator steers: a NORMAL direct message from the
        # operator identity lands in alpha's inbox (FR9).
        sent = client.post(
            "/api/v1/steering/messages",
            json={"workspace": ws, "to_agent_id": "alpha", "body": "focus on tests"},
        )
        assert sent.status_code == 200, sent.text
        assert sent.json()["data"]["message_id"]
        rows = _message_rows(deps)
        assert len(rows) == 1
        assert rows[0]["from_agent_id"] == "operator"
        assert rows[0]["subject"] == "Operator steering"  # the default subject
        assert rows[0]["body"] == "focus on tests"

        # Ghost recipient -> 404; empty body -> fail-closed 422; an
        # UNREGISTERED workspace id -> 404 (never a silent create).
        ghost = client.post(
            "/api/v1/steering/messages",
            json={"workspace": ws, "to_agent_id": "ghost", "body": "hi"},
        )
        assert ghost.status_code == 404
        empty = client.post(
            "/api/v1/steering/messages",
            json={"workspace": ws, "to_agent_id": "alpha", "body": ""},
        )
        assert empty.status_code == 422
        bad_ws = client.post(
            "/api/v1/steering/messages",
            json={"workspace": "ws_nope", "to_agent_id": "alpha", "body": "hi"},
        )
        assert bad_ws.status_code == 404

        # A third party's key is refused: the surface is operator-only.
        alpha_key = _issue_key(deps, "alpha")
        forbidden = client.post(
            "/api/v1/steering/messages",
            json={"workspace": ws, "to_agent_id": "beta", "body": "hi"},
            headers={"x-api-key": alpha_key},
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "PERMISSION_DENIED"
    assert _count(deps, "messages") == 1


def test_ts9_ensure_operator_key_cold_start_only(tmp_path):
    from okto_nexus.adapters.inbound.http.app import ensure_operator_key
    from okto_nexus.application.auth import AgentKeyAuthService

    deps = bootstrap({"OKTO_NEXUS_HOME": str(tmp_path / "home")}, [])
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    issued = ensure_operator_key(deps, auth)
    assert issued is not None
    agent_id, plaintext = issued
    assert agent_id == "operator"
    assert plaintext
    # Never reissued silently once ANY key exists (BR7).
    assert ensure_operator_key(deps, auth) is None


# --------------------------------------------------------------------------- #
# TS10 - operator queue over REST: scoping, filters, BR5 - flag OFF (T6)
# --------------------------------------------------------------------------- #
def test_ts10_queue_is_workspace_scoped_and_readable_with_flags_off(tmp_path):
    deps, tools, root = make_env(tmp_path, feature_hitl=True)
    _require_approval_policy(deps)
    project2 = tmp_path / "project2"
    project2.mkdir(exist_ok=True)
    root2 = str(project2)
    _ok(tools["workspace_resolve"](project_root=root2))
    w1 = _ws_id(tools, root)
    w2 = _ws_id(tools, root2)

    def intercept(send_root: str, body: str) -> str:
        pending = _ok(
            tools["message_create"](
                project_root=send_root,
                from_agent_id="alpha",
                subject="classified subject",
                body=body,
                target=_direct("beta"),
            )
        )
        return pending["approval_id"]

    ids_w1 = [intercept(root, f"classified body {i}") for i in range(3)]
    id_w2 = intercept(root2, "classified other")

    # EVERYTHING below runs with feature_hitl OFF: queue reads and decisions
    # are ungated (BR6) - only the interception needed the flag.
    deps.config.feature_hitl = False

    with _client(deps) as client:
        rejected = client.post(
            f"/api/v1/approvals/{ids_w1[2]}/decision",
            json={"decision": "reject", "justification": "no"},
        )
        assert rejected.status_code == 200, rejected.text

        # Default filter = pending only, W1 only, oldest-first.
        resp = client.get("/api/v1/approvals", params={"workspace": w1})
        assert resp.status_code == 200, resp.text
        items = resp.json()["data"]["items"]
        assert {item["approval_id"] for item in items} == set(ids_w1[:2])
        assert all(item["status"] == "pending" for item in items)
        assert [item["approval_id"] for item in items] == [
            item["approval_id"]
            for item in sorted(items, key=lambda i: (i["created_at"], i["approval_id"]))
        ]
        # Summaries carry routing metadata only, never content (BR5).
        for item in items:
            meta = item["payload_meta"]
            assert meta["kind"] == "message_create"
            assert meta["byte_size"] > 0
            assert meta["target"] == {"strategy": "direct", "agent_id": "beta"}
        assert "classified" not in json.dumps(items)

        # status=all folds the decided row back in; W2 never leaks into W1.
        all_items = client.get(
            "/api/v1/approvals", params={"workspace": w1, "status": "all"}
        ).json()["data"]["items"]
        assert {item["approval_id"] for item in all_items} == set(ids_w1)
        w2_items = client.get("/api/v1/approvals", params={"workspace": w2}).json()[
            "data"
        ]["items"]
        assert [item["approval_id"] for item in w2_items] == [id_w2]

        # Bogus status filter -> fail-closed 422; unknown id -> 404.
        bogus = client.get(
            "/api/v1/approvals", params={"workspace": w1, "status": "bogus"}
        )
        assert bogus.status_code == 422
        assert bogus.json()["error"]["code"] == "VALIDATION_ERROR"
        assert client.get("/api/v1/approvals/apr_missing").status_code == 404

        # Detail is the ONE surface with the intact payload (BR5).
        detail = client.get(f"/api/v1/approvals/{ids_w1[0]}").json()["data"]
        assert detail["workspace_id"] == w1
        assert detail["request_payload"]["kwargs"]["body"] == "classified body 0"

        # Any non-operator key is refused on all three surfaces.
        alpha_key = _issue_key(deps, "alpha")
        hdrs = {"x-api-key": alpha_key}
        assert (
            client.get(
                "/api/v1/approvals", params={"workspace": w1}, headers=hdrs
            ).status_code
            == 403
        )
        assert (
            client.get(f"/api/v1/approvals/{ids_w1[0]}", headers=hdrs).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/approvals/{ids_w1[0]}/decision",
                json={"decision": "approve"},
                headers=hdrs,
            ).status_code
            == 403
        )


# --------------------------------------------------------------------------- #
# TS12 - the HITL correlator survives every projection profile (T7)
# --------------------------------------------------------------------------- #
def test_ts12_approval_id_promoted_in_every_projection_profile():
    from okto_nexus.adapters.inbound.mcp.projection import (
        PROFILE_FULL,
        PROFILES,
        project_event,
    )

    raw = {
        "event_id": 7,
        "type": "approval.granted",
        "actor_agent_id": "operator",
        "created_at": "2026-07-04T00:00:00Z",
        "stream": "workspace",
        "payload": {
            "approval_id": "apr_x",
            "action": "message_create",
            "agent_id": "alpha",
            "policy_id": "pol_1",
            "decided_by": "operator",
        },
    }
    # The pending ENVELOPE is a tool response (never projected - declared
    # drift); the projection guarantee is on the approval.* EVENTS: the
    # blocked requester correlates the decision by approval_id, so it must
    # survive even the aggressive summary profile.
    for profile in PROFILES:
        projected, _omitted, _truncated = project_event(raw, profile)
        if profile == PROFILE_FULL:
            assert projected["payload"]["approval_id"] == "apr_x"
        else:
            assert projected["approval_id"] == "apr_x"
