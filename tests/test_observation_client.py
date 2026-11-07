"""Real loopback HTTP against an explicitly synthetic publication server.

These prove helper transport behavior, not installed Nexus or Herdr conformance.
"""
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

import pytest

from okto_nexus.domain.observation_tokens import generate_observation_token
from okto_nexus.domain.observations import ObservationLimits, compute_freshness, parse_report, report_hash
from okto_nexus.observation_client import ObservationClient, ObservationClientError


NOW = "2026-11-06T15:00:00.000000Z"
SECRET_MARKER = "PRIVATE_REMOTE_TEXT_MUST_NOT_ESCAPE"


def report(**changes):
    value = dict(schema_version=1, source_id="src_test", observed_instance_id="obs_test",
        generation=3, sequence=42, state="blocked", evidence="reported", observed_at=NOW,
        reason_code="external_input_required")
    value.update(changes)
    return value


class FakePublishServer:
    def __init__(self):
        self.requests, self.receipts = [], {}
        self.token = generate_observation_token()
        self.received_at = NOW
        self.responder = self.accept

    def __repr__(self):
        return "<SyntheticPublishServer>"

    def accept(self, payload):
        receipts = []
        for value in payload.get("reports", [payload]):
            parsed = parse_report(value)
            key = (parsed.observed_instance_id, parsed.generation, parsed.sequence)
            replayed = key in self.receipts
            if not replayed:
                fresh = compute_freshness(parsed, received_at=self.received_at,
                                          limits=ObservationLimits(future_tolerance_seconds=300))
                self.receipts[key] = dict(observed_instance_id=parsed.observed_instance_id,
                    generation=parsed.generation, sequence=parsed.sequence, report_hash=report_hash(parsed),
                    received_at=fresh.received_at, valid_until=fresh.valid_until)
            receipts.append(dict(self.receipts[key], replayed=replayed))
        return 200, {"ok": True, "data": {"receipts": receipts}}, {}


@contextmanager
def fake_server():
    state = FakePublishServer()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state.requests.append(dict(method="GET", path=self.path, headers=dict(self.headers), body=b""))
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            state.requests.append(dict(method="POST", path=self.path, headers=dict(self.headers), body=raw))
            response = state.responder(json.loads(raw))
            if response is None:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            status, content, headers = response
            encoded = content if isinstance(content, bytes) else json.dumps(content).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(encoded)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Deliberate response-loss/timeout scenarios disconnect.

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


@pytest.fixture
def server():
    with fake_server() as state:
        yield state


def client(server, **kwargs):
    return ObservationClient(server.origin, token=server.token, **kwargs)


def test_only_publish_posts_use_exclusive_bearer_without_env_proxy_or_cookie(server, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    accept = server.accept
    server.responder = lambda payload: (*accept(payload)[:2], {"Set-Cookie": "unexpected=private; Path=/"})
    sender = client(server)
    original = report()
    first = sender.publish(original)
    second = sender.publish(original)
    assert "valid_for_seconds" not in original
    assert first["receipts"][0]["replayed"] is False
    assert second["receipts"][0]["replayed"] is True
    assert repr(sender) == "ObservationClient()"
    assert len(server.requests) == 2
    for sent in server.requests:
        assert sent["method"] == "POST" and sent["path"] == "/v1/observations/activity"
        assert hmac.compare_digest(sent["headers"]["Authorization"], "Bearer " + server.token)
        assert "Cookie" not in sent["headers"]
        assert sent["headers"]["Content-Type"] == "application/json"


def test_lost_response_has_no_automatic_retry_and_exact_caller_retry_retains_receipt(server):
    def lose_first(payload):
        accepted = server.accept(payload)
        return None if len(server.requests) == 1 else accepted

    server.responder = lose_first
    sender, stable_payload = client(server), report()
    with pytest.raises(ObservationClientError) as caught:
        sender.publish(stable_payload)
    assert caught.value.outcome_unknown is True
    assert len(server.requests) == len(server.receipts) == 1
    stored = deepcopy(next(iter(server.receipts.values())))
    server.received_at = "2026-11-07T15:00:00.000000Z"
    retried = sender.publish(stable_payload)["receipts"][0]
    assert retried == dict(stored, replayed=True)
    assert len(server.requests) == 2 and len(server.receipts) == 1
    assert hashlib.sha256(server.requests[0]["body"]).digest() == hashlib.sha256(server.requests[1]["body"]).digest()


def test_batch_list_and_saved_wrapper_return_matching_receipts(server):
    reports = [report(observed_instance_id=f"obs_{index}") for index in range(100)]
    result = client(server).publish(reports)
    assert len(result["receipts"]) == 100
    assert [entry["observed_instance_id"] for entry in result["receipts"]] == [entry["observed_instance_id"] for entry in reports]
    replay = client(server).publish({"reports": reports})
    assert all(item["replayed"] for item in replay["receipts"])
    assert hashlib.sha256(server.requests[0]["body"]).digest() == hashlib.sha256(server.requests[1]["body"]).digest()


def test_receipt_allows_server_configured_future_tolerance_without_client_clock_policy(server):
    result = client(server).publish(report(observed_at="2026-11-06T15:03:20Z"))
    assert result["receipts"][0]["valid_until"] == "2026-11-06T15:01:30.000000Z"


@pytest.mark.parametrize("payload", [[], [report()] * 101, {"reports": []}, {"reports": [report()], "extra": 1},
    [report(), report()], report(sequence=True), report(agent_id="injected"), report(token=SECRET_MARKER),
    report(reason_text="a" * 513), report(observed_at="2026-11-06T15:00:00")])
def test_invalid_reports_fail_before_any_network(server, payload):
    with pytest.raises(ObservationClientError) as caught:
        client(server).publish(payload)
    assert caught.value.code == "REPORT_INVALID"
    assert caught.value.outcome_unknown is False
    assert not server.requests
    assert SECRET_MARKER not in str(caught.value)


def test_both_input_and_expanded_canonical_report_must_fit_four_kib(server):
    values = [report(source_id="s" * 160, observed_instance_id="o" * 160, reason_text="\0" * 512,
                     observed_at="2026-11-06T15:00:00Z", current_completion_ref="😀" * size)
              for size in range(1, 257)]
    def encode(value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    expanded = next(value for value in values if len(encode(value)) <= 4096
                    < len(encode(parse_report(value).to_dict())))
    oversized = next(value for value in values if len(encode(value)) > 4096)
    for value in (expanded, oversized):
        with pytest.raises(ObservationClientError) as caught:
            client(server).publish(value)
        assert caught.value.outcome_unknown is False
    assert not server.requests


@pytest.mark.parametrize("origin", ["http://example.com", "https://user:private@example.com", "https://example.com/path",
    "https://example.com?secret", "https://example.com#secret", "https://example.com?", "https://example.com#",
    "https://example.com:0", "https://example.com:99999", "http://127.0.0.1\\evil", "https://example.com\n",
    "file:///tmp/report", None, "https://example%2fsecret.com"])
def test_invalid_origins_are_sanitized_before_network(origin):
    with pytest.raises(ObservationClientError) as caught:
        ObservationClient(origin, token=generate_observation_token())
    assert caught.value.code == "SERVER_ORIGIN_INVALID"
    assert caught.value.outcome_unknown is False
    assert "private" not in str(caught.value) and "secret" not in str(caught.value)


@pytest.mark.parametrize("timeout", [True, False, 0, -1, 31, float("nan"), float("inf"), "15", 10 ** 1000])
def test_timeout_is_exact_numeric_finite_and_bounded(timeout):
    with pytest.raises(ObservationClientError) as caught:
        ObservationClient("https://example.com", token=generate_observation_token(), timeout=timeout)
    assert caught.value.code == "TIMEOUT_INVALID"


@pytest.mark.parametrize("prefix", ["nxs_", "nxsept_", "nxc4_", "nxt4_"])
def test_other_credentials_never_gain_publish_authority(prefix):
    with pytest.raises(ObservationClientError) as caught:
        ObservationClient("https://example.com", token=prefix + "a" * 64)
    assert caught.value.code == "TOKEN_INVALID"
    assert prefix not in str(caught.value)


@pytest.mark.parametrize("status,code", [(401, "AUTH_FAILED"), (403, "PERMISSION_DENIED"), (409, "CONFLICT"),
    (413, "CONTENT_TOO_LARGE"), (422, "VALIDATION_ERROR"), (429, "QUOTA_EXCEEDED")])
def test_known_refusals_are_distinct_without_remote_text_or_automatic_retry(server, status, code):
    server.responder = lambda _: (status, {"raw_secret": SECRET_MARKER}, {"Retry-After": "99999999999999999999"})
    with pytest.raises(ObservationClientError) as caught:
        client(server).publish(report())
    error = caught.value
    assert error.code == code and error.status == status and error.outcome_unknown is False
    assert error.retry_after_seconds == (3600 if status == 429 else None)
    assert SECRET_MARKER not in str(error) and SECRET_MARKER not in repr(error.args)
    assert len(server.requests) == 1


@pytest.mark.parametrize("remote_code,unknown", [("OBSERVATION_BUSY", False), ("DB_ERROR", True), ("INTERNAL_ERROR", True),
                                                ("OBSERVATION_UNAVAILABLE", True)])
def test_service_unavailable_only_busy_proves_pre_admission_refusal(server, remote_code, unknown):
    server.responder = lambda _: (503, {"ok": False, "error": {"code": remote_code, "message": SECRET_MARKER}}, {"Retry-After": "2"})
    with pytest.raises(ObservationClientError) as caught:
        client(server).publish(report())
    assert caught.value.status == 503 and caught.value.outcome_unknown is unknown
    assert caught.value.retry_after_seconds == 2
    assert SECRET_MARKER not in str(caught.value)
    assert len(server.requests) == 1


@pytest.mark.parametrize("change", [{"observed_instance_id": "obs_other"}, {"generation": True}, {"sequence": 43},
    {"report_hash": "sha256:" + "0" * 64}, {"received_at": "2026-11-06T15:00:00Z"},
    {"valid_until": "2026-11-06T15:01:31.000000Z"}, {"valid_until": NOW}, {"replayed": 1}, {"raw": SECRET_MARKER}])
def test_invalid_receipt_after_send_preserves_uncertainty_and_drops_remote_values(server, change):
    def corrupt(payload):
        status, body, headers = server.accept(payload)
        body["data"]["receipts"][0].update(change)
        return status, body, headers

    server.responder = corrupt
    with pytest.raises(ObservationClientError) as caught:
        client(server).publish(report())
    assert caught.value.code == "RESPONSE_INVALID" and caught.value.outcome_unknown is True
    assert SECRET_MARKER not in str(caught.value)
    assert len(server.requests) == 1


@pytest.mark.parametrize("body", [b'{"ok":true,"ok":true,"data":{"receipts":[]}}', b'{"ok":true,"data":NaN}',
    b'<html>PRIVATE_REMOTE_TEXT_MUST_NOT_ESCAPE</html>', b"x" * (128 * 1024 + 1)],
    ids=["duplicate_keys", "nonfinite", "html", "oversized"])
def test_malformed_duplicate_or_oversized_response_is_not_a_receipt(server, body):
    server.responder = lambda _: (200, body, {})
    with pytest.raises(ObservationClientError) as caught:
        client(server).publish(report())
    assert caught.value.outcome_unknown is True
    assert SECRET_MARKER not in str(caught.value)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_never_forwards_bearer_or_changes_method(server, status):
    with fake_server() as target:
        server.responder = lambda _: (status, {}, {"Location": target.origin + "/forbidden"})
        with pytest.raises(ObservationClientError) as caught:
            client(server).publish(report())
        assert caught.value.code == "REDIRECT_REFUSED"
        assert caught.value.outcome_unknown is True
        assert len(server.requests) == 1
        assert not target.requests


def test_real_socket_timeout_is_uncertain_after_send_without_automatic_retry(server):
    def slow_reply(payload):
        accepted = server.accept(payload)
        time.sleep(.15)
        return accepted

    server.responder = slow_reply
    started = time.monotonic()
    with pytest.raises(ObservationClientError) as caught:
        client(server, timeout=.03).publish(report())
    assert caught.value.code == "TRANSPORT_ERROR" and caught.value.outcome_unknown is True
    assert time.monotonic() - started < 2
    assert len(server.requests) == len(server.receipts) == 1


@pytest.mark.parametrize("retry", ["-1", "1.5", "tomorrow", "Wed, 21 Oct 2015 07:28:00 GMT"])
def test_invalid_retry_after_never_becomes_an_unbounded_wait(server, retry):
    server.responder = lambda _: (429, {}, {"Retry-After": retry})
    with pytest.raises(ObservationClientError) as caught:
        client(server).publish(report())
    assert caught.value.retry_after_seconds is None
    assert len(server.requests) == 1


def test_example_reads_only_named_token_env_and_prints_validated_receipt(server):
    script = Path(__file__).resolve().parents[1] / "docs" / "observation-client-example.py"
    result = subprocess.run([sys.executable, str(script), "--origin", server.origin,
                             "--token-env", "SYNTHETIC_OBSERVATION_TOKEN"],
        input=json.dumps(report()), capture_output=True, text=True, timeout=10,
        env=dict(os.environ, SYNTHETIC_OBSERVATION_TOKEN=server.token))
    assert result.returncode == 0
    value = json.loads(result.stdout)
    assert set(value) == {"receipts"} and len(value["receipts"]) == 1
    assert not result.stderr
    assert server.token not in result.stdout
    assert len(server.requests) == 1
