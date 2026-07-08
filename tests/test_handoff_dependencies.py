"""Handoff dependencies / DAG (spec 6522ad1f, R-I5) - scenarios TS0..TS11.

T1/TS0 (this section): the PURE domain layer - the fail-closed depends_on
grammar (1..MAX_DEPENDENCIES unique non-empty ids, no silent dedup), the
strict satisfaction rule (only COMPLETED satisfies; VERIFYING does not),
the permanent-failure set (REJECTED|CANCELLED) and the derived claimability
evaluator. No I/O: everything here imports ``okto_nexus.domain.handoff``
only (the import-boundary test keeps it pure).

Later sections (T2..T7) add the application/REST scenarios over the real
bootstrap harness (temp-home make_env, the test_verification.py pattern).
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import queue
import threading
import time

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap, register_tools
from okto_nexus.adapters.outbound.sqlite.observability_repo import (
    SqliteObservabilityQueries,
)
from okto_nexus.application.observability import ObservabilityService
from okto_nexus.domain.handoff import (
    DEPENDENCY_FAILED_STATUSES,
    DEPENDENCY_SATISFYING_STATUSES,
    EVENT_DEPENDENCY_FAILED,
    EVENT_UNBLOCKED,
    MAX_DEPENDENCIES,
    STATUS_CANCELLED,
    STATUS_CLAIMED,
    STATUS_COMPLETED,
    STATUS_OPEN,
    STATUS_REJECTED,
    STATUS_VERIFYING,
    dependencies_satisfied,
    summarize_dependencies,
    validate_depends_on,
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
# T1 / TS0 - depends_on grammar (pure, fail-closed)
# --------------------------------------------------------------------------- #
class TestDependsOnGrammar:
    def test_valid_list_preserves_order_and_strips(self):
        assert validate_depends_on(["hof_b", " hof_a ", "hof_c"]) == [
            "hof_b",
            "hof_a",
            "hof_c",
        ]

    def test_tuple_accepted_as_list(self):
        assert validate_depends_on(("hof_a",)) == ["hof_a"]

    def test_exactly_max_ids_accepted(self):
        ids = [f"hof_{i:02d}" for i in range(MAX_DEPENDENCIES)]
        assert validate_depends_on(ids) == ids

    def test_more_than_max_rejected_with_counts(self):
        ids = [f"hof_{i:02d}" for i in range(MAX_DEPENDENCIES + 1)]
        err = _rejects(validate_depends_on, ids, contains="at most")
        assert err.details == {"count": MAX_DEPENDENCIES + 1, "max": MAX_DEPENDENCIES}

    @pytest.mark.parametrize("raw", ["hof_a", {"id": "hof_a"}, 7, None, True])
    def test_non_list_rejected(self, raw):
        _rejects(validate_depends_on, raw, contains="must be a list")

    def test_empty_list_rejected_omission_is_the_no_deps_path(self):
        err = _rejects(validate_depends_on, [], contains="omit the parameter")
        assert err.details == {"depends_on": []}

    @pytest.mark.parametrize("item", ["", "   ", 7, None, ["hof_a"]])
    def test_non_string_or_blank_item_rejected_with_index(self, item):
        err = _rejects(validate_depends_on, ["hof_ok", item], contains="depends_on[1]")
        assert err.details["index"] == 1

    def test_exact_duplicate_rejected_never_silently_deduped(self):
        err = _rejects(
            validate_depends_on, ["hof_a", "hof_b", "hof_a"], contains="duplicate"
        )
        assert err.details == {"index": 2, "item": "hof_a"}

    def test_duplicate_after_strip_is_still_a_duplicate(self):
        _rejects(validate_depends_on, ["hof_a", "  hof_a  "], contains="duplicate")

    def test_grammar_is_purely_syntactic_no_self_id_parameter(self):
        # Self-reference and cycles are impossible BY CONSTRUCTION, not by a
        # check: the grammar never learns the depending handoff's id (single
        # ``raw`` parameter), every listed id must ALREADY exist while the new
        # handoff does not yet (application's existence gate, TS2), and the
        # list is immutable after creation. A cycle can therefore never form.
        params = list(inspect.signature(validate_depends_on).parameters)
        assert params == ["raw"]


# --------------------------------------------------------------------------- #
# T1 / TS0 - strict satisfaction + permanent failure + derived claimability
# --------------------------------------------------------------------------- #
class TestDependencySatisfaction:
    def test_satisfying_set_is_strictly_completed(self):
        assert DEPENDENCY_SATISFYING_STATUSES == frozenset({STATUS_COMPLETED})

    def test_failed_set_is_rejected_or_cancelled(self):
        assert DEPENDENCY_FAILED_STATUSES == frozenset(
            {STATUS_REJECTED, STATUS_CANCELLED}
        )

    def test_verifying_does_not_satisfy(self):
        # The I4 interop rule: delivered-but-unjudged work is not done yet.
        assert not dependencies_satisfied([STATUS_VERIFYING])
        assert summarize_dependencies([STATUS_VERIFYING])["pending"] == 1

    @pytest.mark.parametrize("status", [STATUS_OPEN, STATUS_CLAIMED, STATUS_VERIFYING])
    def test_any_in_flight_status_blocks(self, status):
        assert not dependencies_satisfied([STATUS_COMPLETED, status])

    @pytest.mark.parametrize("status", sorted(DEPENDENCY_FAILED_STATUSES))
    def test_any_failed_status_blocks(self, status):
        assert not dependencies_satisfied([STATUS_COMPLETED, status])

    def test_all_completed_satisfies(self):
        assert dependencies_satisfied([STATUS_COMPLETED] * 3)

    def test_no_dependencies_qualifies(self):
        # The single claimability rule: a dependency-free handoff never blocks.
        assert dependencies_satisfied([])

    def test_summary_counts_are_canonical(self):
        summary = summarize_dependencies(
            [
                STATUS_COMPLETED,
                STATUS_COMPLETED,
                STATUS_OPEN,
                STATUS_CLAIMED,
                STATUS_VERIFYING,
                STATUS_REJECTED,
                STATUS_CANCELLED,
            ]
        )
        assert summary == {"total": 7, "satisfied": 2, "pending": 3, "failed": 2}

    def test_summary_of_nothing_is_all_zero(self):
        assert summarize_dependencies([]) == {
            "total": 0,
            "satisfied": 0,
            "pending": 0,
            "failed": 0,
        }

    def test_dag_event_type_names(self):
        assert EVENT_UNBLOCKED == "handoff.unblocked"
        assert EVENT_DEPENDENCY_FAILED == "handoff.dependency_failed"


# --------------------------------------------------------------------------- #
# Harness for TS1+ (identical shape to test_verification.py): the REAL
# bootstrap in a temp home with feature_dag ON, tools registered through the
# same path both MCP transports mount, and three agents.
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


def make_env(tmp_path, *, dag: bool = True, extra: dict | None = None):
    """Real bootstrap + alpha/beta/gamma over a temp home (feature_dag ON)."""
    env = {"OKTO_NEXUS_HOME": str(tmp_path / "home")}
    if dag:
        env["OKTO_NEXUS_FEATURE_DAG"] = "true"
    env.update(extra or {})
    deps = bootstrap(env, [])
    server = FakeServer()
    register_tools(server, deps)
    tools = server.tools
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    root = str(project)
    workspace_id = _ok(tools["workspace_resolve"](project_root=root))["workspace_id"]
    _ok(tools["agent_register"](agent_id="alpha", role="builder"))
    _ok(tools["agent_register"](agent_id="beta", role="executor"))
    _ok(tools["agent_register"](agent_id="gamma", role="reviewer"))
    return deps, tools, root, workspace_id


def _count(deps, table: str) -> int:
    conn = deps.connection_factory.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def _snapshot(deps) -> tuple[int, int, int, int]:
    """Row counts of every table a rejected create could have touched."""
    return (
        _count(deps, "handoffs"),
        _count(deps, "handoff_dependencies"),
        _count(deps, "events"),
        _count(deps, "messages"),
    )


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


def _subjects(deps) -> list[str]:
    conn = deps.connection_factory.get_connection()
    try:
        rows = conn.execute(
            "SELECT subject FROM messages ORDER BY created_at"
        ).fetchall()
        return [row["subject"] or "" for row in rows]
    finally:
        conn.close()


def _dep_rows(deps, handoff_id: str) -> list[tuple[str, str]]:
    conn = deps.connection_factory.get_connection()
    try:
        rows = conn.execute(
            "SELECT depends_on_id, workspace_id FROM handoff_dependencies "
            "WHERE handoff_id = ? ORDER BY rowid",
            (handoff_id,),
        ).fetchall()
        return [(row["depends_on_id"], row["workspace_id"]) for row in rows]
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


def _complete(tools, root, handoff_id: str, *, agent: str = "beta") -> dict:
    _ok(
        tools["handoff_claim"](project_root=root, handoff_id=handoff_id, agent_id=agent)
    )
    return _ok(
        tools["handoff_complete"](
            project_root=root, handoff_id=handoff_id, agent_id=agent, result="done"
        )
    )


# --------------------------------------------------------------------------- #
# T2 / TS1 - create with depends_on: persistence + conditional exposure
# --------------------------------------------------------------------------- #
def test_ts1_create_persists_edges_and_echoes_contract(tmp_path):
    deps, tools, root, workspace_id = make_env(tmp_path)
    dep1 = _ok(_create(tools, root))["handoff_id"]
    dep2 = _ok(_create(tools, root))["handoff_id"]

    child = _ok(_create(tools, root, depends_on=[dep2, dep1], payload="assemble"))
    child_id = child["handoff_id"]
    # Envelope echo: the normalised list + the aggregate counters, nothing else.
    assert child["depends_on"] == [dep2, dep1]
    assert child["dependencies"] == {
        "total": 2,
        "satisfied": 0,
        "pending": 2,
        "failed": 0,
    }
    # Persistence: one row per edge, caller's order preserved (rowid), scoped.
    assert _dep_rows(deps, child_id) == [(dep2, workspace_id), (dep1, workspace_id)]
    # handoff.created event carries depends_on for the dependent only.
    created_payloads = {p["handoff_id"]: p for p in _events(deps, "handoff.created")}
    assert created_payloads[child_id]["depends_on"] == [dep2, dep1]
    assert "depends_on" not in created_payloads[dep1]
    # handoff_get mirrors the conditional exposure.
    got = _ok(
        tools["handoff_get"](project_root=root, handoff_id=child_id, agent_id="alpha")
    )
    assert got["depends_on"] == [dep2, dep1]
    assert got["dependencies"]["pending"] == 2
    plain_got = _ok(
        tools["handoff_get"](project_root=root, handoff_id=dep1, agent_id="alpha")
    )
    assert "depends_on" not in plain_got and "dependencies" not in plain_got


def test_ts1_directed_notification_gains_blocked_suffix(tmp_path):
    deps, tools, root, _ = make_env(tmp_path)
    dep = _ok(_create(tools, root))["handoff_id"]
    blocked = _ok(_create(tools, root, depends_on=[dep]))["handoff_id"]
    subjects = _subjects(deps)
    assert f"handoff {blocked} directed to you (blocked)" in subjects
    # The dependency-free directed notification keeps its pre-I5 subject.
    assert f"handoff {dep} directed to you" in subjects


def test_ts1_already_satisfied_dep_creates_unblocked(tmp_path):
    deps, tools, root, _ = make_env(tmp_path)
    dep = _ok(_create(tools, root))["handoff_id"]
    _complete(tools, root, dep)
    child = _ok(_create(tools, root, depends_on=[dep]))
    # Born satisfied: counters say so and the directed subject has NO suffix.
    assert child["dependencies"] == {
        "total": 1,
        "satisfied": 1,
        "pending": 0,
        "failed": 0,
    }
    assert f"handoff {child['handoff_id']} directed to you" in _subjects(deps)
    assert not any("(blocked)" in s for s in _subjects(deps))


# --------------------------------------------------------------------------- #
# T2 / TS2 - fail-closed battery: every rejection leaves ZERO side effects
# --------------------------------------------------------------------------- #
def test_ts2_grammar_violations_reject_with_zero_side_effects(tmp_path):
    deps, tools, root, _ = make_env(tmp_path)
    dep = _ok(_create(tools, root))["handoff_id"]
    before = _snapshot(deps)

    # Over the cap: rejected by the pure grammar before any I/O.
    too_many = [f"hof_{i:032x}" for i in range(MAX_DEPENDENCIES + 1)]
    _err(_create(tools, root, depends_on=too_many), "VALIDATION_ERROR")
    # Exact duplicate: a caller mistake, never silently deduped.
    _err(_create(tools, root, depends_on=[dep, dep]), "VALIDATION_ERROR")
    # Not a list / empty list.
    _err(_create(tools, root, depends_on="hof_x"), "VALIDATION_ERROR")
    _err(_create(tools, root, depends_on=[]), "VALIDATION_ERROR")

    assert _snapshot(deps) == before


def test_ts2_unknown_ids_reject_listing_every_missing_id(tmp_path):
    deps, tools, root, _ = make_env(tmp_path)
    dep = _ok(_create(tools, root))["handoff_id"]
    before = _snapshot(deps)

    err = _err(
        _create(tools, root, depends_on=[dep, "hof_ghost1", "hof_ghost2"]),
        "DEPENDENCY_NOT_FOUND",
    )
    assert err["details"] == {"missing": ["hof_ghost1", "hof_ghost2"]}
    # Structural self-reference: the depending handoff's id does not exist
    # while its own create runs, so ANY attempt lands here - there is no
    # window in which a handoff could name itself (cycle-free by construction).
    err = _err(
        _create(tools, root, depends_on=["hof_never_created"]),
        "DEPENDENCY_NOT_FOUND",
    )
    assert err["details"] == {"missing": ["hof_never_created"]}

    assert _snapshot(deps) == before


def test_ts2_cross_workspace_dep_is_indistinguishable_from_missing(tmp_path):
    deps, tools, root, _ = make_env(tmp_path)
    other_project = tmp_path / "other_project"
    other_project.mkdir()
    other_root = str(other_project)
    _ok(tools["workspace_resolve"](project_root=other_root))
    foreign = _ok(_create(tools, other_root))["handoff_id"]
    before = _snapshot(deps)

    err = _err(_create(tools, root, depends_on=[foreign]), "DEPENDENCY_NOT_FOUND")
    # BR: the error is byte-shaped like a plain miss - an id existing in
    # ANOTHER workspace must not be probeable through richer details.
    assert err["details"] == {"missing": [foreign]}

    assert _snapshot(deps) == before


def test_ts2_terminally_failed_dep_is_statically_unsatisfiable(tmp_path):
    deps, tools, root, _ = make_env(tmp_path)
    cancelled = _ok(_create(tools, root))["handoff_id"]
    _ok(
        tools["handoff_cancel"](
            project_root=root, handoff_id=cancelled, agent_id="alpha"
        )
    )
    rejected = _ok(_create(tools, root))["handoff_id"]
    _ok(tools["handoff_claim"](project_root=root, handoff_id=rejected, agent_id="beta"))
    _ok(
        tools["handoff_reject"](
            project_root=root, handoff_id=rejected, agent_id="beta", reason="nope"
        )
    )
    before = _snapshot(deps)

    for dead in (cancelled, rejected):
        err = _err(_create(tools, root, depends_on=[dead]), "VALIDATION_ERROR")
        assert "statically unsatisfiable" in err["message"]
        assert err["details"]["failed"] == [dead]

    assert _snapshot(deps) == before


def _reopen(tmp_path, *, dag: bool):
    """Second bootstrap over the SAME home (a flag flip between restarts)."""
    env = {"OKTO_NEXUS_HOME": str(tmp_path / "home")}
    if dag:
        env["OKTO_NEXUS_FEATURE_DAG"] = "true"
    deps = bootstrap(env, [])
    server = FakeServer()
    register_tools(server, deps)
    return deps, server.tools


def _broadcast() -> dict:
    return {"strategy": "broadcast"}


def _available_ids(tools, root, agent_id: str) -> list[str]:
    listed = _ok(tools["handoff_list_available"](project_root=root, agent_id=agent_id))
    return [h["handoff_id"] for h in listed["handoffs"]]


# --------------------------------------------------------------------------- #
# T3 / TS3 - feature_dag fail-closed at create; decidable OFF after creation
# --------------------------------------------------------------------------- #
def test_ts3_flag_off_rejects_depends_on_fail_closed(tmp_path):
    # NOTE: scenario TS3 names this refusal "FEATURE_DISABLED". The product's
    # canonical error vocabulary has no such code - the flag gate raises
    # VALIDATION_ERROR whose message cites feature_dag (D4: an edge is never
    # accepted-and-ignored). Same resolution as I1: prove the right surface
    # and record the mapping here instead of inventing a new code.
    deps, tools, root, _ = make_env(tmp_path, dag=False)
    dep = _ok(_create(tools, root))["handoff_id"]
    before = _snapshot(deps)

    err = _err(_create(tools, root, depends_on=[dep]), "VALIDATION_ERROR")
    assert "feature_dag" in err["message"]
    assert err["details"] == {"feature_dag": False}
    # The refusal happens BEFORE the existence gate: an unknown id fails the
    # same way while OFF (the flag outranks I/O), still with no side effects.
    err = _err(_create(tools, root, depends_on=["hof_ghost"]), "VALIDATION_ERROR")
    assert "feature_dag" in err["message"]

    assert _snapshot(deps) == before


def test_ts3_flag_flip_keeps_dep_free_envelopes_byte_identical(tmp_path):
    deps_on, tools_on, root, _ = make_env(tmp_path, dag=True)
    plain = _ok(_create(tools_on, root, payload="job"))
    hid = plain["handoff_id"]
    got_on = _ok(
        tools_on["handoff_get"](project_root=root, handoff_id=hid, agent_id="alpha")
    )
    list_on = _ok(
        tools_on["handoff_list_available"](project_root=root, agent_id="beta")
    )

    # Same HOME reopened with the flag OFF: reads of a dependency-free
    # handoff are byte-identical (same ids, same stamps - the flag only
    # gates creation; it never reshapes read envelopes).
    _, tools_off = _reopen(tmp_path, dag=False)
    got_off = _ok(
        tools_off["handoff_get"](project_root=root, handoff_id=hid, agent_id="alpha")
    )
    assert got_off == got_on
    assert (
        _ok(tools_off["handoff_list_available"](project_root=root, agent_id="beta"))
        == list_on
    )
    # A fresh dependency-free create keeps the exact envelope key set (ids
    # and stamps naturally differ) and never grows the I5 fields.
    plain_off = _ok(_create(tools_off, root))
    assert set(plain_off) == set(plain)
    assert "depends_on" not in plain_off and "dependencies" not in plain_off


def test_ts3_flip_off_after_creation_keeps_gates_on_the_table(tmp_path):
    deps, tools, root, _ = make_env(tmp_path, dag=True)
    dep = _ok(_create(tools, root, target=_broadcast()))["handoff_id"]
    child = _ok(_create(tools, root, target=_broadcast(), depends_on=[dep]))[
        "handoff_id"
    ]

    _, tools_off = _reopen(tmp_path, dag=False)
    # Still blocked while OFF: the gates read the TABLE, never the flag.
    ids = _available_ids(tools_off, root, "beta")
    assert dep in ids and child not in ids
    err = _err(
        tools_off["handoff_claim"](
            project_root=root, handoff_id=child, agent_id="beta"
        ),
        "DEPENDENCY_NOT_MET",
    )
    assert err["details"] == {"handoff_id": child, "pending": 1, "failed": 0}
    # Completing the dependency while OFF unblocks normally (existing DAGs
    # stay decidable after the flip - BR2's accepted-work guarantee).
    _complete(tools_off, root, dep)
    assert len(_events(deps, EVENT_UNBLOCKED)) == 1
    assert child in _available_ids(tools_off, root, "beta")
    _ok(
        tools_off["handoff_claim"](project_root=root, handoff_id=child, agent_id="beta")
    )


# --------------------------------------------------------------------------- #
# T4-scope note: TS4 lives here because it shares the list/claim gate wiring
# --------------------------------------------------------------------------- #
def test_ts4_list_excludes_blocked_and_claim_reveals_aggregates_only(tmp_path):
    deps, tools, root, _ = make_env(tmp_path)
    d1 = _ok(_create(tools, root, target=_broadcast()))["handoff_id"]
    d2 = _ok(_create(tools, root, target=_broadcast()))["handoff_id"]
    child = _ok(_create(tools, root, target=_broadcast(), depends_on=[d1, d2]))[
        "handoff_id"
    ]

    # Blocked: unlisted (the list offers exactly what claim would accept)...
    ids = _available_ids(tools, root, "gamma")
    assert d1 in ids and d2 in ids and child not in ids
    # ...and unclaimable, with AGGREGATE-ONLY details (BR8): the exact dict
    # is asserted so a future leak of dependency ids fails loudly.
    err = _err(
        tools["handoff_claim"](project_root=root, handoff_id=child, agent_id="gamma"),
        "DEPENDENCY_NOT_MET",
    )
    assert err["details"] == {"handoff_id": child, "pending": 2, "failed": 0}

    # One of two done: still blocked, counters advance.
    _complete(tools, root, d1)
    assert child not in _available_ids(tools, root, "gamma")
    err = _err(
        tools["handoff_claim"](project_root=root, handoff_id=child, agent_id="gamma"),
        "DEPENDENCY_NOT_MET",
    )
    assert err["details"] == {"handoff_id": child, "pending": 1, "failed": 0}

    # Last dependency completes: claimable IMMEDIATELY (same-transaction
    # unblock; no queue, no eventual consistency).
    _complete(tools, root, d2)
    assert child in _available_ids(tools, root, "gamma")
    claimed = _ok(
        tools["handoff_claim"](project_root=root, handoff_id=child, agent_id="gamma")
    )
    assert claimed["status"] == "CLAIMED" and claimed["claimed_by"] == "gamma"


def _event_rows(deps, event_type: str) -> list[dict]:
    """Full event rows (actor + decoded payload) of one type, in order."""
    conn = deps.connection_factory.get_connection()
    try:
        rows = conn.execute(
            "SELECT actor_agent_id, payload FROM events WHERE type = ? "
            "ORDER BY event_id",
            (event_type,),
        ).fetchall()
        return [
            {
                "actor_agent_id": row["actor_agent_id"],
                "payload": json.loads(row["payload"]),
            }
            for row in rows
        ]
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# T4 / TS5 - synchronous unblock: event with the DEPENDENT's row, waiter
# wake-up, and the directed-only inbox notice
# --------------------------------------------------------------------------- #
def test_ts5_unblock_event_waiter_and_directed_inbox(tmp_path):
    deps, tools, root, workspace_id = make_env(
        tmp_path, extra={"OKTO_NEXUS_FEATURE_TRACE": "true"}
    )
    dep = _ok(_create(tools, root, target=_broadcast(), trace_id="tr-dep"))[
        "handoff_id"
    ]
    # Two dependents of the same dep: one DIRECTED at beta, one pool-target.
    directed = _ok(_create(tools, root, depends_on=[dep], trace_id="tr-child"))[
        "handoff_id"
    ]
    pooled = _ok(_create(tools, root, target=_broadcast(), depends_on=[dep]))[
        "handoff_id"
    ]

    # beta takes the dep: gamma's available page is now EMPTY (dep CLAIMED,
    # directed not eligible, pooled blocked) - the long-poll below arms.
    _ok(tools["handoff_claim"](project_root=root, handoff_id=dep, agent_id="beta"))
    results: queue.Queue = queue.Queue()

    def _poll():
        results.put(
            tools["handoff_list_available"](
                project_root=root, agent_id="gamma", timeout_seconds=10
            )
        )

    poller = threading.Thread(target=_poll)
    poller.start()
    time.sleep(0.3)
    _ok(
        tools["handoff_complete"](
            project_root=root, handoff_id=dep, agent_id="beta", result="done"
        )
    )
    woken = _ok(results.get(timeout=10))
    poller.join(timeout=10)
    # The unblocking COMMIT woke the waiter: the pooled dependent is offered
    # without waiting out the timeout window.
    assert woken["timed_out"] is False
    assert [h["handoff_id"] for h in woken["handoffs"]] == [pooled]

    # One handoff.unblocked per dependent, both acted by the COMPLETER, each
    # carrying the DEPENDENT's row (id, OPEN status) and its trace - never
    # the dependency's.
    unblocked = _event_rows(deps, EVENT_UNBLOCKED)
    assert len(unblocked) == 2
    by_id = {e["payload"]["handoff_id"]: e for e in unblocked}
    assert set(by_id) == {directed, pooled}
    for event in unblocked:
        assert event["actor_agent_id"] == "beta"
        assert event["payload"]["status"] == "OPEN"
        assert event["payload"]["unblocked_by"] == dep
        assert event["payload"]["workspace_id"] == workspace_id
    assert by_id[directed]["payload"]["trace_id"] == "tr-child"
    # With feature_trace ON every row is auto-stamped: the pooled dependent's
    # event carries the POOLED row's own trace - never the dependency's.
    conn = deps.connection_factory.get_connection()
    try:
        pooled_trace = conn.execute(
            "SELECT trace_id FROM handoffs WHERE handoff_id = ?", (pooled,)
        ).fetchone()["trace_id"]
    finally:
        conn.close()
    assert by_id[pooled]["payload"]["trace_id"] == pooled_trace
    assert pooled_trace not in ("tr-dep", "tr-child")

    # Inbox notice ONLY for the directed dependent's named agent.
    subjects = _subjects(deps)
    assert f"handoff {directed} unblocked" in subjects
    assert f"handoff {pooled} unblocked" not in subjects


# --------------------------------------------------------------------------- #
# T4 / TS6 - fan-in: only the LAST completion unblocks, exactly once
# --------------------------------------------------------------------------- #
def test_ts6_fan_in_unblocks_only_on_the_last_dep_exactly_once(tmp_path):
    deps, tools, root, _ = make_env(tmp_path)
    d1, d2, d3 = (
        _ok(_create(tools, root, target=_broadcast()))["handoff_id"] for _ in range(3)
    )
    child = _ok(_create(tools, root, target=_broadcast(), depends_on=[d1, d2, d3]))[
        "handoff_id"
    ]

    _complete(tools, root, d1)
    assert _event_rows(deps, EVENT_UNBLOCKED) == []
    _complete(tools, root, d2)
    assert _event_rows(deps, EVENT_UNBLOCKED) == []
    err = _err(
        tools["handoff_claim"](project_root=root, handoff_id=child, agent_id="gamma"),
        "DEPENDENCY_NOT_MET",
    )
    assert err["details"]["pending"] == 1

    _complete(tools, root, d3)
    unblocked = _event_rows(deps, EVENT_UNBLOCKED)
    # Exactly once, on the LAST edge - the same-transaction evaluation means
    # only the completion that closes the set ever sees it satisfied.
    assert len(unblocked) == 1
    assert unblocked[0]["payload"]["handoff_id"] == child
    assert unblocked[0]["payload"]["unblocked_by"] == d3
    _ok(tools["handoff_claim"](project_root=root, handoff_id=child, agent_id="gamma"))


def test_ts6_dep_already_completed_at_create_is_born_satisfied(tmp_path):
    deps, tools, root, _ = make_env(tmp_path)
    dep = _ok(_create(tools, root, target=_broadcast()))["handoff_id"]
    _complete(tools, root, dep)

    child = _ok(_create(tools, root, target=_broadcast(), depends_on=[dep]))
    assert child["dependencies"] == {
        "total": 1,
        "satisfied": 1,
        "pending": 0,
        "failed": 0,
    }
    # Immediately claimable, and NO unblocked event: nothing was ever blocked.
    assert child["handoff_id"] in _available_ids(tools, root, "gamma")
    _ok(
        tools["handoff_claim"](
            project_root=root, handoff_id=child["handoff_id"], agent_id="gamma"
        )
    )
    assert _event_rows(deps, EVENT_UNBLOCKED) == []


# --------------------------------------------------------------------------- #
# T5 / TS7 - I4 interop: VERIFYING never satisfies; the verify-pass COMPLETED
# unblocks through the SAME helper (verifier as actor); fail keeps blocking
# --------------------------------------------------------------------------- #
def test_ts7_verifying_never_satisfies_and_pass_unblocks_as_verifier(tmp_path):
    deps, tools, root, _ = make_env(
        tmp_path, extra={"OKTO_NEXUS_FEATURE_VERIFICATION": "true"}
    )
    dep = _ok(
        _create(
            tools,
            root,
            target=_broadcast(),
            acceptance_criteria=["has a summary"],
            verify_by={"kind": "agent", "agent_id": "gamma"},
        )
    )["handoff_id"]
    child = _ok(_create(tools, root, target=_broadcast(), depends_on=[dep]))[
        "handoff_id"
    ]

    # Delivered but unjudged: VERIFYING does NOT satisfy (strict COMPLETED).
    _ok(tools["handoff_claim"](project_root=root, handoff_id=dep, agent_id="beta"))
    parked = _ok(
        tools["handoff_complete"](
            project_root=root, handoff_id=dep, agent_id="beta", result="v1"
        )
    )
    assert parked["status"] == "VERIFYING"
    err = _err(
        tools["handoff_claim"](project_root=root, handoff_id=child, agent_id="gamma"),
        "DEPENDENCY_NOT_MET",
    )
    assert err["details"] == {"handoff_id": child, "pending": 1, "failed": 0}
    assert _event_rows(deps, EVENT_UNBLOCKED) == []

    # Verify FAIL -> the dep returns to CLAIMED: still pending, still blocked.
    _ok(
        tools["handoff_verify"](
            project_root=root,
            handoff_id=dep,
            agent_id="gamma",
            verdict="fail",
            feedback="needs a summary",
        )
    )
    err = _err(
        tools["handoff_claim"](project_root=root, handoff_id=child, agent_id="gamma"),
        "DEPENDENCY_NOT_MET",
    )
    assert err["details"]["pending"] == 1
    assert _event_rows(deps, EVENT_UNBLOCKED) == []

    # Rework + verify PASS -> COMPLETED unblocks through the SAME helper:
    # exactly one event, and the ACTOR is the verifier (gamma), not the
    # claimant that delivered.
    _ok(
        tools["handoff_complete"](
            project_root=root, handoff_id=dep, agent_id="beta", result="v2"
        )
    )
    _ok(
        tools["handoff_verify"](
            project_root=root, handoff_id=dep, agent_id="gamma", verdict="pass"
        )
    )
    unblocked = _event_rows(deps, EVENT_UNBLOCKED)
    assert len(unblocked) == 1
    assert unblocked[0]["actor_agent_id"] == "gamma"
    assert unblocked[0]["payload"]["handoff_id"] == child
    assert unblocked[0]["payload"]["unblocked_by"] == dep
    _ok(tools["handoff_claim"](project_root=root, handoff_id=child, agent_id="gamma"))


# --------------------------------------------------------------------------- #
# T5 / TS8 - terminal dependency failure: event + creator inbox, NO cascade
# --------------------------------------------------------------------------- #
def test_ts8_cancelled_dep_fails_dependents_with_event_and_creator_inbox(tmp_path):
    deps, tools, root, workspace_id = make_env(tmp_path)
    dep = _ok(_create(tools, root, target=_broadcast()))["handoff_id"]
    child = _ok(_create(tools, root, target=_broadcast(), depends_on=[dep]))[
        "handoff_id"
    ]

    _ok(tools["handoff_cancel"](project_root=root, handoff_id=dep, agent_id="alpha"))

    failed = _event_rows(deps, EVENT_DEPENDENCY_FAILED)
    assert len(failed) == 1
    assert failed[0]["actor_agent_id"] == "alpha"
    assert failed[0]["payload"] == {
        "handoff_id": child,
        "workspace_id": workspace_id,
        "status": "OPEN",
        "failed_dependency": dep,
        "dependency_status": "CANCELLED",
    }
    # One inbox notice to the DEPENDENT's creator with the manual next step.
    assert f"handoff {child} has a failed dependency" in _subjects(deps)

    # Retention, NO cascade (BR5): the dependent stays OPEN, unlisted, and
    # unclaimable with failed=1 - the aggregate the dashboard derives the
    # dead badge from.
    got = _ok(
        tools["handoff_get"](project_root=root, handoff_id=child, agent_id="alpha")
    )
    assert got["status"] == "OPEN"
    assert got["dependencies"] == {
        "total": 1,
        "satisfied": 0,
        "pending": 0,
        "failed": 1,
    }
    assert child not in _available_ids(tools, root, "gamma")
    err = _err(
        tools["handoff_claim"](project_root=root, handoff_id=child, agent_id="gamma"),
        "DEPENDENCY_NOT_MET",
    )
    assert err["details"] == {"handoff_id": child, "pending": 0, "failed": 1}


def test_ts8_rejected_dep_marks_dead_and_manual_cancel_stays_available(tmp_path):
    deps, tools, root, _ = make_env(tmp_path)
    dep = _ok(_create(tools, root, target=_broadcast()))["handoff_id"]
    child = _ok(_create(tools, root, target=_broadcast(), depends_on=[dep]))[
        "handoff_id"
    ]

    _ok(tools["handoff_claim"](project_root=root, handoff_id=dep, agent_id="beta"))
    _ok(
        tools["handoff_reject"](
            project_root=root, handoff_id=dep, agent_id="beta", reason="cannot do"
        )
    )
    failed = _event_rows(deps, EVENT_DEPENDENCY_FAILED)
    assert len(failed) == 1
    assert failed[0]["actor_agent_id"] == "beta"
    assert failed[0]["payload"]["dependency_status"] == "REJECTED"

    # The dead dependent never unblocks - but its manual exit stays open:
    # the creator can still cancel it (the documented intervention path).
    cancelled = _ok(
        tools["handoff_cancel"](project_root=root, handoff_id=child, agent_id="alpha")
    )
    assert cancelled["status"] == "CANCELLED"
    # And the cancel of a dependency-free dead END never cascades further:
    # no NEW dependency_failed event beyond the reject's one (the child has
    # no dependents of its own).
    assert len(_event_rows(deps, EVENT_DEPENDENCY_FAILED)) == 1


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


def _client(deps):
    """Operator-authenticated TestClient over the SAME deps (use via with)."""
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


# --------------------------------------------------------------------------- #
# T6 / TS9 - governance interop (BR9): a BLOCKED dependent is OPEN and spends
# the max_open_handoffs budget like any other open handoff
# --------------------------------------------------------------------------- #
def test_ts9_blocked_dependent_counts_in_max_open_handoffs(tmp_path):
    deps, tools, root, _ = make_env(tmp_path)
    _attach(
        deps,
        "alpha",
        governance=[_rule("handoff_create", "max_open_handoffs", limit_value=2)],
    )
    dep = _ok(_create(tools, root, target=_broadcast()))["handoff_id"]
    blocked = _ok(_create(tools, root, target=_broadcast(), depends_on=[dep]))
    assert blocked["dependencies"]["pending"] == 1  # genuinely blocked...

    # ...yet it consumed the second slot: the third create trips the quota,
    # proving blocked == OPEN for governance accounting (never a free pass).
    err = _err(_create(tools, root, target=_broadcast()), "QUOTA_EXCEEDED")
    assert err["details"]["limit_kind"] == "max_open_handoffs"
    assert err["details"]["current"] == 2


# --------------------------------------------------------------------------- #
# T6 / TS9 - HITL interop (BR10): persisted kwargs carry the normalised
# depends_on and never the session credentials; approval re-validates
# --------------------------------------------------------------------------- #
def test_ts9_hitl_kwargs_normalized_depends_on_without_credentials(tmp_path):
    deps, tools, root, workspace_id = make_env(
        tmp_path,
        extra={"OKTO_NEXUS_FEATURE_HITL": "true"},
    )
    dep = _ok(_create(tools, root, target=_broadcast()))["handoff_id"]
    _attach(deps, "alpha", governance=[_rule("handoff_create", "require_approval")])
    session = _ok(tools["session_open"](agent_id="alpha", workspace_id=workspace_id))

    # handoff_create takes session_id only (session_secret belongs to the
    # sensitive verbs) - the credential-free rule covers whatever the tool
    # accepted.
    pending = _ok(
        _create(
            tools,
            root,
            depends_on=[f"  {dep}  "],  # unnormalised on purpose
            session_id=session["session_id"],
        )
    )
    assert pending["status"] == "pending_approval"
    kwargs = deps.approvals.get_approval(approval_id=pending["approval_id"])[
        "request_payload"
    ]["kwargs"]
    # NORMALISED list persisted; the session credentials never are.
    assert kwargs["depends_on"] == [dep]
    assert "session_id" not in kwargs and "session_secret" not in kwargs

    # Approve: the re-execution creates the dependent with its edges intact.
    with _client(deps) as client:
        resp = client.post(
            f"/api/v1/approvals/{pending['approval_id']}/decision",
            json={"decision": "approve"},
        )
        assert resp.status_code == 200, resp.text
        executed = resp.json()["data"]["executed_result"]
    assert executed["depends_on"] == [dep]
    assert _dep_rows(deps, executed["handoff_id"]) == [(dep, workspace_id)]


def test_ts9_br10_dep_failing_before_approval_reverts_to_pending(tmp_path):
    deps, tools, root, _ = make_env(
        tmp_path,
        extra={"OKTO_NEXUS_FEATURE_HITL": "true"},
    )
    dep = _ok(_create(tools, root, target=_broadcast()))["handoff_id"]
    _attach(deps, "alpha", governance=[_rule("handoff_create", "require_approval")])
    pending = _ok(_create(tools, root, depends_on=[dep]))
    approval_id = pending["approval_id"]

    # The dependency dies BETWEEN the request and the decision (cancel is not
    # under the require_approval action, so it executes directly).
    _ok(tools["handoff_cancel"](project_root=root, handoff_id=dep, agent_id="alpha"))

    # Approve: re-execution re-validates the edges (BR10) - the gate's REAL
    # error propagates to the operator and the approval reverts to pending.
    with _client(deps) as client:
        resp = client.post(
            f"/api/v1/approvals/{approval_id}/decision", json={"decision": "approve"}
        )
    assert resp.status_code == 422, resp.text
    error = resp.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "statically unsatisfiable" in error["message"]
    assert deps.approvals.get_approval(approval_id=approval_id)["status"] == "pending"
    # Nothing was created by the failed re-execution: only the dep exists.
    assert _count(deps, "handoffs") == 1
    assert _count(deps, "handoff_dependencies") == 0


# --------------------------------------------------------------------------- #
# T6 / TS10 - REST list: aggregates in ONE extra query per page (AC9), rows
# without dependencies identical to the pre-I5 baseline (BR11)
# --------------------------------------------------------------------------- #
def test_ts10_rest_list_aggregates_one_query_and_baseline_rows(tmp_path):
    deps, tools, root, workspace_id = make_env(tmp_path)
    plains = [
        _ok(_create(tools, root, target=_broadcast()))["handoff_id"] for _ in range(2)
    ]

    with _client(deps) as client:
        baseline = client.get(
            "/api/v1/handoffs", params={"workspace": workspace_id}
        ).json()["data"]["items"]
        baseline_by_id = {row["handoff_id"]: row for row in baseline}

        # FIVE dependents over one dep: per-row lookups would need 5 queries.
        dep = _ok(_create(tools, root, target=_broadcast()))["handoff_id"]
        children = [
            _ok(_create(tools, root, target=_broadcast(), depends_on=[dep]))[
                "handoff_id"
            ]
            for _ in range(5)
        ]
        items = client.get(
            "/api/v1/handoffs", params={"workspace": workspace_id}
        ).json()["data"]["items"]
    by_id = {row["handoff_id"]: row for row in items}
    for child in children:
        assert by_id[child]["depends_on"] == [dep]
        assert by_id[child]["dependencies"] == {
            "total": 1,
            "satisfied": 0,
            "pending": 1,
            "failed": 0,
        }
    # BR11: the dependency-free rows are BYTE-identical to their pre-deps
    # serialisation (same dict, not merely the same keys).
    for plain in plains:
        assert by_id[plain] == baseline_by_id[plain]
    assert "depends_on" not in by_id[dep]

    # AC9 anti-N+1, proven by COUNTING: one page read touches the
    # handoff_dependencies table in EXACTLY one statement, regardless of how
    # many rows carry edges (5 here).
    observability = ObservabilityService(
        SqliteObservabilityQueries(), deps.clock, deps.config
    )
    statements: list[str] = []
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.set_trace_callback(statements.append)
        rows = observability.handoffs(uow, workspace_id=workspace_id, status=None)
        uow.connection.set_trace_callback(None)
    assert len(rows) == 8
    dep_touches = [s for s in statements if "handoff_dependencies" in s]
    assert len(dep_touches) == 1, dep_touches


def test_ts10_admin_cancel_is_raw_and_never_emits_dependency_failed(tmp_path):
    deps, tools, root, workspace_id = make_env(tmp_path)
    dep = _ok(_create(tools, root, target=_broadcast()))["handoff_id"]
    child = _ok(_create(tools, root, target=_broadcast(), depends_on=[dep]))[
        "handoff_id"
    ]

    # Documented caveat S2: the ADMIN cancel is a raw update_status port that
    # BYPASSES HandoffService.handoff_cancel - dependents get NO
    # dependency_failed event and no inbox notice...
    with _client(deps) as client:
        resp = client.post(
            f"/api/v1/handoffs/{dep}/cancel", params={"workspace": workspace_id}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "CANCELLED"
        assert _event_rows(deps, EVENT_DEPENDENCY_FAILED) == []
        assert f"handoff {child} has a failed dependency" not in _subjects(deps)

        # ...while correctness still holds ON-READ: the aggregate turns
        # failed=1 on the very next list and the claim gate refuses.
        items = client.get(
            "/api/v1/handoffs", params={"workspace": workspace_id}
        ).json()["data"]["items"]
    row = {r["handoff_id"]: r for r in items}[child]
    assert row["dependencies"] == {
        "total": 1,
        "satisfied": 0,
        "pending": 0,
        "failed": 1,
    }
    err = _err(
        tools["handoff_claim"](project_root=root, handoff_id=child, agent_id="gamma"),
        "DEPENDENCY_NOT_MET",
    )
    assert err["details"] == {"handoff_id": child, "pending": 0, "failed": 1}


# --------------------------------------------------------------------------- #
# T7 / TS11 - surface: projection promotion, trace filter, revision + budgets
# --------------------------------------------------------------------------- #
def _seed_dag_events(tools, root) -> tuple[str, str]:
    """One unblocked (child_ok) + one dependency_failed (child_dead)."""
    dep_ok = _ok(_create(tools, root, target=_broadcast()))["handoff_id"]
    child_ok = _ok(_create(tools, root, target=_broadcast(), depends_on=[dep_ok]))[
        "handoff_id"
    ]
    _complete(tools, root, dep_ok)
    dep_dead = _ok(_create(tools, root, target=_broadcast()))["handoff_id"]
    child_dead = _ok(_create(tools, root, target=_broadcast(), depends_on=[dep_dead]))[
        "handoff_id"
    ]
    _ok(
        tools["handoff_cancel"](
            project_root=root, handoff_id=dep_dead, agent_id="alpha"
        )
    )
    return child_ok, child_dead


def test_ts11_projection_promotes_handoff_id_on_both_dag_event_types(tmp_path):
    deps, tools, root, _ = make_env(tmp_path)
    child_ok, child_dead = _seed_dag_events(tools, root)

    expected = {EVENT_UNBLOCKED: child_ok, EVENT_DEPENDENCY_FAILED: child_dead}
    # The handoff_id correlator survives EVERY projection profile - and on
    # "summary" it must be PROMOTED top-level (the C4 projection change:
    # _DAG_EVENT_TYPES joined the verification types in the allowlist).
    for profile in ("default", "summary", "full"):
        page = _ok(
            tools["event_get"](
                project_root=root, agent_id="alpha", stream="handoff", profile=profile
            )
        )
        by_type = {}
        for event in page["events"]:
            if event.get("type") in expected:
                by_type[event["type"]] = event
        assert set(by_type) == set(expected), (profile, page["events"])
        for event_type, dependent_id in expected.items():
            event = by_type[event_type]
            correlator = event.get("handoff_id") or (event.get("payload") or {}).get(
                "handoff_id"
            )
            assert correlator == dependent_id, (profile, event)
            if profile == "summary":
                assert event.get("handoff_id") == dependent_id, event


def test_ts11_dag_events_ride_the_trace_filter(tmp_path):
    from fastapi.testclient import TestClient

    from okto_nexus.adapters.inbound.http.app import build_app

    deps, tools, root, _ = make_env(
        tmp_path, extra={"OKTO_NEXUS_FEATURE_TRACE": "true"}
    )
    dep_ok = _ok(_create(tools, root, target=_broadcast()))["handoff_id"]
    child_ok = _ok(
        _create(
            tools, root, target=_broadcast(), depends_on=[dep_ok], trace_id="trc_ok"
        )
    )["handoff_id"]
    _complete(tools, root, dep_ok)
    dep_dead = _ok(_create(tools, root, target=_broadcast()))["handoff_id"]
    _ok(
        _create(
            tools,
            root,
            target=_broadcast(),
            depends_on=[dep_dead],
            trace_id="trc_dead",
        )
    )
    _ok(
        tools["handoff_cancel"](
            project_root=root, handoff_id=dep_dead, agent_id="alpha"
        )
    )

    # MCP event_get: both NEW event types stitch into the DEPENDENT's
    # trajectory (the events inherit the dependent's row, hence its trace).
    page = _ok(
        tools["event_get"](
            project_root=root,
            agent_id="alpha",
            stream="handoff",
            filters={"trace_id": "trc_ok"},
        )
    )
    assert EVENT_UNBLOCKED in {e["type"] for e in page["events"]}
    assert all(e["trace_id"] == "trc_ok" for e in page["events"])
    # event_wait accepts the same filter (events already exist -> immediate).
    waited = _ok(
        tools["event_wait"](
            project_root=root,
            agent_id="alpha",
            stream="handoff",
            filters={"trace_id": "trc_dead"},
            timeout_seconds=1,
        )
    )
    assert waited["timed_out"] is False
    assert EVENT_DEPENDENCY_FAILED in {e["type"] for e in waited["events"]}
    # REST timeline: /events?trace= surfaces the same trajectories.
    loopback = TestClient(build_app(deps), client=("127.0.0.1", 51519))
    data = loopback.get("/api/v1/events?trace=trc_ok").json()["data"]
    assert EVENT_UNBLOCKED in {e["type"] for e in data["items"]}
    data = loopback.get("/api/v1/events?trace=trc_dead").json()["data"]
    assert EVENT_DEPENDENCY_FAILED in {e["type"] for e in data["items"]}
    assert child_ok  # correlators asserted through the projection test above


def test_ts11_surface_revision_feature_flag_and_budgets(tmp_path):
    from okto_nexus.adapters.inbound.mcp.server import (
        SURFACE_REVISION,
        register_meta_tools,
    )
    from okto_nexus.adapters.inbound.mcp.tools.handoff import _P_DEPENDS_ON

    deps, tools, root, _ = make_env(tmp_path)
    meta = FakeServer()
    register_meta_tools(meta, deps)
    info = _ok(meta.tools["nexus_info"]())
    assert info["surface_revision"] == SURFACE_REVISION == 29
    assert info["features"]["feature_dag"] is True

    # Zero new tools: I5 rides existing verbs only - no tool name mentions
    # the DAG vocabulary (the growth ledger covers the one new parameter).
    assert not any(
        "depend" in name or "dag" in name or "unblock" in name for name in tools
    ), sorted(tools)
    # One-line description budgets (the docstring IS the MCP description):
    # the create tool and the new parameter both fit the S2 gate.
    doc = tools["handoff_create"].__doc__
    assert doc is not None and len(doc.strip()) <= 200
    assert "\n" not in _P_DEPENDS_ON and len(_P_DEPENDS_ON) <= 200
