"""Opt-in qualification of the real connection test with a loopback model."""

from contextlib import closing
from hashlib import file_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
from threading import Thread
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
from nexus_connector_core import InstallationCandidate
from nexus_connector_core.build_identity import executable_build_identity
from nexus_connector_core.discovery import fingerprint
from nexus_connector_core.native.adapters.codex import _CodexTransport
import pytest

from okto_nexus.bootstrap import embedded_inventory
from test_connection_setup import count, request_for
from test_embedded_inventory import app_for, wait_inventory


PIN = "ed1c7b36e44536809c868864c833af8a857f56599a7a7fe23b908a1ba1093b1f"
SETUP_ROOT = "/api/v1/runtime-management/connections"
SETUP_SCOPE = ("connection-test", "local", "session", "epoch")


@pytest.fixture
def reviewed_codex():
    executable = os.environ.get("SI038_REVIEWED_CODEX_ENGINE")
    if os.name != "nt" or not executable:
        pytest.skip("requires the reviewed Windows app-server binary")
    binary = Path(executable).resolve(strict=True)
    with binary.open("rb") as stream:
        assert file_digest(stream, "sha256").hexdigest() == PIN
    return InstallationCandidate("codex_app_server", str(binary), fingerprint(binary), "explicit", "selected",
                                 version="0.157.0", architecture="x86_64",
                                 build_identity=executable_build_identity(binary))


@pytest.mark.parametrize("text, expected", [("NEXUS_CONNECTION_OK", "succeeded"),
                                            ("Different response", "failed")])
def test_setup_accounts_for_one_native_turn_before_finish(tmp_path, monkeypatch, reviewed_codex, text, expected):
    provider_home, workspace = tmp_path / "codex-home", tmp_path / "workspace"
    provider_home.mkdir()
    workspace.mkdir()
    requests, processes = [], []
    start = _CodexTransport.start

    def watch_start(transport):
        assert transport._env["CODEX_HOME"] == str(provider_home)
        assert Path(transport._cwd).resolve() == workspace
        assert Path(transport._command[0]).resolve() == Path(reviewed_codex.executable)
        deny_external = "http://127.0.0.1:1"
        transport._env.update(HTTP_PROXY=deny_external, HTTPS_PROXY=deny_external, ALL_PROXY=deny_external,
                              NO_PROXY="127.0.0.1", DO_NOT_TRACK="1")
        start(transport)
        processes.append(transport._proc)

    monkeypatch.setattr(_CodexTransport, "start", watch_start)

    class Peer(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            requests.append(self.path)
            assert len(requests) == 1
            assert self.path == "/v1/responses" and self.headers.get("Authorization") is None
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert request["stream"] is True and "Reply with exactly NEXUS_CONNECTION_OK." in json.dumps(request["input"])
            part = {"type": "output_text", "text": text, "annotations": [], "logprobs": []}
            item = {"id": "msg_setup", "role": "assistant", "type": "message", "status": "in_progress", "content": []}
            response = {"id": "resp_setup", "object": "response", "created_at": 0, "status": "in_progress",
                        "error": None, "incomplete_details": None, "output": []}
            completed = item | {"status": "completed", "content": [part]}
            usage = {"input_tokens": 100, "input_tokens_details": {"cached_tokens": 0},
                     "output_tokens": 5, "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 105}
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("connection", "close")
            self.end_headers()
            frames = [
                ("created", {"response": response}),
                ("output_item.added", {"output_index": 0, "item": item}),
                ("content_part.added", {"output_index": 0, "content_index": 0, "item_id": "msg_setup",
                                        "part": part | {"text": ""}}),
                ("output_text.delta", {"output_index": 0, "content_index": 0, "item_id": "msg_setup", "delta": text}),
                ("output_text.done", {"output_index": 0, "content_index": 0, "item_id": "msg_setup",
                                      "text": text, "logprobs": []}),
                ("content_part.done", {"output_index": 0, "content_index": 0, "item_id": "msg_setup", "part": part}),
                ("output_item.done", {"output_index": 0, "item": completed}),
                ("completed", {"response": response | {"output": [completed], "status": "completed", "usage": usage}}),
            ]
            for sequence, (name, payload) in enumerate(frames, 1):
                event = "response." + name
                record = {"type": event, "sequence_number": sequence, **payload}
                self.wfile.write(f"event: {event}\ndata: {json.dumps(record)}\n\n".encode())
                self.wfile.flush()

    with ThreadingHTTPServer(("127.0.0.1", 0), Peer) as provider:
        (provider_home / "config.toml").write_text(f"""
check_for_update_on_startup = false
model = "gpt-5.4"
model_provider = "fixture"
[analytics]
enabled = false
[model_providers.fixture]
name = "Loopback fixture"
base_url = "http://127.0.0.1:{provider.server_port}/v1"
wire_api = "responses"
requires_openai_auth = false
request_max_retries = 0
stream_max_retries = 0
""".lstrip(), encoding="utf-8")
        thread = Thread(target=provider.serve_forever, daemon=True)
        thread.start()
        try:
            _run_setup(tmp_path, monkeypatch, reviewed_codex, provider_home, workspace, requests, processes, expected)
        finally:
            provider.shutdown()
            thread.join()


def _run_setup(root, monkeypatch, candidate, provider_home, workspace, requests, processes, expected):
    from tools.si038_codex_budget import BudgetStop, CampaignBudget
    from tools.si038_codex_usage import read_turn_usage

    def discover(**kwargs):
        adapters = kwargs.get("adapter_ids")
        return SimpleNamespace(candidates=(candidate,) if not adapters or candidate.adapter_id in adapters else ())

    monkeypatch.setattr(embedded_inventory, "discover_local_candidates", discover)
    deps, app = app_for(root / "home")
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id="subject")
        deps.repos.agents.upsert(uow, agent_id="operator")
        app.state.auth.issue_key(uow, agent_id="subject")
        token = app.state.auth.issue_key(uow, agent_id="operator")
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        wait_inventory(client)
        headers = {"Authorization": "Bearer " + token}
        executor = app.state.embedded_inventory_owner.key.executor_id
        discovery = client.get(f"/v1/runtime/executors/{executor}/inventory", headers=headers)
        assert discovery.status_code == 200, discovery.text
        inventory = discovery.json()["snapshot"]
        body = dict(adapter_id=candidate.adapter_id, candidate_ref=inventory["evidence"][0]["candidate_ref"],
                    inventory_revision=inventory["inventory_revision"])
        setup = deps, app, client, headers, body, candidate, workspace
        _, request = request_for(setup)
        request["configuration"]["provider_home"] = str(provider_home)
        request["configuration"]["harness_settings"] = {"model": "gpt-5.4", "inherit_global_mcps": "disabled"}
        assert client.post(SETUP_ROOT + "/setup:finish", headers=headers, json=request).status_code == 409
        assert not requests and count(setup, "execution_bindings") == 0
        intent = request["client_intent_id"]
        budget = CampaignBudget(root)
        budget.reserve("setup", intent)
        first = client.post(SETUP_ROOT + "/setup:test", headers=headers, json=request)
        assert first.status_code == 200, first.text
        assert first.json()["test_id"] == intent
        deadline = time.monotonic() + 80
        while time.monotonic() < deadline:
            result = client.get(SETUP_ROOT + "/setup-tests/" + intent, headers=headers)
            assert result.status_code == 200, result.text
            view = result.json()
            if view["status"] != "running" and processes and processes[0].poll() is not None:
                break
            time.sleep(.1)
        assert view["status"] == expected, view
        assert len(requests) == len(processes) == 1 and processes[0].returncode is not None
        assert count(setup, "execution_bindings") == 0

        journal, = (root / "home" / "connection-tests").glob("*/journal.db")
        with closing(sqlite3.connect(journal.as_uri() + "?mode=ro", uri=True)) as db:
            thread_id, = db.execute("""SELECT json_extract(body,'$.payload.thread_id') FROM events
                WHERE json_extract(body,'$.operation_id')='turn'
                AND json_extract(body,'$.payload.delivery_phase')='started'""").fetchone()
            assert db.execute("PRAGMA quick_check").fetchone() == ("ok",)
        observed = read_turn_usage(journal, SETUP_SCOPE, thread_id=thread_id, operation_id="turn")
        assert observed.tokens == 105 and observed.terminal_outcome == "success"
        budget.observe("setup", observed.tokens, terminal=expected == "succeeded")

        replay = client.post(SETUP_ROOT + "/setup:test", headers=headers, json=request)
        assert replay.status_code == 200 and replay.json() == view
        finished = client.post(SETUP_ROOT + "/setup:finish", headers=headers, json=request)
        if expected == "succeeded":
            assert finished.status_code == 200, finished.text
            assert finished.json()["saved"]
            assert count(setup, "execution_bindings") == count(setup, "connection_setup_commits") == 1
            receipt = client.post(SETUP_ROOT + "/setup:recover", headers=headers, json=request)
            assert receipt.status_code == 200 and receipt.json()["result"] == finished.json()
        else:
            assert finished.status_code == 409
            assert "UNEXPECTED_MODEL_RESPONSE" in view["details"]
            assert count(setup, "execution_bindings") == count(setup, "connection_setup_commits") == 0
            with pytest.raises(BudgetStop, match="PREVIOUS_ACCOUNTING_UNCONFIRMED"):
                budget.reserve("home", "first-work")
        assert len(requests) == len(processes) == 1
        assert count(setup, "execution_sessions") == 0
