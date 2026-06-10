"""Tests for the unified target grammar (``okto_nexus.domain.targets``).

M9: the grammar used to be DUPLICATED between routing and handoff and had
diverged for real - ``mixed`` with ``rules=[]`` was accepted by routing but
rejected by handoff, and a null sub-rule slipped through message validation
(the ``__validate__`` eligibility probe short-circuited on it) as a covert,
S1-defeating broadcast. These tests pin the SINGLE grammar and prove, at the
behaviour level, that every consumer (routing eligibility, handoff descriptor
validation, message send-time validation / recipient resolution) now agrees.
"""

from __future__ import annotations

import json

import pytest

from okto_nexus.domain.handoff import validate_target as handoff_validate_target
from okto_nexus.domain.inbox import resolve_recipients
from okto_nexus.domain.messages import validate_target as message_validate_target
from okto_nexus.domain.routing import RoutingAgent, is_agent_eligible
from okto_nexus.domain.targets import (
    VALID_STRATEGIES,
    coerce_target,
    is_direct_target,
    normalize_strategy,
    target_strategy,
    validate_target,
)
from okto_nexus.errors import ErrorCode, OktoNexusError

NOW = "2026-06-07T00:00:00.000000Z"


def assert_validation_error(exc_info) -> None:
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# Vocabulary & coercion
# --------------------------------------------------------------------------- #
def test_valid_strategies_closed_set():
    assert VALID_STRATEGIES == frozenset(
        {"direct", "capability", "role", "broadcast", "mixed", "direct_with_fallback"}
    )


def test_normalize_strategy_token_rules():
    assert normalize_strategy("Direct-With-Fallback") == "direct_with_fallback"
    assert normalize_strategy("  BROADCAST ") == "broadcast"
    for bad in (None, "", "   ", "telepathy"):
        with pytest.raises(OktoNexusError) as ei:
            normalize_strategy(bad)
        assert_validation_error(ei)


def test_coerce_target_shapes():
    assert coerce_target(None) is None
    assert coerce_target("   ") is None
    assert coerce_target({"strategy": "broadcast"}) == {"strategy": "broadcast"}
    assert coerce_target('{"strategy": "broadcast"}') == {"strategy": "broadcast"}
    with pytest.raises(OktoNexusError) as required:
        coerce_target(None, required=True)
    assert_validation_error(required)
    for bad in ("{not json", "[1, 2]", 42):
        with pytest.raises(OktoNexusError) as ei:
            coerce_target(bad)
        assert_validation_error(ei)


def test_target_strategy_resolves_discriminator_only():
    assert target_strategy(None) is None
    assert target_strategy({"strategy": "Direct"}) == "direct"
    assert target_strategy({"kind": "broadcast"}) == "broadcast"
    with pytest.raises(OktoNexusError) as ei:
        target_strategy({"agent_id": "a"})
    assert_validation_error(ei)


# --------------------------------------------------------------------------- #
# validate_target: per-strategy required fields
# --------------------------------------------------------------------------- #
def test_validate_target_happy_paths_normalise():
    assert validate_target(None) is None
    assert validate_target({"strategy": "broadcast"})["strategy"] == "broadcast"
    direct = validate_target({"strategy": "Direct", "agent_id": "a"})
    assert direct == {"strategy": "direct", "agent_id": "a"}
    role = validate_target('{"strategy": "role", "role": "validator"}')
    assert role["role"] == "validator"
    cap = validate_target({"strategy": "capability", "capability": ["ocr", "pdf"]})
    assert cap["capability"] == ["ocr", "pdf"]
    dwf = validate_target(
        {
            "strategy": "direct_with_fallback",
            "agent_id": "a",
            "fallback_after_seconds": 0,
            "fallback": {"strategy": "Role", "role": "validator"},
        }
    )
    assert dwf["fallback"]["strategy"] == "role"


@pytest.mark.parametrize(
    "bad",
    [
        {"strategy": "direct"},  # direct requires agent_id
        {"strategy": "direct", "agent_id": "  "},
        {"strategy": "role"},
        {"strategy": "capability"},
        {"strategy": "capability", "capability": []},  # empty list
        {"strategy": "capability", "capability": ["ocr", "  "]},  # blank name
        {"strategy": "capability", "capability": 42},
        {"strategy": "direct_with_fallback", "agent_id": "a"},  # missing delay
        {
            "strategy": "direct_with_fallback",
            "agent_id": "a",
            "fallback_after_seconds": -1,
        },
        {
            "strategy": "direct_with_fallback",
            "agent_id": "a",
            "fallback_after_seconds": True,  # bool is not a number
        },
        {
            "strategy": "direct_with_fallback",
            "agent_id": "a",
            "fallback_after_seconds": 60,
            "fallback": {"strategy": "direct"},  # invalid fallback (recursive)
        },
        {"strategy": "nope"},
        {"agent_id": "a"},  # missing discriminator
    ],
)
def test_validate_target_rejects_malformed(bad):
    with pytest.raises(OktoNexusError) as ei:
        validate_target(bad)
    assert_validation_error(ei)


# --------------------------------------------------------------------------- #
# validate_target: mixed (the rule that had diverged)
# --------------------------------------------------------------------------- #
def test_mixed_valid_rules_normalised_recursively():
    out = validate_target(
        {
            "strategy": "Mixed",
            "rules": [
                {"strategy": "Direct", "agent_id": "a"},
                {"strategy": "capability", "capability": "ocr"},
            ],
        }
    )
    assert out is not None
    assert [r["strategy"] for r in out["rules"]] == ["direct", "capability"]


def test_mixed_targets_alias_normalised_to_rules():
    out = validate_target(
        {"strategy": "mixed", "targets": [{"strategy": "role", "role": "x"}]}
    )
    assert out is not None
    assert out["rules"][0]["role"] == "x"
    assert "targets" not in out


def test_mixed_nested_mixed_is_allowed():
    out = validate_target(
        {
            "strategy": "mixed",
            "rules": [
                {
                    "strategy": "mixed",
                    "rules": [{"strategy": "direct", "agent_id": "a"}],
                }
            ],
        }
    )
    assert out is not None
    assert out["rules"][0]["rules"][0]["agent_id"] == "a"


@pytest.mark.parametrize(
    "bad",
    [
        {"strategy": "mixed"},  # missing rules
        {"strategy": "mixed", "rules": []},  # empty
        {"strategy": "mixed", "rules": "direct"},  # not a list
        {"strategy": "mixed", "rules": [None]},  # nested null
        {"strategy": "mixed", "rules": ["  "]},  # nested blank
        {"strategy": "mixed", "rules": [{"strategy": "broadcast"}]},  # nested broadcast
        {
            "strategy": "mixed",
            "rules": [{"strategy": "role", "role": "x"}, {"strategy": "direct"}],
        },  # invalid sub-rule AFTER a valid one (no short-circuit)
    ],
)
def test_mixed_rejects_malformed_rule_lists(bad):
    with pytest.raises(OktoNexusError) as ei:
        validate_target(bad)
    assert_validation_error(ei)


# --------------------------------------------------------------------------- #
# is_direct_target (moved from domain.handoff; never raises)
# --------------------------------------------------------------------------- #
def test_is_direct_target():
    assert is_direct_target({"strategy": "direct", "agent_id": "a"}, "a") is True
    assert is_direct_target({"strategy": "Direct", "agent_id": "a"}, "a") is True
    assert is_direct_target({"strategy": "direct", "agent_id": "a"}, "b") is False
    assert is_direct_target({"strategy": "broadcast"}, "a") is False
    assert is_direct_target('{"strategy":"direct","agent_id":"a"}', "a") is True
    assert is_direct_target("not-json", "a") is False
    assert is_direct_target(None, "a") is False
    assert is_direct_target({"strategy": "direct", "agent_id": "a"}, "") is False


# --------------------------------------------------------------------------- #
# The SAME grammar in every consumer (the real M9 divergence)
# --------------------------------------------------------------------------- #
def test_routing_and_handoff_agree_on_empty_mixed_rules():
    """routing used to accept ``rules=[]`` (matches-no-one); handoff rejected it.

    With the single grammar source, BOTH reject it with VALIDATION_ERROR.
    """
    target = {"strategy": "mixed", "rules": []}
    agent = RoutingAgent(agent_id="a", workspace_id="w" * 64)
    with pytest.raises(OktoNexusError) as routing_err:
        is_agent_eligible(agent, target)
    assert_validation_error(routing_err)
    with pytest.raises(OktoNexusError) as handoff_err:
        handoff_validate_target(target)
    assert_validation_error(handoff_err)


def test_handoff_validate_target_still_requires_descriptor():
    with pytest.raises(OktoNexusError) as ei:
        handoff_validate_target(None)
    assert_validation_error(ei)
    out = handoff_validate_target('{"strategy":"Role","role":"builder"}')
    assert out == {"strategy": "role", "role": "builder"}


def test_message_validation_rejects_null_mixed_subrule():
    """The ``__validate__`` probe accepted ``rules=[null]`` (a covert broadcast).

    Structural validation rejects it - closing the S1 guard bypass.
    """
    target = {"strategy": "mixed", "rules": [None]}
    with pytest.raises(OktoNexusError) as ei:
        message_validate_target(target, NOW)
    assert_validation_error(ei)


def test_message_validation_no_short_circuit_past_bad_subrule():
    # The old probe short-circuited on the first sub-rule that matched and
    # never validated the following ones; the single grammar validates ALL.
    target = {
        "strategy": "mixed",
        "rules": [
            {"strategy": "direct", "agent_id": "__validate__"},  # probe match
            {"strategy": "direct"},  # malformed
        ],
    }
    with pytest.raises(OktoNexusError) as ei:
        message_validate_target(target, NOW)
    assert_validation_error(ei)


def test_resolve_recipients_rejects_null_subrule_even_with_candidates():
    """Closes the S1 bypass at recipient resolution (eager fan-out).

    Before: ``rules=[null]`` resolved EVERY candidate (a covert global
    broadcast). Now: VALIDATION_ERROR before any matching happens.
    """
    candidates = [
        RoutingAgent(agent_id="a1", workspace_id="w" * 64),
        RoutingAgent(agent_id="a2", workspace_id="w" * 64),
    ]
    with pytest.raises(OktoNexusError) as ei:
        resolve_recipients({"strategy": "mixed", "rules": [None]}, candidates, NOW)
    assert_validation_error(ei)
    # Also via the JSON-string form (the stored/transported shape).
    with pytest.raises(OktoNexusError) as ei2:
        resolve_recipients(
            json.dumps({"strategy": "mixed", "rules": [None]}), candidates, NOW
        )
    assert_validation_error(ei2)


def test_resolve_recipients_still_resolves_valid_mixed_union():
    candidates = [
        RoutingAgent(agent_id="v1", workspace_id="w" * 64, role="validator"),
        RoutingAgent(agent_id="w1", workspace_id="w" * 64, capabilities=["ocr"]),
        RoutingAgent(agent_id="x1", workspace_id="w" * 64),
    ]
    out = resolve_recipients(
        {
            "strategy": "mixed",
            "rules": [
                {"strategy": "role", "role": "validator"},
                {"strategy": "capability", "capability": "ocr"},
            ],
        },
        candidates,
        NOW,
    )
    assert out == frozenset({"v1", "w1"})
