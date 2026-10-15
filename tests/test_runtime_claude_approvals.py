"""Claude control protocol uses the shared durable approval service."""
import sys
import time
import json

import pytest

from test_pr34_remediation import runtime as runtime_fixture, send_message
from test_runtime_native_approvals import pending
from test_runtime_handoff_dispatch import wait_result

runtime = runtime_fixture

PEER = r'''
import json,sys
def emit(value):
    print(json.dumps(value),flush=True)
for line in sys.stdin:
    value=json.loads(line)
    if value.get("type")=="user":
        emit({"type":"system","subtype":"init","session_id":"fixture-session"})
        emit({"type":"control_request","request_id":"permission-1","request":{
            "subtype":"can_use_tool","tool_name":"Write","tool_use_id":"tool-1",
            "input":{"file_path":"fixture.txt","content":"fixture"}}})
    elif value.get("type")=="control_response":
        emit({"type":"result","subtype":"success","result":json.dumps(value)})
'''


def claude_peer(runtime, source=PEER):
    from legacy_native_fixture.claude_code_stream import ClaudeCodeStreamConnector
    deps, client, root, _, operator, _ = runtime
    deps.config.feature_hitl = True
    deps.harness_connector_factories["claude_code"] = lambda **kwargs: ClaudeCodeStreamConnector(
        binary=sys._base_executable, argv=["-u", "-c", source], cwd=root, env=kwargs["backend"]["env"],
        version_argv=["-c", "print('2.1.281 (Claude Code)')"])
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "claude_code", "endpoint_id": "endpoint-claude_code.stream", "project_root": root})
    assert opened.status_code == 200, opened.text
    return opened.json()["data"]["session_id"]
