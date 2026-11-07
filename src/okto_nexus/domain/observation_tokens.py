"""Exclusive opaque publish-token primitives for external activity telemetry.

Shape is never authentication. The application must revalidate the stored hash,
expiry, source revision, instance scope and current identity on every admission.
Only the digest belongs in storage; raw credentials are returned once. These
tokens confer no EPT, canonical key, MCP, runtime or management authority.
"""
from __future__ import annotations

import hashlib
import secrets

from ..errors import ErrorCode, OktoNexusError


OBSERVATION_TOKEN_PREFIX = "nxobs_"
_TOKEN_BYTES = 32
_HEX_DIGITS = frozenset("0123456789abcdef")


def generate_observation_token() -> str:
    """Generate 256 random bits with a dedicated, unambiguous family prefix."""
    return OBSERVATION_TOKEN_PREFIX + secrets.token_hex(_TOKEN_BYTES)


def is_well_formed_observation_token(value: object) -> bool:
    """Cheap shape routing only; no database, clock or authorization check."""
    if type(value) is not str or not value.startswith(OBSERVATION_TOKEN_PREFIX):
        return False
    token = value[len(OBSERVATION_TOKEN_PREFIX):]
    return len(token) == _TOKEN_BYTES * 2 and all(char in _HEX_DIGITS for char in token)


def hash_observation_token(token: str) -> str:
    """Return the SHA-256 hex digest of a well-formed token, never the bearer."""
    if not is_well_formed_observation_token(token):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid observation token.", {})
    return hashlib.sha256(token.encode("ascii")).hexdigest()
