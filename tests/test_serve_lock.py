"""Single-server lock (spec S1, C3 / D4 / TS7-adjacent unit coverage)."""

from __future__ import annotations

import json
import os
import time

import pytest

from okto_nexus.adapters.inbound.http.lock import ServeLock
from okto_nexus.errors import ErrorCode, OktoNexusError


def test_acquire_writes_pid_and_release_removes(tmp_path):
    lock = ServeLock(tmp_path)
    lock.acquire(pid=4242)
    payload = json.loads(lock.path.read_text(encoding="utf-8"))
    assert payload["pid"] == 4242
    lock.release()
    assert not lock.path.exists()
    lock.release()  # idempotent


def test_second_acquire_fails_citing_active_pid(tmp_path):
    first = ServeLock(tmp_path)
    first.acquire(pid=1111)
    second = ServeLock(tmp_path)
    with pytest.raises(OktoNexusError) as excinfo:
        second.acquire(pid=2222)
    assert excinfo.value.code == ErrorCode.CONFIG_ERROR
    assert "1111" in excinfo.value.message  # PID is surfaced to the operator
    assert first.path.exists()  # loser never clobbers a fresh lock
    first.release()


def test_stale_lock_is_taken_over(tmp_path):
    abandoned = ServeLock(tmp_path)
    abandoned.acquire(pid=9999)
    # Simulate a crashed serve: heartbeat silent for far longer than the
    # staleness budget (mtime pushed into the past; no release).
    old = time.time() - 3600
    os.utime(abandoned.path, (old, old))

    successor = ServeLock(tmp_path)
    successor.acquire(pid=1234)  # must NOT raise
    payload = json.loads(successor.path.read_text(encoding="utf-8"))
    assert payload["pid"] == 1234
    successor.release()


def test_heartbeat_refreshes_mtime(tmp_path):
    lock = ServeLock(tmp_path)
    lock.acquire()
    old = time.time() - 120
    os.utime(lock.path, (old, old))
    lock.heartbeat()
    assert time.time() - lock.path.stat().st_mtime < 5
    lock.release()


def test_context_manager_releases_on_exit(tmp_path):
    with ServeLock(tmp_path) as lock:
        assert lock.path.exists()
    assert not lock.path.exists()
