"""Bounded retirement of structurally proved, unsent competitive notices."""
from typing import Protocol


class HandoffNoticeRetirement(Protocol):
    def retire_page(self, uow, *, now, limit) -> int: ...
