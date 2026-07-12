"""Handoff verification (spec c692da7e, R-I4) - scenarios TS0..TS11.

T1/TS0 (this section): the PURE domain layer - the VERIFYING state machine,
the fail-closed contract grammar (acceptance criteria / verify_by / verdict)
and the pure verifier-eligibility helpers. No I/O: everything here imports
``okto_nexus.domain.handoff`` only (the import-boundary test keeps it pure).

Later sections (T2..T7) add the application/REST scenarios over the real
bootstrap harness (temp-home make_env, the test_hitl.py pattern).
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import itertools
import json

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap, register_tools
from okto_nexus.domain.handoff import (
    EVENT_VERIFICATION_FAILED,
    EVENT_VERIFICATION_REQUESTED,
    MAX_ACCEPTANCE_CRITERIA,
    MAX_CRITERION_LENGTH,
    MAX_VERIFICATION_FEEDBACK_LENGTH,
    STATUS_CANCELLED,
    STATUS_CLAIMED,
    STATUS_COMPLETED,
    STATUS_OPEN,
    STATUS_REJECTED,
    STATUS_VERIFYING,
    TERMINAL_STATUSES,
    V1_STATUSES,
    VALID_VERDICTS,
    VERIFY_BY_KINDS,
    can_transition,
    is_degenerate_self_claim,
    is_eligible_verifier,
    static_verifier_for,
    validate_acceptance_criteria,
    validate_verdict,
    validate_verify_by,
)
from okto_nexus.domain.policy import validate_agent_bindings
from okto_nexus.errors import ErrorCode, OktoNexusError


def _rejects(fn, *args, contains: str = "") -> OktoNexusError:
    """Assert ``fn(*args)`` raises VALIDATION_ERROR mentioning ``contains``."""
    with pytest.raises(OktoNexusError) as exc_info:
        fn(*args)
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
    if contains:
        assert contains in exc_info.value.message, exc_info.value.message
    return exc_info.value


# --------------------------------------------------------------------------- #
# TS0 - state machine
# --------------------------------------------------------------------------- #
def test_verifying_transition_pairs_are_exactly_three():
    # EXHAUSTIVE sweep of every ordered V1 pair involving VERIFYING: the only
    # valid ones are the three the spec names (AC/TS0) - anything else
    # (OPEN->VERIFYING, VERIFYING->OPEN/REJECTED/CANCELLED, ...) is invalid.
    allowed = {
        (STATUS_CLAIMED, STATUS_VERIFYING),
        (STATUS_VERIFYING, STATUS_COMPLETED),
        (STATUS_VERIFYING, STATUS_CLAIMED),
    }
    for src, dst in itertools.product(sorted(V1_STATUSES), sorted(V1_STATUSES)):
        if STATUS_VERIFYING not in (src, dst):
            continue
        assert can_transition(src, dst) == ((src, dst) in allowed), (src, dst)


def test_verifying_is_not_terminal_and_terminals_stay_dead_ends():
    assert STATUS_VERIFYING in V1_STATUSES
    assert STATUS_VERIFYING not in TERMINAL_STATUSES
    # The pre-I4 terminal set is untouched, and no terminal grew an exit -
    # including into VERIFYING.
    assert TERMINAL_STATUSES == {STATUS_COMPLETED, STATUS_REJECTED, STATUS_CANCELLED}
    for terminal in TERMINAL_STATUSES:
        for dst in V1_STATUSES:
            assert not can_transition(terminal, dst), (terminal, dst)


def test_creation_still_lands_on_open_only():
    # can_transition(None/"") models creation: VERIFYING can never be born.
    for src in (None, ""):
        assert can_transition(src, STATUS_OPEN)
        assert not can_transition(src, STATUS_VERIFYING)


def test_verification_event_constants():
    assert EVENT_VERIFICATION_REQUESTED == "handoff.verification_requested"
    assert EVENT_VERIFICATION_FAILED == "handoff.verification_failed"


# --------------------------------------------------------------------------- #
# TS0 - acceptance_criteria grammar (BR8: fail-closed, bordas 1/20/500)
# --------------------------------------------------------------------------- #
def test_acceptance_criteria_happy_paths():
    # Single item, strip applied, order preserved.
    assert validate_acceptance_criteria(["  a  "]) == ["a"]
    many = [f"criterion {i}" for i in range(MAX_ACCEPTANCE_CRITERIA)]
    assert validate_acceptance_criteria(many) == many
    # Exactly MAX_CRITERION_LENGTH chars passes (the limit is inclusive).
    edge = "x" * MAX_CRITERION_LENGTH
    assert validate_acceptance_criteria([edge]) == [edge]
    # Order is preserved verbatim, never sorted or deduped-in-place.
    assert validate_acceptance_criteria(["b", "a"]) == ["b", "a"]


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        ("not a list", "must be a list"),
        ({"0": "x"}, "must be a list"),
        (None, "must be a list"),
        ([], "cannot be empty"),
        ([f"c{i}" for i in range(MAX_ACCEPTANCE_CRITERIA + 1)], "at most"),
        ([42], "non-empty string"),
        ([""], "non-empty string"),
        (["   "], "non-empty string"),
        (["x" * (MAX_CRITERION_LENGTH + 1)], "exceeds"),
        (["same", "same"], "duplicate"),
        # Duplicates are detected AFTER strip: "a" and " a " collide.
        (["a", " a "], "duplicate"),
    ],
)
def test_acceptance_criteria_rejections(raw, fragment):
    err = _rejects(validate_acceptance_criteria, raw, contains=fragment)
    assert err.code == ErrorCode.VALIDATION_ERROR


# --------------------------------------------------------------------------- #
# TS0 - verify_by grammar (exactly three forms, no extras)
# --------------------------------------------------------------------------- #
def test_verify_by_happy_paths():
    assert VERIFY_BY_KINDS == {"creator", "agent", "capability"}
    assert validate_verify_by({"kind": "creator"}) == {"kind": "creator"}
    assert validate_verify_by({"kind": "agent", "agent_id": " qa "}) == {
        "kind": "agent",
        "agent_id": "qa",
    }
    assert validate_verify_by({"kind": "capability", "capability": "review"}) == {
        "kind": "capability",
        "capability": "review",
    }
    # kind is case-insensitive and stripped on input, canonical on output.
    assert validate_verify_by({"kind": " Creator "}) == {"kind": "creator"}


@pytest.mark.parametrize(
    "raw",
    [
        "creator",  # not an object
        ["creator"],
        {},  # kind missing
        {"kind": "owner"},  # unknown kind
        {"kind": 3},
        {"kind": "creator", "agent_id": "x"},  # extra field on creator
        {"kind": "agent"},  # missing agent_id
        {"kind": "agent", "agent_id": ""},
        {"kind": "agent", "agent_id": "a", "capability": "c"},  # cross-field
        {"kind": "capability"},  # missing capability
        {"kind": "capability", "capability": "  "},
    ],
)
def test_verify_by_rejections(raw):
    _rejects(validate_verify_by, raw)


# --------------------------------------------------------------------------- #
# TS0 - verdict grammar (closed lowercase vocabulary; feedback fail-only)
# --------------------------------------------------------------------------- #
def test_verdict_happy_paths():
    assert VALID_VERDICTS == {"pass", "fail"}
    assert validate_verdict("pass", None) == ("pass", None)
    assert validate_verdict("fail", None) == ("fail", None)
    assert validate_verdict("fail", "needs a summary") == ("fail", "needs a summary")
    # Empty-string feedback is treated as absent, on both verdicts.
    assert validate_verdict("pass", "") == ("pass", None)
    assert validate_verdict("fail", "") == ("fail", None)
    edge = "f" * MAX_VERIFICATION_FEEDBACK_LENGTH
    assert validate_verdict("fail", edge) == ("fail", edge)


@pytest.mark.parametrize(
    ("verdict", "feedback", "fragment"),
    [
        ("PASS", None, "verdict must be one of"),  # uppercase is NOT accepted
        ("Fail", None, "verdict must be one of"),
        ("approve", None, "verdict must be one of"),
        (None, None, "verdict must be one of"),
        ("pass", "looks great", "only accepted with verdict 'fail'"),
        ("fail", 42, "must be a string"),
        ("fail", "x" * (MAX_VERIFICATION_FEEDBACK_LENGTH + 1), "exceeds"),
    ],
)
def test_verdict_rejections(verdict, feedback, fragment):
    _rejects(validate_verdict, verdict, feedback, contains=fragment)


# --------------------------------------------------------------------------- #
# TS0 - pure eligibility: caller x claimed_by x verify_by matrix
# --------------------------------------------------------------------------- #
def _may_verify(caller, *, claimed_by, creator, verify_by, caps=()) -> bool:
    # The composed domain rule in the order the application applies it (FR5):
    # anti-self-verification WINS over eligibility, then the descriptor
    # resolves dynamically. is_eligible_verifier itself deliberately does NOT
    # ban the claimant (its docstring makes the caller responsible).
    if caller == claimed_by:
        return False
    return is_eligible_verifier(
        caller, creator=creator, verify_by=verify_by, caller_capabilities=caps
    )


def test_eligibility_matrix_anti_self_verification_always_wins():
    # The claimant is banned under EVERY descriptor kind - even as the named
    # agent, the creator, or the only capability holder (BR3).
    for verify_by, caps in (
        ({"kind": "creator"}, ()),
        ({"kind": "agent", "agent_id": "beta"}, ()),
        ({"kind": "capability", "capability": "review"}, ("review",)),
    ):
        assert not _may_verify(
            "beta",
            claimed_by="beta",
            creator="beta",
            verify_by=verify_by,
            caps=caps,
        ), verify_by


def test_eligibility_matrix_by_kind():
    # creator: only the creator qualifies.
    creator_kind = {"kind": "creator"}
    assert _may_verify(
        "alpha", claimed_by="beta", creator="alpha", verify_by=creator_kind
    )
    assert not _may_verify(
        "gamma", claimed_by="beta", creator="alpha", verify_by=creator_kind
    )
    # agent: only the exact named agent.
    agent_kind = {"kind": "agent", "agent_id": "gamma"}
    assert _may_verify(
        "gamma", claimed_by="beta", creator="alpha", verify_by=agent_kind
    )
    assert not _may_verify(
        "alpha", claimed_by="beta", creator="alpha", verify_by=agent_kind
    )
    # capability: whoever advertises it AT VERIFY TIME (dynamic, claim-style).
    cap_kind = {"kind": "capability", "capability": "review"}
    assert _may_verify(
        "gamma",
        claimed_by="beta",
        creator="alpha",
        verify_by=cap_kind,
        caps=("review",),
    )
    assert not _may_verify(
        "gamma",
        claimed_by="beta",
        creator="alpha",
        verify_by=cap_kind,
        caps=("deploy",),
    )
    assert not _may_verify(
        "gamma", claimed_by="beta", creator="alpha", verify_by=cap_kind
    )
    # Unknown kind (defensive): never eligible.
    assert not is_eligible_verifier(
        "alpha", creator="alpha", verify_by={"kind": "boss"}
    )


def test_static_verifier_resolution():
    assert static_verifier_for({"kind": "creator"}, "alpha") == "alpha"
    assert static_verifier_for({"kind": "agent", "agent_id": "qa"}, "alpha") == "qa"
    # capability resolves dynamically at verify time: statically unknown.
    assert (
        static_verifier_for({"kind": "capability", "capability": "review"}, "alpha")
        is None
    )


def test_degenerate_self_claim_detection():
    # direct target aimed at the statically resolved verifier: unsolvable,
    # must be rejected at creation (BR3).
    assert is_degenerate_self_claim(
        {"strategy": "direct", "agent_id": "qa"},
        creator="alpha",
        verify_by={"kind": "agent", "agent_id": "qa"},
    )
    assert is_degenerate_self_claim(
        {"strategy": "direct", "agent_id": "alpha"},
        creator="alpha",
        verify_by={"kind": "creator"},
    )
    # direct at someone else: solvable.
    assert not is_degenerate_self_claim(
        {"strategy": "direct", "agent_id": "beta"},
        creator="alpha",
        verify_by={"kind": "agent", "agent_id": "qa"},
    )
    # capability descriptor is dynamic - never statically degenerate.
    assert not is_degenerate_self_claim(
        {"strategy": "direct", "agent_id": "beta"},
        creator="alpha",
        verify_by={"kind": "capability", "capability": "review"},
    )
    # Broad targets resolve claimants dynamically: policed at verify time.
    assert not is_degenerate_self_claim(
        {"strategy": "broadcast"},
        creator="alpha",
        verify_by={"kind": "creator"},
    )


# --------------------------------------------------------------------------- #
# Harness for TS1+ (identical shape to test_hitl.py / test_governance.py):
# the REAL bootstrap in a temp home with feature_verification ON, tools
# registered through the same path both MCP transports mount, three agents
# and a catalogued "review" capability.
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


def make_env(tmp_path, *, verification: bool = True, extra: dict | None = None):
    """Real bootstrap + alpha/beta/gamma; gamma advertises 'review'."""
    env = {"OKTO_NEXUS_HOME": str(tmp_path / "home")}
    if verification:
        env["OKTO_NEXUS_FEATURE_VERIFICATION"] = "true"
    env.update(extra or {})
    deps = bootstrap(env, [])
    server = FakeServer()
    register_tools(server, deps)
    tools = server.tools
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    root = str(project)
    _ok(tools["workspace_resolve"](project_root=root))
    # The capability catalog is fail-closed (migration 014): seed the name
    # BEFORE an agent may announce it or a verify_by descriptor may cite it.
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.capability_catalog.create(uow, name="review")
    _ok(tools["agent_register"](agent_id="alpha", role="builder"))
    _ok(tools["agent_register"](agent_id="beta", role="executor"))
    _ok(
        tools["agent_register"](
            agent_id="gamma", role="reviewer", capabilities=["review"]
        )
    )
    return deps, tools, root


def _count(deps, table: str) -> int:
    conn = deps.connection_factory.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def _row(deps, handoff_id: str):
    conn = deps.connection_factory.get_connection()
    try:
        return conn.execute(
            "SELECT acceptance_criteria, verify_by, verification_feedback, status "
            "FROM handoffs WHERE handoff_id = ?",
            (handoff_id,),
        ).fetchone()
    finally:
        conn.close()


def _direct(agent_id: str) -> dict:
    return {"strategy": "direct", "agent_id": agent_id}


def _create(tools, root, *, from_agent="alpha", target=None, **kwargs) -> dict:
    return tools["handoff_create"](
        project_root=root,
        from_agent_id=from_agent,
        target=target if target is not None else _direct("beta"),
        visibility="public",
        **kwargs,
    )


def _rule(action, limit_kind, *, limit_value=None, window=None) -> dict:
    """One subject-less governance rule for an inline binding (spec 80624c1a)."""
    rule: dict = {"action": action, "limit_kind": limit_kind}
    if limit_value is not None:
        rule["limit_value"] = limit_value
    if window is not None:
        rule["window"] = window
    return rule


def _attach(deps, agent_id, *, governance=()):
    """Overwrite ``agent_id``'s bindings with ONE inline binding. Enforcement is
    binding-driven now (D-FLAG): attaching is the only way a rule bites."""
    bindings = validate_agent_bindings(
        [{"source": "inline", "governance": list(governance)}]
    )
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.policy_bindings.replace(uow, agent_id=agent_id, bindings=bindings)


# --------------------------------------------------------------------------- #
# TS1 - verifiable create: persistence, materialised default and exposure
# --------------------------------------------------------------------------- #
def test_ts1_create_materialises_creator_default_and_persists_order(tmp_path):
    deps, tools, root = make_env(tmp_path)
    criteria = ["has b", "has a"]  # deliberately unsorted: order is preserved
    created = _ok(_create(tools, root, acceptance_criteria=criteria))
    assert created["acceptance_criteria"] == criteria
    # verify_by omitted with criteria present -> {kind: creator} MATERIALISED
    # at write time (BR8): explicit in the response AND in the row, never an
    # inferred-on-read default.
    assert created["verify_by"] == {"kind": "creator"}
    row = _row(deps, created["handoff_id"])
    assert json.loads(row["acceptance_criteria"]) == criteria
    assert json.loads(row["verify_by"]) == {"kind": "creator"}
    assert row["verification_feedback"] is None


def test_ts1_create_persists_agent_and_capability_descriptors(tmp_path):
    deps, tools, root = make_env(tmp_path)
    by_agent = _ok(
        _create(
            tools,
            root,
            acceptance_criteria=["works"],
            verify_by={"kind": "agent", "agent_id": "gamma"},
        )
    )
    assert json.loads(_row(deps, by_agent["handoff_id"])["verify_by"]) == {
        "kind": "agent",
        "agent_id": "gamma",
    }
    by_cap = _ok(
        _create(
            tools,
            root,
            acceptance_criteria=["works"],
            verify_by={"kind": "capability", "capability": "review"},
        )
    )
    assert json.loads(_row(deps, by_cap["handoff_id"])["verify_by"]) == {
        "kind": "capability",
        "capability": "review",
    }


def test_ts1_get_exposes_contract_and_plain_handoff_omits_fields(tmp_path):
    deps, tools, root = make_env(tmp_path)
    verifiable = _ok(_create(tools, root, acceptance_criteria=["has a title"]))
    got = _ok(
        tools["handoff_get"](
            project_root=root,
            handoff_id=verifiable["handoff_id"],
            agent_id="alpha",
        )
    )
    assert got["acceptance_criteria"] == ["has a title"]
    assert got["verify_by"] == {"kind": "creator"}
    assert "verification_feedback" not in got  # NULL -> omitted, never null
    # A handoff created WITHOUT criteria never grows the fields: omitted (not
    # null) in the create response, the get response and the row (BR1).
    plain = _ok(_create(tools, root))
    for field in ("acceptance_criteria", "verify_by", "verification_feedback"):
        assert field not in plain
    plain_got = _ok(
        tools["handoff_get"](
            project_root=root, handoff_id=plain["handoff_id"], agent_id="alpha"
        )
    )
    for field in ("acceptance_criteria", "verify_by", "verification_feedback"):
        assert field not in plain_got
    row = _row(deps, plain["handoff_id"])
    assert row["acceptance_criteria"] is None and row["verify_by"] is None


def test_ts1_list_available_keeps_the_lean_pre_i4_shape(tmp_path):
    _, tools, root = make_env(tmp_path)
    created = _ok(_create(tools, root, acceptance_criteria=["works"]))
    page = _ok(tools["handoff_list_available"](project_root=root, agent_id="beta"))
    mine = [h for h in page["handoffs"] if h["handoff_id"] == created["handoff_id"]]
    assert mine, page
    # FR6 names handoff_get + the REST serializers only: the discovery list
    # keeps its lean pre-I4 shape (the full contract is one get away).
    for field in ("acceptance_criteria", "verify_by", "verification_feedback"):
        assert field not in mine[0]


# --------------------------------------------------------------------------- #
# TS2 - fail-closed grammar at creation: every violation rejected, no effects
# --------------------------------------------------------------------------- #
_TS2_VIOLATIONS: list = [
    ("empty-list", {"acceptance_criteria": []}, "cannot be empty"),
    ("21-items", {"acceptance_criteria": [f"c{i}" for i in range(21)]}, "at most"),
    ("blank-item", {"acceptance_criteria": ["   "]}, "non-empty string"),
    ("501-chars", {"acceptance_criteria": ["x" * 501]}, "exceeds"),
    ("non-string-item", {"acceptance_criteria": [42]}, "non-empty string"),
    ("exact-duplicate", {"acceptance_criteria": ["same", "same"]}, "exact duplicate"),
    (
        "unknown-kind",
        {"acceptance_criteria": ["ok"], "verify_by": {"kind": "owner"}},
        "Unknown verify_by kind",
    ),
    (
        "extra-field",
        {
            "acceptance_criteria": ["ok"],
            "verify_by": {"kind": "creator", "agent_id": "alpha"},
        },
        "unsupported field",
    ),
    (
        "ghost-agent",
        {
            "acceptance_criteria": ["ok"],
            "verify_by": {"kind": "agent", "agent_id": "ghost"},
        },
        "not a registered agent",
    ),
    (
        "ghost-capability",
        {
            "acceptance_criteria": ["ok"],
            "verify_by": {"kind": "capability", "capability": "ghost-cap"},
        },
        "unregistered capability",
    ),
    (
        "verify-by-alone",
        {"verify_by": {"kind": "creator"}},
        "requires acceptance_criteria",
    ),
]


def test_ts2_grammar_violations_reject_with_zero_side_effects(tmp_path):
    deps, tools, root = make_env(tmp_path)
    handoffs_before = _count(deps, "handoffs")
    events_before = _count(deps, "events")
    for label, kwargs, fragment in _TS2_VIOLATIONS:
        err = _err(_create(tools, root, **kwargs), "VALIDATION_ERROR")
        assert fragment in err["message"], (label, err["message"])
    # Degenerate self-claims (BR3): the statically resolved verifier is the
    # only possible claimant - rejected at creation, in both spellings
    # (explicit agent descriptor AND the materialised creator default).
    err = _err(
        _create(
            tools,
            root,
            acceptance_criteria=["ok"],
            verify_by={"kind": "agent", "agent_id": "beta"},
        ),
        "VALIDATION_ERROR",
    )
    assert "statically unsatisfiable" in err["message"], err["message"]
    err = _err(
        _create(
            tools,
            root,
            target=_direct("alpha"),
            acceptance_criteria=["ok"],
            # verify_by omitted: the creator default resolves alpha, who is
            # also the only possible claimant of a direct-to-alpha handoff.
        ),
        "VALIDATION_ERROR",
    )
    assert "statically unsatisfiable" in err["message"], err["message"]
    # The WHOLE battery left the store untouched: no rows, no events.
    assert _count(deps, "handoffs") == handoffs_before
    assert _count(deps, "events") == events_before


# --------------------------------------------------------------------------- #
# TS3 - flag gating: OFF rejects the new params fail-closed; without them the
# bus is byte-identical ON x OFF; a contract created ON stays decidable OFF
# --------------------------------------------------------------------------- #
_VOLATILE_KEYS = frozenset(
    {
        "handoff_id",
        "created_at",
        "updated_at",
        "lease_expires_at",
        "event_id",
        "delivered_at",
    }
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


def test_ts3_flag_off_rejects_verification_params_fail_closed(tmp_path):
    deps, tools, root = make_env(tmp_path, verification=False)
    handoffs_before = _count(deps, "handoffs")
    events_before = _count(deps, "events")
    # BR2 - the deliberate EXCEPTION to the program's D4 accept-and-ignore:
    # silently dropping a verification contract would hand the creator a
    # false quality guarantee, so OFF rejects BOTH parameters loudly.
    err = _err(_create(tools, root, acceptance_criteria=["works"]), "VALIDATION_ERROR")
    assert "feature_verification" in err["message"], err["message"]
    err = _err(_create(tools, root, verify_by={"kind": "creator"}), "VALIDATION_ERROR")
    assert "feature_verification" in err["message"], err["message"]
    assert _count(deps, "handoffs") == handoffs_before
    assert _count(deps, "events") == events_before


def test_ts3_plain_cycle_is_byte_identical_across_the_live_flip(tmp_path):
    deps, tools, root = make_env(tmp_path, verification=False)

    def cycle() -> list:
        created = _ok(_create(tools, root, payload="p"))
        hid = created["handoff_id"]
        claimed = _ok(
            tools["handoff_claim"](project_root=root, handoff_id=hid, agent_id="beta")
        )
        completed = _ok(
            tools["handoff_complete"](
                project_root=root, handoff_id=hid, agent_id="beta", result="r"
            )
        )
        got = _ok(
            tools["handoff_get"](project_root=root, handoff_id=hid, agent_id="alpha")
        )
        return [created, claimed, completed, got]

    baseline = cycle()
    # Live flip (the I0 settings PATCH mutates the shared config in place):
    # the SAME parameterless cycle must stay byte-identical to the flag-OFF
    # baseline once per-row volatile ids/timestamps are masked (the TS7/I3
    # methodology) - the flag gates the new PARAMETERS, not the old flow.
    deps.config.feature_verification = True
    flipped = cycle()
    assert json.dumps(_mask_volatile(flipped), sort_keys=True) == json.dumps(
        _mask_volatile(baseline), sort_keys=True
    )


def test_ts3_contract_created_on_stays_readable_and_decidable_off(tmp_path):
    deps, tools, root = make_env(tmp_path)
    created = _ok(
        _create(
            tools,
            root,
            acceptance_criteria=["works"],
            verify_by={"kind": "agent", "agent_id": "gamma"},
        )
    )
    hid = created["handoff_id"]
    _ok(tools["handoff_claim"](project_root=root, handoff_id=hid, agent_id="beta"))
    parked = _ok(
        tools["handoff_complete"](
            project_root=root, handoff_id=hid, agent_id="beta", result="done"
        )
    )
    assert parked["status"] == STATUS_VERIFYING
    # The flag gates the CREATION of a contract, never its decision (the
    # BR6/I3 rationale): flipped OFF, the parked handoff stays readable
    # with its contract exposed AND the verifier can still decide it.
    deps.config.feature_verification = False
    got = _ok(tools["handoff_get"](project_root=root, handoff_id=hid, agent_id="alpha"))
    assert got["status"] == STATUS_VERIFYING
    assert got["acceptance_criteria"] == ["works"]
    assert got["verify_by"] == {"kind": "agent", "agent_id": "gamma"}
    verified = _ok(
        tools["handoff_verify"](
            project_root=root, handoff_id=hid, agent_id="gamma", verdict="pass"
        )
    )
    assert verified["status"] == STATUS_COMPLETED
    assert verified["verified_by"] == "gamma"


# --------------------------------------------------------------------------- #
# TS4 - complete with criteria parks in VERIFYING (event + notification);
# TS5 - verify pass completes onto the CANONICAL handoff.completed (BR5)
# --------------------------------------------------------------------------- #
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


def _park(tools, root, **kwargs) -> str:
    """create -> claim (beta) -> complete (beta): a delivered handoff's id."""
    created = _ok(_create(tools, root, **kwargs))
    hid = created["handoff_id"]
    _ok(tools["handoff_claim"](project_root=root, handoff_id=hid, agent_id="beta"))
    _ok(
        tools["handoff_complete"](
            project_root=root, handoff_id=hid, agent_id="beta", result="delivered"
        )
    )
    return hid


def test_ts4_complete_with_criteria_parks_in_verifying(tmp_path):
    deps, tools, root = make_env(tmp_path)
    by_creator = _ok(_create(tools, root, acceptance_criteria=["ok"], payload="job"))
    by_agent = _ok(
        _create(
            tools,
            root,
            acceptance_criteria=["ok"],
            verify_by={"kind": "agent", "agent_id": "gamma"},
        )
    )
    plain = _ok(_create(tools, root))
    for h in (by_creator, by_agent, plain):
        _ok(
            tools["handoff_claim"](
                project_root=root, handoff_id=h["handoff_id"], agent_id="beta"
            )
        )
    done1 = _ok(
        tools["handoff_complete"](
            project_root=root,
            handoff_id=by_creator["handoff_id"],
            agent_id="beta",
            result="r1",
        )
    )
    done2 = _ok(
        tools["handoff_complete"](
            project_root=root,
            handoff_id=by_agent["handoff_id"],
            agent_id="beta",
            result="r2",
        )
    )
    done3 = _ok(
        tools["handoff_complete"](
            project_root=root,
            handoff_id=plain["handoff_id"],
            agent_id="beta",
            result="r3",
        )
    )
    # Verifiable deliveries PARK and wake their statically resolvable verifier.
    assert done1["status"] == STATUS_VERIFYING and done1["notified"] == ["alpha"]
    assert done2["status"] == STATUS_VERIFYING and done2["notified"] == ["gamma"]
    assert done3["status"] == STATUS_COMPLETED
    # The delivered result is persisted and readable while parked.
    got = _ok(
        tools["handoff_get"](
            project_root=root, handoff_id=by_creator["handoff_id"], agent_id="alpha"
        )
    )
    assert got["status"] == STATUS_VERIFYING and got["result"] == "r1"
    # Metadata-only event: the CONTRACT rides along, the delivered result
    # does not (the verifier inspects it via handoff_get).
    requested = _events(deps, EVENT_VERIFICATION_REQUESTED)
    assert [e["handoff_id"] for e in requested] == [
        by_creator["handoff_id"],
        by_agent["handoff_id"],
    ]
    assert requested[0]["verify_by"] == {"kind": "creator"}
    assert requested[1]["verify_by"] == {"kind": "agent", "agent_id": "gamma"}
    assert requested[0]["acceptance_criteria"] == ["ok"]
    assert requested[0]["claimed_by"] == "beta"
    assert all("result" not in e for e in requested)
    # The plain handoff kept the pre-I4 flow byte-for-byte: the canonical
    # completed event, and NO verified_by on it.
    completed = _events(deps, "handoff.completed")
    assert [e["handoff_id"] for e in completed] == [plain["handoff_id"]]
    assert "verified_by" not in completed[0]
    # Both static verifier kinds got the synthetic pending-verification note.
    for agent, hid in (
        ("alpha", by_creator["handoff_id"]),
        ("gamma", by_agent["handoff_id"]),
    ):
        pulled = _ok(tools["inbox_pull"](agent_id=agent))
        subjects = [m["subject"] for m in pulled["messages"]]
        assert f"handoff {hid} awaits your verification" in subjects, subjects
    # TR4: the handoff_id correlator survives EVERY projection profile - the
    # consumer's next step is always "act on THAT handoff".
    for profile in ("default", "summary", "full"):
        page = _ok(
            tools["event_get"](
                project_root=root, agent_id="alpha", stream="handoff", profile=profile
            )
        )
        mine = [
            e for e in page["events"] if e.get("type") == EVENT_VERIFICATION_REQUESTED
        ]
        assert len(mine) == 2, (profile, page)
        for ev in mine:
            correlator = ev.get("handoff_id") or (ev.get("payload") or {}).get(
                "handoff_id"
            )
            assert correlator in {
                by_creator["handoff_id"],
                by_agent["handoff_id"],
            }, (profile, ev)


def test_ts5_verify_pass_completes_with_verified_by_on_the_canonical_event(tmp_path):
    deps, tools, root = make_env(tmp_path)
    by_creator = _park(tools, root, acceptance_criteria=["ok"])
    by_capability = _park(
        tools,
        root,
        acceptance_criteria=["ok"],
        verify_by={"kind": "capability", "capability": "review"},
    )
    # pass + feedback is rejected loudly, WITHOUT a transition.
    err = _err(
        tools["handoff_verify"](
            project_root=root,
            handoff_id=by_creator,
            agent_id="alpha",
            verdict="pass",
            feedback="nice",
        ),
        "VALIDATION_ERROR",
    )
    assert "only accepted with verdict 'fail'" in err["message"], err["message"]
    still = _ok(
        tools["handoff_get"](project_root=root, handoff_id=by_creator, agent_id="alpha")
    )
    assert still["status"] == STATUS_VERIFYING
    # creator kind: alpha decides; capability kind: gamma qualifies AT VERIFY
    # TIME by currently holding 'review' (D5 - dynamic resolution).
    first = _ok(
        tools["handoff_verify"](
            project_root=root, handoff_id=by_creator, agent_id="alpha", verdict="pass"
        )
    )
    assert first["status"] == STATUS_COMPLETED and first["verified_by"] == "alpha"
    second = _ok(
        tools["handoff_verify"](
            project_root=root,
            handoff_id=by_capability,
            agent_id="gamma",
            verdict="pass",
        )
    )
    assert second["status"] == STATUS_COMPLETED and second["verified_by"] == "gamma"
    # BR5: the CANONICAL handoff.completed carries verified_by - a separate
    # 'verification_passed' event type never exists in the log.
    completed = _events(deps, "handoff.completed")
    assert [(e["handoff_id"], e.get("verified_by")) for e in completed] == [
        (by_creator, "alpha"),
        (by_capability, "gamma"),
    ]
    assert all(e["result"] == "delivered" for e in completed)
    assert _events(deps, "handoff.verification_passed") == []
    # The creator hears the outcome through the CURRENT flow
    # (_notify_creator_outcome): skipped when the verifier IS the creator,
    # delivered to alpha's inbox when gamma decides.
    assert first["notified"] is False
    assert second["notified"] is True
    pulled = _ok(tools["inbox_pull"](agent_id="alpha"))
    subjects = [m["subject"] for m in pulled["messages"]]
    assert f"handoff {by_capability} completed by gamma" in subjects, subjects
    # The contract stays exposed after completion.
    final = _ok(
        tools["handoff_get"](
            project_root=root, handoff_id=by_capability, agent_id="alpha"
        )
    )
    assert final["status"] == STATUS_COMPLETED
    assert final["acceptance_criteria"] == ["ok"]
    assert final["verify_by"] == {"kind": "capability", "capability": "review"}
    assert final["result"] == "delivered"


# --------------------------------------------------------------------------- #
# TS6 - verify fail: directed rework cycles (feedback overwrite + lease renew);
# TS7 - verify authorization: anti-self-verification always wins (fail-closed)
# --------------------------------------------------------------------------- #
def test_ts6_verify_fail_drives_rework_cycles_with_renewed_lease(tmp_path):
    deps, tools, root = make_env(tmp_path)
    created = _ok(_create(tools, root, acceptance_criteria=["ok"]))
    hid = created["handoff_id"]
    claimed = _ok(
        tools["handoff_claim"](project_root=root, handoff_id=hid, agent_id="beta")
    )
    lease0 = claimed["lease_expires_at"]
    _ok(
        tools["handoff_complete"](
            project_root=root, handoff_id=hid, agent_id="beta", result="v1"
        )
    )

    def fail(feedback: str) -> dict:
        return _ok(
            tools["handoff_verify"](
                project_root=root,
                handoff_id=hid,
                agent_id="alpha",
                verdict="fail",
                feedback=feedback,
            )
        )

    fail1 = fail("missing tests")
    assert fail1["status"] == STATUS_CLAIMED and fail1["claimed_by"] == "beta"
    assert fail1["verification_feedback"] == "missing tests"
    # BR4: the lease renews now+ttl in the SAME UPDATE - strictly later than
    # the claim's (canonical fixed-width ISO orders lexicographically).
    assert fail1["lease_expires_at"] > lease0

    _ok(
        tools["handoff_complete"](
            project_root=root, handoff_id=hid, agent_id="beta", result="v2"
        )
    )
    fail2 = fail("still failing on edge case")
    assert fail2["status"] == STATUS_CLAIMED and fail2["claimed_by"] == "beta"
    assert fail2["verification_feedback"] == "still failing on edge case"
    assert fail2["lease_expires_at"] > fail1["lease_expires_at"]
    # The row holds only the LATEST feedback (round 2 OVERWRITES round 1)...
    assert _row(deps, hid)["verification_feedback"] == "still failing on edge case"
    # ...while the event log keeps BOTH rounds intact - history is immutable.
    failed_events = _events(deps, EVENT_VERIFICATION_FAILED)
    assert [e.get("feedback") for e in failed_events] == [
        "missing tests",
        "still failing on edge case",
    ]
    assert all(
        e["handoff_id"] == hid and e["claimed_by"] == "beta" for e in failed_events
    )
    # The claimant was woken for rework on each round.
    pulled = _ok(tools["inbox_pull"](agent_id="beta"))
    subjects = [m["subject"] for m in pulled["messages"]]
    assert subjects.count(f"handoff {hid} verification failed") == 2, subjects

    _ok(
        tools["handoff_complete"](
            project_root=root, handoff_id=hid, agent_id="beta", result="v3"
        )
    )
    final = _ok(
        tools["handoff_verify"](
            project_root=root, handoff_id=hid, agent_id="alpha", verdict="pass"
        )
    )
    assert final["status"] == STATUS_COMPLETED and final["verified_by"] == "alpha"
    # Each (re-)delivery re-parked through a FRESH verification_requested.
    assert len(_events(deps, EVENT_VERIFICATION_REQUESTED)) == 3

    # fail WITHOUT feedback also works: row stays NULL, event carries none.
    hid2 = _park(tools, root, acceptance_criteria=["ok"])
    bare = _ok(
        tools["handoff_verify"](
            project_root=root, handoff_id=hid2, agent_id="alpha", verdict="fail"
        )
    )
    assert bare["status"] == STATUS_CLAIMED
    assert "verification_feedback" not in bare
    assert _row(deps, hid2)["verification_feedback"] is None
    last_failed = _events(deps, EVENT_VERIFICATION_FAILED)[-1]
    assert last_failed["handoff_id"] == hid2 and "feedback" not in last_failed


def test_ts7_verify_authorization_is_fail_closed(tmp_path):
    deps, tools, root = make_env(tmp_path)
    # A capability ONLY delta announces (catalogued first - fail-closed).
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.capability_catalog.create(uow, name="solo")
    _ok(tools["agent_register"](agent_id="delta", role="worker", capabilities=["solo"]))
    by_solo = _ok(
        _create(
            tools,
            root,
            target=_direct("delta"),
            acceptance_criteria=["ok"],
            verify_by={"kind": "capability", "capability": "solo"},
        )
    )["handoff_id"]
    _ok(tools["handoff_claim"](project_root=root, handoff_id=by_solo, agent_id="delta"))
    _ok(
        tools["handoff_complete"](
            project_root=root, handoff_id=by_solo, agent_id="delta", result="done"
        )
    )
    by_creator = _park(tools, root, acceptance_criteria=["ok"])  # claimant: beta
    open_h = _ok(_create(tools, root, acceptance_criteria=["ok"]))["handoff_id"]
    claimed_h = _ok(_create(tools, root))["handoff_id"]
    _ok(
        tools["handoff_claim"](project_root=root, handoff_id=claimed_h, agent_id="beta")
    )
    completed_h = _park(tools, root)  # plain: COMPLETED, never verifiable

    all_ids = (by_solo, by_creator, open_h, claimed_h, completed_h)
    statuses_before = {h: _row(deps, h)["status"] for h in all_ids}
    events_before = _count(deps, "events")

    def deny(hid: str, agent: str, code: str, verdict: str = "pass") -> dict:
        return _err(
            tools["handoff_verify"](
                project_root=root, handoff_id=hid, agent_id=agent, verdict=verdict
            ),
            code,
        )

    # BR3: the executor is refused EVEN as the only current holder of the
    # verify_by capability - anti-self-verification beats eligibility.
    err = deny(by_solo, "delta", "PERMISSION_DENIED")
    assert "executor" in err["message"], err["message"]
    # A non-eligible third party under a creator descriptor is refused too.
    err = deny(by_creator, "gamma", "PERMISSION_DENIED")
    assert "not this handoff's verifier" in err["message"], err["message"]
    # Any status other than VERIFYING is a directed INVALID_TRANSITION.
    for hid in (open_h, claimed_h, completed_h):
        deny(hid, "alpha", "INVALID_TRANSITION")
    # Verdicts outside the closed lowercase vocabulary are rejected upfront.
    for bad in ("PASS", "maybe"):
        deny(by_creator, "alpha", "VALIDATION_ERROR", verdict=bad)

    # NONE of the denied attempts moved a row or emitted an event.
    assert {h: _row(deps, h)["status"] for h in all_ids} == statuses_before
    assert _count(deps, "events") == events_before


# --------------------------------------------------------------------------- #
# TS8 - VERIFYING is protected: cancel/reject blocked, opportunistic expiry
# immune (structurally: the sweep only scans CLAIMED rows);
# TS9 - REST verify is verifier-only across both operator identities
# --------------------------------------------------------------------------- #
def _force_stale_lease(deps, handoff_id: str) -> None:
    conn = deps.connection_factory.get_connection()
    try:
        conn.execute(
            "UPDATE handoffs SET lease_expires_at = ? WHERE handoff_id = ?",
            ("2000-01-01T00:00:00.000000Z", handoff_id),
        )
        conn.commit()
    finally:
        conn.close()


def test_ts8_verifying_is_immune_to_cancel_reject_and_expiry(tmp_path):
    deps, tools, root = make_env(tmp_path)
    parked = _park(tools, root, acceptance_criteria=["ok"])  # VERIFYING, by beta
    _force_stale_lease(deps, parked)
    # BR6: neither end can pull a delivered handoff out of verification -
    # the judgement (handoff_verify) is the only exit.
    err = _err(
        tools["handoff_cancel"](project_root=root, handoff_id=parked, agent_id="alpha"),
        "INVALID_TRANSITION",
    )
    assert "already submitted" in err["message"], err["message"]
    err = _err(
        tools["handoff_reject"](project_root=root, handoff_id=parked, agent_id="beta"),
        "INVALID_TRANSITION",
    )
    assert "under verification" in err["message"], err["message"]
    # Positive control: a plain CLAIMED handoff with the SAME stale lease
    # must reopen, proving the sweep ran and skipped VERIFYING on purpose.
    control = _ok(_create(tools, root))["handoff_id"]
    _ok(tools["handoff_claim"](project_root=root, handoff_id=control, agent_id="beta"))
    _force_stale_lease(deps, control)
    # Fire EVERY opportunistic expiry trigger.
    other = _ok(_create(tools, root))["handoff_id"]
    _ok(tools["handoff_claim"](project_root=root, handoff_id=other, agent_id="beta"))
    _ok(tools["handoff_list_available"](project_root=root, agent_id="gamma"))
    cancellable = _ok(_create(tools, root))["handoff_id"]
    _ok(
        tools["handoff_cancel"](
            project_root=root, handoff_id=cancellable, agent_id="alpha"
        )
    )
    got = _ok(
        tools["handoff_get"](project_root=root, handoff_id=parked, agent_id="alpha")
    )
    # After ALL triggers: still parked with its executor, never reopened.
    assert got["status"] == STATUS_VERIFYING and got["claimed_by"] == "beta"
    expired_events = _events(deps, "handoff.expired")
    assert [e["handoff_id"] for e in expired_events] == [control]
    assert _row(deps, control)["status"] == STATUS_OPEN


def test_ts9_rest_verify_is_verifier_only_across_both_identities(tmp_path):
    from fastapi.testclient import TestClient

    from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
    from okto_nexus.application.auth import AgentKeyAuthService

    deps, tools, root = make_env(tmp_path)
    ws = _ok(tools["workspace_resolve"](project_root=root))["workspace_id"]
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    issued = ensure_operator_key(deps, auth)
    assert issued is not None and issued[0] == "operator", issued
    op_key = issued[1]
    with deps.connection_factory.unit_of_work() as uow:
        alpha_key = auth.issue_key(uow, agent_id="alpha")
        beta_key = auth.issue_key(uow, agent_id="beta")
        gamma_key = auth.issue_key(uow, agent_id="gamma")

    app = build_app(deps)
    # Host "testclient" is NOT loopback: x-api-key required per request. The
    # loopback client rides local_open and acts as the operator with no key.
    # No context manager: REST routes never need the MCP sub-app lifespan.
    client = TestClient(app)
    loopback = TestClient(app, client=("127.0.0.1", 51515))

    def verify_url(hid: str) -> str:
        return f"/api/v1/workspaces/{ws}/handoffs/{hid}/verify"

    def post(hid: str, body: dict, key: str):
        return client.post(verify_url(hid), json=body, headers={"x-api-key": key})

    def rows() -> dict:
        page = client.get(
            "/api/v1/handoffs",
            params={"workspace": ws},
            headers={"x-api-key": op_key},
        )
        assert page.status_code == 200, page.text
        return {i["handoff_id"]: i for i in page.json()["data"]["items"]}

    by_operator = _park(
        tools,
        root,
        acceptance_criteria=["ok"],
        verify_by={"kind": "agent", "agent_id": "operator"},
    )
    by_operator2 = _park(
        tools,
        root,
        acceptance_criteria=["ok"],
        verify_by={"kind": "agent", "agent_id": "operator"},
    )
    by_creator = _park(tools, root, acceptance_criteria=["ok"])

    # While parked, the LIST serializer exposes the contract + VERIFYING
    # top-level, and only when non-NULL (feedback stays omitted).
    listed = rows()
    assert listed[by_creator]["status"] == "VERIFYING"
    assert listed[by_creator]["acceptance_criteria"] == ["ok"]
    assert listed[by_creator]["verify_by"] == {"kind": "creator"}
    assert "verification_feedback" not in listed[by_creator]

    # Non-verifier (gamma) and claimant (beta): 403; bad verdict: 422;
    # missing handoff: 404 - each through the canonical REST error mapping.
    r = post(by_creator, {"verdict": "pass"}, gamma_key)
    assert r.status_code == 403 and r.json()["error"]["code"] == "PERMISSION_DENIED", (
        r.text
    )
    r = post(by_creator, {"verdict": "pass"}, beta_key)
    assert r.status_code == 403 and r.json()["error"]["code"] == "PERMISSION_DENIED", (
        r.text
    )
    r = post(by_creator, {"verdict": "maybe"}, alpha_key)
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR", (
        r.text
    )
    r = post("hof_missing", {"verdict": "pass"}, op_key)
    assert r.status_code == 404, r.text

    # Operator by KEY: fail with feedback -> 200 CLAIMED, fields top-level.
    r = post(by_operator, {"verdict": "fail", "feedback": "needs a summary"}, op_key)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "CLAIMED"
    assert data["verification_feedback"] == "needs a summary"

    # Operator by LOOPBACK (local_open, no key): pass -> 200 COMPLETED.
    r = loopback.post(verify_url(by_operator2), json={"verdict": "pass"})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "COMPLETED" and data["verified_by"] == "operator"

    # The creator's own key: pass -> 200 COMPLETED.
    r = post(by_creator, {"verdict": "pass"}, alpha_key)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "COMPLETED" and data["verified_by"] == "alpha"

    # And the list reflects the fail round: CLAIMED with its feedback.
    listed = rows()
    assert listed[by_operator]["status"] == "CLAIMED"
    assert listed[by_operator]["verification_feedback"] == "needs a summary"


# --------------------------------------------------------------------------- #
# TS10 - governance (I2): VERIFYING holds the max_open_handoffs slot;
# TS11 - HITL (I3) re-executes a verifiable create + surface/trace echoes
# --------------------------------------------------------------------------- #
def test_ts10_verifying_holds_the_max_open_handoffs_slot(tmp_path):
    deps, tools, root = make_env(tmp_path)
    # Attached to alpha (the creator): enforcement is binding-driven now.
    _attach(
        deps,
        "alpha",
        governance=[_rule("handoff_create", "max_open_handoffs", limit_value=1)],
    )
    parked = _park(tools, root, acceptance_criteria=["ok"])
    # BR9: VERIFYING is NOT terminal - the delivered-but-unjudged handoff
    # still occupies alpha's only slot, with zero governance code changes
    # (the quota counts non-terminal statuses; VERIFYING joined that set).
    err = _err(_create(tools, root), "QUOTA_EXCEEDED")
    assert err["details"]["limit_kind"] == "max_open_handoffs"
    assert err["details"]["current"] == 1
    # pass -> COMPLETED (terminal): the slot frees and the create succeeds.
    _ok(
        tools["handoff_verify"](
            project_root=root, handoff_id=parked, agent_id="alpha", verdict="pass"
        )
    )
    _ok(_create(tools, root))


def test_ts11_hitl_intercepts_and_reexecutes_a_verifiable_create(tmp_path):
    from fastapi.testclient import TestClient

    from okto_nexus.adapters.inbound.http.app import build_app

    deps, tools, root = make_env(
        tmp_path,
        extra={"OKTO_NEXUS_FEATURE_HITL": "true"},
    )
    _attach(deps, "alpha", governance=[_rule("handoff_create", "require_approval")])
    pending = _ok(
        _create(
            tools,
            root,
            acceptance_criteria=["has a title"],
            verify_by={"kind": "agent", "agent_id": "gamma"},
        )
    )
    assert pending["status"] == "pending_approval"
    approval_id = pending["approval_id"]
    assert _count(deps, "handoffs") == 0
    assert _events(deps, "handoff.created") == []
    # The persisted request carries the CONTRACT verbatim and NEVER session
    # credentials (the I3 BR2 scrub) - an approved re-execution must bear
    # exactly the verification the creator asked for.
    kwargs = deps.approvals.get_approval(approval_id=approval_id)["request_payload"][
        "kwargs"
    ]
    assert kwargs["acceptance_criteria"] == ["has a title"]
    assert kwargs["verify_by"] == {"kind": "agent", "agent_id": "gamma"}
    assert "session_id" not in kwargs and "session_secret" not in kwargs
    # The operator approves over REST (loopback rides local_open).
    loopback = TestClient(build_app(deps), client=("127.0.0.1", 51516))
    r = loopback.post(
        f"/api/v1/approvals/{approval_id}/decision", json={"decision": "approve"}
    )
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["status"] == "approved" and result["decided_by"] == "operator"
    hid = result["executed_result"]["handoff_id"]
    # The approved re-execution bore a VERIFIABLE handoff, authored by alpha.
    row = _row(deps, hid)
    assert json.loads(row["acceptance_criteria"]) == ["has a title"]
    assert json.loads(row["verify_by"]) == {"kind": "agent", "agent_id": "gamma"}
    got = _ok(tools["handoff_get"](project_root=root, handoff_id=hid, agent_id="alpha"))
    assert got["from_agent_id"] == "alpha"
    assert got["acceptance_criteria"] == ["has a title"]
    assert got["verify_by"] == {"kind": "agent", "agent_id": "gamma"}


def test_ts11_surface_revision_and_verify_description_budget(tmp_path):
    from okto_nexus.adapters.inbound.mcp.server import (
        SURFACE_REVISION,
        register_meta_tools,
    )

    deps, tools, root = make_env(tmp_path)
    server = FakeServer()
    register_meta_tools(server, deps)
    info = _ok(server.tools["nexus_info"]())
    assert info["surface_revision"] == SURFACE_REVISION == 31
    assert info["features"]["feature_verification"] is True
    # The one-line tool description budget (docstring IS the MCP description).
    doc = tools["handoff_verify"].__doc__
    assert doc is not None and len(doc.strip()) <= 200


def test_ts11_verification_events_ride_the_trace_filter(tmp_path):
    from fastapi.testclient import TestClient

    from okto_nexus.adapters.inbound.http.app import build_app

    deps, tools, root = make_env(tmp_path, extra={"OKTO_NEXUS_FEATURE_TRACE": "true"})
    created = _ok(_create(tools, root, acceptance_criteria=["ok"], trace_id="trc_i4"))
    hid = created["handoff_id"]
    assert created["trace_id"] == "trc_i4"
    _ok(tools["handoff_claim"](project_root=root, handoff_id=hid, agent_id="beta"))
    _ok(
        tools["handoff_complete"](
            project_root=root, handoff_id=hid, agent_id="beta", result="v1"
        )
    )
    _ok(
        tools["handoff_verify"](
            project_root=root,
            handoff_id=hid,
            agent_id="alpha",
            verdict="fail",
            feedback="redo",
        )
    )
    both = {EVENT_VERIFICATION_REQUESTED, EVENT_VERIFICATION_FAILED}
    # MCP event_get: the trace filter stitches the NEW event types into the
    # trajectory (the I1 echo - every handoff.* event rides the row's trace).
    page = _ok(
        tools["event_get"](
            project_root=root,
            agent_id="alpha",
            stream="handoff",
            filters={"trace_id": "trc_i4"},
        )
    )
    assert both <= {e["type"] for e in page["events"]}
    assert all(e["trace_id"] == "trc_i4" for e in page["events"])
    # event_wait accepts the same filter (events already exist -> immediate).
    waited = _ok(
        tools["event_wait"](
            project_root=root,
            agent_id="alpha",
            stream="handoff",
            filters={"trace_id": "trc_i4"},
            timeout_seconds=1,
        )
    )
    assert waited["timed_out"] is False
    assert both <= {e["type"] for e in waited["events"]}
    # REST timeline: /events?trace= surfaces the same trajectory.
    loopback = TestClient(build_app(deps), client=("127.0.0.1", 51517))
    data = loopback.get("/api/v1/events?trace=trc_i4").json()["data"]
    assert both <= {e["type"] for e in data["items"]}
