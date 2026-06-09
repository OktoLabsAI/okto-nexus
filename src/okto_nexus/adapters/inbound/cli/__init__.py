"""Inbound CLI adapters.

Subcommands of the ``okto-nexus`` console script that are NOT the MCP stdio
server. Each module here drives the application services through the SAME public
ports the MCP tools use, so the CLI never bypasses visibility/routing or touches
the SQLite file directly.
"""
