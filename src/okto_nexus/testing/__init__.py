"""Shipped eval scaffolding for the I8 replay harness (spec c7c1f834).

Turns the append-only event log into a re-executable coordination benchmark:
boot an isolated hub (:func:`build_hub`, :func:`pin_clock`, :class:`FakeServer`),
export it, then parse + reconstruct + re-export (:func:`load_replay`,
:func:`replay`, :func:`export_lines`) and assert structural equality via the pure
:func:`coordination_invariants`. Lives outside the domain/application import
boundary on purpose — it drives the mcp bootstrap and sqlite adapters directly.
"""

from __future__ import annotations

from .harness import ClockControl, FakeServer, Hub, build_hub, pin_clock
from .replay import (
    ReplayBundle,
    coordination_invariants,
    export_lines,
    load_replay,
    replay,
)

__all__ = [
    "FakeServer",
    "Hub",
    "ClockControl",
    "build_hub",
    "pin_clock",
    "ReplayBundle",
    "load_replay",
    "replay",
    "export_lines",
    "coordination_invariants",
]
