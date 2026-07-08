"""Guardrail administration is intentionally not exposed as MCP tools.

Guardrails, explicit agent groups, assignments and denial inspection are
critical operational controls. Agents must not receive schemas that can mutate
or inspect those controls; the human UI/REST surface remains the only admin
path.
"""

from __future__ import annotations

from typing import Any


def register(server: Any, deps: Any) -> None:
    """Participate in module discovery without registering agent tools."""
    _ = (server, deps)
    return None
