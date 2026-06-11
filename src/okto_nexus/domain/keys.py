"""Agent API key primitives (Nexus v2, spec S1).

A registered key is the primary credential on the HTTP transport (decision
D5 - Pulse policy): the connection's identity IS the agent the key was issued
to. Only the SHA256 hash of a key is ever persisted (BR7); the plaintext
exists solely in the response of the operation that generated it.

Key format: ``nxs_`` + 48 lowercase hex chars (``secrets.token_hex(24)``).

Pure module: stdlib only (``hashlib``/``secrets``), no ``sqlite3``/``mcp``
(enforced by the import boundary test).
"""

from __future__ import annotations

import hashlib
import secrets

API_KEY_PREFIX = "nxs_"
_TOKEN_BYTES = 24
_TOKEN_HEX_LEN = _TOKEN_BYTES * 2
_HEX_DIGITS = frozenset("0123456789abcdef")


def generate_api_key() -> str:
    """Return a fresh agent API key: ``nxs_`` + 48 lowercase hex chars."""
    return API_KEY_PREFIX + secrets.token_hex(_TOKEN_BYTES)


def hash_api_key(api_key: str) -> str:
    """Return the lowercase hex SHA256 of ``api_key``.

    The ONLY representation of a key that may be persisted or compared
    against storage. Hashing is total (any string hashes); well-formedness
    is a separate concern (:func:`is_well_formed_api_key`).
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest().lower()


def is_well_formed_api_key(value: str) -> bool:
    """Whether ``value`` has the shape of a key this module generates.

    A cheap pre-filter for inbound credentials (middleware can skip the
    storage lookup for garbage); NOT an authentication check.
    """
    if not isinstance(value, str) or not value.startswith(API_KEY_PREFIX):
        return False
    token = value[len(API_KEY_PREFIX) :]
    if len(token) != _TOKEN_HEX_LEN:
        return False
    return all(ch in _HEX_DIGITS for ch in token)
