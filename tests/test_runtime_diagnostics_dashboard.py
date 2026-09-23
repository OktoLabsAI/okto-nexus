"""Opt-in browser diagnostics over production APIs, isolated protocol peers only."""
import json
import os
from pathlib import Path

import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, tool
from test_runtime_input_dashboard import dashboard as dashboard_fixture, dashboard_build as build_fixture
from test_runtime_operation_reconciliation import uncertain_delivery
from test_runtime_commands import wait_close_result

runtime = runtime_fixture
dashboard = dashboard_fixture
dashboard_build = build_fixture
pytestmark = pytest.mark.skipif(os.environ.get("OKTO_NEXUS_UI_CAMPAIGN") != "1", reason="Isolated browser campaign not enabled")


def open_view(page):
    page.get_by_role("button", name="Runtimes", exact=True).click()


def test_unknown_operation_shows_cause_without_success_or_retry(runtime, dashboard):
    from playwright.sync_api import expect
    _, row = uncertain_delivery(runtime)
    open_view(dashboard)
    card = dashboard.get_by_test_id("runtime-operation-" + row["operation_id"])
    expect(card).to_contain_text("OUTCOME_UNKNOWN")
    expect(card).to_contain_text("Do not resend automatically")
    card.get_by_text("Attempt and recovery details", exact=True).click()
    expect(card).to_contain_text(row["attempt_id"])
    expect(card).to_contain_text("Managed handoff claims cannot be released as conversation")
    assert card.get_by_role("button").count() == 0  # no retry/approval masquerading as success
    screenshot = Path(runtime[2]).parent / "runtime-diagnostics.png"
    dashboard.set_viewport_size({"width": 1440, "height": 1800})
    dashboard.get_by_test_id("runtimes-view").evaluate("element => { element.parentElement.scrollTop = 0; }")
    dashboard.screenshot(path=str(screenshot), full_page=True)
    print("UI screenshot:", screenshot)


def test_detached_external_runtime_is_not_presented_as_terminated(runtime, dashboard):
    from playwright.sync_api import expect
    deps, client, root, _, operator, _ = runtime
    deps.config.feature_harness_attach = True
    opened = tool(client, operator, "harness_open", {
        "agent_id": "worker", "kind": "claude_code", "substrate": "attach",
        "project_root": root, "target_pid": 12345})
    assert opened["ok"], opened
    sid = opened["data"]["session_id"]
    wait_close_result(client, operator, tool(client, operator, "harness_close", {"session_id": sid}))
    open_view(dashboard)
    card = dashboard.get_by_test_id("runtime-session-" + sid)
    expect(card).to_contain_text("detached")
    expect(card).to_contain_text("external process was not declared terminated")


def test_multiple_bindings_explain_selection_instead_of_choosing_an_executor(runtime, dashboard):
    from playwright.sync_api import expect
    _, client, root, _, operator, caller = runtime
    assert open_rest(runtime).status_code == 200
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "codex", "project_root": root})
    assert opened.status_code == 200, opened.text
    rejected = tool(client, caller, "message_create", {"project_root": root, "from_agent_id": "caller",
        "target": {"strategy": "direct", "agent_id": "worker"}, "subject": "ambiguous", "body": "fixture"})
    assert not rejected["ok"] and "AMBIGUOUS_BINDING" in rejected["error"]["message"], rejected
    open_view(dashboard)
    card = dashboard.get_by_test_id("runtime-agent-worker")
    expect(card).to_contain_text("Multiple ready bindings")
    expect(card).to_contain_text("endpoint-pi")
    expect(card).to_contain_text("endpoint-codex")
    expect(card).to_contain_text("not_probed")


def test_authority_change_clears_previously_visible_operator_metadata(runtime, dashboard):
    from playwright.sync_api import expect
    _, row = uncertain_delivery(runtime)
    open_view(dashboard)
    expect(dashboard.get_by_test_id("runtime-operation-" + row["operation_id"])).to_be_visible()
    dashboard.evaluate("sessionStorage.setItem('okto_nexus_operator_key', " + json.dumps(runtime[5]) + ")")
    dashboard.get_by_role("button", name="Refresh runtimes", exact=True).click()
    expect(dashboard.get_by_text("Operator operation inspection unavailable", exact=False)).to_be_visible()
    expect(dashboard.get_by_test_id("runtime-operation-" + row["operation_id"])).to_have_count(0)


def test_disabled_admission_still_shows_operator_recovery_records(runtime, dashboard):
    from playwright.sync_api import expect
    _, row = uncertain_delivery(runtime)
    runtime[0].config.feature_harness_integrations = False
    open_view(dashboard)
    expect(dashboard.get_by_test_id("runtime-operation-" + row["operation_id"])).to_contain_text("OUTCOME_UNKNOWN")
    expect(dashboard.get_by_text("Connection discovery unavailable", exact=False)).to_be_visible()


def test_native_approval_navigation_uses_existing_canonical_view(runtime, dashboard):
    from playwright.sync_api import expect
    from test_pr34_remediation import send_message
    from test_runtime_native_approvals import approval_peer, pending
    approval_peer(runtime)
    send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    open_view(dashboard)
    dashboard.get_by_role("button", name="Review native approvals", exact=True).click()
    expect(dashboard.get_by_test_id("detail-" + request["approval_id"])).to_be_visible()
