"""System clock adapter implementing the :class:`Clock` port.

Pure stdlib; safe to construct during bootstrap. Tests use a deterministic
fake clock instead (see ``tests/conftest.py``).
"""

from __future__ import annotations

import time

from ...domain.base import utc_now_iso


class SystemClock:
    """Real wall-clock implementation of the :class:`Clock` port."""

    def now_iso(self) -> str:
        return utc_now_iso()

    def now_epoch(self) -> float:
        return time.time()
