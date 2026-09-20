"""Shared pytest fixtures.

These fixtures exercise the outbound SQLite adapters using only the stdlib
``sqlite3`` (via the adapters); they do NOT require the MCP SDK. Domain,
application, and SQLite tests can therefore run without ``mcp`` installed.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.config import NexusConfig


class FakeClock:
    """Deterministic :class:`Clock` implementation for tests.

    Starts at a fixed instant; :meth:`tick` advances the epoch (and is also
    reflected via :meth:`set_iso` for the ISO string when needed).
    """

    def __init__(
        self,
        # Canonical fixed-width form (utc_now_iso's shape): the lease-write
        # boundary (domain.base.iso_plus) rejects a non-lexicographically
        # comparable clock value by design.
        iso: str = "2026-06-07T00:00:00.000000Z",
        epoch: float = 1_780_000_000.0,
    ) -> None:
        self._iso = iso
        self._epoch = epoch

    def now_iso(self) -> str:
        return self._iso

    def now_epoch(self) -> float:
        return self._epoch

    def set_iso(self, iso: str) -> None:
        self._iso = iso

    def tick(self, seconds: float = 1.0) -> None:
        self._epoch += seconds


@pytest.fixture
def tmp_config(tmp_path) -> NexusConfig:
    """A :class:`NexusConfig` rooted under pytest's ``tmp_path``."""
    home = tmp_path / "okto_home"
    return NexusConfig(home_dir=home)


@pytest.fixture
def conn_factory(tmp_config: NexusConfig) -> ConnectionFactory:
    """A :class:`ConnectionFactory` over the temp config (home dir created)."""
    return ConnectionFactory(tmp_config)


@pytest.fixture
def migrated_factory(conn_factory: ConnectionFactory) -> ConnectionFactory:
    """A :class:`ConnectionFactory` whose database has all migrations applied."""
    MigrationRunner(conn_factory).apply()
    return conn_factory


@pytest.fixture
def fake_clock() -> FakeClock:
    """A deterministic clock implementing the :class:`Clock` port."""
    return FakeClock()


# --------------------------------------------------------------------- #
# Real subprocess `okto-nexus serve` fixture (Phase 1.1, S1.1)
# --------------------------------------------------------------------- #
#
# Every piece of DoD evidence for the harness-integrations work must come
# from a REAL running server bound to a REAL socket - no in-process
# TestClient. This fixture boots the actual `serve` CLI path
# (adapters.inbound.mcp.server:main -> cli.serve.run_serve -> uvicorn) as a
# child process, waits for it to answer over real HTTP, and yields a base
# URL a test can hit with any real HTTP client (httpx, requests, curl).
#
# Session-scoped: measured cold boot (embedding warm-up included) is ~2-4s,
# too slow to pay per-test. Isolation instead comes from `OKTO_NEXUS_HOME`
# pointed at a session-scoped tmp dir (pytest's `tmp_path_factory`), which
# also isolates the serve lock file (`{home}/nexus.serve.lock`) and the
# default `db_path` (`{home}/nexus.db`) - so a single boot can never see,
# let alone touch, the developer's real `~/.okto_nexus/nexus.db`.


def _free_port() -> int:
    """Bind an ephemeral port, read it, release it immediately.

    There is an inherent (tiny) TOCTOU window between releasing the socket
    here and uvicorn binding it in the child process; acceptable for tests,
    and readiness polling below still fails loudly if the race is lost.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _drain(pipe, sink: list[str]) -> None:
    """Drain a subprocess pipe on a background thread into ``sink``.

    Without this, a chatty child (uvicorn access logs, warm-up prints) can
    fill the OS pipe buffer and deadlock once nobody is reading stdout/
    stderr - a real failure mode, not a hypothetical one.
    """
    try:
        for line in iter(pipe.readline, ""):
            sink.append(line)
    except (ValueError, OSError):
        pass  # pipe closed under us during teardown


@dataclass
class RealServer:
    base_url: str
    port: int
    home_dir: Path
    process: subprocess.Popen
    stdout_lines: list[str]
    stderr_lines: list[str]

    def output(self) -> str:
        return (
            "--- stdout ---\n"
            + "".join(self.stdout_lines)
            + "\n--- stderr ---\n"
            + "".join(self.stderr_lines)
        )


@pytest.fixture(scope="session")
def real_server(tmp_path_factory):
    """Boot a real `okto-nexus serve` subprocess on an ephemeral port.

    Yields a :class:`RealServer` with a base URL already confirmed to be
    answering `GET /api/v1/info`. Isolated: `OKTO_NEXUS_HOME` (and hence the
    default `db_path` and the serve lock, both derived from it) points at a
    session-scoped tmp dir, never the developer's real `~/.okto_nexus`.
    """
    home_dir = tmp_path_factory.mktemp("okto_nexus_home")
    port = _free_port()

    env = dict(os.environ)
    env["OKTO_NEXUS_HOME"] = str(home_dir)
    env["OKTO_NEXUS_DB_PATH"] = str(home_dir / "nexus.db")
    env["OKTO_NEXUS_PORT"] = str(port)
    env["OKTO_NEXUS_HOST"] = "127.0.0.1"
    env["OKTO_NEXUS_NO_BANNER"] = "1"
    env["OKTO_NEXUS_LOG_LEVEL"] = "warning"

    # Invoke the same module the `okto-nexus` console script wraps, via
    # `sys.executable`, so the fixture works regardless of PATH/venv
    # activation state and always uses the interpreter running pytest.
    cmd = [sys.executable, "-m", "okto_nexus.adapters.inbound.mcp.server", "serve"]

    popen_kwargs: dict = dict(
        cwd=str(home_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True  # own process group, for group-kill

    process = subprocess.Popen(cmd, **popen_kwargs)

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    out_thread = threading.Thread(
        target=_drain, args=(process.stdout, stdout_lines), daemon=True
    )
    err_thread = threading.Thread(
        target=_drain, args=(process.stderr, stderr_lines), daemon=True
    )
    out_thread.start()
    err_thread.start()

    base_url = f"http://127.0.0.1:{port}"
    server = RealServer(
        base_url=base_url,
        port=port,
        home_dir=home_dir,
        process=process,
        stdout_lines=stdout_lines,
        stderr_lines=stderr_lines,
    )

    try:
        import httpx

        deadline = time.monotonic() + 30.0
        last_error: Exception | None = None
        ready = False
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(
                    "`okto-nexus serve` exited early (code "
                    f"{process.returncode}) before becoming ready.\n"
                    f"{server.output()}"
                )
            try:
                resp = httpx.get(f"{base_url}/api/v1/info", timeout=1.0)
                if resp.status_code == 200:
                    ready = True
                    break
            except httpx.HTTPError as exc:
                last_error = exc
            time.sleep(0.2)

        if not ready:
            _terminate(process)
            raise AssertionError(
                "`okto-nexus serve` did not become ready on "
                f"{base_url}/api/v1/info within 30s (last error: {last_error}).\n"
                f"{server.output()}"
            )

        yield server
    finally:
        _terminate(process)
        out_thread.join(timeout=5)
        err_thread.join(timeout=5)


def _terminate(process: subprocess.Popen) -> None:
    """SIGTERM, then SIGKILL after a grace period; reap unconditionally.

    Kills the whole process group on POSIX (the server was started with
    ``start_new_session=True``) so no child survives the test session.
    """
    if process.poll() is not None:
        return
    import signal

    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except (ProcessLookupError, OSError):
        pass

    try:
        process.wait(timeout=10)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except (ProcessLookupError, OSError):
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
