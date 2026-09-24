"""Disposable behavior audit: known backend secret echoed by a native peer.

Uses only a synthetic value and an owned Python protocol peer. It does not read
any installed provider configuration or login file. Keep source/tests frozen.
"""
import json
import logging
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import os

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_pr34_remediation import runtime, tool  # noqa: E402
from test_runtime_commands import wait_operation, wait_close_result  # noqa: E402
from test_harness_codex_connector import _FAKE_SERVER_SOURCE  # noqa: E402
from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector  # noqa: E402


def main():
    logging.disable(logging.INFO)
    secret = "fixture-opaque-backend-credential-43816"
    with tempfile.TemporaryDirectory(prefix="okto-secret-audit-") as directory:
        fixture = runtime.__wrapped__(Path(directory), SimpleNamespace(param=True))
        current = next(fixture)
        try:
            deps, client, root, _, operator, _ = current
            with patch.dict(os.environ, {"FIXTURE_BACKEND_CREDENTIAL_SOURCE": secret}):
                response = client.patch("/api/v1/harness/profiles/profile-codex",
                    headers={"x-api-key": operator}, json={"expected_revision": 1,
                        "secret_refs": {"FIXTURE_BACKEND_KEY": "env:FIXTURE_BACKEND_CREDENTIAL_SOURCE"}})
                assert response.status_code == 200, response.text
                source = _FAKE_SERVER_SOURCE.replace('"delta": text', '"delta": os.environ["FIXTURE_BACKEND_KEY"]')
                assert source != _FAKE_SERVER_SOURCE
                deps.harness_connector_factories["codex"] = lambda **options: CodexAppServerConnector(
                    command=[sys._base_executable, "-u", "-c", source], cwd=root, env=options["backend"]["env"])
                opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
                    "agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
                assert opened.status_code == 200, opened.text
                sid = opened.json()["data"]["session_id"]
                native = deps.harness_supervisor._live[sid].connector.native
                process = native._transport._proc
                assert native._env["FIXTURE_BACKEND_KEY"] == secret
                sent = tool(client, operator, "harness_send", {"session_id": sid,
                    "payload": {"text": "Echo fixture backend diagnostic"}})
                assert sent["ok"], sent
                result = wait_operation(current, sent["data"]["operation_id"], lambda row: row["result_durable"])
                events = deps.harness_supervisor.replay_events(sid)
                wire = b"".join(path.read_bytes() for path in deps.harness_supervisor.event_ingress.journal.root.glob("segment-*.bin"))
                observations = {"journal_contains_resolved_secret": secret.encode() in wire,
                    "durable_result_contains_resolved_secret": secret in result["result"]["output_text"],
                    "replay_contains_resolved_secret": any(secret in str(event.payload) or secret in str(event.output_text) for event in events)}
                closed = tool(client, operator, "harness_close", {"session_id": sid})
                assert wait_close_result(client, operator, closed)["lifecycle_state"] == "stopped"
                assert process.wait(timeout=5) is not None
        finally:
            fixture.close()
    evidence = {"source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "test_id": "T-AUTH-09", "status": "FAIL" if any(observations.values()) else "PASS",
        "command": "rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/audit_backend_secret.py",
        "observations": observations,
        "limitations": "Synthetic secret reference and owned Python Codex-shaped protocol peer, production HTTP/MCP/journal. No personal/provider credentials or model calls. Other logging/startup-error paths not exercised."}
    target = ROOT / "plans/pr34-remediation/evidence/p12-backend-secret-audit.json"
    target.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence))
    return 1 if evidence["status"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
