"""In-process hub harness for replay evals (spec c7c1f834, I8).

This is the SHIPPED eval scaffolding — first-class, not a test-only fixture — so
an external benchmark can drive the real MCP tools without a socket, a broker or
the ``serve`` lock. It is deliberately OUTSIDE the domain/application import
boundary (the boundary test scans only those two packages), so it is free to
touch the mcp server bootstrap and the sqlite adapters.

``FakeServer`` mimics FastMCP's ``@server.tool()`` registration in memory —
``register_tools`` populates it and each tool becomes a plain callable that
returns the canonical ``{ok, data}`` envelope. ``build_hub`` bootstraps a fresh,
ISOLATED hub on a throwaway ``OKTO_NEXUS_HOME`` (so it NEVER collides with a
running ``serve`` — the operator's live bus is untouched) and registers every
tool. ``pin_clock`` freezes/advances the injected clock so a seeded scenario has
deterministic timestamps — the precondition for the byte-identity contract.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

__all__ = ["FakeServer", "Hub", "ClockControl", "build_hub", "pin_clock"]


class FakeServer:
    """Minimal in-memory stand-in for the FastMCP server.

    ``@server.tool()`` (called, with or without kwargs) registers a function
    under its ``__name__``; coroutine tools are wrapped so callers invoke them
    synchronously. ``tools`` is the resulting name -> callable registry.
    """

    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}

    def tool(self, *_args: Any, **_kwargs: Any) -> Callable[[Callable], Callable]:
        def register(fn: Callable) -> Callable:
            if inspect.iscoroutinefunction(fn):

                @functools.wraps(fn)
                def _sync(*a: Any, **k: Any) -> Any:
                    return asyncio.run(fn(*a, **k))

                self.tools[fn.__name__] = _sync
            else:
                self.tools[fn.__name__] = fn
            return fn

        return register


@dataclass
class Hub:
    """A booted, isolated hub: its ``deps``, the ``FakeServer`` and its tool map."""

    deps: Any
    server: FakeServer
    tools: dict[str, Callable[..., Any]]
    home: Path


def build_hub(
    env: Mapping[str, str] | None = None,
    *,
    argv: list[str] | None = None,
    register: bool = True,
) -> Hub:
    """Bootstrap a fresh, isolated hub and (by default) register every tool.

    A throwaway ``OKTO_NEXUS_HOME`` is minted unless ``env`` already pins one,
    so two hubs (e.g. the seeder and the reconstruction) never share a store and
    never touch the operator's live bus. The mcp server import is LAZY (kept out
    of ``import okto_nexus.testing``) — only ``build_hub`` pulls it in.
    """
    from okto_nexus.adapters.inbound.mcp.server import (
        bootstrap,
        register_meta_tools,
        register_tools,
    )

    resolved_env: dict[str, str] = dict(env or {})
    home = Path(
        resolved_env.get("OKTO_NEXUS_HOME") or tempfile.mkdtemp(prefix="nexus_eval_")
    )
    resolved_env.setdefault("OKTO_NEXUS_HOME", str(home))

    deps = bootstrap(resolved_env, list(argv or []))
    server = FakeServer()
    if register:
        # Both registration paths the real server mounts: the auto-discovered
        # slice tools AND the server-level meta tools (nexus_info).
        register_tools(server, deps)
        register_meta_tools(server, deps)
    return Hub(deps=deps, server=server, tools=server.tools, home=home)


def _epoch_to_iso(epoch: float) -> str:
    """Render epoch seconds as the canonical UTC ISO instant (…Z, microseconds)."""
    return (
        datetime.fromtimestamp(epoch, timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


class ClockControl:
    """Handle over a pinned clock: ``set``/``advance`` move deterministic time.

    Installs ``now_epoch``/``now_iso`` closures that read ``self.epoch`` at call
    time, so mutating the handle steers every subsequent timestamp the hub
    stamps — the mechanism a scenario uses to lay events at chosen instants.
    """

    def __init__(self, deps: Any, epoch: float) -> None:
        self._deps = deps
        self.epoch = float(epoch)
        deps.clock.now_epoch = lambda: self.epoch
        deps.clock.now_iso = lambda: _epoch_to_iso(self.epoch)

    def set(self, epoch: float) -> "ClockControl":
        self.epoch = float(epoch)
        return self

    def advance(self, seconds: float) -> "ClockControl":
        self.epoch += float(seconds)
        return self


def pin_clock(deps: Any, epoch: float) -> ClockControl:
    """Freeze the hub's clock at ``epoch`` and return a steerable handle."""
    return ClockControl(deps, epoch)
