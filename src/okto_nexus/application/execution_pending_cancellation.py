"""Cancellation before the canonical send fence, shared by recovery policies."""
from typing import Protocol


class PendingExecutionCancellation(Protocol):
    def cancel(self, uow, operation_id, *, code='OPERATOR_CANCELLED', preserve_started_openings=False): ...
