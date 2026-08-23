"""Resident-surface token measurement (Frente 1, card C3 / FR7).

Measures the size of the MCP surface that sits in an agent's context window on
EVERY turn, split into:

* ``cuttable`` - instructions + tool docstrings + parameter descriptions: the
  free text the token-reduction front actually controls; and
* ``total`` - the instructions plus the unavoidable JSON-schema scaffolding of
  every tool (names, types, ``required`` arrays, enum arrays) that the lock
  requires keeping.

Owner decision (2026-06-18): the >=40% reduction target (AC5) is measured on the
``cuttable`` component, EXCLUDING the scaffolding. A deterministic char-count
proxy for tokens (chars / :data:`TOKEN_PROXY_DIVISOR`) is used - the SAME proxy
that froze the baseline (BR8), so before/after are comparable and reproducible.

Pure measurement, part of the inbound MCP adapter; never touches
domain/application (hexagonal).
"""

from __future__ import annotations

import json
from typing import Any

#: chars/4 token proxy (BR8): the same divisor used to freeze the baseline.
TOKEN_PROXY_DIVISOR = 4

#: FROZEN baseline (BR8): the cuttable resident surface measured against the
#: pre-Frente-1 code (git 830a6ab) with the char-count proxy above. This is the
#: immutable point of comparison for the >=40% target - do NOT recompute it at
#: test time. Captured via a detached worktree at HEAD, 2026-06-19.
BASELINE: dict[str, int] = {
    "instructions": 11206,
    "docstrings": 13983,
    "params": 16406,
    "cuttable": 41595,  # == instructions + docstrings + params
}

#: Deliberate, spec-approved surface growth AFTER the Frente-1 baseline froze.
#: The >=40% gate (AC5) measures the Frente-1 CUT against the pre-Frente-1
#: surface - it is NOT a budget that forbids later features. Each later spec
#: that adds tools/params records its measured cuttable cost here (chars, the
#: same proxy, measured on the live server at landing time) and the gate
#: discounts exactly that; anything NOT in this ledger still trips the gate,
#: so gratuitous description bloat stays caught. The BASELINE above remains
#: frozen (BR8) - this ledger is additive and auditable per spec.
APPROVED_GROWTH: dict[str, int] = {
    # I4 handoff verification (spec c692da7e, SURFACE_REVISION 21): the
    # handoff_verify tool (docstring + params, 1076) + the optional
    # acceptance_criteria/verify_by params on handoff_create (569) + the
    # complete/get docstring updates (71).
    "verification_i4": 1716,
    # I5 handoff dependencies (spec 6522ad1f, SURFACE_REVISION 22): the
    # optional depends_on param on handoff_create (199) + the handoff_get
    # docstring update (+3). No new tool; depth lives in tool-docs/handoff v3.
    "orchestration_i5": 202,
    # I6 workspace memory (spec 8928b320, SURFACE_REVISION 23): THREE new
    # tools measured on the live server at landing time - memory_put
    # (docstring 123 + params 1315 = 1438), memory_get (108 + 196 = 304),
    # memory_search (129 + 517 = 646; _P_QUERY trimmed to the <=200 budget
    # during the T7 surface tests). Revision 29 made this experimental at
    # registration time, so the default surface no longer carries this cost;
    # the ledger keeps the approved cost for feature_memory-enabled servers.
    "memory_i6": 2388,
    # I7 coordination health (spec 7df9b1e0, SURFACE_REVISION 24): ONE new
    # tool measured on the live server at landing time - coordination_health
    # (docstring 159 + params 132 = 291: project_root 81, window 51). No
    # pre-existing tool touched; no new resource.
    "health_i7": 291,
    # B3 attachable policies (spec 80624c1a, SURFACE_REVISION 25): NO new tool -
    # two existing docstrings grew for the unified-policy surface, each kept under
    # the 200-char one-line tool-description budget (S2). agent_whoami now
    # advertises effective_policies (policy_id@version) + governance (+9);
    # artifact_get documents its audience-scoped read (+118). Measured on the
    # live server at landing time; no param added.
    "policies_b3": 127,
    # Communication presets (spec 6f961722, SURFACE_REVISION 26): NO new tool and
    # NO net resident growth - the agent_whoami one-line description was REWORDED
    # (197 -> 194 chars) to advertise the self-only communication block, and no
    # param was added. The feature surfaces at RUNTIME (a whoami response field),
    # not on the resident schema, so the ledger entry is 0. Recorded for audit
    # (every surface-touching spec appears here), kept under the 200-char S2
    # budget.
    "comm_presets_c5": 0,
    # EPT remote monitor data plane (spec nexus-monitor-spec, SURFACE_REVISION
    # 28): THREE new control-plane tools - poll_token_issue (269),
    # poll_token_renew (222), poll_token_revoke (152) - plus the compact
    # resident instruction delta pointing agents at the EPT monitoring resource.
    # Full remote-poller prose lives in okto-nexus://reference/monitoring.
    "monitor_ept": 760,
    # Intent-based coordination guidance (SURFACE_REVISION 32): the resident
    # SERVER_INSTRUCTIONS grew by 1240 chars to make role/communication profile
    # adherence and handoff-vs-message selection unambiguous; correcting the
    # stale handoff_list_available docstring removed 19 chars. Deep prose lives
    # in versioned resources and is not resident. Net measured growth: 1221.
    "coordination_guidance_r32": 1221,
}

#: Ledger entries whose tools are EXPERIMENTAL at the surface boundary
#: (registered only behind a feature flag, revision 29): their approved cost
#: is discounted from the 40% gate ONLY when the corresponding tools are
#: actually on the measured surface. Discounting them against the default
#: (flag-off) surface would shelter that many chars of phantom growth
#: (surface rev 31; análise 0003 finding metrics-phantom-memory-discount).
EXPERIMENTAL_GROWTH_KEYS: frozenset[str] = frozenset({"memory_i6"})


async def measure_resident_surface(server: Any) -> dict[str, int]:
    """Measure the live FastMCP ``server``'s resident surface in chars.

    Returns ``{instructions, docstrings, params, cuttable, total,
    cuttable_tokens, total_tokens}``. ``cuttable`` is the free text the front
    controls; ``total`` adds the serialized JSON-schema of every tool (the
    scaffolding the lock keeps). Token figures use the chars/4 proxy.
    """
    tools = await server.list_tools()
    instructions = len(getattr(server, "instructions", "") or "")
    docstrings = sum(len(t.description or "") for t in tools)
    params = sum(
        len(p.get("description", "") or "")
        for t in tools
        for p in (t.inputSchema or {}).get("properties", {}).values()
    )
    cuttable = instructions + docstrings + params
    schema_chars = sum(
        len(json.dumps(t.inputSchema or {}, ensure_ascii=False)) for t in tools
    )
    total = instructions + schema_chars
    return {
        "instructions": instructions,
        "docstrings": docstrings,
        "params": params,
        "cuttable": cuttable,
        "total": total,
        "cuttable_tokens": cuttable // TOKEN_PROXY_DIVISOR,
        "total_tokens": total // TOKEN_PROXY_DIVISOR,
    }


def cuttable_reduction_pct(
    current_cuttable: int, *, include_experimental: bool = False
) -> float:
    """Reduction of the cuttable surface vs the frozen baseline (0..1).

    ``(baseline_cuttable - (current_cuttable - approved_growth)) /
    baseline_cuttable`` - the exact quantity AC5/BR8 gate on (>= 0.40),
    discounting only the :data:`APPROVED_GROWTH` ledger (surface later specs
    deliberately added; unlisted growth still lowers the figure). Ledger
    entries in :data:`EXPERIMENTAL_GROWTH_KEYS` are discounted ONLY when
    ``include_experimental`` is True (i.e. the measured server registered the
    flag-gated tools) - against the default surface they would discount
    growth that is not there.
    """
    base = BASELINE["cuttable"]
    approved = sum(
        cost
        for key, cost in APPROVED_GROWTH.items()
        if include_experimental or key not in EXPERIMENTAL_GROWTH_KEYS
    )
    return (base - (int(current_cuttable) - approved)) / base
