"""Unit tests for the tag / selector GRAMMAR and matching (domain, F1).

Covers :mod:`okto_nexus.domain.tag_selector` - the single source of truth for
the SHAPE of ``tags`` / ``selector`` / ``comm_scope`` and for the read-time
matching semantics: AND across selector keys, OR (non-empty intersection)
within a key's values, case-sensitive comparison, ``None``/empty selector =
allow-all, selector key absent from the agent's tags = no match. Existence
against the central catalog is the application layer's job and is NOT tested
here.
"""

from __future__ import annotations

import pytest

from okto_nexus.domain.tag_selector import (
    iter_pairs,
    iter_selector_keys,
    iter_selector_pairs,
    reachable,
    selector_matches,
    validate_comm_scope,
    validate_selector,
    validate_tags,
)
from okto_nexus.errors import ErrorCode, OktoNexusError


def assert_validation_error(exc_info) -> None:
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# validate_tags / validate_selector: shape
# --------------------------------------------------------------------------- #
def test_validate_tags_none_and_empty_normalise_to_none():
    assert validate_tags(None) is None
    assert validate_tags({}) is None


def test_validate_tags_normalises_values_and_dedupes():
    tags = validate_tags({"team": ["backend", "backend", " infra "], "env": "dev"})
    assert tags == {"team": ["backend", "infra"], "env": ["dev"]}


@pytest.mark.parametrize(
    "bad",
    [
        "team=backend",  # not a mapping
        ["team"],  # not a mapping
        {"": ["x"]},  # blank key
        {"team": []},  # empty value list (can never match)
        {"team": [""]},  # blank value
        {"team": [1]},  # non-string value
        {"team": {"backend": True}},  # mapping value
        {"team": None},  # null value
    ],
)
def test_validate_tags_rejects_malformed_shapes(bad):
    with pytest.raises(OktoNexusError) as ei:
        validate_tags(bad)
    assert_validation_error(ei)


def test_validate_selector_mirrors_tags_shape():
    assert validate_selector(None) is None
    assert validate_selector({}) is None
    assert validate_selector({"team": "backend"}) == {"team": ["backend"]}
    with pytest.raises(OktoNexusError) as ei:
        validate_selector({"team": []})
    assert_validation_error(ei)


# --------------------------------------------------------------------------- #
# validate_comm_scope: envelope
# --------------------------------------------------------------------------- #
def test_validate_comm_scope_none_empty_and_all_null_normalise_to_none():
    assert validate_comm_scope(None) is None
    assert validate_comm_scope({}) is None
    assert validate_comm_scope({"outbound": None}) is None
    assert validate_comm_scope({"outbound": None, "inbound": None}) is None


def test_validate_comm_scope_keeps_normalised_outbound_selector():
    scope = validate_comm_scope({"outbound": {"team": "backend"}})
    assert scope == {"outbound": {"team": ["backend"]}}


def test_validate_comm_scope_rejects_unknown_directions_fail_closed():
    with pytest.raises(OktoNexusError) as ei:
        validate_comm_scope({"outbond": {"team": ["backend"]}})  # typo
    assert_validation_error(ei)
    assert "outbond" in str(ei.value.details.get("unknown"))


def test_validate_comm_scope_accepts_and_normalises_inbound():
    # F2: the inbound direction ("who may reach me") ships - same selector
    # grammar as outbound, string values normalised to one-element lists.
    scope = validate_comm_scope({"inbound": {"team": "backend"}})
    assert scope == {"inbound": {"team": ["backend"]}}
    both = validate_comm_scope(
        {"outbound": {"env": ["dev"]}, "inbound": {"team": ["backend", "infra"]}}
    )
    assert both == {
        "outbound": {"env": ["dev"]},
        "inbound": {"team": ["backend", "infra"]},
    }


def test_validate_comm_scope_rejects_malformed_inbound_selector():
    with pytest.raises(OktoNexusError) as ei:
        validate_comm_scope({"inbound": {"team": []}})
    assert_validation_error(ei)


def test_validate_comm_scope_rejects_non_mapping():
    with pytest.raises(OktoNexusError) as ei:
        validate_comm_scope("outbound: team=backend")
    assert_validation_error(ei)


# --------------------------------------------------------------------------- #
# selector_matches: read-time semantics (AC1)
# --------------------------------------------------------------------------- #
def test_none_and_empty_selector_match_everyone():
    assert selector_matches(None, {"team": ["backend"]}) is True
    assert selector_matches({}, {"team": ["backend"]}) is True
    assert selector_matches(None, None) is True
    assert selector_matches({}, {}) is True


def test_single_key_matches_on_non_empty_intersection():
    selector = {"team": ["backend", "infra"]}
    assert selector_matches(selector, {"team": ["backend"]}) is True
    assert selector_matches(selector, {"team": ["infra", "qa"]}) is True
    assert selector_matches(selector, {"team": ["frontend"]}) is False


def test_multiple_keys_are_anded():
    selector = {"team": ["backend"], "env": ["prod"]}
    assert selector_matches(selector, {"team": ["backend"], "env": ["prod"]}) is True
    assert selector_matches(selector, {"team": ["backend"], "env": ["dev"]}) is False
    assert selector_matches(selector, {"team": ["backend"]}) is False


def test_absent_key_never_matches():
    assert selector_matches({"team": ["backend"]}, {}) is False
    assert selector_matches({"team": ["backend"]}, None) is False
    assert selector_matches({"team": ["backend"]}, {"env": ["prod"]}) is False


def test_matching_is_case_sensitive():
    assert selector_matches({"team": ["Backend"]}, {"team": ["backend"]}) is False
    assert selector_matches({"Team": ["backend"]}, {"team": ["backend"]}) is False


def test_matching_never_raises_on_malformed_sides():
    # Malformed selector entries simply do not match (fail-closed at read).
    assert selector_matches({"team": 42}, {"team": ["backend"]}) is False
    assert selector_matches({"team": ["backend"]}, {"team": 42}) is False
    assert selector_matches("garbage", {"team": ["backend"]}) is False


def test_matching_accepts_bare_string_values_on_either_side():
    assert selector_matches({"team": "backend"}, {"team": ["backend"]}) is True
    assert selector_matches({"team": ["backend"]}, {"team": "backend"}) is True


# --------------------------------------------------------------------------- #
# iter_pairs: the catalog existence-check feeder
# --------------------------------------------------------------------------- #
def test_iter_pairs_yields_every_key_value_pair():
    pairs = list(iter_pairs({"team": ["backend", "infra"], "env": ["prod"]}))
    assert pairs == [("team", "backend"), ("team", "infra"), ("env", "prod")]


def test_iter_pairs_tolerates_none_and_bare_strings():
    assert list(iter_pairs(None)) == []
    assert list(iter_pairs({"team": "backend"})) == [("team", "backend")]


# --------------------------------------------------------------------------- #
# reachable: the F2 double-intersection predicate (AC2)
# --------------------------------------------------------------------------- #
def _agent(agent_id, tags=None, outbound=None, inbound=None):
    scope: dict = {}
    if outbound is not None:
        scope["outbound"] = outbound
    if inbound is not None:
        scope["inbound"] = inbound
    return {"agent_id": agent_id, "tags": tags, "comm_scope": scope or None}


def test_reachable_with_no_selectors_on_either_side_is_true():
    assert reachable(_agent("a"), _agent("b")) is True


def test_reachable_false_when_sender_outbound_misses_recipient_tags():
    sender = _agent("a", outbound={"team": ["backend"]})
    recipient = _agent("b", tags={"team": ["frontend"]})
    assert reachable(sender, recipient) is False


def test_reachable_false_when_recipient_inbound_misses_sender_tags():
    sender = _agent("a", tags={"sector": ["DEV"]})
    recipient = _agent("b", inbound={"sector": ["OPS"]})
    assert reachable(sender, recipient) is False


def test_reachable_true_when_both_legs_match():
    sender = _agent("a", tags={"sector": ["DEV"]}, outbound={"team": ["core"]})
    recipient = _agent("b", tags={"team": ["core"]}, inbound={"sector": ["DEV"]})
    assert reachable(sender, recipient) is True


def test_reachable_self_is_always_true_even_with_non_matching_selectors():
    # The agent's own selectors do not match its own tags - self still passes.
    me = _agent(
        "a",
        tags={"team": ["qa"]},
        outbound={"team": ["core"]},
        inbound={"team": ["core"]},
    )
    assert reachable(me, me) is True
    assert reachable(me, _agent("a")) is True


def test_reachable_accepts_object_participants_too():
    class P:
        def __init__(self, agent_id, tags=None, comm_scope=None):
            self.agent_id = agent_id
            self.tags = tags
            self.comm_scope = comm_scope

    sender = P("a", tags={"sector": ["DEV"]})
    recipient = P("b", comm_scope={"inbound": {"sector": ["DEV"]}})
    assert reachable(sender, recipient) is True
    blocked = P("c", comm_scope={"inbound": {"sector": ["OPS"]}})
    assert reachable(sender, blocked) is False


# --------------------------------------------------------------------------- #
# F3 - rich form validation (fail-closed) - AC1 / ts_fe17e4d3
# --------------------------------------------------------------------------- #
def test_validate_selector_accepts_rich_form_and_normalises():
    rich = validate_selector(
        [
            {"key": " team ", "operator": "In", "values": ["backend", "backend"]},
            {"key": "env", "operator": "NotIn", "values": "prod"},
            {"key": "sector", "operator": "Exists"},
            {"key": "legacy", "operator": "DoesNotExist", "values": []},
        ]
    )
    assert rich == [
        {"key": "team", "operator": "In", "values": ["backend"]},
        {"key": "env", "operator": "NotIn", "values": ["prod"]},
        {"key": "sector", "operator": "Exists"},
        {"key": "legacy", "operator": "DoesNotExist"},
    ]


def test_validate_selector_empty_expression_list_is_allow_all():
    assert validate_selector([]) is None


@pytest.mark.parametrize(
    "bad_expression",
    [
        {"key": "team", "operator": "Foo", "values": ["x"]},  # unknown operator
        {"key": "team", "operator": "in", "values": ["x"]},  # case-sensitive
        {"key": "team", "operator": "Exists", "values": ["x"]},  # values forbidden
        {"key": "team", "operator": "DoesNotExist", "values": ["x"]},
        {"key": "team", "operator": "In"},  # values required
        {"key": "team", "operator": "NotIn", "values": []},  # empty values
        {"key": "team", "operator": "In", "values": [""]},  # blank value
        {"key": "team", "operator": "In", "values": 42},  # non-list values
        {"key": "", "operator": "In", "values": ["x"]},  # blank key
        {"operator": "In", "values": ["x"]},  # missing key
        {"key": "team"},  # missing operator
        {"key": "team", "operator": "In", "values": ["x"], "vaules": 1},  # typo field
        "team=backend",  # non-mapping expression
        42,
    ],
)
def test_validate_selector_rejects_malformed_expressions(bad_expression):
    with pytest.raises(OktoNexusError) as ei:
        validate_selector([bad_expression])
    assert_validation_error(ei)


def test_validate_selector_rejects_non_map_non_list():
    with pytest.raises(OktoNexusError) as ei:
        validate_selector("team=backend")
    assert_validation_error(ei)


def test_validate_tags_never_accepts_expressions():
    # Tags are ALWAYS flat - the rich form exists only on the selector side.
    with pytest.raises(OktoNexusError) as ei:
        validate_tags([{"key": "team", "operator": "In", "values": ["x"]}])
    assert_validation_error(ei)


def test_validate_comm_scope_accepts_rich_selectors_per_direction():
    scope = validate_comm_scope(
        {
            "outbound": [{"key": "sector", "operator": "NotIn", "values": ["OPS"]}],
            "inbound": {"team": "core"},
        }
    )
    assert scope == {
        "outbound": [{"key": "sector", "operator": "NotIn", "values": ["OPS"]}],
        "inbound": {"team": ["core"]},
    }
    with pytest.raises(OktoNexusError) as ei:
        validate_comm_scope(
            {"outbound": [{"key": "sector", "operator": "Exists", "values": ["x"]}]}
        )
    assert_validation_error(ei)


# --------------------------------------------------------------------------- #
# F3 - operator truth table over multi-value tags - AC3 / ts_9bbbcdea
# --------------------------------------------------------------------------- #
def _expr(key, operator, values=None):
    expression = {"key": key, "operator": operator}
    if values is not None:
        expression["values"] = values
    return [expression]


@pytest.mark.parametrize(
    ("operator", "values", "tags", "expected"),
    [
        # In: present-and-intersecting matches; present-disjoint and ABSENT do not.
        ("In", ["DEV"], {"sector": ["DEV", "QA"]}, True),
        ("In", ["OPS"], {"sector": ["DEV", "QA"]}, False),
        ("In", ["DEV"], {}, False),
        ("In", ["DEV"], None, False),
        ("In", ["OPS", "QA"], {"sector": ["DEV", "QA"]}, True),  # multi-value OR
        # NotIn: disjoint matches; ANY intersection blocks; ABSENT MATCHES (K8s).
        ("NotIn", ["OPS"], {"sector": ["DEV", "QA"]}, True),
        ("NotIn", ["DEV"], {"sector": ["DEV", "QA"]}, False),  # AC3 explicit case
        ("NotIn", ["DEV"], {}, True),
        ("NotIn", ["DEV"], None, True),
        ("NotIn", ["DEV", "QA"], {"sector": ["QA"]}, False),
        # Exists: presence alone decides (values forbidden at write time).
        ("Exists", None, {"sector": ["DEV"]}, True),
        ("Exists", None, {"other": ["X"]}, False),
        ("Exists", None, {}, False),
        ("Exists", None, None, False),
        # DoesNotExist: absence alone decides - ABSENT MATCHES (K8s parity).
        ("DoesNotExist", None, {"sector": ["DEV"]}, False),
        ("DoesNotExist", None, {"other": ["X"]}, True),
        ("DoesNotExist", None, {}, True),
        ("DoesNotExist", None, None, True),
    ],
)
def test_expression_truth_table(operator, values, tags, expected):
    assert selector_matches(_expr("sector", operator, values), tags) is expected


def test_expressions_are_anded_exists_plus_notin():
    # The documented composition against the absence trap: "has the key AND
    # is not X" - a lone NotIn would match untagged agents.
    selector = [
        {"key": "sector", "operator": "Exists"},
        {"key": "sector", "operator": "NotIn", "values": ["OPS"]},
    ]
    assert selector_matches(selector, {"sector": ["DEV"]}) is True
    assert selector_matches(selector, {"sector": ["OPS"]}) is False
    assert selector_matches(selector, {}) is False  # untagged blocked by Exists
    assert selector_matches(selector, None) is False


def test_lone_notin_matches_untagged_agents_absence_trap():
    # The trap itself, pinned as behaviour: NotIn alone matches agents with
    # no tags at all (K8s parity - decided in Q&A).
    assert selector_matches(_expr("sector", "NotIn", ["OPS"]), None) is True
    assert selector_matches(_expr("sector", "NotIn", ["OPS"]), {}) is True


# --------------------------------------------------------------------------- #
# F3 - flat form is In sugar (programmatic equivalence) - AC2 / ts_2a138c8c
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "tags",
    [
        None,
        {},
        {"team": ["backend"]},
        {"team": ["frontend"]},
        {"team": ["backend", "infra"], "env": ["prod"]},
        {"team": ["backend"], "env": ["dev"]},
        {"env": ["prod"]},
        {"area": ["ENG/BACKEND"]},
        {"area": ["ENGX"]},
    ],
)
def test_flat_selector_equals_its_in_translation(tags):
    flat = {"team": ["backend", "infra"], "env": ["prod"], "area": ["ENG"]}
    rich = [
        {"key": key, "operator": "In", "values": values} for key, values in flat.items()
    ]
    assert selector_matches(flat, tags) is selector_matches(rich, tags)


# --------------------------------------------------------------------------- #
# F3 - hierarchical segment matching - AC4 / ts_99713507
# --------------------------------------------------------------------------- #
def test_hierarchy_selector_covers_subtree_segmentwise():
    selector = _expr("area", "In", ["ENG"])
    assert selector_matches(selector, {"area": ["ENG"]}) is True
    assert selector_matches(selector, {"area": ["ENG/BACKEND"]}) is True
    assert selector_matches(selector, {"area": ["ENG/BACKEND/API"]}) is True
    # Segment comparison, never a string prefix.
    assert selector_matches(selector, {"area": ["ENGX"]}) is False
    assert selector_matches(selector, {"area": ["ENGINEERING"]}) is False


def test_hierarchy_is_one_directional():
    # A more specific selector does NOT cover a more general tag.
    selector = _expr("area", "In", ["ENG/BACKEND"])
    assert selector_matches(selector, {"area": ["ENG"]}) is False
    assert selector_matches(selector, {"area": ["ENG/BACKEND"]}) is True


def test_hierarchy_notin_excludes_whole_subtree():
    selector = _expr("area", "NotIn", ["ENG"])
    assert selector_matches(selector, {"area": ["ENG"]}) is False
    assert selector_matches(selector, {"area": ["ENG/BACKEND"]}) is False
    assert selector_matches(selector, {"area": ["ENGX"]}) is True
    assert selector_matches(selector, {"area": ["SALES"]}) is True
    assert selector_matches(selector, {}) is True  # absent still matches NotIn


def test_hierarchy_applies_to_flat_form_too():
    assert selector_matches({"area": ["ENG"]}, {"area": ["ENG/BACKEND"]}) is True
    assert selector_matches({"area": ["ENG"]}, {"area": ["ENGX"]}) is False
    assert selector_matches({"area": ["ENG"]}, {"area": ["eng/backend"]}) is False


# --------------------------------------------------------------------------- #
# F3 - selector iterators (the catalog existence-gate feeders)
# --------------------------------------------------------------------------- #
def test_iter_selector_keys_covers_both_forms_including_presence_ops():
    assert list(iter_selector_keys({"team": ["backend"], "env": ["prod"]})) == [
        "team",
        "env",
    ]
    rich = [
        {"key": "team", "operator": "In", "values": ["backend"]},
        {"key": "sector", "operator": "Exists"},
        {"key": "legacy", "operator": "DoesNotExist"},
    ]
    assert list(iter_selector_keys(rich)) == ["team", "sector", "legacy"]
    assert list(iter_selector_keys(None)) == []


def test_iter_selector_pairs_only_value_operators_contribute():
    assert list(iter_selector_pairs({"team": ["backend", "infra"]})) == [
        ("team", "backend"),
        ("team", "infra"),
    ]
    rich = [
        {"key": "team", "operator": "In", "values": ["backend"]},
        {"key": "env", "operator": "NotIn", "values": ["prod", "stage"]},
        {"key": "sector", "operator": "Exists"},
    ]
    assert list(iter_selector_pairs(rich)) == [
        ("team", "backend"),
        ("env", "prod"),
        ("env", "stage"),
    ]
    assert list(iter_selector_pairs(None)) == []


# --------------------------------------------------------------------------- #
# F3 - reachable composes with rich selectors (smoke; E2E lives in C3 tests)
# --------------------------------------------------------------------------- #
def test_reachable_with_rich_selectors_on_both_legs():
    sender = _agent(
        "a",
        tags={"sector": ["DEV"]},
        outbound=[{"key": "sector", "operator": "NotIn", "values": ["OPS"]}],
    )
    recipient = _agent(
        "b",
        tags={"sector": ["QA"]},
        inbound=[{"key": "sector", "operator": "Exists"}],
    )
    assert reachable(sender, recipient) is True
    ops = _agent("c", tags={"sector": ["OPS"]})
    assert reachable(sender, ops) is False  # sender's NotIn blocks OPS
    untagged = _agent("d")
    assert reachable(untagged, recipient) is False  # recipient requires Exists
