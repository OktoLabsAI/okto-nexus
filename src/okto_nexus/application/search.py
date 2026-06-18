"""Semantic search over message content (Frente 3, FR5).

``MessageSearchService`` embeds a free-text query and ranks messages by cosine
similarity over their stored embeddings (the ``MessageVectorStore`` port),
hydrating each hit into the contract shape (message_id, score, from_agent_id,
subject, created_at). Strictly READ-ONLY: the cosine scan runs in a deferred
WAL snapshot (``write=False``), never competing for the writer lock.

Availability is a first-class outcome (rule br_c24d5284): when semantic search
is not usable - ``embedding_mode=off``, or ``local`` requested without the
optional extra - the service raises :class:`EmbeddingsUnavailable`, which the
HTTP route maps to ``503 EMBEDDINGS_UNAVAILABLE``. Malformed parameters raise the
catalogued ``VALIDATION_ERROR`` (``422``). Pure application code: ports + stdlib
+ the error catalogue only (import boundary enforced).
"""

from __future__ import annotations

from typing import Any

from ..errors import ErrorCode, OktoNexusError
from .ports import (
    ConnectionFactory,
    EmbeddingProvider,
    MessageRepo,
    MessageVectorStore,
)

#: Default and hard-max number of results (rule br_38e80c8d): ``k`` absent ->
#: DEFAULT_K; a provided ``k`` is clamped into ``[1, MAX_K]``.
DEFAULT_K = 10
MAX_K = 50


class EmbeddingsUnavailable(Exception):
    """Semantic search is not usable in the current configuration.

    Carries the operator-facing reason; the HTTP route turns it into the
    ``503 EMBEDDINGS_UNAVAILABLE`` envelope. Intentionally NOT an
    :class:`OktoNexusError` - ``EMBEDDINGS_UNAVAILABLE`` is a transport-level
    status, not one of the frozen domain error codes.
    """


class MessageSearchService:
    """Cosine search over message embeddings (read-only)."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        provider: EmbeddingProvider | None,
        vectors: MessageVectorStore,
        messages: MessageRepo,
        search_enabled: bool,
        default_k: int = DEFAULT_K,
        max_k: int = MAX_K,
    ) -> None:
        self._cf = connection_factory
        self._provider = provider
        self._vectors = vectors
        self._messages = messages
        self._search_enabled = bool(search_enabled)
        self._default_k = int(default_k)
        self._max_k = int(max_k)

    def search(self, *, query: Any, k: Any = None) -> dict[str, Any]:
        """Embed ``query`` and return up to ``k`` cosine-ranked messages.

        Raises :class:`EmbeddingsUnavailable` when search is disabled and
        ``VALIDATION_ERROR`` when ``query`` is blank or ``k`` is non-integer.
        """
        if not self._search_enabled or self._provider is None:
            raise EmbeddingsUnavailable(
                "Semantic search requires the [embeddings] extra "
                "(sentence-transformers) and embedding_mode=stub or local."
            )
        text = query.strip() if isinstance(query, str) else ""
        if not text:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "q is required; k must be 1..50.",
                {"q": query},
            )
        resolved_k = self._resolve_k(k)

        query_vector = self._provider.encode(text)
        with self._cf.unit_of_work(write=False) as uow:
            hits = self._vectors.search(
                uow, query_vector=query_vector, k=resolved_k
            )
            message_ids = [message_id for message_id, _ in hits]
            by_id = {
                message.message_id: message
                for message in self._messages.list_by_ids(
                    uow, message_ids=message_ids
                )
            }

        items: list[dict[str, Any]] = []
        for message_id, score in hits:
            message = by_id.get(message_id)
            if message is None:
                # A vector with no message row (e.g. raced deletion): skip it
                # rather than surface a half-hydrated hit.
                continue
            items.append(
                {
                    "message_id": message.message_id,
                    "score": round(float(score), 6),
                    "from_agent_id": message.from_agent_id,
                    "subject": message.subject,
                    "created_at": message.created_at,
                }
            )
        return {"items": items, "total": len(items), "query": text, "k": resolved_k}

    def _resolve_k(self, k: Any) -> int:
        """``None`` -> default; integer (or digit-string) clamped to [1, max].

        A non-integer ``k`` is the only ``k`` rejection (``VALIDATION_ERROR``);
        an in-type out-of-range value is CLAMPED, never rejected (br_38e80c8d).
        """
        if k is None or (isinstance(k, str) and not k.strip()):
            return self._default_k
        if isinstance(k, bool) or not isinstance(k, (int, str)):
            raise self._bad_k(k)
        try:
            value = int(str(k).strip())
        except (TypeError, ValueError):
            raise self._bad_k(k) from None
        return max(1, min(self._max_k, value))

    def _bad_k(self, k: Any) -> OktoNexusError:
        return OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"k must be an integer in 1..{self._max_k}.",
            {"k": k},
        )
