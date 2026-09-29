"""Complete immutable keys for R4 execution state.

Short IDs are inputs to an explicit resolver at the human boundary. Internal
mutation and deletion use these tuple-shaped keys, never a concatenated ID.
"""

from __future__ import annotations

from dataclasses import dataclass, fields


def _id(value: str, name: str) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= 160:
        raise ValueError(f"{name} must be a 1-160 character string")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError(f"{name} contains an unpaired surrogate")


def _validate_ids(instance: object) -> None:
    for field in fields(instance):
        value = getattr(instance, field.name)
        if field.name != "session_owner_generation":
            _id(value, field.name)


@dataclass(frozen=True, slots=True)
class SessionOwnerGeneration:
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int or self.value < 1:
            raise ValueError("session owner generation must be a positive integer")


@dataclass(frozen=True, slots=True)
class ExecutorKey:
    server_id: str
    executor_id: str

    def __post_init__(self) -> None:
        _validate_ids(self)


@dataclass(frozen=True, slots=True)
class BindingKey:
    server_id: str
    executor_id: str
    binding_id: str

    def __post_init__(self) -> None:
        _validate_ids(self)


@dataclass(frozen=True, slots=True)
class SessionKey:
    server_id: str
    executor_id: str
    session_id: str

    def __post_init__(self) -> None:
        _validate_ids(self)


@dataclass(frozen=True, slots=True)
class StreamKey:
    server_id: str
    executor_id: str
    session_id: str
    stream_epoch: str

    def __post_init__(self) -> None:
        _validate_ids(self)


@dataclass(frozen=True, slots=True)
class ApprovalKey:
    server_id: str
    executor_id: str
    binding_id: str
    agent_id: str
    workspace_id: str
    session_id: str
    session_owner_generation: SessionOwnerGeneration
    canonical_request_id: str
    kind: str

    def __post_init__(self) -> None:
        _validate_ids(self)
        if not isinstance(self.session_owner_generation, SessionOwnerGeneration):
            raise TypeError("session_owner_generation must be typed")
