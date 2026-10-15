"""Disabled execution preserves HTTP MCP; the removed stdio entry is refused."""
import subprocess
import sys
from pathlib import Path

import okto_nexus

import pytest

from test_pr34_remediation import runtime as runtime_fixture, mcp_call, stdio_environment, tool

runtime = runtime_fixture


@pytest.mark.parametrize("runtime", [False], indirect=True)
def test_disabled_http_and_rest_do_not_start_implicit_runtime(runtime):
    deps, client, root, peers, operator, caller = runtime
    http_tools = mcp_call(client, operator, "tools/list", {})["tools"]
    assert mcp_call(client, operator, "resources/list", {})["resources"]
    names = {t["name"] for t in http_tools}
    assert {"message_create", "runtime_input_list", "runtime_input_respond"} <= names
    assert not any(name.startswith("harness_") for name in names)

    code = ("import sys; sys.path.insert(0," + repr(str(Path(okto_nexus.__file__).resolve().parent.parent)) +
            "); from okto_nexus.adapters.inbound.cli.main import main; raise SystemExit(main())")
    rejected = subprocess.run([sys.executable, "-I", "-c", code,
        "--home", str(deps.config.home_dir), "--feature-harness-integrations", "false"],
        env=stdio_environment(runtime), capture_output=True, text=True, timeout=10)
    assert rejected.returncode == 2 and "MCP stdio is no longer available" in rejected.stderr
    body = tool(client, caller, "message_create", {"project_root": root,
        "from_agent_id": "caller", "subject": "disabled baseline", "body": "logical inbox still works",
        "target": {"strategy": "direct", "agent_id": "worker"}})
    assert body["ok"] and body["data"]["delivered_count"] == 1, body
    assert not body["data"].get("runtime_operations")
    response = client.get("/api/v1/harness/sessions/missing", headers={"x-api-key": operator})
    assert response.status_code == 404, response.text
    response = client.get("/api/v1/harness/sessions/missing/events", headers={"x-api-key": operator})
    assert response.status_code == 200 and response.json()["data"] == {"events": [], "count": 0}
    routes = [("GET", "/kinds", None),
        ("POST", "/sessions", {"agent_id": "worker", "kind": "pi", "project_root": root})]
    routes += [("POST", "/sessions/missing/" + verb, {"payload": {"text": "unused"}} if verb in {"send", "steer"} else {})
        for verb in ("send", "steer", "interrupt", "close")]
    for method, suffix, body in routes:
        response = client.request(method, "/api/v1/harness" + suffix,
            headers={"x-api-key": operator}, **({"json": body} if body is not None else {}))
        assert response.status_code == 403, (suffix, response.text)
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    assert peers == []
    assert getattr(deps, "runtime_dispatcher", None) is None
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM message_deliveries").fetchone()[0] == 1
        for table in ("harness_sessions", "runtime_commands", "delivery_outbox"):
            assert uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
