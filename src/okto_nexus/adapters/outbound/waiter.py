"""Sleep-poll implementation of the :class:`Waiter` port (V1).

This is the OUTBOUND adapter behind ``event_wait`` / ``handoff_list_available``
blocking. The application layer only talks to the
:class:`okto_nexus.application.ports.Waiter` protocol; this module supplies the
V1 strategy:

* sleep in increments of the configured poll interval (the same cadence the
  pre-M5 in-service loops used), and
* between sleeps, probe a CHEAP store-change counter (SQLite's
  ``PRAGMA data_version`` via ``ConnectionFactory.data_version``) instead of
  re-running the caller's SELECT scan. The caller re-scans ONLY when the
  counter moved, i.e. when some connection in some process committed a write.

Failure posture is fail-open towards delivery: when the probe degrades (the
cached probe connection cannot answer), the waiter reports a change after one
poll interval - the caller's regular read path then re-scans and surfaces the
real, actionable ``DB_ERROR`` if the store is truly down. A broken probe can
therefore never silently absorb a write or park a caller past its timeout.

A future SSE/notify transport replaces this class with a subscription-backed
``Waiter`` (block on a notification instead of sleeping) - same port, no
change to the application layer.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from ...errors import OktoNexusError


class SleepPollWaiter:
    """Incremental-sleep :class:`Waiter` gated by a store-version probe.

    Parameters
    ----------
    version_probe:
        Zero-argument callable returning the store's current change counter
        (``ConnectionFactory.data_version``). Two equal values mean "no commit
        happened in between"; raising ``OktoNexusError`` marks the probe as
        degraded for that check (treated as a change after one poll interval).
    poll_interval_s:
        Sleep increment between probes, in seconds (floored at 1ms so a
        misconfigured zero interval can never busy-spin).
    sleep / monotonic:
        Injectable for deterministic tests; real ``time.sleep`` /
        ``time.monotonic`` in production.
    """

    def __init__(
        self,
        version_probe: Callable[[], int],
        poll_interval_s: float,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._probe = version_probe
        self._poll_interval_s = max(float(poll_interval_s), 0.001)
        self._sleep = sleep
        self._monotonic = monotonic

    # ------------------------------------------------------------------ #
    # Waiter port
    # ------------------------------------------------------------------ #
    def monotonic(self) -> float:
        return self._monotonic()

    def snapshot(self) -> Any:
        """Current change token; ``None`` when the probe is degraded.

        A ``None`` token downgrades the NEXT waits to the pre-M5 behaviour
        (report a change every poll interval) instead of failing the read.
        """
        try:
            return self._probe()
        except OktoNexusError:
            return None

    def wait_for_change(self, since: Any, timeout_s: float) -> bool:
        """Sleep-poll up to ``timeout_s``; ``True`` iff the counter moved.

        Probes BEFORE the first sleep, so a write that landed between the
        caller's ``snapshot`` + scan and this call wakes it immediately (zero
        sleeps). ``False`` is returned only after the full timeout elapsed
        with the counter unchanged - the caller may then time out without
        re-scanning.
        """
        timeout_s = max(0.0, float(timeout_s))
        if since is not None and self._changed(since):
            return True
        deadline = self._monotonic() + timeout_s
        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                return False
            self._sleep(min(self._poll_interval_s, remaining))
            if since is None or self._changed(since):
                return True

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _changed(self, since: Any) -> bool:
        """Whether the counter moved since ``since`` (degraded probe = moved)."""
        try:
            return self._probe() != since
        except OktoNexusError:
            # Fail open: force a re-scan so the caller's read path surfaces
            # the real error (or succeeds, if only the probe is broken).
            return True
