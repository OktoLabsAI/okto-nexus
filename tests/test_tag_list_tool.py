"""The read-only ``tag_list`` MCP tool (F1 / C6).

``tag_list`` returns the FULL central tag catalog (keys -> values, with
descriptions) - the vocabulary every ``tags`` / ``comm_scope`` / ``tag``
target is validated against. Registry writes stay operator-only on the REST
surface; the tool never mutates anything.

Covered here: the register(server, deps) auto-discovery contract over a fake
server (no SDK needed) and the tool end-to-end through a REAL FastMCP server
(the exact validation path agents hit). stdio<->HTTP parity is enforced
globally by ``test_http_parity.py``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.inbound.mcp.tools.tags import register


class FakeServer:
    """Captures FastMCP-style ``@server.tool()`` registrations by name."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture
def deps(tmp_path):
    return bootstrap({}, ["--home", str(tmp_path / "home")])


def _seed(deps) -> None:
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.tag_catalog.create_key(
            uow, key="SECTOR", description="Business sector"
        )
        deps.repos.tag_catalog.create_value(
            uow, key="SECTOR", value="DEV", description=None
        )
        deps.repos.tag_catalog.create_value(
            uow, key="SECTOR", value="OPS", description=None
        )
        deps.repos.tag_catalog.create_key(uow, key="TEAM", description=None)


def test_tag_list_registers_and_returns_the_full_catalog(deps):
    server = FakeServer()
    register(server, deps)
    assert set(server.tools) == {"tag_list"}

    empty = server.tools["tag_list"]()
    assert empty == {"ok": True, "data": {"tags": [], "total": 0}}

    _seed(deps)
    out = server.tools["tag_list"]()
    assert out["ok"] is True
    data = out["data"]
    assert data["total"] == 2
    by_key = {entry["key"]: entry for entry in data["tags"]}
    assert set(by_key) == {"SECTOR", "TEAM"}
    assert by_key["SECTOR"]["description"] == "Business sector"
    assert [v["value"] for v in by_key["SECTOR"]["values"]] == ["DEV", "OPS"]
    assert by_key["TEAM"]["values"] == []


def test_tag_list_over_the_real_fastmcp_server(deps, tmp_path):
    pytest.importorskip("mcp", reason="MCP SDK required to call tools via FastMCP")
    from okto_nexus.adapters.inbound.mcp.server import create_server

    _seed(deps)
    server = create_server(deps)

    def _call(name: str, arguments: dict | None = None) -> dict:
        result = asyncio.run(server.call_tool(name, arguments or {}))
        if isinstance(result, tuple):
            return result[1]
        block = result[0]
        return json.loads(block.text)

    env: dict[str, Any] = _call("tag_list")
    assert env["ok"] is True
    assert env["data"]["total"] == 2
    assert {entry["key"] for entry in env["data"]["tags"]} == {"SECTOR", "TEAM"}
