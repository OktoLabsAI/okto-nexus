"""R4 transport separation and packaging gates."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import subprocess
import sys
import tomllib
from io import StringIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from okto_nexus.adapters.inbound.cli.main import main
from okto_nexus.adapters.inbound.cli.admin import run_admin
from okto_nexus.adapters.inbound.cli.mcp_config_migration import (
    MigrationConflict, apply_entry_migration, plan_entry_migration,
)
from okto_nexus.adapters.inbound.cli.serve import _mcp_json_snippet
from okto_nexus.adapters.inbound.http.app import build_app, create_http_mcp_server
from okto_nexus.adapters.inbound.mcp.registration import create_server
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.domain.keys import generate_api_key


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


def test_ns01_03(capsys):
    """Packaged serve-lite pins a local, byte-verified Core wheel."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["scripts"]["okto-nexus"].endswith("cli.main:main")
    for extra in ("serve", "serve-lite"):
        requirements = project["project"]["optional-dependencies"][extra]
        assert "nexus-connector-core==0.2.28.dev0" in requirements
        assert not any(item.startswith("okto-nexus-connector") for item in requirements)
    assert "mcp>=1.0,<2" in project["project"]["dependencies"]
    wheel = (ROOT / "vendor/wheels/"
             "nexus_connector_core-0.2.28.dev0-py3-none-any.whl")
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == (
            "27df75100dea033ca5456f2d571eb41b6311fa3ce530a723ecd6c606d257953c"
    )
    assert main(["--help"]) == 0
    assert "HTTP" in capsys.readouterr().out


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


def test_ns01_05(tmp_path):
    """Only the chosen entry changes, with reviewed hash and backup."""
    key = generate_api_key()
    config = tmp_path / ".mcp.json"
    original = {"mcpServers": {
        "nexus-selected": {"command": "okto-nexus", "args": ["--home", "old"]},
        "third-party-a": {"command": "other", "args": ["run"]},
        "third-party-b": {"url": "https://other.example/mcp", "headers": {"X": "Y"}},
    }}
    config.write_text(json.dumps(original, indent=2), encoding="utf-8")
    url = "http://127.0.0.1:8202/mcp"
    plan = plan_entry_migration(config, entry_name="nexus-selected", url=url,
                                existing_api_key=key)
    assert key not in json.dumps(plan.redacted_summary())
    assert plan.redacted_summary()["expected_sha256"]
    config.write_text(json.dumps({**original, "concurrent": True}), encoding="utf-8")
    with pytest.raises(MigrationConflict):
        apply_entry_migration(plan)
    config.write_text(json.dumps(original, indent=2), encoding="utf-8")
    plan = plan_entry_migration(config, entry_name="nexus-selected", url=url,
                                existing_api_key=key)
    backup = apply_entry_migration(plan)
    assert backup is not None
    assert json.loads(backup.read_text(encoding="utf-8")) == original
    migrated = json.loads(config.read_text(encoding="utf-8"))
    assert migrated["mcpServers"]["third-party-a"] == original["mcpServers"]["third-party-a"]
    assert migrated["mcpServers"]["third-party-b"] == original["mcpServers"]["third-party-b"]
    selected = migrated["mcpServers"]["nexus-selected"]
    assert selected == {"url": url, "headers": {"Authorization": f"Bearer {key}"}}
    repeat = plan_entry_migration(config, entry_name="nexus-selected", url=url,
                                  existing_api_key=key)
    assert repeat.already_applied is True
    assert apply_entry_migration(repeat) is None
    output = StringIO()
    assert run_admin(["migrate-mcp-entry", "--config", str(config),
                      "--entry", "nexus-selected", "--url", url],
                     env={"OKTO_NEXUS_MCP_KEY": key}, out=output,
                     deps_factory=lambda *_: (_ for _ in ()).throw(
                         AssertionError("bootstrap called"))) == 0
    assert key not in output.getvalue()
    second_config = tmp_path / "second.json"
    second_config.write_text(json.dumps(original), encoding="utf-8")
    preview = StringIO()
    args = ["migrate-mcp-entry", "--config", str(second_config),
            "--entry", "nexus-selected", "--url", url]
    assert run_admin(args, env={"OKTO_NEXUS_MCP_KEY": key}, out=preview) == 0
    expected = json.loads(preview.getvalue())["expected_sha256"]
    applied = StringIO()
    assert run_admin([*args, "--apply", "--expected-sha256", expected],
                     env={"OKTO_NEXUS_MCP_KEY": key}, out=applied) == 0
    assert json.loads(applied.getvalue())["applied"] is True
    assert key not in applied.getvalue()
