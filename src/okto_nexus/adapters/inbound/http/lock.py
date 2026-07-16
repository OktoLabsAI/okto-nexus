"""Single-server lock for `okto-nexus serve` (spec S1, decision D4).

At most ONE serve process per nexus home: two would duplicate the reaper,
retention sweeps and SSE pollers. The lock is a file created with
``O_CREAT | O_EXCL`` containing the owner PID; liveness is the file mtime,
refreshed by the owner (heartbeat). A second serve fails closed with a
message citing the active PID; takeover is allowed only when the heartbeat
has been silent for longer than ``stale_after_seconds`` (covers a crashed
serve that never released). stdio clients never touch this lock - WAL
concurrency between stdio and serve is unaffected by design.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ....errors import ErrorCode, OktoNexusError

LOCK_FILENAME = "nexus.serve.lock"

#: Heartbeat refresh cadence expected from the owner (TR6: <=10s).
HEARTBEAT_INTERVAL_SECONDS = 10.0

#: A lock whose mtime is older than this is considered abandoned (TR6: >60s).
DEFAULT_STALE_AFTER_SECONDS = 60.0


class ServeLock:
    """Filesystem lock with PID payload and mtime heartbeat."""

    def __init__(
        self,
        home_dir: Path,
        *,
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
    ) -> None:
        self.path = Path(home_dir) / LOCK_FILENAME
        self._stale_after = float(stale_after_seconds)
        self._owned = False

    # ------------------------------------------------------------------ #
    def acquire(self, *, pid: int | None = None) -> None:
        """Take the lock or raise ``CONFIG_ERROR`` citing the active PID.

        One takeover attempt is made when the existing lock's heartbeat is
        stale (owner crashed); a FRESH lock always aborts the bootstrap
        before anything touches the database.
        """
        pid = os.getpid() if pid is None else pid
        for attempt in (1, 2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                holder_pid, age = self._holder()
                if age is not None and age > self._stale_after and attempt == 1:
                    # Abandoned lock (crashed serve): take it over, loudly.
                    try:
                        self.path.unlink()
                    except OSError:
                        pass
                    continue
                raise OktoNexusError(
                    ErrorCode.CONFIG_ERROR,
                    "Another `okto-nexus serve` is already running for this "
                    f"home (PID {holder_pid if holder_pid is not None else 'unknown'}; "
                    f"lock {self.path}). Stop it first, or pass a different "
                    "--home. stdio clients are unaffected.",
                    {
                        "lock_path": str(self.path),
                        "holder_pid": holder_pid,
                        "heartbeat_age_seconds": age,
                    },
                )
            else:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump({"pid": pid}, handle)
                self._owned = True
                return

    def heartbeat(self) -> None:
        """Refresh the liveness mtime (owner only; call every <=10s)."""
        if self._owned:
            try:
                os.utime(self.path, None)
            except OSError:  # pragma: no cover - best-effort liveness
                pass

    def release(self) -> None:
        """Remove the lock if this instance owns it (idempotent)."""
        if self._owned:
            self._owned = False
            try:
                self.path.unlink()
            except OSError:  # pragma: no cover - already gone
                pass

    # ------------------------------------------------------------------ #
    def _holder(self) -> tuple[int | None, float | None]:
        """Return ``(holder_pid, heartbeat_age_seconds)`` for the existing lock."""
        pid: int | None = None
        age: float | None = None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8") or "{}")
            raw = payload.get("pid")
            pid = int(raw) if raw is not None else None
        except (OSError, ValueError, TypeError):
            pid = None
        try:
            age = max(0.0, time.time() - self.path.stat().st_mtime)
        except OSError:
            age = None
        return pid, age

    def __enter__(self) -> "ServeLock":
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()
