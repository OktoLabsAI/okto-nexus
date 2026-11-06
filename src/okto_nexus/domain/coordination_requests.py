"""Bounded, secret-free identities for canonical coordination requests.

These are persistence primitives, not authentication or a public retry API.
Callers must authenticate the actor and check current visibility before lookup.
Hash inputs must be normalized by the canonical creation use case. In particular,
trace_id is the explicit effective value, never an automatically generated trace;
source_session_key is verified provenance, never a session secret or bearer.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from .base import iso_plus
from ..errors import ErrorCode, OktoNexusError


RETENTION_DAYS = 30
RETENTION_SECONDS = RETENTION_DAYS * 86400
OPERATIONS = frozenset({"message_create", "handoff_create"})
_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")


def conflict(reason: str) -> OktoNexusError:
    return OktoNexusError(ErrorCode.CONFLICT,
        "The coordination request cannot be replayed with this intent or state.",
        {"reason": reason})


def _identifier(name: str, value: str) -> None:
    if type(value) is not str or not 1 <= len(value) <= 160 or not value.isprintable() or value.strip() != value:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, f"Invalid {name}.", {})


@dataclass(frozen=True, slots=True)
class CoordinationRequestKey:
    server_id: str
    actor_agent_id: str
    workspace_id: str
    operation: str
    client_request_id: str

    def __post_init__(self):
        for name in ("server_id", "actor_agent_id", "workspace_id"):
            _identifier(name, getattr(self, name))
        if type(self.operation) is not str or self.operation not in OPERATIONS:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid coordination operation.", {})
        if type(self.client_request_id) is not str or not _REQUEST_ID.fullmatch(self.client_request_id):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                "client_request_id must be 1..128 ASCII letters, digits, dots, colons, underscores or hyphens, starting with a letter or digit.", {})

    def values(self) -> tuple[str, ...]:
        return (self.server_id, self.actor_agent_id, self.workspace_id,
                self.operation, self.client_request_id)


def validate_hash(value: str) -> None:
    if type(value) is not str or not _HASH.fullmatch(value):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid coordination request hash.", {})


def _hash(operation: str, values: dict) -> str:
    # Refuse non-JSON data, non-string mapping keys, NaN and infinity instead
    # of hashing str(object), unstable reprs, or lossy key conversions.
    def check(value):
        if type(value) is dict:
            if any(type(key) is not str for key in value):
                raise ValueError("Non-string JSON key")
            for item in value.values():
                check(item)
        elif type(value) is list:
            for item in value:
                check(item)
        elif value is not None and type(value) not in (str, int, float, bool):
            raise ValueError("Non-JSON value")
    try:
        check(values)
        encoded = json.dumps({"revision": 1, "operation": operation, "semantics": values},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
            "Coordination request semantics must be valid JSON.", {}) from exc
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def message_request_hash(*, subject, body, target, channel_id=None, artifacts=None,
                         parent_message_id=None, trace_id=None, session_id=None,
                         source_session_key="", no_reply=False) -> str:
    """Explicit allowlist: authentication credentials cannot be arguments."""
    return _hash("message_create", dict(subject=subject, body=body, target=target,
        channel_id=channel_id, artifacts=artifacts, parent_message_id=parent_message_id,
        trace_id=trace_id, session_id=session_id, source_session_key=source_session_key,
        no_reply=no_reply))


def handoff_request_hash(*, target, visibility, payload=None, trace_id=None,
                         acceptance_criteria=None, verify_by=None, depends_on=None,
                         session_id=None, source_session_key="") -> str:
    return _hash("handoff_create", dict(target=target, visibility=visibility,
        payload=payload, trace_id=trace_id, acceptance_criteria=acceptance_criteria,
        verify_by=verify_by, depends_on=depends_on, session_id=session_id,
        source_session_key=source_session_key))


@dataclass(frozen=True, slots=True)
class CoordinationReceipt:
    key: CoordinationRequestKey
    request_hash: str
    state: str
    resource_id: str | None
    approval_id: str | None
    created_at: str
    expires_at: str

    def require_replay(self, *, request_hash: str, now: str) -> None:
        validate_hash(request_hash)
        iso_plus(now, 0)  # canonical UTC comparison, not arbitrary ISO strings
        if self.request_hash != request_hash:
            raise conflict("CLIENT_REQUEST_CONTENT_CONFLICT")
        if now < self.created_at or now >= self.expires_at:
            raise conflict("CLIENT_REQUEST_WINDOW_EXPIRED")

    def reference(self) -> dict:
        """References only. This is neither current resource status nor a grant."""
        return dict(server_id=self.key.server_id, actor_agent_id=self.key.actor_agent_id,
            workspace_id=self.key.workspace_id, operation=self.key.operation,
            client_request_id=self.key.client_request_id, state=self.state,
            resource_id=self.resource_id, approval_id=self.approval_id,
            created_at=self.created_at, expires_at=self.expires_at)
