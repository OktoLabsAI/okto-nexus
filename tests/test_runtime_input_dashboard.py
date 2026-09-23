"""Opt-in real browser + production HTTP + native protocol fixture.

OKTO_NEXUS_UI_CAMPAIGN=1, playwright installed, Node frontend dependencies and
an installed Edge browser are required. No provider/model or personal profile.
"""
import json
import os
from pathlib import Path
import re
import subprocess

import pytest

from test_pr34_remediation import runtime as runtime_fixture, send_message
from test_runtime_native_approvals import approval_peer, pending
from test_runtime_native_inputs import QUESTION, FORM
from test_runtime_handoff_dispatch import wait_result

runtime = runtime_fixture
pytestmark = pytest.mark.skipif(os.environ.get("OKTO_NEXUS_UI_CAMPAIGN") != "1", reason="Isolated browser campaign not enabled")


@pytest.fixture(scope="module")
def dashboard_build(tmp_path_factory):
    output = tmp_path_factory.mktemp("runtime-dashboard")
    frontend = Path(__file__).resolve().parents[1] / "frontend"
    subprocess.run(["node", "node_modules/vite/bin/vite.js", "build", "--outDir", str(output)],
                   cwd=frontend, check=True, capture_output=True, timeout=120)
    return output


@pytest.fixture
def dashboard(runtime, dashboard_build):
    from playwright.sync_api import sync_playwright
    _, client, _, _, operator, _ = runtime
    base = str(client.base_url).rstrip("/")
    with sync_playwright() as driver:
        browser = driver.chromium.launch(channel="msedge", headless=True, chromium_sandbox=True)
        print("Isolated Edge version:", browser.version)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.set_default_timeout(5000)
        context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base + "/") else route.abort())
        context.add_init_script("sessionStorage.setItem('okto_nexus_operator_key', " + json.dumps(operator) + ");")
        context.add_init_script("localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0', 'fixture');")
        page = context.new_page()
        # Only build artifacts are served by the fixture. Every /api request
        # goes to the real Nexus composition with its real authentication.
        page.route(base + "/", lambda route: route.fulfill(path=str(dashboard_build / "index.html")))
        def asset(route):
            filename = Path(route.request.url.split("?")[0]).name
            route.fulfill(path=str(dashboard_build / "assets" / filename))
        page.route(base + "/assets/*", asset)
        try:
            page.goto(base + "/")
            page.get_by_test_id("onboarding-close").click()
            page.get_by_role("button", name=re.compile("^Approvals")).click()
            yield page
        finally:
            context.close()
            browser.close()


def test_dashboard_submits_explicit_native_answer(runtime, dashboard):
    page = dashboard
    approval_peer(runtime, method="item/tool/requestUserInput", extra_params=QUESTION)
    sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    page.get_by_test_id("detail-" + request["approval_id"]).click()
    page.get_by_role("button", name="Send answer", exact=True).click()
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT response_payload FROM runtime_native_approvals").fetchone()[0] is None
    page.get_by_label("Choose fixture color", exact=True).select_option(label="blue")
    page.get_by_role("button", name="Send answer", exact=True).click()
    wire = json.loads(wait_result(runtime, sent["runtime_operations"][0])["output_text"])
    assert wire["result"] == {"answers": {"color": {"answers": ["blue"]}}}


def test_dashboard_form_preserves_types_and_never_selects_native_defaults(runtime, dashboard):
    from playwright.sync_api import expect
    page = dashboard
    params = {**FORM, "requestedSchema": {**FORM["requestedSchema"], "properties": {
        key: {**prop, "default": {"color": "blue", "count": 2, "enabled": True}[key]}
        for key, prop in FORM["requestedSchema"]["properties"].items()}}}
    params["requestedSchema"]["properties"]["note"] = {"type": "string"}
    approval_peer(runtime, method="mcpServer/elicitation/request", extra_params=params)
    sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    page.get_by_test_id("approve-" + request["approval_id"]).click()
    expect(page.get_by_label("color *", exact=True)).to_have_value("")
    expect(page.get_by_label("count *", exact=True)).to_have_value("")
    expect(page.get_by_label("enabled *", exact=True)).to_have_value("")
    page.get_by_label("color *", exact=True).select_option(label="green")
    page.get_by_label("count *", exact=True).fill("3")
    page.get_by_label("enabled *", exact=True).select_option(label="No")
    page.get_by_label("Send empty text for note", exact=True).check()
    screenshot = Path(runtime[2]).parent / "native-input-form.png"
    page.screenshot(path=str(screenshot), full_page=True)
    print("UI screenshot:", screenshot)
    page.get_by_role("button", name="Send answer", exact=True).click()
    wire = json.loads(wait_result(runtime, sent["runtime_operations"][0])["output_text"])
    assert wire["result"] == {"action": "accept", "content": {"color": "green", "count": 3, "enabled": False, "note": ""}}


def test_dashboard_claude_question_keeps_original_input_and_explicit_answer(runtime, dashboard):
    from test_runtime_claude_approvals import PEER, claude_peer
    question = {"question": "Choose fixture color", "header": "Color", "multiSelect": True,
                "options": [{"label": "blue", "description": "Fixture blue"}, {"label": "green", "description": "Fixture green"}]}
    source = PEER.replace('"tool_name":"Write"', '"tool_name":"AskUserQuestion"').replace(
        '"input":{"file_path":"fixture.txt","content":"fixture"}', '"input":' + repr({"questions": [question]}))
    claude_peer(runtime, source)
    sent = send_message(runtime, body="Isolated dashboard question")
    request = pending(runtime)
    page = dashboard
    page.get_by_test_id("detail-" + request["approval_id"]).click()
    page.get_by_label("Choose fixture color", exact=True).select_option(label=["blue", "green"])
    page.get_by_role("button", name="Send answer", exact=True).click()
    wire = json.loads(wait_result(runtime, sent["runtime_operations"][0])["output_text"])
    assert wire["response"]["response"] == {"behavior": "allow", "updatedInput": {
        "questions": [question], "answers": {"Choose fixture color": ["blue", "green"]}}}


def test_dashboard_rejects_question_without_fabricating_answer(runtime, dashboard):
    approval_peer(runtime, method="item/tool/requestUserInput", extra_params=QUESTION)
    sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    page = dashboard
    page.get_by_test_id("reject-" + request["approval_id"]).click()
    page.get_by_test_id("justification-" + request["approval_id"]).fill("Fixture denial")
    page.get_by_test_id("confirm-reject-" + request["approval_id"]).click()
    wire = json.loads(wait_result(runtime, sent["runtime_operations"][0])["output_text"])
    assert wire["result"] == {"answers": {}}


def test_dashboard_native_permission_remains_explicit_and_separate_from_input(runtime, dashboard):
    approval_peer(runtime)
    sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    page = dashboard
    page.get_by_test_id("approve-" + request["approval_id"]).click()
    page.get_by_role("button", name="Approve request", exact=True).click()
    wire = json.loads(wait_result(runtime, sent["runtime_operations"][0])["output_text"])
    assert wire["result"] == {"decision": "accept"}


def test_dashboard_expired_request_shows_delivery_state_without_answer_control(runtime, dashboard):
    from playwright.sync_api import expect
    deps = runtime[0]
    approval_peer(runtime, method="item/tool/requestUserInput", extra_params=QUESTION)
    sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_native_approvals SET expires_at='2000-01-01T00:00:00.000000Z'")
    wire = json.loads(wait_result(runtime, sent["runtime_operations"][0])["output_text"])
    assert wire["result"] == {"answers": {}}
    page = dashboard
    page.get_by_test_id("detail-" + request["approval_id"]).click()
    expect(page.get_by_test_id("native-approval-input")).to_contain_text("expired")
    expect(page.get_by_role("button", name="Send answer", exact=True)).to_have_count(0)
