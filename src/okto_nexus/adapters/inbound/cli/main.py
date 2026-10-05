"""HTTP-only Nexus command entry point.

Harness native stdio protocols belong to the Core. Nexus MCP is served only
through ``okto-nexus serve`` and its HTTP ``/mcp`` endpoint.
"""

from __future__ import annotations

import sys

_HELP = """okto-nexus - local agent coordination bus

Usage:
  okto-nexus serve [options]   Start HTTP MCP, REST and dashboard
  okto-nexus tail [options]    Stream the event log as NDJSON
  okto-nexus admin <command>   Run maintenance commands
  okto-nexus provider-credentials <set|remove>  Manage provider secrets

Use `okto-nexus serve --help` for server options. Agents connect to /mcp
over HTTP with their existing API key.
"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:]) if argv is None else list(argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(_HELP)
        return 0
    command, rest = args[0], args[1:]
    if command == "serve":
        from .serve import run_serve
        return run_serve(rest)
    if command == "tail":
        from .tail import run_tail
        return run_tail(rest)
    if command == "admin":
        from .admin import run_admin
        return run_admin(rest)
    if command == "provider-credentials":
        from .provider_credentials import run_provider_credentials
        return run_provider_credentials(rest)
    print(
        "[okto-nexus] MCP stdio is no longer available. "
        "Run `okto-nexus serve` and connect to its HTTP /mcp endpoint.\n\n"
        + _HELP,
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
