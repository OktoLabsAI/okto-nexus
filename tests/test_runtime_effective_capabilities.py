"""Unknown native contracts cannot inherit execution from adapter declarations."""
import sys
import json
from pathlib import Path

import pytest

from legacy_native_fixture.codex import CodexAppServerConnector
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_pr34_remediation import runtime as runtime_fixture, send_message, tool

runtime = runtime_fixture






def configure_codex(runtime, version="0.156.1", disabled=()):
    deps, client, root, _, operator, _ = runtime
    result = {"userAgent": "okto-nexus/" + version} if version else {}
    source = _FAKE_SERVER_SOURCE.replace('"result": {"userAgent": "okto-nexus/0.156.1"}', '"result": ' + repr(result), 1)
    source = source.replace('method = msg.get("method")', 'method = msg.get("method"); log({"request_method": method})')
    deps.harness_connector_factories["codex"] = lambda **options: CodexAppServerConnector(
        command=[sys._base_executable, "-u", "-c", source, str(Path(root) / "capability-wire.jsonl")], cwd=root, env=options["backend"]["env"])
    if disabled:
        changed = client.patch("/api/v1/harness/profiles/profile-codex", headers={"x-api-key": operator},
            json={"expected_revision": 1, "config": {"disabled_capabilities": list(disabled)}})
        assert changed.status_code == 200, changed.text
    return {"agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root}


def open_codex(runtime, **options):
    _, client, _, _, operator, _ = runtime
    body = configure_codex(runtime, **options)
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        **body, "metadata": {"effective_capabilities": {"conversation": True, "native_deduplication": True}}})
    assert opened.status_code == 200, opened.text
    return opened.json()["data"]
