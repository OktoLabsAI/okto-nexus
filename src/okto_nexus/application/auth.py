"""Agent key authentication service (Nexus v2, spec S1 / C2).

``AgentKeyAuthService`` is the single authority that turns an inbound API key
into an agent identity on the HTTP transport (decision D5 - Pulse policy),
and the issuing/revocation primitive used by the management REST surface and
by `okto-nexus admin issue-keys`.

Design notes
------------
* Pure application code: depends only on ports (``AgentRepo``, ``Clock``) and
  the key primitives in :mod:`okto_nexus.domain.keys`. No I/O imports here
  (enforced by the import boundary test). This service IS the local adapter
  of the ``AuthProvider`` seam; a SaaS deployment swaps it for an IdP-backed
  implementation without touching callers (decision D6).
* Resolution caches positive hits per key hash with a short TTL so the hot
  per-request lookup does not hit storage every time. Invalidation is
  SYNCHRONOUS on regenerate/revoke (BR: the previous key must stop
  authenticating immediately) and negative results are never cached (a key
  issued by a concurrent process must work at once).
* The failure mode is uniform: unknown key, malformed key and revoked agent
  all resolve to ``None`` - callers translate that into one 401 (AC2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..domain.keys import generate_api_key, hash_api_key, is_well_formed_api_key
from ..domain.models import Agent
from ..errors import ErrorCode, OktoNexusError
from .ports import AgentRepo, Clock, UnitOfWork

# Positive-hit cache TTL. Mirrors the Pulse dashboard's 60s agent cache: long
# enough to amortise the per-request lookup, short enough that a revocation
# missed by an invalidation race (multi-process serve is excluded by the
# single-server lock, D4) still converges within a minute.
DEFAULT_CACHE_TTL_SECONDS = 60.0


@dataclass(slots=True)
class _CacheEntry:
    agent: Agent
    expires_epoch: float


class AgentKeyAuthService:
    """Issue, resolve and revoke per-agent API keys (local AuthProvider)."""

    def __init__(
        self,
        agents: AgentRepo,
        clock: Clock,
        *,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self._agents = agents
        self._clock = clock
        self._ttl = float(cache_ttl_seconds)
        self._by_hash: dict[str, _CacheEntry] = {}
        self._hash_by_agent: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Issuing / rotation / revocation
    # ------------------------------------------------------------------ #
    def issue_key(self, uow: UnitOfWork, *, agent_id: str) -> str:
        """Issue (or rotate) the agent's key; return the plaintext ONCE.

        Replacing the stored hash is the rotation primitive: the previous
        key stops resolving within this transaction, and the cache entry is
        dropped synchronously (BR: immediate invalidation). The plaintext is
        returned to the caller and never persisted or logged (BR7).

        Raises ``NOT_FOUND`` when the agent does not exist - issuing must
        never invent identities (registration is a separate, deliberate act).
        """
        api_key = generate_api_key()
        updated = self._agents.set_key_hash(
            uow, agent_id=agent_id, api_key_hash=hash_api_key(api_key)
        )
        if not updated:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "agent_id does not exist; register the agent before issuing a key.",
                {"agent_id": agent_id},
            )
        self.invalidate_agent(agent_id)
        return api_key

    def set_active(
        self, uow: UnitOfWork, *, agent_id: str, is_active: bool
    ) -> bool:
        """Flip the revocation switch, dropping any cached resolution.

        Returns ``True`` if the agent existed. Deactivation makes the
        agent's key stop authenticating immediately (cache invalidated in
        the same call, before the caller's transaction even commits).
        """
        updated = self._agents.set_active(uow, agent_id=agent_id, is_active=is_active)
        if updated:
            self.invalidate_agent(agent_id)
        return updated

    # ------------------------------------------------------------------ #
    # Resolution (the per-request hot path)
    # ------------------------------------------------------------------ #
    def resolve(self, uow: UnitOfWork, api_key: str | None) -> Optional[Agent]:
        """Resolve an inbound key to its ACTIVE agent, or ``None``.

        Uniform failure: ``None`` covers missing, malformed and unknown keys
        as well as revoked agents - the transport layer maps all of them to
        one 401 with no side effects (AC2). On success the agent's
        ``last_seen_at`` is stamped (the only write on the read path,
        br_5865bb88).
        """
        if not api_key or not is_well_formed_api_key(api_key):
            return None
        key_hash = hash_api_key(api_key)

        cached = self._by_hash.get(key_hash)
        if cached is not None and cached.expires_epoch > self._clock.now_epoch():
            self._agents.touch(uow, agent_id=cached.agent.agent_id)
            return cached.agent

        agent = self._agents.get_active_by_key_hash(uow, api_key_hash=key_hash)
        if agent is None:
            # Negative results are deliberately NOT cached: a key issued by
            # a parallel writer must start working immediately.
            self._evict_hash(key_hash)
            return None

        self._by_hash[key_hash] = _CacheEntry(
            agent=agent, expires_epoch=self._clock.now_epoch() + self._ttl
        )
        self._hash_by_agent[agent.agent_id] = key_hash
        self._agents.touch(uow, agent_id=agent.agent_id)
        return agent

    # ------------------------------------------------------------------ #
    # Cache management
    # ------------------------------------------------------------------ #
    def invalidate_agent(self, agent_id: str) -> None:
        """Drop the cached resolution for an agent (rotation/revocation)."""
        key_hash = self._hash_by_agent.pop(agent_id, None)
        if key_hash is not None:
            self._by_hash.pop(key_hash, None)

    def invalidate_all(self) -> None:
        """Drop every cached resolution at once (admin store reset)."""
        self._by_hash.clear()
        self._hash_by_agent.clear()

    def _evict_hash(self, key_hash: str) -> None:
        entry = self._by_hash.pop(key_hash, None)
        if entry is not None:
            self._hash_by_agent.pop(entry.agent.agent_id, None)
