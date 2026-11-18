"""Session interaction vocabulary, separate from canonical R4 turn outcomes."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from .execution.keys import SessionKey, SessionOwnerGeneration

MAX_INPUT_BYTES = 64 * 1024
MAX_SQLITE_INTEGER = 2**63 - 1
Surface = Literal["web", "nexus_cli", "native_terminal"]


def validate_input_text(text: str) -> str:
    if not text.strip():
        raise ValueError("Enter a message.")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise ValueError("The message must be valid UTF-8.") from error
    if size > MAX_INPUT_BYTES:
        raise ValueError("The message exceeds the UTF-8 byte limit.")
    return text


@dataclass(frozen=True, slots=True)
class InputScope:
    session: SessionKey
    generation: SessionOwnerGeneration
    binding_id: str
    workspace_id: str
    workspace_binding_id: str
    agent_id: str

    def __post_init__(self) -> None:
        if self.generation.value > MAX_SQLITE_INTEGER:
            raise ValueError("Session generation exceeds the stored integer range.")


@dataclass(frozen=True, slots=True)
class InputAuthor:
    """Opaque Server-issued reference to revocable interactive authority."""

    authority_ref: str
    surface: Surface


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


@dataclass(frozen=True, slots=True)
class QueuedReceipt:
    input_id: str
    sequence: int
    input_revision: int
    queue_revision: int
    status: InputDeliveryState
    operation_id: str | None
    possible_effect: bool
    steer_submitted: bool = False
    reorientation: bool = False


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
