"""Server-owned native observations survive persistence without trusting metadata."""
import json
import sys

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector

runtime = runtime_fixture


@pytest.mark.parametrize("user_agent,version", [
    ("okto-nexus/0.156.1 (fixture OS)", "0.156.1"),
    ("unknown-product/0.156.1", None),
    (None, None),
    ("okto-nexus/0.156.1-malformed-version", None),
])
def test_native_version_is_separate_from_metadata_and_not_a_capability_claim(runtime, tmp_path, user_agent, version):
    deps, client, root, _, operator, _ = runtime
    response = {"userAgent": user_agent, "codexHome": "fixture-private-path-never-return",
                "futureSecretField": "fixture-private-token-never-return"}
    source = _FAKE_SERVER_SOURCE.replace('"result": {"userAgent": "okto-nexus/0.156.1"}', '"result": ' + repr(response), 1)
    script = tmp_path / "version_peer.py"
    script.write_text(source, encoding="utf-8")
    deps.harness_connector_factories["codex"] = lambda **options: CodexAppServerConnector(
        command=[sys.executable, "-u", str(script), str(tmp_path / "wire.jsonl")], env=options["backend"]["env"])
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root,
        "metadata": {"compatibility_report": {"native_version": "99.0.0", "capabilities_verified": True}}})
    assert opened.status_code == 200, opened.text
    session = opened.json()["data"]
    report = session.get("compatibility_report", {})
    qualification = {name: report[name] for name in ("effective_capabilities", "effective_capability_contract", "effective_capability_basis")}
    assert qualification["effective_capability_contract"] == 1
    assert qualification["effective_capability_basis"] == "trusted_adapter_probe_and_profile"
    assert qualification["effective_capabilities"]["conversation"] is (version == "0.156.1")
    assert not qualification["effective_capabilities"]["native_deduplication"]
    assert {name: value for name, value in report.items() if name not in qualification} == {"schema_version": 1, "native_version": version,
        "observation": "initialize_version" if version else "version_not_observed", "capabilities_verified": False,
        "compatible_native_requests": ["item/commandExecution/requestApproval", "item/fileChange/requestApproval",
            "item/tool/requestUserInput", "mcpServer/elicitation/request"] if version == "0.156.1" else [],
        "native_request_basis": "tested_version_contract" if version == "0.156.1" else "unverified",
        "compatible_controls": ["steer", "interrupt"] if version == "0.156.1" else [],
        "control_contract_basis": "tested_version_contract" if version == "0.156.1" else "unverified"}
    assert "fixture-private" not in json.dumps(session)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stored = deps.repos.harness_sessions.get(uow, session_id=session["session_id"])
        assert stored.compatibility_report == report
    result = tool(client, operator, "harness_get", {"session_id": session["session_id"]})
    assert result["ok"] and result["data"]["compatibility_report"] == report, result
    bindings = client.get("/api/v1/harness/bindings", headers={"x-api-key": operator})
    assert bindings.status_code == 200, bindings.text
    endpoint = next(e for a in bindings.json()["data"]["agents"] for e in a["endpoints"] if e["endpoint_id"] == "endpoint-codex")
    assert endpoint["sessions"][0]["compatibility_report"] == report
    assert endpoint["capability_verification"] == "not_probed"
