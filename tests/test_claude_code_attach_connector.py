"""Tests for the Claude Code ATTACH (``cc-socks``) connector, ADR 0004 D7b.

Every test here runs against a FAKE ``AF_UNIX`` socket bound under ``tmp_path``
plus fabricated registry/token files - never the real ``~/.claude/sessions``
tree and never a real Claude Code binary (task instruction: tests must not
require the real binary). The only "real" process ever probed is this test
process's own pid (``os.getpid()``), purely so ``os.kill(pid, 0)`` liveness
checks have something legitimate to check - no signal with any effect is ever
sent, and this never touches a live Claude Code session, per the task's
SAFETY rule.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest

from legacy_native_fixture.claude_code_attach import (
    CAPABILITIES,
    ClaudeCodeAttachConnector,
    ProbeResult,
    _INJECTION_BANNER,
    discover_attachable_sessions,
)
from okto_nexus.domain.harness import (
    STATUS_RUNNING,
    STATUS_STARTING,
    HarnessCommand,
    HarnessSession,
)
from okto_nexus.errors import OktoNexusError


pytestmark = pytest.mark.skipif(
    os.name != "posix",
    reason="NOT_RUN: attach fixture requires POSIX UID, process, and socket ownership semantics",
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
class _FakeSocketServer:
    """A real ``AF_UNIX`` listener recording every connection's NDJSON lines."""

    def __init__(self, sock_path: Path) -> None:
        self.sock_path = sock_path
        self.connections: list[list[dict]] = []
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(sock_path))
        self._server.listen(4)
        self._server.settimeout(0.2)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with conn:
                conn.settimeout(1.0)
                data = b""
                try:
                    while True:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                except socket.timeout:
                    pass
                lines = [
                    json.loads(line) for line in data.decode("utf-8").splitlines() if line
                ]
                self.connections.append(lines)

    def wait_for_connections(self, count: int, timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(self.connections) >= count:
                return
            time.sleep(0.02)
        raise AssertionError(
            f"expected {count} connections, got {len(self.connections)}: "
            f"{self.connections!r}"
        )

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._server.close()


@pytest.fixture
def fake_server():
    # AF_UNIX's sun_path is capped at ~103 bytes; pytest's own tmp_path (deep
    # under pytest-of-<user>/pytest-N/...) regularly exceeds that on macOS -
    # exactly the ceiling ADR 0004 D7b's path-resolution rule accounts for.
    # The socket therefore lives in a short, dedicated /tmp directory; the
    # registry/key JSON FILES (not bind targets) still use pytest's tmp_path.
    short_dir = tempfile.mkdtemp(dir="/tmp", prefix="nxs-")
    server = _FakeSocketServer(Path(short_dir) / "p.sock")
    yield server
    server.close()
    shutil.rmtree(short_dir, ignore_errors=True)


def _write_registry(
    sessions_dir: Path,
    pid: int,
    *,
    kind: str = "interactive",
    socket_path: str | None = None,
    peer_protocol: int | None = 1,
    **extra,
) -> None:
    payload = {
        "pid": pid,
        "sessionId": "sess-abc123",
        "cwd": "/tmp/project",
        "startedAt": 1789903982261,
        "version": "2.1.278",
        "peerProtocol": peer_protocol,
        "peerFeatures": ["notify_idle"],
        "kind": kind,
        "tmux": None,
        "messagingSocketPath": socket_path,
        "name": "test-session",
        "status": "idle",
    }
    payload.update(extra)
    (sessions_dir / f"{pid}.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_key(
    sessions_dir: Path,
    pid: int,
    *,
    key_hash: str = "deadbeef",
    token: str = "tok-xyz",
    proc_start: str | None = "12345",
) -> Path:
    path = sessions_dir / f"{pid}.{key_hash}.key"
    path.write_text(
        json.dumps({"peerToken": token, "procStart": proc_start, "pidDomain": "darwin"}),
        encoding="utf-8",
    )
    return path


def _live_pid() -> int:
    # This test process's own pid: os.kill(pid, 0) succeeds legitimately and
    # sends no signal with any effect. Never a real Claude Code session.
    return os.getpid()


# --------------------------------------------------------------------------- #
# discover_attachable_sessions
# --------------------------------------------------------------------------- #




# --------------------------------------------------------------------------- #
# probe()
# --------------------------------------------------------------------------- #








# --------------------------------------------------------------------------- #
# start()
# --------------------------------------------------------------------------- #










# --------------------------------------------------------------------------- #
# send()
# --------------------------------------------------------------------------- #
def _started_connector(
    tmp_path: Path, fake_server: _FakeSocketServer, *, token: str = "tok-xyz"
) -> tuple[ClaudeCodeAttachConnector, HarnessSession]:
    pid = _live_pid()
    _write_registry(tmp_path, pid, socket_path=str(fake_server.sock_path))
    _write_key(tmp_path, pid, key_hash="deadbeef", token=token)
    connector = ClaudeCodeAttachConnector(pid, sessions_dir=tmp_path, connect_timeout_s=1.0)
    session = connector.start(owning_agent_id="agent-1")
    return connector, session
















# --------------------------------------------------------------------------- #
# events()
# --------------------------------------------------------------------------- #




# --------------------------------------------------------------------------- #
# Adversarial-review defects (EV-REV-002 / journal wf_de1d2ad9-17f)
# --------------------------------------------------------------------------- #
# PRIORITY 1 (critical): probe()/start() must never leak a bare, non-OktoNexusError
# exception when registry-sourced data is malformed - an embedded NUL in
# messagingSocketPath makes os.stat()/socket.connect() raise ValueError, which is
# NOT an OSError and previously escaped every `except OSError` guard.






# PRIORITY 1b: probe() and start() must validate in the SAME order so probe()'s
# diagnosis matches what a real start() would raise for the same underlying state.








# _computed_socket_path is a pure function of (pid, env) - the report itself
# flagged these two branches as the least-certain, untested part of the module.




# _check_no_pid_reuse: the realistic recycling case is the ORIGINAL key file
# disappearing (session ended) and, for a true pid reuse, a NEW <pid>.<hash>.key
# appearing - not an in-place rewrite of the same path.




# Ack-less limitation (EV-CC-001): a clean sendall() is NOT proof of delivery.
# A peer that accepts the connection and then immediately closes it on the auth
# line is indistinguishable, at the socket-write level, from a real success.
class _AcceptThenCloseServer:
    """Accepts every connection and closes it immediately without reading."""

    def __init__(self, sock_path: Path) -> None:
        self.sock_path = sock_path
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(sock_path))
        self._server.listen(4)
        self._server.settimeout(0.2)
        self._stop = threading.Event()
        self.accepted = 0
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self.accepted += 1
            conn.close()  # reject immediately, no read, no ack

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._server.close()




class _RejectAfterAuthServer:
    """Reads exactly the auth line (matching EV-CC-001's shape), validates it
    against an expected token, then CLOSES without reading the user line and
    without ever sending anything back - simulating a peer that rejects a
    bad/stale auth line. Records the parsed auth line it actually saw, so a
    test can assert the connector really did send auth-first NDJSON shaped
    exactly like EV-CC-001 documents, not merely "something"."""

    def __init__(self, sock_path: Path, *, expected_token: str) -> None:
        self.sock_path = sock_path
        self.expected_token = expected_token
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(sock_path))
        self._server.listen(4)
        self._server.settimeout(0.2)
        self._stop = threading.Event()
        self.accepted = 0
        self.observed_auth_lines: list[dict] = []
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self.accepted += 1
            with conn:
                conn.settimeout(1.0)
                buf = b""
                try:
                    while b"\n" not in buf:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        buf += chunk
                except socket.timeout:
                    pass
                first_line = buf.split(b"\n", 1)[0]
                if first_line:
                    try:
                        parsed = json.loads(first_line.decode("utf-8"))
                    except ValueError:
                        parsed = None
                    if isinstance(parsed, dict):
                        self.observed_auth_lines.append(parsed)
                # Reject regardless of validity: close immediately, no ack,
                # never read the user line. EV-CC-001: send is fire-and-
                # forget with no synchronous ack on this transport at all.

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._server.close()


class _CloseMidMessageServer:
    """Reads the auth line fully, then reads only PART of the user line
    before closing - simulating a connection dropped mid-message rather than
    rejected outright at the auth boundary."""

    def __init__(self, sock_path: Path) -> None:
        self.sock_path = sock_path
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(sock_path))
        self._server.listen(4)
        self._server.settimeout(0.2)
        self._stop = threading.Event()
        self.accepted = 0
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self.accepted += 1
            with conn:
                conn.settimeout(1.0)
                buf = b""
                try:
                    while b"\n" not in buf:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        buf += chunk
                    # Auth line consumed; now read only a few bytes of the
                    # user line (deliberately truncated) before dropping.
                    conn.recv(8)
                except socket.timeout:
                    pass
                # Falls out of `with conn:` here -> socket closed mid-message.

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._server.close()










# Cross-cutting audit: single-consume shutdown sentinel / unbounded blocking wait.
# This connector's events() is a bounded, lock-guarded history snapshot (RES-A2 fix:
# an append-only list, not a destructively-drained Queue/deque pump with a background
# reader thread), so this class of hang structurally cannot occur here - this test
# documents that rather than fixing anything.


# L14 (later verify run, EV-REV-002): neither start() nor send() verified the
# connecting socket's owning uid before writing the bearer token to it - a
# latent token-disclosure risk on the world-writable /tmp fallback path.




# --------------------------------------------------------------------------- #
# RES suite (plans/harness-integrations/01-test-plan.md, added 2026-09-20 -
# resilience cases from EV-REV-002's three recurring defect classes)
# --------------------------------------------------------------------------- #
#
# RES-A1 (events() called twice returns both times, does not hang) is ALREADY
# covered above by test_events_can_be_called_twice_without_hanging - cited as
# existing evidence, not duplicated here.
#
# RES-C1 (fake wire behaviour justified against captured bytes) and RES-C3
# (fakes can fail, not only succeed) are ALREADY covered above:
# test_send_delivers_auth_then_user_ndjson_lines asserts the exact
# {"type":"auth","token":...} / {"type":"user","message":{...}} shape and
# auth-then-user ordering documented verbatim in
# docs/harness-integrations/evidence/EV-CC-001-cc-socks-external-inject.md
# ("An auth line is REQUIRED first ... echo '{"type":"auth"...}'; echo
# '{"type":"user","message":{"role":"user","content":"hello"}}'"); the
# _AcceptThenCloseServer / _RejectAfterAuthServer / _CloseMidMessageServer
# fakes above are all fakes that REJECT/drop rather than only ever succeed.
#
# RES-B1/B2/B3 (guarded per-line dispatch in a reader thread) and RES-C2 (the
# fake emits the real interrupt/abort ordering) DO NOT APPLY to this
# connector and are not faked here: cc-socks is SEND-ONLY with NO inbound
# channel at all (module docstring; capabilities.send_only=True) - there is
# no reader thread, no per-line dispatch loop, and no interrupt/abort verb on
# this transport (send() rejects every verb other than "send_turn" -
# claude_code_attach.py:702-710). The nearest structural analogue - malformed
# JSON-shaped INPUT this connector actually parses (the registry/key files,
# not a wire read loop) - is already covered by
# test_probe_and_start_agree_when_key_file_exists_but_is_unparseable and the
# two NUL-byte tests
# (test_probe_never_raises_on_embedded_null_byte_in_socket_path,
# test_start_raises_oktonexuserror_not_valueerror_on_embedded_null_byte):
# each surfaces a structured OktoNexusError, never a bare exception, exactly
# the discipline RES-B1 asks of a per-line dispatch loop this connector does
# not have.













# --------------------------------------------------------------------------- #
# LIMITATION 3 - cc-socks breakage detection (this task)
#
# The connector already had probe()/ProbeResult from an earlier round. The gap
# this section closes: many genuinely different failure causes collapsed into
# the SAME generic `reason` string via probe()'s `details.get("reason",
# exc.code.lower())` fallback ("not_found" covered a missing registry file
# AND a missing key file; "config_error" covered a corrupted registry, an
# unparseable key file, a NUL byte in a socket path, and an ambiguous key-file
# set - four unrelated causes, one string). That violates the task's own bar:
# "an operator should be able to tell 'Claude Code changed its protocol'
# apart from 'no session is running' and from 'wrong permissions' ...
# distinct, attributable outcome - not one generic error."
#
# Every raise site in this module now sets an explicit, UNIQUE `reason` plus
# a coarse `category` in `("ok", "protocol_drift", "no_session", "permission",
# "internal")` - `category` is the operator's triage bucket (maps 1:1 onto the
# task's three-way ask, plus "internal" for this code's own unanticipated
# failures); `reason` stays the precise, machine-stable code. Neither is a
# structural guarantee that a REAL future Claude Code release will be caught -
# nobody can test the future. What is proven here is narrower and honest: five
# specific, observable registry/key-file shapes each produce a distinct,
# attributable outcome, and a change that moves one of those specific fields
# will land in one of these buckets rather than a generic catch-all.
# --------------------------------------------------------------------------- #


























#: Methods this audit holds to the reason+category contract: everything
#: ``probe()``/``start()`` call to check an attach PRECONDITION (registry
#: shape, process liveness, protocol value, key file shape, socket
#: shape/ownership), plus the pid-reuse guard (an environmental "is this
#: still the same session" check, the same family). Deliberately EXCLUDES
#: ``send()``'s own basic input-validation raises (wrong verb, empty
#: content, a session this connector never started) - those are ordinary
#: API-contract violations by NEXUS'S OWN CALLER, not cc-socks breakage
#: signals, and forcing them into "protocol_drift"/"no_session"/
#: "permission" would misattribute a programming error as a transport
#: problem. Named explicitly (not "every function") so a new attach-path
#: check added later must be added here too, on purpose, not swept in or
#: silently skipped by accident.
_ATTACH_PRECONDITION_METHODS = {
    "_read_registry",
    "_resolve_socket_path",
    "_find_key_file",
    "_read_key",
    "_check_process_alive",
    "_check_peer_protocol",
    "_check_socket_ownership",
    "_check_socket_is_socket",
    "start",
    "_raise_pid_reuse_guard",
}
