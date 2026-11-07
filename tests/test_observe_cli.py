"""CLI integration with real journal/TCP and explicit synthetic Herdr/OS ports.

The loopback responder proves client/CLI behavior, not Nexus admission or a
provider integration. No test starts Herdr, a Nexus Server, or a real agent.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.cli import observe
from okto_nexus.adapters.inbound.cli.main import main
from okto_nexus.adapters.outbound.observation.herdr import HerdrCLI, HerdrTransportError
from okto_nexus.adapters.outbound.observation.journal import ObservationJournal
from okto_nexus.domain.herdr_observations import WindowsProcessIdentity
from okto_nexus.domain.observation_tokens import generate_observation_token
from okto_nexus.domain.observations import parse_report, report_hash


REMOTE_PRIVATE = "SYNTHETIC_PRIVATE_REMOTE_MESSAGE"


@contextmanager
def _publication_server():
    state = SimpleNamespace(requests=[], receipts={}, response=None)

    def accept(payload):
        report = parse_report(payload)
        key = (report.observed_instance_id, report.generation, report.sequence)
        replayed = key in state.receipts
        if not replayed:
            stamp = datetime.fromisoformat(report.observed_at.replace("Z", "+00:00"))
            state.receipts[key] = dict(observed_instance_id=report.observed_instance_id,
                generation=report.generation, sequence=report.sequence, report_hash=report_hash(report),
                received_at=report.observed_at,
                valid_until=(stamp + timedelta(seconds=report.valid_for_seconds)).isoformat(
                    timespec="microseconds").replace("+00:00", "Z"))
        return 200, {"ok": True, "data": {"receipts": [dict(state.receipts[key], replayed=replayed)]}}, {}

    state.accept = accept

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            state.requests.append(dict(path=self.path, headers=dict(self.headers), body=raw))
            result = (state.response or accept)(json.loads(raw))
            if result is None:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            status, content, headers = result
            body = json.dumps(content).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, kwargs={"poll_interval": .01})
    thread.start()
    state.origin = f"http://127.0.0.1:{http.server_port}"
    try:
        yield state
    finally:
        http.shutdown()
        thread.join(5)
        http.server_close()
        assert not thread.is_alive()


def _forbidden(*_args, **_kwargs):
    raise AssertionError("Unexpected external operation")


@pytest.fixture
def cli(tmp_path, monkeypatch, capsys):
    with _publication_server() as server:
        executable = tmp_path / "herdr.exe"
        executable.write_bytes(b"synthetic executable placeholder; never launched")
        state = SimpleNamespace(path=tmp_path / "binding.json", executable=executable,
            server=server, source_calls=[], environments=[], source_error=None,
            token=generate_observation_token(), identity_checks=0, identity_closed=0)
        state.agent = dict(workspace_id="w1", tab_id="w1:t1", pane_id="w1:p1",
            terminal_id="term_fixture", agent_status="working", revision=1,
            state_change_seq=1, completion_seq=None, agent_session=None)
        state.info = dict(pane_id="w1:p1", shell_pid=100,
            foreground_process_group_id=101, foreground_processes=[{"pid": 101}])
        state.identity = WindowsProcessIdentity("a" * 64, 101, 134384870609652051,
                                               r"C:\fixture\native-agent.exe")

        class Source(HerdrCLI):
            # Keep actual executable/session validation and child environment
            # filtering; only the external metadata command boundary is fake.
            def __init__(self, executable, session):
                super().__init__(executable, session)
                state.environments.append(dict(self._environment))

            def contract(self):
                state.source_calls.append("contract")
                return dict(version="0.9.5", protocol=22, schema_version=1)

            def status(self):
                state.source_calls.append("status")
                if state.source_error:
                    raise state.source_error

            def process_info(self, pane):
                state.source_calls.append(("process_info", pane))
                return deepcopy(state.info)

            def snapshot(self):
                state.source_calls.append("snapshot")
                return {"agents": [deepcopy(state.agent)]}

        class Identity:
            def require_alive(self):
                state.identity_checks += 1
                return state.identity

        @contextmanager
        def open_identity(pid):
            assert pid == state.identity.pid
            try:
                yield Identity()
            finally:
                state.identity_closed += 1

        def invoke(*arguments):
            code = main(["observe", "herdr", *arguments])
            captured = capsys.readouterr()
            assert captured.err == ""
            assert state.token not in captured.out and REMOTE_PRIVATE not in captured.out
            return code, [json.loads(line) for line in captured.out.splitlines()]

        def bind_args(**changes):
            values = dict(state=str(state.path), herdr_executable=str(executable),
                session="synthetic-session", namespace="synthetic-installation", pane="w1:p1",
                server=server.origin, source_id="source:fixture", instance_id="instance:fixture",
                generation="7")
            values.update(changes)
            return ["bind", *(part for name, value in values.items()
                              for part in ("--" + name.replace("_", "-"), str(value)))]

        def bind(**changes):
            args = bind_args(**changes)
            code, preview = invoke(*args)
            assert code == 0 and preview[0]["status"] == "preview"
            code, result = invoke(*args, "--approve-selection", preview[0]["selection"])
            assert code == 0 and result[0]["status"] == "bound"
            return preview[0]

        state.invoke, state.bind_args, state.bind = invoke, bind_args, bind
        state.run_args = ["run", "--state", str(state.path), "--token-env", "TEST_OBSERVATION_TOKEN"]
        state.read = lambda: json.loads(state.path.read_text(encoding="utf-8"))
        monkeypatch.setenv("TEST_OBSERVATION_TOKEN", state.token)
        monkeypatch.setattr(observe, "HerdrCLI", Source)
        monkeypatch.setattr(observe, "open_process_identity", open_identity)
        monkeypatch.setattr(observe.time, "sleep", _forbidden)
        yield state


def test_bind_preview_and_matching_consent_are_local_and_never_publish(cli):
    before = {path.name for path in cli.path.parent.iterdir()}
    code, output = cli.invoke(*cli.bind_args())
    assert code == 0 and len(output) == 1
    preview = output[0]
    assert preview["status"] == "preview" and preview["evidence"] == "inferred"
    assert preview["selection"].startswith("sha256:") and len(preview["selection"]) == 71
    assert preview["binding"]["namespace"] == "synthetic-installation"
    assert preview["binding"]["session"] == "synthetic-session"
    assert preview["generation"] == 7 and preview["activity"] == "working"
    assert {path.name for path in cli.path.parent.iterdir()} == before
    assert cli.identity_checks == 3 and cli.identity_closed == 1
    code, output = cli.invoke(*cli.bind_args(), "--approve-selection", preview["selection"])
    assert code == 0 and output[0]["status"] == "bound"
    saved = cli.read()
    assert saved["sequence"] == 0 and saved["pending"] is None and saved["last_receipt"] is None
    assert cli.token not in cli.path.read_text(encoding="utf-8")
    assert not cli.server.requests


@pytest.mark.parametrize("change", ["generation", "instance_id", "source_id", "namespace", "interval", "ttl"])
def test_changed_selection_requires_new_consent_without_writing(cli, change):
    _, output = cli.invoke(*cli.bind_args())
    changes = {"generation": "8", "instance_id": "other", "source_id": "other",
               "namespace": "other", "interval": "20", "ttl": "120"}
    code, output = cli.invoke(*cli.bind_args(**{change: changes[change]}),
                             "--approve-selection", output[0]["selection"])
    assert code == 2 and output == [{"status": "unavailable", "code": "OBSERVER_SELECTION_CHANGED"}]
    assert not cli.path.exists() and not cli.server.requests


@pytest.mark.parametrize("existing", ["valid", "malformed"])
def test_approval_never_overwrites_existing_binding(cli, existing):
    preview = cli.bind()
    if existing == "malformed":
        cli.path.write_bytes(b"not-json; must never be reset")
    before = cli.path.read_bytes()
    code, output = cli.invoke(*cli.bind_args(), "--approve-selection", preview["selection"])
    assert code == 2 and output[0]["code"] == "JOURNAL_EXISTS"
    assert cli.path.read_bytes() == before and not cli.server.requests


def test_source_off_refuses_binding_without_creating_checkpoint(cli):
    cli.source_error = HerdrTransportError("HERDR_SERVER_UNAVAILABLE")
    code, output = cli.invoke(*cli.bind_args())
    assert code == 2 and output == [{"status": "unavailable", "code": "HERDR_SERVER_UNAVAILABLE"}]
    assert cli.source_calls == ["contract", "status"] and cli.identity_checks == 0
    assert not cli.path.exists() and not cli.server.requests


def test_source_off_run_does_not_reserve_sequence_or_permanently_invalidate(cli):
    cli.bind()
    before = cli.path.read_bytes()
    cli.source_error = HerdrTransportError("HERDR_SERVER_UNAVAILABLE")
    code, output = cli.invoke(*cli.run_args, "--once")
    assert code == 2 and output[0]["code"] == "HERDR_SERVER_UNAVAILABLE"
    assert cli.path.read_bytes() == before and not cli.server.requests


@pytest.mark.parametrize("invalidated", [False, True])
def test_status_reads_only_local_metadata_without_credentials_or_external_calls(cli, monkeypatch, invalidated):
    cli.bind()
    if invalidated:
        with ObservationJournal(cli.path) as journal:
            document = journal.read()
            document["invalidated"] = True
            journal.write(document)
    before = {path.name: path.read_bytes() for path in cli.path.parent.iterdir()}
    for name in ("_token", "HerdrCLI", "open_process_identity", "ObservationClient"):
        monkeypatch.setattr(observe, name, _forbidden)
    monkeypatch.delenv("TEST_OBSERVATION_TOKEN")
    code, output = cli.invoke("status", "--state", str(cli.path))
    assert code == 0 and output == [dict(status="reassociation_required" if invalidated else "bound",
        source_id="source:fixture", observed_instance_id="instance:fixture", generation=7,
        sequence=0, pending=False, pending_failure=None, last_receipt=None)]
    assert {path.name: path.read_bytes() for path in cli.path.parent.iterdir()} == before
    assert not cli.server.requests


def test_status_missing_binding_does_not_invent_checkpoint(cli, monkeypatch):
    monkeypatch.setattr(observe, "HerdrCLI", _forbidden)
    code, output = cli.invoke("status", "--state", str(cli.path))
    assert code == 2 and output[0]["code"] == "OBSERVER_BINDING_REQUIRED"
    assert not cli.path.exists() and not cli.server.requests


def test_once_publishes_exactly_one_fresh_snapshot_and_persists_receipt(cli):
    cli.bind()
    cli.source_calls.clear()
    code, output = cli.invoke(*cli.run_args, "--once")
    assert code == 0 and len(output) == 1 and output[0]["status"] == "published"
    assert cli.source_calls.count("snapshot") == 1 and len(cli.server.requests) == 1
    sent = json.loads(cli.server.requests[0]["body"])
    assert sent["sequence"] == 1 and sent["generation"] == 7 and sent["evidence"] == "inferred"
    assert cli.server.requests[0]["path"] == "/v1/observations/activity"
    assert not {"binding", "pid", "image_path", "agent_session"} & sent.keys()
    assert cli.read()["pending"] is None and cli.read()["last_receipt"] == output[0]["receipt"]


def test_continuous_run_waits_configured_interval_and_ctrl_c_stops_cleanly(cli, monkeypatch):
    cli.bind(interval=20)
    waits = []

    def interrupt(seconds):
        waits.append(seconds)
        raise KeyboardInterrupt

    monkeypatch.setattr(observe.time, "sleep", interrupt)
    code, output = cli.invoke(*cli.run_args)
    assert code == 130 and waits == [20] and len(cli.server.requests) == 1
    assert [value["status"] for value in output] == ["published", "stopped"]
    assert output[-1]["reason"] == "OBSERVER_INTERRUPTED"
    with ObservationJournal(cli.path) as journal:
        assert journal.read()["pending"] is None  # The lifetime lock was released.


def test_credential_is_only_sent_to_nexus_and_removed_from_herdr_environment(cli, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-provider-must-not-propagate")
    monkeypatch.setenv("HERDR_SESSION", "unapproved-ambient-session")
    monkeypatch.setenv("HERDR_CONFIG_PATH", str(cli.path.parent / "ambient.toml"))
    cli.bind()
    code, output = cli.invoke(*cli.run_args, "--once")
    assert code == 0 and output[0]["status"] == "published"
    assert cli.server.requests[0]["headers"]["Authorization"] == "Bearer " + cli.token
    for environment in cli.environments:
        assert not {"TEST_OBSERVATION_TOKEN", "OPENAI_API_KEY", "HERDR_SESSION", "HERDR_CONFIG_PATH"} & environment.keys()
        assert not any(cli.token in value for value in environment.values())
    assert cli.token not in cli.path.read_text(encoding="utf-8")


@pytest.mark.parametrize("variable", ["TEMP", "path", "HERDR_TOKEN", "XDG_TOKEN", "bad-name", "A" * 129])
def test_reserved_or_invalid_token_environment_names_fail_before_source(cli, variable):
    cli.bind()
    cli.source_calls.clear()
    code, output = cli.invoke("run", "--state", str(cli.path), "--token-env", variable, "--once")
    assert code == 2 and output[0]["code"] == "OBSERVER_TOKEN_ENV_INVALID"
    assert not cli.source_calls and not cli.server.requests


@pytest.mark.parametrize("token", [None, "nxs_" + "a" * 64, "nxobs_short"])
def test_missing_or_wrong_family_token_fails_before_herdr(cli, monkeypatch, token):
    cli.bind()
    cli.source_calls.clear()
    if token is None:
        monkeypatch.delenv("TEST_OBSERVATION_TOKEN")
    else:
        monkeypatch.setenv("TEST_OBSERVATION_TOKEN", token)
    code, output = cli.invoke(*cli.run_args, "--once")
    assert code == 2 and output[0]["code"] == ("OBSERVER_TOKEN_REQUIRED" if token is None else "TOKEN_INVALID")
    assert not cli.source_calls and not cli.server.requests


@pytest.mark.parametrize("status,code,retry", [(401, "AUTH_FAILED", None), (403, "PERMISSION_DENIED", None),
    (409, "CONFLICT", None), (429, "QUOTA_EXCEEDED", 17)])
def test_known_refusal_stops_without_auto_retry_and_keeps_exact_pending(cli, status, code, retry):
    cli.bind()
    cli.server.response = lambda _: (status, {"message": REMOTE_PRIVATE}, {"Retry-After": "17"})
    result, output = cli.invoke(*cli.run_args, "--once")
    assert result == 2 and output == [dict(status="publication_failed", code=code,
        outcome_unknown=False, http_status=status, retry_after_seconds=retry)]
    saved = cli.read()
    assert saved["pending"] == json.loads(cli.server.requests[0]["body"])
    assert saved["pending_failure"] == {"code": code, "outcome_unknown": False}
    before = cli.path.read_bytes()
    result, output = cli.invoke(*cli.run_args, "--once")
    assert result == 2 and output[0]["code"] == "OBSERVER_PENDING_REPORT"
    assert cli.path.read_bytes() == before and len(cli.server.requests) == 1


def test_response_loss_requires_explicit_exact_retry_once_without_herdr(cli, monkeypatch):
    cli.bind()

    def lose_response(payload):
        cli.server.accept(payload)
        return None

    cli.server.response = lose_response
    code, output = cli.invoke(*cli.run_args, "--once")
    assert code == 3 and output[0]["outcome_unknown"] is True
    original = cli.server.requests[0]["body"]
    stored_receipt = deepcopy(next(iter(cli.server.receipts.values())))
    code, output = cli.invoke(*cli.run_args, "--once", "--discard-refused")
    assert code == 2 and output[0]["code"] == "OBSERVER_PENDING_OUTCOME_UNKNOWN"
    assert len(cli.server.requests) == 1
    cli.server.response = cli.server.accept
    cli.executable.unlink()
    monkeypatch.setattr(observe, "HerdrCLI", _forbidden)
    monkeypatch.setattr(observe, "open_process_identity", _forbidden)
    code, output = cli.invoke(*cli.run_args, "--once", "--retry-pending")
    assert code == 0 and output == [{"status": "historical_receipt", "receipt": dict(stored_receipt, replayed=True)}]
    assert cli.server.requests[1]["body"] == original and len(cli.server.requests) == 2
    assert cli.read()["sequence"] == 1 and cli.read()["pending"] is None


def test_discard_known_refusal_preserves_reserved_sequence_and_requires_fresh_sample(cli):
    cli.bind()
    cli.server.response = lambda _: (409, {"message": REMOTE_PRIVATE}, {})
    assert cli.invoke(*cli.run_args, "--once")[0] == 2
    cli.server.response = cli.server.accept
    cli.source_calls.clear()
    code, output = cli.invoke(*cli.run_args, "--once", "--discard-refused")
    assert code == 0 and [value["status"] for value in output] == ["published"]
    assert [json.loads(value["body"])["sequence"] for value in cli.server.requests] == [1, 2]
    assert cli.source_calls.count("snapshot") == 1 and cli.read()["sequence"] == 2


def test_uncertain_outcome_stays_uncertain_after_retry_credential_refusal(cli):
    cli.bind()

    def lose_response(payload):
        cli.server.accept(payload)
        return None

    cli.server.response = lose_response
    assert cli.invoke(*cli.run_args, "--once")[0] == 3
    cli.server.response = lambda _: (401, {"message": REMOTE_PRIVATE}, {})
    code, output = cli.invoke(*cli.run_args, "--once", "--retry-pending")
    assert code == 3 and output[0]["code"] == "AUTH_FAILED" and output[0]["outcome_unknown"] is True
    assert cli.server.requests[0]["body"] == cli.server.requests[1]["body"]
    assert cli.read()["pending_failure"] == {"code": "AUTH_FAILED", "outcome_unknown": True}
    code, output = cli.invoke(*cli.run_args, "--once", "--discard-refused")
    assert code == 2 and output[0]["code"] == "OBSERVER_PENDING_OUTCOME_UNKNOWN"
    assert len(cli.server.requests) == 2


def test_outbox_write_failure_prevents_every_http_publication(cli, monkeypatch):
    cli.bind()
    before = cli.path.read_bytes()

    def fail_write(_journal, _document):
        raise OSError(REMOTE_PRIVATE)

    monkeypatch.setattr(ObservationJournal, "write", fail_write)
    code, output = cli.invoke(*cli.run_args, "--once")
    assert code == 2 and output == [{"status": "unavailable", "code": "OBSERVER_LOCAL_IO_ERROR"}]
    assert cli.path.read_bytes() == before and not cli.server.requests


@pytest.mark.parametrize("outcome", ["accepted", "refused", "lost_response"])
def test_post_http_checkpoint_failure_reports_remote_evidence_and_keeps_outbox(cli, monkeypatch, outcome):
    cli.bind()
    if outcome == "refused":
        cli.server.response = lambda _: (403, {"message": REMOTE_PRIVATE}, {})
    elif outcome == "lost_response":
        def lose_response(payload):
            cli.server.accept(payload)
            return None
        cli.server.response = lose_response
    original_write = ObservationJournal.write
    writes = []

    def fail_outcome_write(journal, document):
        writes.append(deepcopy(document))
        if len(writes) == 2:
            raise OSError(REMOTE_PRIVATE)
        return original_write(journal, document)

    monkeypatch.setattr(ObservationJournal, "write", fail_outcome_write)
    code, output = cli.invoke(*cli.run_args, "--once")
    assert code == 3 and len(output) == 1
    result = output[0]
    assert result["status"] == "checkpoint_failed" and result["code"] == "OBSERVER_OUTBOX_UNRESOLVED"
    assert result["outcome_unknown"] is (outcome == "lost_response")
    assert result["remote_admitted"] is {"accepted": True, "refused": False, "lost_response": None}[outcome]
    if outcome == "accepted":
        assert result["receipt"] == dict(next(iter(cli.server.receipts.values())), replayed=False)
    else:
        assert result["receipt"] is None
    assert len(cli.server.requests) == 1
    saved = cli.read()
    assert saved["pending"] == json.loads(cli.server.requests[0]["body"])
    assert saved["sequence"] == 1 and saved["pending_failure"] is None and saved["last_receipt"] is None


@pytest.mark.parametrize("flag", ["--retry-pending", "--discard-refused"])
def test_recovery_flags_without_pending_report_do_not_publish(cli, flag):
    cli.bind()
    cli.source_calls.clear()
    code, output = cli.invoke(*cli.run_args, "--once", flag)
    assert code == 2 and output[0]["code"] == "OBSERVER_NO_PENDING_REPORT"
    assert not cli.source_calls and not cli.server.requests


@pytest.mark.parametrize("arguments", [
    ["run", "--state", "unused", "--token-env", "TOKEN", "--retry-pending", "--discard-refused"],
    ["status", "--state", "unused", "--token-env", "TOKEN"],
    ["run", "--state", "unused", "--token-env", "TOKEN", "--token", "raw-value"],
    ["run", "--state", "unused", "--token-env", "TOKEN", "--onc"],
])
def test_parser_rejects_conflicting_or_unsupported_controls_before_effect(cli, capsys, arguments):
    with pytest.raises(SystemExit) as caught:
        main(["observe", "herdr", *arguments])
    assert caught.value.code == 2
    assert "error:" in capsys.readouterr().err
    assert not cli.source_calls and not cli.server.requests and not cli.path.exists()
