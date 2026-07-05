"""TC4 - replay-harness tests (spec c7c1f834, TS8 + TS9 + TS10).

Anchored on the committed golden fixture ``tests/replay_fixtures/*.ndjson``:
``replay()`` reconstructs it into a fresh empty hub preserving event_id +
created_at (re-export byte-identical modulo the manifest), and
``coordination_invariants`` over it matches the hand-verified V1 baseline. TS10
proves the shipped ``okto_nexus.testing`` package stays off the mcp import path
and adds zero third-party dependency.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from okto_nexus.testing import (
    build_hub,
    coordination_invariants,
    export_lines,
    load_replay,
    replay,
)

pytestmark = pytest.mark.replay

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE = _REPO_ROOT / "tests" / "replay_fixtures" / "coordination_v1.ndjson"
_GOLDEN_WS = "ws_golden_00000000000000000000000000000000"

# Hand-verified V1 invariants of the golden fixture (a coordination scenario:
# 3 agents, 3 messages, 4 handoffs incl. one reclaim cycle w/ lease expiry).
_EXPECTED_INVARIANTS = {
    "total_events": 15,
    "event_id_min": 1,
    "event_id_max": 15,
    "distinct_actors": 3,
    "event_type_histogram": {
        "handoff.claimed": 4,
        "handoff.completed": 2,
        "handoff.created": 4,
        "handoff.expired": 1,
        "handoff.rejected": 1,
        "message.created": 3,
    },
    "stream_histogram": {"handoff": 12, "workspace": 3},
    "actor_activity": {"alpha": 7, "beta": 5, "gamma": 2},
    "handoff_lifecycle": {
        "distinct_handoffs": 4,
        "created": 4,
        "claimed": 4,
        "completed": 2,
        "rejected": 1,
        "cancelled": 0,
        "terminal_reached": 3,
        "reclaim_cycles": 1,
    },
    "claim_to_complete_latencies": [40.0, 60.0],
    "message_fanout": {
        "total_messages": 3,
        "by_strategy": {"broadcast": 1, "direct": 2},
    },
}


def test_fixture_is_present_and_parses() -> None:
    assert _FIXTURE.exists(), f"missing golden fixture: {_FIXTURE}"
    bundle = load_replay(_FIXTURE)
    assert bundle.manifest["format_version"] == 1
    assert bundle.manifest["workspace_id"] == _GOLDEN_WS
    assert len(bundle.events) == bundle.manifest["event_count"]


# --------------------------------------------------------------------------- #
# TS8 - replay() preserves event_id + created_at; re-export byte-identical
# --------------------------------------------------------------------------- #
def test_ts8_replay_round_trip_is_faithful() -> None:
    bundle = load_replay(_FIXTURE)
    fixture_event_lines = _FIXTURE.read_text(encoding="utf-8").splitlines()[1:]

    hub = build_hub()  # empty, freshly bootstrapped -> no AUTOINCREMENT collision
    seeded = replay(hub.deps, bundle.events)
    assert seeded == {_GOLDEN_WS}

    # event_id + created_at preserved verbatim in the reconstructed table
    reread = export_lines(
        hub.deps, _GOLDEN_WS, generated_at="2020-01-01T00:00:00.000000Z"
    )
    import json

    re_events = [json.loads(x) for x in reread[1:]]
    assert {(e["event_id"], e["created_at"]) for e in re_events} == {
        (e["event_id"], e["created_at"]) for e in bundle.events
    }

    # re-export event lines are BYTE-identical to the fixture (single serializer)
    assert reread[1:] == fixture_event_lines


# --------------------------------------------------------------------------- #
# TS9 - coordination_invariants over the golden fixture = expected baseline
# --------------------------------------------------------------------------- #
def test_ts9_coordination_invariants_match_golden() -> None:
    bundle = load_replay(_FIXTURE)
    assert coordination_invariants(bundle.events) == _EXPECTED_INVARIANTS


def test_ts9_invariants_stable_after_reconstruction() -> None:
    # The benchmark is re-executable: invariants are identical whether computed
    # from the raw bundle or after a reconstruct + re-export round-trip.
    bundle = load_replay(_FIXTURE)
    hub = build_hub()
    replay(hub.deps, bundle.events)
    reread = export_lines(hub.deps, _GOLDEN_WS, generated_at="x")
    import json

    re_events = [json.loads(x) for x in reread[1:]]
    assert coordination_invariants(re_events) == _EXPECTED_INVARIANTS


# --------------------------------------------------------------------------- #
# TS10 - okto_nexus.testing: mcp stays off the import path; zero new dep
# --------------------------------------------------------------------------- #
def test_ts10_importing_testing_does_not_pull_mcp() -> None:
    # A FRESH interpreter importing only the harness must NOT import the mcp SDK
    # (build_hub pulls it lazily). Run out-of-process so a suite that already
    # imported mcp elsewhere cannot mask the regression.
    code = (
        "import sys; import okto_nexus.testing as t; "
        "assert 'mcp' not in sys.modules, sorted(m for m in sys.modules if m.startswith('mcp')); "
        "assert hasattr(t, 'FakeServer') and hasattr(t, 'coordination_invariants')"
    )
    # extend (not replace) the env: a bare env breaks winsock/asyncio init on
    # Windows. PYTHONPATH points the fresh interpreter at the source tree.
    env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "src")}
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env
    )
    assert proc.returncode == 0, proc.stderr


def test_ts10_fakeserver_registers_tools_without_fastmcp() -> None:
    from okto_nexus.testing import FakeServer

    server = FakeServer()

    @server.tool()
    def sample_tool(x: int) -> int:
        return x + 1

    assert "sample_tool" in server.tools
    assert server.tools["sample_tool"](x=41) == 42
