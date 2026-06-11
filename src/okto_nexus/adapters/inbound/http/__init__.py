"""HTTP inbound adapter (Nexus v2): MCP streamable-http + REST + dashboard.

Everything under this package is transport plumbing for `okto-nexus serve`.
It may import FastAPI/uvicorn/the MCP SDK; domain/ and application/ must
never import from here (enforced by the import boundary test).
"""
