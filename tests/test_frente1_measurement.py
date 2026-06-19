"""Frente 1 (resident-surface token reduction) measurement contract — card T3.

Two scenarios from the spec:

* **S4 (AC5)** — the >=40% cuttable-reduction gate. We build the REAL FastMCP
  server (``create_server`` over a real migrated temp store), measure its
  resident surface with the SAME deterministic char-count proxy that froze the
  baseline (BR8), and assert the cuttable component shrank by at least 40%
  versus the frozen :data:`BASELINE` AND is strictly below it.

* **S5 (AC6)** — the A/B assertiveness battery is a PROBABILISTIC/MANUAL gate
  (BR7): it requires live agents across two harnesses and the OLD surface
  (obtained by ``git checkout 830a6ab`` or a flag), so it is NOT run in the unit
  suite. The test documents the operator procedure and ``pytest.skip``s, but
  first asserts the STRUCTURAL readiness of the instrument: the operator
  measures the new surface with ``measure_resident_surface`` and the old surface
  by checking out the baseline commit and running the same instrument, both
  comparable to the frozen :data:`BASELINE`.

Both build the server exactly as ``tests/test_tools_surface.py`` /
``tests/test_tool_schemas.py`` do; the MCP SDK is required to build the live
surface, so the slice is skipped if it is absent.
"""

from __future__ import annotations

import asyncio

import pytest

from okto_nexus.adapters.inbound.mcp.surface_metrics import (
    BASELINE,
    cuttable_reduction_pct,
    measure_resident_surface,
)

pytest.importorskip("mcp", reason="MCP SDK required to build the live MCP surface")

from okto_nexus.adapters.inbound.mcp.server import bootstrap, create_server


def _build_server(tmp_path):
    """Build the live FastMCP server over a real migrated temp store."""
    deps = bootstrap({"OKTO_NEXUS_HOME": str(tmp_path / "home")}, [])
    return create_server(deps)


# --------------------------------------------------------------------------- #
# S4 (AC5): the >=40% cuttable-reduction gate
# --------------------------------------------------------------------------- #
def test_s4_cuttable_surface_meets_40pct_reduction_gate(tmp_path):
    """AC5: the cuttable resident surface is >=40% smaller than the baseline."""
    server = _build_server(tmp_path)

    m = asyncio.run(measure_resident_surface(server))

    # The cuttable component the front controls (instructions + docstrings +
    # param descriptions).
    cuttable = m["cuttable"]
    assert isinstance(cuttable, int)

    # Gate 1: >=40% reduction vs the FROZEN baseline (BR8), measured with the
    # same char-count proxy that captured the baseline.
    reduction = cuttable_reduction_pct(cuttable)
    assert reduction >= 0.40, (
        f"cuttable resident surface must shrink >=40% vs baseline "
        f"{BASELINE['cuttable']} chars; measured {cuttable} chars "
        f"(reduction {reduction:.2%})"
    )

    # Gate 2: the new cuttable surface is strictly below the frozen baseline.
    assert cuttable < BASELINE["cuttable"], (
        f"cuttable surface {cuttable} must be strictly below baseline "
        f"{BASELINE['cuttable']}"
    )


# --------------------------------------------------------------------------- #
# S5 (AC6): A/B assertiveness battery — manual/probabilistic gate (BR7)
# --------------------------------------------------------------------------- #
def test_s5_ab_assertiveness_battery_is_a_manual_gate(tmp_path):
    """AC6/BR7: the A/B assertiveness battery is a manual, probabilistic gate.

    It is NOT run in the unit suite (it needs live agents across two harnesses
    and the OLD surface via ``git checkout 830a6ab``). Before skipping we assert
    the instrument is structurally ready: the operator measures the NEW surface
    with ``measure_resident_surface`` and the OLD surface by checking out the
    baseline commit and running the SAME instrument, comparing both to the
    frozen :data:`BASELINE`.
    """
    # Structural readiness of the instrument the operator drives by hand.
    assert callable(measure_resident_surface), (
        "operator needs measure_resident_surface to measure both surfaces"
    )
    assert isinstance(BASELINE, dict) and "cuttable" in BASELINE, (
        "operator needs the frozen BASELINE as the comparable reference point"
    )
    # And it actually runs against the live (new) surface — same instrument the
    # operator re-runs against the old surface after the checkout.
    server = _build_server(tmp_path)
    measured = asyncio.run(measure_resident_surface(server))
    assert "cuttable" in measured

    pytest.skip(
        "BR7: the A/B assertiveness battery is a MANUAL/CI probabilistic gate, "
        "not a unit test. The operator: (1) measures the NEW surface with "
        "measure_resident_surface; (2) checks out the OLD surface via "
        "`git checkout 830a6ab` (or an equivalent flag) and runs the SAME "
        "instrument; (3) runs >=10 trials per task per harness across 2 "
        "harnesses; (4) requires a Wilson 95% no-regression interval on task "
        "assertiveness before the gate passes."
    )
