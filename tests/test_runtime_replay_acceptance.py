"""Authenticated replay pagination through both public surfaces."""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, tool
from test_runtime_event_journal import event

runtime = runtime_fixture


@pytest.mark.parametrize("surface", ["rest", "mcp"])
def test_replay_pages_keep_concurrent_append_and_retained_cursor_with_acl(runtime, surface):
    deps, client, _, _, operator, caller = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    supervisor = deps.harness_supervisor
    supervisor.event_ingress.journal.segment_bytes = 900
    for index in range(4):
        supervisor._handle_event(sid, event(sid, text=str(index)))

    def page(cursor, key=operator):
        if surface == "mcp":
            return tool(client, key, "harness_event_list", {"session_id": sid, "after_sequence": cursor, "limit": 2})
        response = client.get(f"/api/v1/harness/sessions/{sid}/events", headers={"x-api-key": key},
            params={"after_sequence": cursor, "limit": 2})
        assert response.status_code == (200 if key == operator else 403), response.text
        return response.json()

    release = threading.Event()
    def append():
        assert release.wait(5)
        supervisor._handle_event(sid, event(sid, text="appended concurrently"))
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(append)
        try:
            first = page(0)
            assert first["ok"], first
        finally:
            release.set()
        future.result(timeout=5)
    second = page(first["data"]["events"][-1]["sequence"])
    third = page(second["data"]["events"][-1]["sequence"])
    combined = [row for response in (first, second, third) for row in response["data"]["events"]]
    assert [row["sequence"] for row in combined] == [1, 2, 3, 4, 5]
    assert not page(5)["data"]["events"]
    # File-journal retention must not expire a projected public replay cursor.
    compact = tool(client, operator, "harness_list", {"view": "journal", "compact": True})
    assert compact["ok"] and compact["data"]["removed_segments"] > 0, compact
    assert page(0) == first
    for cursor in (0, 2, 5):
        denied = page(cursor, caller)
        assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.parametrize("arguments", [{"limit": -1}, {"limit": 0}, {"limit": 1001}, {"after_sequence": -1}])
def test_invalid_replay_cursor_or_limit_has_same_validation_contract(runtime, arguments):
    _, client, _, _, operator, caller = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    mcp = tool(client, operator, "harness_event_list", {"session_id": sid, **arguments})
    rest = client.get(f"/api/v1/harness/sessions/{sid}/events", headers={"x-api-key": operator}, params=arguments)
    assert not mcp["ok"] and mcp["error"]["code"] == "VALIDATION_ERROR", mcp
    assert rest.status_code == 422 and rest.json()["error"]["code"] == "VALIDATION_ERROR", rest.text
    # Foreign readers still receive authorization denial before cursor validation.
    denied = client.get(f"/api/v1/harness/sessions/{sid}/events", headers={"x-api-key": caller}, params=arguments)
    assert denied.status_code == 403
    mcp_denied = tool(client, caller, "harness_event_list", {"session_id": sid, **arguments})
    assert not mcp_denied["ok"] and mcp_denied["error"]["code"] == "PERMISSION_DENIED"
