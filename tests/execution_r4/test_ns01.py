"""R4 transport separation and packaging gates."""

from __future__ import annotations

import asyncio
import importlib
import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from okto_nexus.adapters.inbound.cli.main import main
from okto_nexus.adapters.inbound.cli.serve import _mcp_json_snippet
from okto_nexus.adapters.inbound.http.app import build_app, create_http_mcp_server
from okto_nexus.adapters.inbound.mcp.registration import create_server
from okto_nexus.bootstrap.dependencies import bootstrap


ROOT = Path(__file__).resolve().parents[2]


def test_ns01_01(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    direct = create_server(deps)
    http = create_http_mcp_server(deps)
    def surface(server):
        return (
            {item.name: (item.description, item.inputSchema)
             for item in asyncio.run(server.list_tools())},
            {str(item.uri) for item in asyncio.run(server.list_resources())},
        )
    assert surface(direct) == surface(http)
    assert "okto_nexus.adapters.inbound.mcp.server" not in sys.modules or (
        importlib.import_module("okto_nexus.adapters.inbound.http.app").Deps
        is importlib.import_module("okto_nexus.bootstrap.dependencies").Deps
    )
    probe = subprocess.run(
        [sys.executable, "-I", "-c",
         "import sys; sys.path.insert(0, r'%s'); "
         "import okto_nexus.bootstrap.dependencies; "
         "import okto_nexus.adapters.inbound.mcp.registration; "
         "print('ok')" % (ROOT / "src")],
        capture_output=True, text=True, timeout=10,
    )
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip() == "ok"


def test_ns01_02(tmp_path, capsys):
    for args in ([], ["stdio"], ["mcp"], ["--home", str(tmp_path)]):
        exit_code = main(args)
        assert exit_code == (0 if not args else 2)
    assert "HTTP /mcp" in capsys.readouterr().err


def test_mcp_config_uses_bearer_header():
    config = json.loads(_mcp_json_snippet("127.0.0.1", 8202, "nxs_secret"))
    entry = config["mcpServers"]["okto-nexus"]
    assert entry["url"] == "http://127.0.0.1:8202/mcp"
    assert entry["headers"] == {"Authorization": "Bearer nxs_secret"}
    assert "nxs_secret" not in entry["url"]


def test_v1_auth_is_bearer_only_and_direct(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    with TestClient(build_app(deps)) as client:
        protocol = client.get("/v1/connections/protocol")
        assert protocol.status_code == 200
        assert "ok" not in protocol.json()
        revision = protocol.headers["X-Nexus-Connections-Revision"]
        assert revision.endswith("-r4")
        rejected = client.get("/v1/connections/protocol?api_key=secret")
        assert rejected.status_code == 401
        assert rejected.headers["X-Nexus-Connections-Revision"] == revision
        assert rejected.json()["error"]["code"] == "AUTH_FAILED"
        assert "ok" not in rejected.json()
        protected = client.get("/v1/connections/me")
        assert protected.status_code == 401
        assert protected.json()["error"]["code"] == "AUTH_FAILED"
