"""Public/legacy entry routing and exact HTTP capability diagnostics.

All networking is bounded loopback owned by the test. No Server, account,
vault, native harness, setup Test or provider is started.
"""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.cli import connect, quick_connect_selection
from okto_nexus.adapters.inbound.cli.connect_arguments import parse_connect_args
from okto_nexus.adapters.inbound.cli.quick_connect_ids import require_public_ids
from okto_nexus.adapters.outbound.operator_client import RemoteOperatorHTTP
from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
from okto_nexus.application.terminal_connection import ConnectionError


@pytest.mark.parametrize(
    "flags",
    [
        [],
        ["--plan"],
        ["--json"],
        ["--no-chat"],
        ["--timeout", "12"],
        ["--start-at-login"],
        ["codex"],
        ["codex", "Project"],
        ["--id", "reviewer"],
        ["codex", "--project", "C:/owned"],
        ["codex", "--client", "codex"],
        ["--id", "reviewer", "--profile", "existing"],
    ],
)
def test_public_entry(flags):
    args, _ = parse_connect_args(flags)
    assert connect._quick_entry_requested(args) is True


@pytest.mark.parametrize(
    "flags",
    [
        ["--profile", "existing"],
        ["--project", "C:/owned"],
        ["--client", "codex"],
        ["--agent", "a"],
        ["--new-agent", "b"],
        ["--name", "Named"],
        ["--workspace-id", "w"],
        ["--binding-id", "b"],
        ["--candidate-ref", "c"],
        ["--provider-home", "C:/owned"],
        ["--operator-profile", "remote"],
        ["--remote-draft", "C:/owned"],
        ["--setup-receipt-output", "C:/owned"],
        ["--approve", "revision"],
        ["--new-connection"],
        ["--review-current"],
    ],
)
def test_legacy_selectors(flags):
    args, _ = parse_connect_args(flags)
    assert connect._quick_entry_requested(args) is False


@pytest.mark.parametrize(
    "flags,checkpoint",
    [
        ([], False),
        (["codex"], False),
        (["--id", "reviewer"], False),
        (["--profile", "retained"], True),
    ],
)
def test_quick_route_and_saved_checkpoint_reach_prepare(
    tmp_path, monkeypatch, capsys, flags, checkpoint
):
    home = tmp_path / "home"
    if checkpoint:
        target = home / "terminal/profiles/retained.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"selection": {"quick_connect": {"version": 1}}}))
    service = SimpleNamespace(
        adapter=SimpleNamespace(home=home, host="127.0.0.1", port=1),
        ensure_running=lambda **kwargs: {"state": "ready"},
        inspect=lambda: {"state": "ready"},
    )
    monkeypatch.setattr(connect, "resolve_local_service", lambda args: service)
    monkeypatch.setattr(connect.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    calls = []

    def prepare(*args, **kwargs):
        calls.append(kwargs.get("saved"))
        raise ConnectionError(
            "QUICK_ROUTE_SENTINEL", "No HTTP, provider or setup effects"
        )

    monkeypatch.setattr(quick_connect_selection, "prepare", prepare)
    assert connect.run_connect([*flags, "--home", str(home), "--json", "--plan"]) == 3
    assert len(calls) == 1
    assert "QUICK_ROUTE_SENTINEL" in capsys.readouterr().out
    assert bool(calls[0]) is checkpoint


def operator_transport(kind, port):
    if kind == "remote":
        transport = RemoteOperatorHTTP(f"http://127.0.0.1:{port}")
        transport.timeout = 1
        return transport
    return LocalOperatorHTTP(host="127.0.0.1", port=port, timeout=1)


@pytest.mark.parametrize("kind", ["local", "remote"])
@pytest.mark.parametrize(
    "status,error_code,malformed,expected",
    [
        (404, None, False, "CONNECT_ID_UNSUPPORTED_SERVER"),
        (405, None, False, "CONNECT_ID_UNSUPPORTED_SERVER"),
        (404, None, True, "CONNECT_ID_UNSUPPORTED_SERVER"),
        (401, "AUTH_FAILED", False, "AUTH_FAILED"),
        (403, "PERMISSION_DENIED", False, "PERMISSION_DENIED"),
        (403, "HTTP_ERROR", False, "HTTP_ERROR"),
        (403, None, False, "REQUEST_REFUSED"),
        (500, "HTTP_ERROR", False, "HTTP_ERROR"),
    ],
)
def test_public_id_http_status_is_precise(
    kind, status, error_code, malformed, expected
):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.command, self.path))
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            value = (
                {"error": {"code": error_code}} if error_code else {"detail": "refused"}
            )
            self.wfile.write(b"bad" if malformed else json.dumps(value).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=lambda: server.serve_forever(poll_interval=0.01), daemon=True
    )
    thread.start()
    try:
        transport = operator_transport(kind, server.server_port)
        route = "/api/v1/runtime-management/connections/public-ids"
        with pytest.raises(ConnectionError) as raw:
            transport("GET", route)
        assert raw.value.http_status == status
        assert raw.value.possible_effect is False
        with pytest.raises(ConnectionError) as refusal:
            require_public_ids(transport, "own-test-server")
        if kind == "remote" and expected == "AUTH_FAILED":
            expected = "OPERATOR_LOGIN_REQUIRED"
        assert refusal.value.code == expected
        assert refusal.value.possible_effect is False
        if expected != "CONNECT_ID_UNSUPPORTED_SERVER":
            assert refusal.value.http_status == status
        assert calls == [("GET", route), ("GET", route)]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


@pytest.mark.parametrize("kind", ["local", "remote"])
def test_public_id_network_refusal_is_not_unsupported(kind):
    # Keep the port bound but not listening, so another fixture cannot claim it.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        transport = operator_transport(kind, sock.getsockname()[1])
        with pytest.raises(ConnectionError) as refusal:
            require_public_ids(transport, "own-test-server")
    assert refusal.value.code == "SERVER_UNREACHABLE"
    assert refusal.value.http_status is None
    assert refusal.value.possible_effect is False
