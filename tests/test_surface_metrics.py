"""C3 / FR7: the resident-surface measurement instrument + frozen baseline.

Verifies the instrument computes the cuttable/total split correctly and that
the frozen baseline (BR8) is internally consistent. The >=40% reduction
ASSERTION (AC5) is owned by the T3/S4 test, which consumes this instrument.
"""

from __future__ import annotations

import asyncio
import os

from okto_nexus.adapters.inbound.mcp.server import bootstrap, create_server
from okto_nexus.adapters.inbound.mcp.surface_metrics import (
    BASELINE,
    cuttable_reduction_pct,
    measure_resident_surface,
)


def _server(tmp_path):
    env = {**os.environ, "OKTO_NEXUS_HOME": str(tmp_path)}
    return create_server(bootstrap(env, []))


def test_baseline_is_internally_consistent():
    assert BASELINE["cuttable"] == (
        BASELINE["instructions"] + BASELINE["docstrings"] + BASELINE["params"]
    )
    assert BASELINE["cuttable"] > 0


def test_measure_resident_surface_reports_components(tmp_path):
    server = _server(tmp_path)
    m = asyncio.run(measure_resident_surface(server))
    assert m["cuttable"] == m["instructions"] + m["docstrings"] + m["params"]
    # TOTAL adds the unavoidable JSON-schema scaffolding, so it exceeds the
    # instructions alone and the docstrings+params free text.
    assert m["total"] >= m["instructions"]
    assert m["cuttable"] > 0 and m["total"] > 0
    assert m["cuttable_tokens"] == m["cuttable"] // 4


def test_cuttable_reduction_helper_matches_baseline_math(tmp_path):
    server = _server(tmp_path)
    m = asyncio.run(measure_resident_surface(server))
    pct = cuttable_reduction_pct(m["cuttable"])
    assert pct == (BASELINE["cuttable"] - m["cuttable"]) / BASELINE["cuttable"]
    assert 0.0 <= pct < 1.0
