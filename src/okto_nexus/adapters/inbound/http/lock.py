"""One foreground/background Server per canonical home and database.

OS-held locks survive slow heartbeats and are released by process exit. The JSON
sidecar is diagnostic/generation metadata, never authority to kill a PID. Legacy
metadata is recovered only after a same-host process is confirmed dead; a stale
timestamp or a reused/unknown PID cannot authorize takeover of an older Server.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import tempfile
import time

from ....errors import ErrorCode, OktoNexusError
from ...outbound.process_liveness import process_exited
from ...outbound.service_manager.locking import ExclusiveFileLock, LockBusy

LOCK_FILENAME = 'nexus.serve.lock'
HEARTBEAT_INTERVAL_SECONDS = 10.0
DEFAULT_STALE_AFTER_SECONDS = 60.0  # retained API compatibility; not takeover authority


class ServeLock:
    def __init__(self, home_dir: Path, *, db_path: Path | None = None,
                 stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS) -> None:
        self.home_dir = Path(home_dir).resolve()
        self.db_path = Path(db_path).resolve() if db_path is not None else self.home_dir / 'nexus.db'
        self.path = self.home_dir / LOCK_FILENAME
        self._guards: list[ExclusiveFileLock] = []
        self._owned = False
        self.generation: str | None = None

    @property
    def owned(self) -> bool:
        return self._owned and bool(self._guards)

    def _payload(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _conflict(self, reason: str) -> OktoNexusError:
        pid, age = self._holder()
        return OktoNexusError(ErrorCode.CONFIG_ERROR,
            'Another Server owns this home or database, or its ownership cannot be '
            f'safely resolved (PID {pid if pid is not None else "unknown"}). '
            'Stop the existing instance before starting another.',
            {'lock_path': str(self.path), 'holder_pid': pid,
             'heartbeat_age_seconds': age, 'reason': reason})

    def acquire(self, *, pid: int | None = None) -> None:
        if self._owned:
            raise self._conflict('already_owned')
        self.home_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        guard_paths = {self.home_dir / 'nexus.serve.guard',
                       self.db_path.with_name(self.db_path.name + '.serve.guard')}
        try:
            for path in sorted(guard_paths):
                guard = ExclusiveFileLock(path)
                try:
                    guard.acquire()
                except LockBusy:
                    raise self._conflict('os_lock_held') from None
                self._guards.append(guard)
            # Older Servers do not hold these guards: require positive legacy
            # death proof instead of interpreting a stale heartbeat as permission.
            if self.path.exists():
                previous = self._payload()
                if previous.get('lock_version') != 2:
                    if (previous.get('host') != socket.gethostname()
                            or process_exited(previous.get('pid')) is not True):
                        raise self._conflict('legacy_owner_unconfirmed')
            self.generation = secrets.token_hex(16)
            payload = {'lock_version': 2, 'pid': os.getpid() if pid is None else pid,
                       'host': socket.gethostname(), 'generation': self.generation,
                       'started_at_epoch': time.time()}
            fd, name = tempfile.mkstemp(prefix='.serve-', dir=self.home_dir)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(payload, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, self.path)
            finally:
                Path(name).unlink(missing_ok=True)
            self._owned = True
        except BaseException:
            self._release_guards()
            self.generation = None
            raise

    def heartbeat(self) -> None:
        if self._owned and self._payload().get('generation') == self.generation:
            try:
                os.utime(self.path, None)
            except OSError:
                pass  # diagnostic only; never drops OS exclusion

    def _release_guards(self) -> None:
        guards, self._guards = self._guards, []
        for guard in reversed(guards):
            guard.release()

    def release(self) -> None:
        try:
            if self._owned:
                self._owned = False
                if self._payload().get('generation') == self.generation:
                    self.path.unlink(missing_ok=True)
        finally:
            self.generation = None
            self._release_guards()

    def _holder(self) -> tuple[int | None, float | None]:
        pid = self._payload().get('pid')
        if type(pid) is not int or pid <= 0:
            pid = None
        try:
            age = max(0.0, time.time() - self.path.stat().st_mtime)
        except OSError:
            age = None
        return pid, age

    def __enter__(self) -> ServeLock:
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()
