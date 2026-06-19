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


def cuttable_reduction_pct(current_cuttable: int) -> float:
    """Reduction of the cuttable surface vs the frozen baseline (0..1).

    ``(baseline_cuttable - current_cuttable) / baseline_cuttable`` - the exact
    quantity AC5/BR8 gate on (>= 0.40).
    """
    base = BASELINE["cuttable"]
    return (base - int(current_cuttable)) / base
