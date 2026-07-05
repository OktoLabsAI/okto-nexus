"""TC1 - pure domain/replay tests (spec c7c1f834, TS0 + TS1).

Exercises the canonical serializer/parser round-trip, the versioned fail-closed
manifest parser, and the coordination invariants over a HAND-COMPUTED synthetic
event list (structural, field-by-field - never a payload snapshot). Pure stdlib:
no bootstrap, no sqlite, no mcp.
"""

from __future__ import annotations

import json

import pytest

from okto_nexus.domain.handoff import (
    EVENT_CLAIMED,
    EVENT_COMPLETED,
    EVENT_CREATED,
    EVENT_REJECTED,
    HANDOFF_STREAM,
)
from okto_nexus.domain.replay import (
    EVENT_COLUMNS,
    FORMAT_VERSION,
    MANIFEST_KIND,
    actor_activity,
    canonical_filters,
    claim_to_complete_latencies,
    coordination_invariants,
    event_type_histogram,
    handoff_lifecycle,
    message_fanout,
    parse_line,
    parse_manifest,
    serialize_event,
    serialize_manifest,
    stream_histogram,
)
from okto_nexus.errors import ErrorCode, OktoNexusError

pytestmark = pytest.mark.replay

_BASE = 1_800_000_000


def _iso(offset: int) -> str:
    # Canonical UTC instant used by the store; kept literal so the test never
    # depends on the clock adapter.
    from datetime import datetime, timezone

    return (
        datetime.fromtimestamp(_BASE + offset, timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


# --------------------------------------------------------------------------- #
# TS0 - round-trip serialize/parse + FORMAT_VERSION + fail-closed parser
# --------------------------------------------------------------------------- #
def test_ts0_event_round_trip_is_byte_stable_and_ordered() -> None:
    event = {
        "event_id": 7,
        "workspace_id": "ws_abc",
        "stream": "handoff",
        "type": "handoff.created",
        "actor_agent_id": "álpha",  # non-ASCII: ensure_ascii=False must preserve it
        "payload": {"handoff_id": "h1", "note": "café"},
        "visibility": "public",
        "target": {"strategy": "direct", "agent_id": "beta"},
        "created_at": _iso(0),
        # a derived convenience key the read layer may add - must be DROPPED:
        "trace_id": "should-not-ship",
    }
    line = serialize_event(event)

    # Keys ship in the fixed EVENT_COLUMNS order; the derived trace_id is gone.
    expected = {col: event[col] for col in EVENT_COLUMNS}
    assert line == json.dumps(expected, ensure_ascii=False, separators=(",", ":"))
    assert "café" in line and "álpha" in line  # not \uXXXX-escaped
    assert "trace_id" not in json.loads(line)

    # Round-trip: parse_line reconstructs exactly the 9-column projection.
    assert parse_line(line) == expected


def test_ts0_manifest_round_trip_and_version() -> None:
    filters = canonical_filters(
        stream="handoff", trace_id=None, since_event_id=0, until_event_id=None
    )
    line = serialize_manifest(
        workspace_id="ws_abc",
        filters=filters,
        event_count=3,
        event_id_min=1,
        event_id_max=9,
        generated_at=_iso(10),
    )
    manifest = parse_manifest(line)
    assert manifest["kind"] == MANIFEST_KIND
    assert manifest["format_version"] == FORMAT_VERSION == 1
    assert manifest["workspace_id"] == "ws_abc"
    assert manifest["filters"] == {
        "stream": "handoff",
        "trace_id": None,
        "since_event_id": 0,
        "until_event_id": None,
    }
    assert (
        manifest["event_count"],
        manifest["event_id_min"],
        manifest["event_id_max"],
    ) == (
        3,
        1,
        9,
    )


def test_ts0_parse_manifest_rejects_unknown_version_fail_closed() -> None:
    bogus = json.dumps(
        {"kind": "manifest", "format_version": 999, "workspace_id": "ws"},
        separators=(",", ":"),
    )
    with pytest.raises(OktoNexusError) as ei:
        parse_manifest(bogus)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR
    assert "999" in ei.value.message  # cites the offending version


def test_ts0_parser_rejects_non_manifest_first_line() -> None:
    not_a_manifest = json.dumps({"kind": "event", "format_version": 1})
    with pytest.raises(OktoNexusError) as ei:
        parse_manifest(not_a_manifest)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR


def test_ts0_parse_line_rejects_malformed_and_non_object() -> None:
    with pytest.raises(OktoNexusError):
        parse_line("{not json")
    with pytest.raises(OktoNexusError):
        parse_line("[1, 2, 3]")  # valid JSON, but not an object


# --------------------------------------------------------------------------- #
# TS1 - invariants over a hand-computed synthetic log (exact values)
# --------------------------------------------------------------------------- #
def _ev(eid, stream, type_, actor, created_off, payload=None, target=None):
    return {
        "event_id": eid,
        "workspace_id": "ws",
        "stream": stream,
        "type": type_,
        "actor_agent_id": actor,
        "payload": payload or {},
        "visibility": "public",
        "target": target,
        "created_at": _iso(created_off),
    }


def _msg(eid, off, strategy, agent=None):
    target = {"strategy": strategy}
    if agent is not None:
        target["agent_id"] = agent
    return _ev(
        eid,
        "workspace",
        "message.created",
        "alpha",
        off,
        payload={"target": target},
        target=target,
    )


def _handoff(eid, off, type_, actor, hid):
    return _ev(eid, HANDOFF_STREAM, type_, actor, off, payload={"handoff_id": hid})


@pytest.fixture
def synthetic_events():
    return [
        # a null-actor system event: counted in totals, SKIPPED by actor_activity
        _ev(1, "workspace", "workspace.tick", None, 0),
        _msg(2, 1, "direct", "beta"),
        _msg(3, 2, "direct", "gamma"),
        _msg(4, 3, "broadcast"),
        # h1: created -> claimed(110) -> completed(140) => latency 30.0
        _handoff(5, 100, EVENT_CREATED, "alpha", "h1"),
        _handoff(6, 110, EVENT_CLAIMED, "beta", "h1"),
        _handoff(7, 140, EVENT_COMPLETED, "beta", "h1"),
        # h2: created -> claimed -> rejected (no complete)
        _handoff(8, 200, EVENT_CREATED, "alpha", "h2"),
        _handoff(9, 205, EVENT_CLAIMED, "beta", "h2"),
        _handoff(10, 208, EVENT_REJECTED, "beta", "h2"),
        # h3: created -> claimed(300) -> completed(345) => latency 45.0
        _handoff(11, 300, EVENT_CREATED, "alpha", "h3"),
        _handoff(12, 300, EVENT_CLAIMED, "gamma", "h3"),
        _handoff(13, 345, EVENT_COMPLETED, "gamma", "h3"),
        # h4: created -> claimed -> claimed (reclaim cycle; NEVER terminal)
        _handoff(14, 400, EVENT_CREATED, "alpha", "h4"),
        _handoff(15, 401, EVENT_CLAIMED, "beta", "h4"),
        _handoff(16, 520, EVENT_CLAIMED, "gamma", "h4"),
    ]


def test_ts1_event_type_and_stream_histograms(synthetic_events) -> None:
    assert event_type_histogram(synthetic_events) == {
        "handoff.claimed": 5,
        "handoff.completed": 2,
        "handoff.created": 4,
        "handoff.rejected": 1,
        "message.created": 3,
        "workspace.tick": 1,
    }
    assert stream_histogram(synthetic_events) == {"handoff": 12, "workspace": 4}


def test_ts1_actor_activity_skips_null_actor(synthetic_events) -> None:
    assert actor_activity(synthetic_events) == {"alpha": 7, "beta": 5, "gamma": 3}


def test_ts1_handoff_lifecycle_counts_and_reclaims(synthetic_events) -> None:
    assert handoff_lifecycle(synthetic_events) == {
        "distinct_handoffs": 4,
        "created": 4,
        "claimed": 5,
        "completed": 2,
        "rejected": 1,
        "cancelled": 0,
        "terminal_reached": 3,  # h1, h2, h3 (h4 never terminal)
        "reclaim_cycles": 1,  # h4 claimed twice
    }


def test_ts1_claim_to_complete_reuses_i7_correlator(synthetic_events) -> None:
    assert claim_to_complete_latencies(synthetic_events) == [30.0, 45.0]


def test_ts1_message_fanout_by_strategy(synthetic_events) -> None:
    assert message_fanout(synthetic_events) == {
        "total_messages": 3,
        "by_strategy": {"broadcast": 1, "direct": 2},
    }


def test_ts1_coordination_invariants_aggregate(synthetic_events) -> None:
    inv = coordination_invariants(synthetic_events)
    assert inv["total_events"] == 16
    assert (inv["event_id_min"], inv["event_id_max"]) == (1, 16)
    assert inv["distinct_actors"] == 3
    # the aggregate embeds every per-dimension breakdown verbatim
    assert inv["handoff_lifecycle"]["reclaim_cycles"] == 1
    assert inv["claim_to_complete_latencies"] == [30.0, 45.0]
    assert inv["message_fanout"]["total_messages"] == 3
