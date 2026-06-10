"""Unit tests for the pure routing domain (``okto_nexus.domain.routing``).

These tests are fully hexagonal: routing has **no IO**, so no DB/MCP fixtures
are needed. We exercise the 6 target strategies, the 3 visibilities, the
inclusive/monotonic time boundary of ``direct_with_fallback``, strict
workspace isolation, and the ``VALIDATION_ERROR`` cases from the canonical
error catalogue.
"""

from __future__ import annotations

import json

import pytest

from okto_nexus.errors import ErrorCode, OktoNexusError
from okto_nexus.domain.routing import (
    RoutingAgent,
    can_agent_see_event,
    is_agent_eligible,
    normalize_capabilities,
)

WS = "a" * 64  # a plausible workspace_id (hex sha256 shape)
WS_OTHER = "b" * 64


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def agent(
    agent_id: str = "agent-1",
    *,
    workspace_id: str = WS,
    role: str | None = None,
    capabilities=None,
) -> RoutingAgent:
    return RoutingAgent(
        agent_id=agent_id,
        workspace_id=workspace_id,
        role=role,
        capabilities=capabilities,
    )


class FakeEvent:
    """Duck-typed stand-in for an Event/Handoff row (object access path)."""

    def __init__(
        self,
        *,
        workspace_id=WS,
        visibility=None,
        target=None,
        created_at=None,
        actor_agent_id=None,
    ):
        self.workspace_id = workspace_id
        self.visibility = visibility
        self.target = target
        self.created_at = created_at
        self.actor_agent_id = actor_agent_id


# --------------------------------------------------------------------------- #
# normalize_capabilities (shared by capability routing AND capability_list)
# --------------------------------------------------------------------------- #
def test_normalize_capabilities():
    assert normalize_capabilities(None) == frozenset()
    assert normalize_capabilities({"py": True, "js": False}) == frozenset({"py"})
    assert normalize_capabilities(["py", "ocr"]) == frozenset({"py", "ocr"})
    assert normalize_capabilities("review") == frozenset({"review"})
    assert normalize_capabilities(("a", "b")) == frozenset({"a", "b"})
    assert normalize_capabilities([]) == frozenset()
    # Blank/whitespace names are dropped (unmatchable by a capability target).
    assert normalize_capabilities("") == frozenset()
    assert normalize_capabilities("   ") == frozenset()
    assert normalize_capabilities(["py", "", "  "]) == frozenset({"py"})
    assert normalize_capabilities({"py": True, "": True}) == frozenset({"py"})
    with pytest.raises(OktoNexusError) as ei:
        normalize_capabilities(123)  # non-iterable, non-mapping
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# Strategy: direct
# --------------------------------------------------------------------------- #
def test_direct_matches_exact_agent_id():
    target = {"strategy": "direct", "agent_id": "agent-1"}
    assert is_agent_eligible(agent("agent-1"), target) is True
    assert is_agent_eligible(agent("agent-2"), target) is False


def test_direct_is_exact_not_substring():
    target = {"strategy": "direct", "agent_id": "agent-1"}
    assert is_agent_eligible(agent("agent-10"), target) is False


def test_direct_missing_agent_id_raises_validation_error():
    with pytest.raises(OktoNexusError) as exc:
        is_agent_eligible(agent("a"), {"strategy": "direct"})
    assert exc.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# Strategy: capability
# --------------------------------------------------------------------------- #
def test_capability_exact_case_sensitive_match():
    target = {"strategy": "capability", "capability": "python"}
    assert is_agent_eligible(agent(capabilities=["python", "rust"]), target) is True
    # Case-sensitive: "Python" != "python".
    assert is_agent_eligible(agent(capabilities=["Python"]), target) is False


def test_capability_flag_mapping_truthy_only():
    target = {"strategy": "capability", "capability": "python"}
    # Mapping form: capability present but falsey -> NOT possessed.
    assert is_agent_eligible(agent(capabilities={"python": False}), target) is False
    assert is_agent_eligible(agent(capabilities={"python": True}), target) is True


def test_capability_preferred_is_advisory_only():
    # ``preferred`` must not affect eligibility in any direction.
    target = {
        "strategy": "capability",
        "capability": "python",
        "preferred": ["agent-9", "rust"],
    }
    assert is_agent_eligible(agent("agent-1", capabilities=["python"]), target) is True
    assert is_agent_eligible(agent("agent-9", capabilities=["rust"]), target) is False


def test_capability_list_is_any_of():
    target = {"strategy": "capability", "capability": ["python", "go"]}
    assert is_agent_eligible(agent(capabilities=["go"]), target) is True
    assert is_agent_eligible(agent(capabilities=["java"]), target) is False


def test_capability_missing_field_raises_validation_error():
    with pytest.raises(OktoNexusError) as exc:
        is_agent_eligible(agent(), {"strategy": "capability"})
    assert exc.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# Strategy: role
# --------------------------------------------------------------------------- #
def test_role_exact_case_sensitive_match():
    target = {"strategy": "role", "role": "reviewer"}
    assert is_agent_eligible(agent(role="reviewer"), target) is True
    assert is_agent_eligible(agent(role="Reviewer"), target) is False
    assert is_agent_eligible(agent(role=None), target) is False


def test_role_missing_field_raises_validation_error():
    with pytest.raises(OktoNexusError) as exc:
        is_agent_eligible(agent(role="x"), {"strategy": "role"})
    assert exc.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# Strategy: broadcast
# --------------------------------------------------------------------------- #
def test_broadcast_matches_any_agent():
    target = {"strategy": "broadcast"}
    assert is_agent_eligible(agent("anyone"), target) is True
    assert is_agent_eligible(agent("other", role="x", capabilities=[]), target) is True


def test_none_or_blank_target_is_broadcast():
    assert is_agent_eligible(agent("x"), None) is True
    assert is_agent_eligible(agent("x"), "") is True
    assert is_agent_eligible(agent("x"), "   ") is True


# --------------------------------------------------------------------------- #
# Strategy: mixed (union / OR)
# --------------------------------------------------------------------------- #
def test_mixed_is_union_of_subrules():
    target = {
        "strategy": "mixed",
        "rules": [
            {"strategy": "direct", "agent_id": "agent-1"},
            {"strategy": "role", "role": "reviewer"},
        ],
    }
    assert is_agent_eligible(agent("agent-1"), target) is True  # via direct
    assert is_agent_eligible(agent("agent-2", role="reviewer"), target) is True  # via role
    assert is_agent_eligible(agent("agent-3", role="dev"), target) is False


def test_mixed_accepts_targets_alias():
    target = {
        "strategy": "mixed",
        "targets": [{"strategy": "capability", "capability": "py"}],
    }
    assert is_agent_eligible(agent(capabilities=["py"]), target) is True


def test_mixed_empty_rules_matches_no_one():
    target = {"strategy": "mixed", "rules": []}
    assert is_agent_eligible(agent("x"), target) is False


def test_mixed_missing_rules_raises_validation_error():
    with pytest.raises(OktoNexusError) as exc:
        is_agent_eligible(agent("x"), {"strategy": "mixed"})
    assert exc.value.code == ErrorCode.VALIDATION_ERROR.value


def test_mixed_nested_direct_with_fallback_propagates_time():
    target = {
        "strategy": "mixed",
        "rules": [
            {"strategy": "role", "role": "reviewer"},
            {
                "strategy": "direct_with_fallback",
                "agent_id": "primary",
                "fallback_after_seconds": 60,
            },
        ],
    }
    a = agent("late-comer", role="dev")
    # Before fallback: neither sub-rule matches.
    assert is_agent_eligible(a, target, created_at=1000.0, now=1059.0) is False
    # After fallback: broadcast fallback inside the nested rule matches.
    assert is_agent_eligible(a, target, created_at=1000.0, now=1060.0) is True


# --------------------------------------------------------------------------- #
# Strategy: direct_with_fallback (inclusive boundary, monotonic)
# --------------------------------------------------------------------------- #
def test_dwf_direct_agent_always_eligible_regardless_of_time():
    target = {
        "strategy": "direct_with_fallback",
        "agent_id": "primary",
        "fallback_after_seconds": 9999,
    }
    a = agent("primary")
    assert is_agent_eligible(a, target, created_at=1000.0, now=1000.0) is True
    assert is_agent_eligible(a, target, created_at=1000.0, now=2_000_000.0) is True


def test_dwf_fallback_boundary_is_inclusive():
    target = {
        "strategy": "direct_with_fallback",
        "agent_id": "primary",
        "fallback_after_seconds": 60,
    }
    other = agent("other")
    assert is_agent_eligible(other, target, created_at=1000.0, now=1059.999) is False
    # Exactly at created_at + fallback_after_seconds -> eligible (inclusive).
    assert is_agent_eligible(other, target, created_at=1000.0, now=1060.0) is True
    assert is_agent_eligible(other, target, created_at=1000.0, now=1060.001) is True


def test_dwf_boundary_inclusive_with_iso_timestamps():
    target = {
        "strategy": "direct_with_fallback",
        "agent_id": "primary",
        "fallback_after_seconds": 60,
    }
    other = agent("other")
    created = "2026-06-07T00:00:00Z"
    assert is_agent_eligible(other, target, created, "2026-06-07T00:00:59Z") is False
    assert is_agent_eligible(other, target, created, "2026-06-07T00:01:00Z") is True


def test_dwf_is_monotonic_in_now():
    target = {
        "strategy": "direct_with_fallback",
        "agent_id": "primary",
        "fallback_after_seconds": 30,
    }
    other = agent("other")
    seen_true = False
    prev = False
    for now in range(1000, 1061):
        cur = is_agent_eligible(other, target, created_at=1000.0, now=float(now))
        # Once eligible, never reverts (monotonic non-decreasing).
        assert not (prev and not cur)
        prev = cur
        seen_true = seen_true or cur
    assert seen_true is True


def test_dwf_fallback_subtarget_restricts_pool():
    target = {
        "strategy": "direct_with_fallback",
        "agent_id": "primary",
        "fallback_after_seconds": 60,
        "fallback": {"strategy": "capability", "capability": "python"},
    }
    capable = agent("c", capabilities=["python"])
    incapable = agent("d", capabilities=["rust"])
    # After threshold, only the fallback capability pool is eligible.
    assert is_agent_eligible(capable, target, created_at=1000.0, now=1060.0) is True
    assert is_agent_eligible(incapable, target, created_at=1000.0, now=1060.0) is False
    # Before threshold, no non-direct agent is eligible.
    assert is_agent_eligible(capable, target, created_at=1000.0, now=1059.0) is False


def test_dwf_missing_fallback_after_seconds_raises():
    with pytest.raises(OktoNexusError) as exc:
        is_agent_eligible(
            agent("other"),
            {"strategy": "direct_with_fallback", "agent_id": "primary"},
            created_at=1000.0,
            now=2000.0,
        )
    assert exc.value.code == ErrorCode.VALIDATION_ERROR.value


def test_dwf_negative_fallback_after_seconds_raises():
    with pytest.raises(OktoNexusError) as exc:
        is_agent_eligible(
            agent("other"),
            {
                "strategy": "direct_with_fallback",
                "agent_id": "primary",
                "fallback_after_seconds": -1,
            },
            created_at=1000.0,
            now=2000.0,
        )
    assert exc.value.code == ErrorCode.VALIDATION_ERROR.value


def test_dwf_requires_timestamps_for_non_direct_agent():
    with pytest.raises(OktoNexusError) as exc:
        is_agent_eligible(
            agent("other"),
            {
                "strategy": "direct_with_fallback",
                "agent_id": "primary",
                "fallback_after_seconds": 60,
            },
            created_at=None,
            now=None,
        )
    assert exc.value.code == ErrorCode.VALIDATION_ERROR.value


def test_dwf_direct_agent_does_not_need_timestamps():
    # The direct recipient short-circuits before any time computation.
    target = {
        "strategy": "direct_with_fallback",
        "agent_id": "primary",
        "fallback_after_seconds": 60,
    }
    assert is_agent_eligible(agent("primary"), target) is True


# --------------------------------------------------------------------------- #
# Timestamp coercion
# --------------------------------------------------------------------------- #
def test_naive_iso_assumed_utc_matches_z_suffixed():
    target = {
        "strategy": "direct_with_fallback",
        "agent_id": "primary",
        "fallback_after_seconds": 0,
    }
    # fallback_after_seconds=0 -> fallback active immediately at created_at.
    assert is_agent_eligible(
        agent("other"), target, "2026-06-07T00:00:00", "2026-06-07T00:00:00Z"
    ) is True


def test_iso_with_offset_is_normalized():
    target = {
        "strategy": "direct_with_fallback",
        "agent_id": "primary",
        "fallback_after_seconds": 3600,
    }
    other = agent("other")
    # created 01:00+01:00 == 00:00Z; +3600s == 01:00Z.
    created = "2026-06-07T01:00:00+01:00"
    assert is_agent_eligible(other, target, created, "2026-06-07T00:59:59Z") is False
    assert is_agent_eligible(other, target, created, "2026-06-07T01:00:00Z") is True


def test_unparseable_timestamp_raises_validation_error():
    target = {
        "strategy": "direct_with_fallback",
        "agent_id": "primary",
        "fallback_after_seconds": 60,
    }
    with pytest.raises(OktoNexusError) as exc:
        is_agent_eligible(agent("other"), target, "not-a-date", "2026-06-07T00:00:00Z")
    assert exc.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# Target shape / strategy validation
# --------------------------------------------------------------------------- #
def test_unknown_strategy_raises_validation_error():
    with pytest.raises(OktoNexusError) as exc:
        is_agent_eligible(agent("x"), {"strategy": "telepathy"})
    assert exc.value.code == ErrorCode.VALIDATION_ERROR.value


def test_target_missing_strategy_raises_validation_error():
    with pytest.raises(OktoNexusError) as exc:
        is_agent_eligible(agent("x"), {"agent_id": "x"})
    assert exc.value.code == ErrorCode.VALIDATION_ERROR.value


def test_strategy_token_is_normalized():
    # "Direct-With-Fallback" -> "direct_with_fallback".
    target = {"strategy": "Direct-With-Fallback", "agent_id": "primary",
              "fallback_after_seconds": 60}
    assert is_agent_eligible(agent("primary"), target) is True


def test_target_json_string_is_parsed():
    target = json.dumps({"strategy": "direct", "agent_id": "agent-1"})
    assert is_agent_eligible(agent("agent-1"), target) is True
    assert is_agent_eligible(agent("agent-2"), target) is False


def test_target_invalid_json_string_raises():
    with pytest.raises(OktoNexusError) as exc:
        is_agent_eligible(agent("x"), "{not json")
    assert exc.value.code == ErrorCode.VALIDATION_ERROR.value


def test_target_json_non_object_raises():
    with pytest.raises(OktoNexusError) as exc:
        is_agent_eligible(agent("x"), "[1, 2, 3]")
    assert exc.value.code == ErrorCode.VALIDATION_ERROR.value


def test_agent_and_target_accept_plain_dicts():
    # Duck typing: a plain dict agent works just like RoutingAgent.
    dict_agent = {"agent_id": "agent-1", "workspace_id": WS, "role": "dev"}
    assert is_agent_eligible(dict_agent, {"strategy": "direct", "agent_id": "agent-1"})


# --------------------------------------------------------------------------- #
# Visibility: public
# --------------------------------------------------------------------------- #
def test_public_visible_to_any_agent_in_workspace_even_if_not_eligible():
    item = FakeEvent(
        workspace_id=WS,
        visibility="public",
        target={"strategy": "direct", "agent_id": "someone-else"},
    )
    # Not the direct target, but public -> still visible.
    assert can_agent_see_event(agent("not-the-target"), item) is True


def test_default_visibility_is_public():
    item = FakeEvent(
        workspace_id=WS,
        visibility=None,
        target={"strategy": "direct", "agent_id": "someone-else"},
    )
    assert can_agent_see_event(agent("bystander"), item) is True


# --------------------------------------------------------------------------- #
# Visibility: eligible
# --------------------------------------------------------------------------- #
def test_eligible_mirrors_is_agent_eligible():
    item = FakeEvent(
        workspace_id=WS,
        visibility="eligible",
        target={"strategy": "role", "role": "reviewer"},
    )
    assert can_agent_see_event(agent("a", role="reviewer"), item) is True
    assert can_agent_see_event(agent("b", role="dev"), item) is False


def test_eligible_with_time_based_target_uses_now():
    item = FakeEvent(
        workspace_id=WS,
        visibility="eligible",
        target={
            "strategy": "direct_with_fallback",
            "agent_id": "primary",
            "fallback_after_seconds": 60,
        },
        created_at=1000.0,
    )
    other = agent("other")
    assert can_agent_see_event(other, item, now=1059.0) is False
    assert can_agent_see_event(other, item, now=1060.0) is True


# --------------------------------------------------------------------------- #
# Visibility: private
# --------------------------------------------------------------------------- #
def test_private_direct_visible_only_to_direct_target():
    item = FakeEvent(
        workspace_id=WS,
        visibility="private",
        target={"strategy": "direct", "agent_id": "agent-1"},
    )
    assert can_agent_see_event(agent("agent-1"), item) is True
    assert can_agent_see_event(agent("agent-2"), item) is False


def test_private_non_direct_equals_eligible():
    # For a non-direct (role) target, private == eligible: the eligible pool sees it.
    item = FakeEvent(
        workspace_id=WS,
        visibility="private",
        target={"strategy": "role", "role": "reviewer"},
    )
    assert can_agent_see_event(agent("a", role="reviewer"), item) is True
    assert can_agent_see_event(agent("b", role="dev"), item) is False


def test_visibility_is_case_insensitive():
    item = FakeEvent(workspace_id=WS, visibility="PUBLIC")
    assert can_agent_see_event(agent("x"), item) is True


def test_unknown_visibility_raises_validation_error():
    item = FakeEvent(workspace_id=WS, visibility="secret-eyes-only")
    with pytest.raises(OktoNexusError) as exc:
        can_agent_see_event(agent("x"), item)
    assert exc.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# Actor carve-out (ADR 0001: "... or you are the sender")
# --------------------------------------------------------------------------- #
def test_actor_sees_own_eligible_event_even_when_not_in_target():
    # M2 defect 4: the sender of a directed message was NOT eligible for its own
    # message.created event. The actor always sees what it emitted.
    item = FakeEvent(
        workspace_id=WS,
        visibility="eligible",
        target={"strategy": "direct", "agent_id": "recipient"},
        actor_agent_id="sender",
    )
    assert can_agent_see_event(agent("sender"), item) is True  # the carve-out
    assert can_agent_see_event(agent("recipient"), item) is True  # eligibility
    assert can_agent_see_event(agent("third-party"), item) is False  # neither


def test_actor_sees_own_private_direct_event():
    item = FakeEvent(
        workspace_id=WS,
        visibility="private",
        target={"strategy": "direct", "agent_id": "recipient"},
        actor_agent_id="sender",
    )
    assert can_agent_see_event(agent("sender"), item) is True
    assert can_agent_see_event(agent("third-party"), item) is False


def test_actor_carveout_is_workspace_isolated():
    # The carve-out NEVER crosses workspaces: same actor id, other workspace.
    item = FakeEvent(
        workspace_id=WS_OTHER,
        visibility="eligible",
        target={"strategy": "direct", "agent_id": "recipient"},
        actor_agent_id="sender",
    )
    assert can_agent_see_event(agent("sender", workspace_id=WS), item) is False


def test_no_actor_field_changes_nothing():
    # Handoffs (no actor_agent_id) keep the pre-carve-out behaviour exactly.
    item = FakeEvent(
        workspace_id=WS,
        visibility="eligible",
        target={"strategy": "direct", "agent_id": "recipient"},
    )
    assert can_agent_see_event(agent("someone-else"), item) is False


# --------------------------------------------------------------------------- #
# Workspace isolation
# --------------------------------------------------------------------------- #
def test_cross_workspace_is_never_visible_even_if_public():
    item = FakeEvent(workspace_id=WS_OTHER, visibility="public")
    assert can_agent_see_event(agent("x", workspace_id=WS), item) is False


def test_cross_workspace_is_never_visible_even_if_eligible():
    item = FakeEvent(
        workspace_id=WS_OTHER,
        visibility="eligible",
        target={"strategy": "direct", "agent_id": "agent-1"},
    )
    assert can_agent_see_event(agent("agent-1", workspace_id=WS), item) is False


def test_same_workspace_required_when_agent_has_no_workspace():
    item = FakeEvent(workspace_id=WS, visibility="public")
    no_ws_agent = {"agent_id": "x"}  # no workspace_id key
    assert can_agent_see_event(no_ws_agent, item) is False


def test_can_see_accepts_dict_item():
    item = {
        "workspace_id": WS,
        "visibility": "eligible",
        "target": {"strategy": "broadcast"},
        "created_at": None,
    }
    assert can_agent_see_event(agent("anyone"), item) is True


def test_can_see_accepts_json_string_target_on_item():
    item = FakeEvent(
        workspace_id=WS,
        visibility="eligible",
        target=json.dumps({"strategy": "direct", "agent_id": "agent-1"}),
    )
    assert can_agent_see_event(agent("agent-1"), item) is True
    assert can_agent_see_event(agent("agent-2"), item) is False
