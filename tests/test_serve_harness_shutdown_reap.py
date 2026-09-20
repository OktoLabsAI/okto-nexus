"""EV-OPS-001: `serve` must reap live harness children on shutdown.

Reproduces (before the fix) and then proves (after the fix) the defect
recorded in `docs/harness-integrations/evidence/EV-OPS-001-uat-orphan-
children.md`: two real `pi --mode rpc` children survived 1.5 hours after
their `okto-nexus serve` process exited, reparented to PPID=1 (`launchd`).

Every assertion here is on PPID reparenting via a real `ps` snapshot, NEVER
a binary-name grep - EV-OPS-001's own postmortem is explicit that a name
grep is exactly what let the original orphan go undetected (it matched a
PATH shim's `python3` argv, not `pi`).

This file boots its OWN `okto-nexus serve` subprocess per test (NOT the
session-scoped `real_server` fixture in `conftest.py`) because it needs to
send a single, targeted signal to the SERVE PROCESS ONLY - never its whole
process group - to reproduce the real-world shutdown path (a supervisor,
`launchd`/`systemd`, or an operator's plain `kill <pid>` signals one pid,
not a group).

## Why a FAKE `pi` binary, not the real one

An independent verifier already tried this with the REAL `pi` binary (live
serve + live pi session + `kill -9` on the server) and saw no orphan - but
correctly attributed that to `pi` self-exiting on stdin EOF (its write end
closes when serve dies), an INCIDENTAL behaviour of that one harness, not a
deliberate reap by okto-nexus. EV-OPS-001's own instructions are explicit
that repeating that as "closed" would be the exact mistake this project has
already made twice. Since the real `pi` binary exits on EOF regardless of
whether our fix exists, it CANNOT distinguish "our supervisor reaped it"
from "it happened to die on its own" - a real-`pi` test would pass both
before and after the fix, proving nothing.

`_FAKE_PI_SOURCE` below is a tiny stand-in placed first on `PATH` for the
spawned `serve` subprocess. It speaks exactly the one exchange
`PiRpcConnector.start()`'s handshake needs (a `get_state` command must get a
`response` envelope back - see `docs/harness-integrations/research/pi-rpc-
protocol-reference.md` -1 and `pi.py::start()`), so the REAL `PiRpcConnector`
and the REAL `HarnessSupervisor`/`serve.py` reap path run unmodified. Unlike
real `pi`, it does NOT exit on stdin EOF - it blocks forever until a signal
kills it. That makes "the child is dead" unambiguous evidence that OUR
`close()`/SIGTERM-then-SIGKILL path did it, and "the child is alive and
reparented to PPID=1" unambiguous evidence that nothing reaped it. No
network call, no model, no `.secrets/harness.env` dependency - `pi`'s
`--provider`/`--model` args are accepted and ignored by the stub, so the
usual `zai/glm-5.3` box-safety override is a no-op here but kept anyway
for hygiene and consistency with every other harness test in this repo.

Every server + child this file spawns is torn down (SIGKILL fallback) in a
`finally` block, and each assertion helper is PPID-based so a straggler
would be caught rather than silently ignored.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

httpx = pytest.importorskip("httpx")

_REPO_ROOT = Path(__file__).resolve().parent.parent

_FAKE_PI_SOURCE = '''#!/usr/bin/env python3
import json
import sys
import time

for line in iter(sys.stdin.readline, ""):
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except ValueError:
        continue
    verb = msg.get("type")
    if verb:
        resp = {"type": "response", "command": verb, "success": True, "data": {}}
        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()

# Real EOF handling ends here (real `pi` self-exits at this point - the
# documented confound this stub exists to remove). Block until a signal
# (SIGTERM/SIGKILL from HarnessSupervisor's own teardown) kills us instead.
while True:
    time.sleep(3600)
'''


def _materialize_fake_pi(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "pi"
    script.write_text(_FAKE_PI_SOURCE, encoding="utf-8")
    script.chmod(0o755)
    return script


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _ps_snapshot() -> list[tuple[int, int, str]]:
    """`(pid, ppid, command)` for every process visible to this user."""
    out = subprocess.run(
        ["ps", "-A", "-o", "pid=,ppid=,command="],
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout
    rows = []
    for line in out.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 2:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        command = parts[2] if len(parts) > 2 else ""
        rows.append((pid, ppid, command))
    return rows


def _descendants(root_pid: int, snapshot: list[tuple[int, int, str]]) -> set[int]:
    children: dict[int, list[int]] = {}
    for pid, ppid, _ in snapshot:
        children.setdefault(ppid, []).append(pid)
    out: set[int] = set()
    frontier = [root_pid]
    while frontier:
        pid = frontier.pop()
        for child in children.get(pid, ()):
            if child not in out:
                out.add(child)
                frontier.append(child)
    return out


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _ppid_of(pid: int, snapshot: list[tuple[int, int, str]]) -> int | None:
    for p, ppid, _ in snapshot:
        if p == pid:
            return ppid
    return None


@dataclass
class _Server:
    process: subprocess.Popen
    base_url: str
    home_dir: Path


def _spawn_server(tmp_path: Path) -> _Server:
    """Boot a fresh, single-use `okto-nexus serve` child with the fake `pi`
    stub placed first on `PATH`. Own PID, own process group
    (`start_new_session=True`) - but this module signals the PID alone,
    never the group, to reproduce the real "supervisor kills one process"
    shutdown path."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    bin_dir = tmp_path / "bin"
    _materialize_fake_pi(bin_dir)
    port = _free_port()
    env = dict(os.environ)
    env["OKTO_NEXUS_HOME"] = str(home_dir)
    env["OKTO_NEXUS_DB_PATH"] = str(home_dir / "nexus.db")
    env["OKTO_NEXUS_PORT"] = str(port)
    env["OKTO_NEXUS_HOST"] = "127.0.0.1"
    env["OKTO_NEXUS_NO_BANNER"] = "1"
    env["OKTO_NEXUS_LOG_LEVEL"] = "warning"
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"

    cmd = [sys.executable, "-m", "okto_nexus.adapters.inbound.mcp.server", "serve"]
    process = subprocess.Popen(
        cmd,
        cwd=str(home_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=(os.name == "posix"),
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 30.0
    ready = False
    while time.monotonic() < deadline:
        if process.poll() is not None:
            out, err = process.communicate(timeout=5)
            raise AssertionError(
                f"serve exited early (code {process.returncode})\n{out}\n{err}"
            )
        try:
            resp = httpx.get(f"{base_url}/api/v1/info", timeout=1.0)
            if resp.status_code == 200:
                ready = True
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    if not ready:
        _hard_kill(process)
        raise AssertionError(f"serve did not become ready on {base_url}")
    return _Server(process=process, base_url=base_url, home_dir=home_dir)


def _hard_kill(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, OSError, PermissionError):
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _open_pi_session(base_url: str, project_root: Path) -> str:
    resp = httpx.post(
        f"{base_url}/api/v1/harness/sessions",
        json={
            "agent_id": "ev_ops_001_probe",
            "kind": "pi",
            "project_root": str(project_root),
            # Ignored by the fake `pi` stub, kept for hygiene/consistency
            # with every other harness test in this repo (D4/D5 box-safety:
            # `pi`'s own default provider `local-mac` resolves to the
            # off-limits LAN box).
            "backend": {"provider": "zai", "model": "glm-5.3"},
        },
        timeout=30.0,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["session_id"]


def _find_pi_child(server_pid: int, timeout_s: float = 15.0) -> int:
    """Poll for the fake `pi` process among `server_pid`'s REAL descendants
    (a PPID-chain walk from a `ps` snapshot). The name check only picks
    WHICH descendant to watch; the actual EV-OPS-001 defect check
    (`_assert_no_orphan`) is PPID-based, never name-based."""
    deadline = time.monotonic() + timeout_s
    last_descendants: set[int] = set()
    while time.monotonic() < deadline:
        snap = _ps_snapshot()
        descendants = _descendants(server_pid, snap)
        last_descendants = descendants
        for pid, ppid, command in snap:
            if pid not in descendants:
                continue
            # The stub has a `#!/usr/bin/env python3` shebang, so the OS
            # re-execs it as `python3 <path-to>/pi ...` - argv[0] alone is
            # NOT "pi" (this is exactly EV-OPS-001's own "PATH shim put
            # python3 first" observation, reproduced here on purpose rather
            # than avoided). Check every token's basename, not just argv[0].
            tokens = command.strip().split()
            if any(tok.rsplit("/", 1)[-1] == "pi" for tok in tokens):
                return pid
        time.sleep(0.3)
    raise AssertionError(
        f"no `pi` child found among descendants of {server_pid} within "
        f"{timeout_s}s (last descendants: {last_descendants})"
    )


def _assert_no_orphan(pi_pid: int, *, timeout_s: float = 15.0) -> None:
    """The core EV-OPS-001 assertion: within `timeout_s` of the signal, the
    `pi` child is EITHER dead, OR still alive but NOT reparented to PPID=1.
    Reparenting to PPID=1 (launchd/init) with the process still running is
    exactly the orphan EV-OPS-001 found - a survived, un-reaped child. The
    fake `pi` stub never exits on its own (see module docstring), so
    "dead" here can only mean our own reap path signalled it."""
    deadline = time.monotonic() + timeout_s
    last_ppid: int | None = -1
    while time.monotonic() < deadline:
        if not _pid_alive(pi_pid):
            return  # reaped - the good outcome
        snap = _ps_snapshot()
        last_ppid = _ppid_of(pi_pid, snap)
        if last_ppid == 1:
            pytest.fail(
                f"pi child pid={pi_pid} survived shutdown reparented to "
                f"PPID=1 (launchd) - an orphan, exactly EV-OPS-001's defect"
            )
        time.sleep(0.3)
    pytest.fail(
        f"pi child pid={pi_pid} still alive {timeout_s}s after shutdown "
        f"(last observed ppid={last_ppid}); reap did not converge in time"
    )


def _signal_serve_pid_only(server: _Server, sig: "signal.Signals") -> None:
    """Send ONE signal to the serve PID itself - never `killpg` - matching
    how a real supervisor/operator stops the process (the fake `pi` has its
    own session too, so a group-kill would mask this defect entirely)."""
    os.kill(server.process.pid, sig)


def test_sigterm_with_live_session_reaps_the_harness_child(tmp_path):
    server = _spawn_server(tmp_path)
    try:
        project = tmp_path / "project"
        project.mkdir()
        _open_pi_session(server.base_url, project)
        pi_pid = _find_pi_child(server.process.pid)

        _signal_serve_pid_only(server, signal.SIGTERM)
        server.process.wait(timeout=30)

        _assert_no_orphan(pi_pid)
    finally:
        _hard_kill(server.process)


def test_sigint_with_live_session_reaps_the_harness_child(tmp_path):
    server = _spawn_server(tmp_path)
    try:
        project = tmp_path / "project"
        project.mkdir()
        _open_pi_session(server.base_url, project)
        pi_pid = _find_pi_child(server.process.pid)

        _signal_serve_pid_only(server, signal.SIGINT)
        server.process.wait(timeout=30)

        _assert_no_orphan(pi_pid)
    finally:
        _hard_kill(server.process)


def test_clean_shutdown_after_explicit_close_leaves_no_orphan(tmp_path):
    """Sanity companion to SYS-10 (EV-SYS-010): the explicit-close path this
    file's two SIGTERM/SIGINT cases do NOT exercise. Kept here (not just
    trusted from SYS-10) so this module alone proves all three shutdown
    paths the task asked for, with the same PPID-based assertion."""
    server = _spawn_server(tmp_path)
    try:
        project = tmp_path / "project"
        project.mkdir()
        session_id = _open_pi_session(server.base_url, project)
        pi_pid = _find_pi_child(server.process.pid)

        close = httpx.post(
            f"{server.base_url}/api/v1/harness/sessions/{session_id}/close",
            timeout=30.0,
        )
        assert close.status_code == 200, close.text

        _signal_serve_pid_only(server, signal.SIGTERM)
        server.process.wait(timeout=30)

        _assert_no_orphan(pi_pid)
    finally:
        _hard_kill(server.process)
