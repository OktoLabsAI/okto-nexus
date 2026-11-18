"""Session interaction vocabulary, separate from canonical R4 turn outcomes."""

from enum import StrEnum


class InputDeliveryState(StrEnum):
    QUEUED = "QUEUED"
    DISPATCHING = "DISPATCHING"
    ACCEPTED_NATIVE = "ACCEPTED_NATIVE"
    REFUSED_BEFORE_SEND = "REFUSED_BEFORE_SEND"
    DELIVERY_UNKNOWN = "DELIVERY_UNKNOWN"
    BLOCKED_AUTH = "BLOCKED_AUTH"
    BLOCKED_SESSION = "BLOCKED_SESSION"
    PAUSED = "PAUSED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


# Ordinary dispatch, not explicit recovery or reconciliation of a receipt.
# The DB must still check the fence and revision in the selecting transaction.
def may_dispatch(state: InputDeliveryState) -> bool:
    return state is InputDeliveryState.QUEUED


def may_cancel(state: InputDeliveryState) -> bool:
    """Cancellation is limited to entries held before the dispatch boundary."""
    return state in {InputDeliveryState.QUEUED, InputDeliveryState.PAUSED}


def may_promote(state: InputDeliveryState) -> bool:
    """A queued entry can move to an exact steer operation, never both paths."""
    return state is InputDeliveryState.QUEUED
