"""Shared deterministic clock, independent of pytest conftest import order."""

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

