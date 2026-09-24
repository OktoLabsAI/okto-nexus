"""Protocol drift cannot publish a false ready binding in production composition."""
import json
import sys

import pytest

from test_pr34_remediation import runtime as runtime_fixture
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from okto_nexus.adapters.outbound.harness.pi import PiRpcConnector
from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector

runtime = runtime_fixture


@pytest.mark.parametrize("reply", [
    {"success": False, "error": "fixture command unsupported"},
    {"success": "true", "data": {}},
    {"success": True, "data": []},
])
def test_pi_incompatible_readiness_is_quarantined_without_affecting_other_adapter(runtime, tmp_path, reply):
    deps, client, root, _, operator, _ = runtime
    script = tmp_path / "incompatible_pi.py"
    script.write_text("import sys,json\nfor line in sys.stdin:\n"
        " msg=json.loads(line)\n"
        f" print(json.dumps(dict(type='response',command=msg['type'],**{reply!r})),flush=True)\n", encoding="utf-8")
    connectors = []
    def factory(**options):
        connector = PiRpcConnector(command=[sys.executable, "-u", str(script)], env=options["backend"]["env"])
        connectors.append(connector)
        return connector
    deps.harness_connector_factories["pi"] = factory
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "pi", "endpoint_id": "endpoint-pi", "project_root": root})
    assert response.status_code >= 400, response.text
    assert "protocol_incompatible" in response.text
    assert connectors[0]._transport is None
    with deps.connection_factory.unit_of_work(write=False) as uow:
        endpoint = uow.connection.execute("SELECT health FROM agent_endpoints WHERE endpoint_id='endpoint-pi'").fetchone()
        assert endpoint["health"] == "quarantined"
        assert not uow.connection.execute("SELECT 1 FROM harness_sessions WHERE endpoint_id='endpoint-pi' AND lifecycle_state='protocol_ready'").fetchone()
    healthy = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert healthy.status_code == 200, healthy.text


@pytest.mark.parametrize("thread_id", ["", 42, None])
def test_codex_incompatible_thread_identity_never_becomes_ready(runtime, tmp_path, thread_id):
    deps, client, root, _, operator, _ = runtime
    script = tmp_path / "incompatible_codex.py"
    source = _FAKE_SERVER_SOURCE.replace('thread_id = next_thread_id()', f'thread_id = {thread_id!r}')
    source = source.replace("method = msg.get(\"method\")", "method = msg.get(\"method\"); log({\"method\": method})")
    script.write_text(source, encoding="utf-8")
    deps.harness_connector_factories["codex"] = lambda **options: CodexAppServerConnector(
        command=[sys.executable, "-u", str(script), str(tmp_path / "wire.jsonl")], env=options["backend"]["env"])
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert response.status_code >= 400, response.text
    assert "protocol_incompatible" in response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute("SELECT 1 FROM harness_sessions WHERE endpoint_id='endpoint-codex' AND lifecycle_state='protocol_ready'").fetchone()
    records = [json.loads(line) for line in (tmp_path / "wire.jsonl").read_text(encoding="utf-8").splitlines()]
    assert not any(record.get("method") == "turn/start" for record in records)
