"""Legacy import surface for MCP registration and transport-neutral bootstrap.

The executable CLI dispatches HTTP only; no MCP stdio transport is started.
"""
from __future__ import annotations

from okto_nexus.bootstrap.dependencies import (
    Deps, bootstrap, build_repos, build_telemetry, maybe_auto_prune,
)
from .registration import (
    SERVER_INSTRUCTIONS, SURFACE_REVISION, TelemetryToolServer,
    _load_fastmcp, _package_version, _schema_version, create_server,
    register_meta_tools, register_resources, register_tools,
)

__all__ = [
    "Deps", "bootstrap", "build_repos", "build_telemetry", "maybe_auto_prune",
    "SERVER_INSTRUCTIONS", "SURFACE_REVISION", "TelemetryToolServer",
    "_load_fastmcp", "_package_version", "_schema_version", "create_server",
    "register_meta_tools", "register_resources", "register_tools", "main",
]

def main(argv: list[str] | None = None) -> int:
    """Compatibility import for callers of the old Python entry point.

    The CLI implementation lives in ``adapters.inbound.cli.main``. No call
    path from here starts an MCP stdio transport.
    """
    from ..cli.main import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
