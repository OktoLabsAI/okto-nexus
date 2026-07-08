"""Workspace memory slice application service (spec 8928b320, I6).

Implements the use cases this slice OWNS:

* ``memory_put``    - validate, persist ONE memory row, optionally supersede a
  previous entry (bilateral stamp in the same unit of work) and emit
  ``memory.created`` (+ ``memory.superseded``) atomically; then embed the new
  entry BEST-EFFORT in its own transaction (a failed embed never fails a put);
* ``memory_get``    - return one entry in full (superseded or not);
* ``memory_search`` - rank entries semantically when embeddings are enabled,
  degrade to a deterministic lexical match otherwise, browse by recency when
  no query is given - ALWAYS declaring the effective ``search_mode`` (BR6);
* the operator's REST reads (``browse``/``get_raw``) and physical ``delete``
  (curation, no event - BR9), which are deliberately NOT feature-gated.

The three agent-facing verbs are experimental. The MCP composition root only
registers them when ``feature_memory`` is ON at server bootstrap; the service
also keeps a LIVE guard (read from the shared NexusConfig at the start of each
use case) so already-running servers reject the primitive if the flag is later
flipped OFF. Reads are included in that guard because memory is a whole new
primitive, not a new parameter on an existing tool.

Application layer: depends only on the ports, the pure domain helpers and the
error catalogue - never ``sqlite3`` nor ``mcp`` (import-boundary test).
"""

from __future__ import annotations

from typing import Any

from ..config import TRUST_MODE_OPEN
from ..domain.base import utf8_byte_len
from ..domain.ids import resolve_realpath, resolve_workspace_id
from ..domain.memory import (
    MEMORY_CREATED_EVENT,
    MEMORY_STREAM,
    MEMORY_SUPERSEDED_EVENT,
    new_memory_id,
    normalize_memory_topics,
    validate_memory_content,
    validate_memory_provenance,
    validate_memory_title,
)
from ..domain.models import Memory
from ..domain.trace import resolve_trace, validate_trace_id
from ..errors import ErrorCode, OktoNexusError
from .identity import advance_session_presence, verify_session_credentials
from .ports import (
    AgentRepo,
    Clock,
    ConnectionFactory,
    EmbeddingProvider,
    EventEmitter,
    MemoryRepo,
    MemoryVectorStore,
    SessionRepo,
    UnitOfWork,
    WorkspaceRepo,
)

#: Search page size: default / inclusive clamp bounds (FR4).
SEARCH_K_DEFAULT = 10
SEARCH_K_MIN = 1
SEARCH_K_MAX = 50

#: Candidate pool inflation for the semantic mode: the vector ranking runs
#: over the GLOBAL embeddings table, so we over-fetch before the workspace /
#: superseded / topics filters cut the pool down to ``k`` (FR4).
SEARCH_K_FETCH_MIN = 50
SEARCH_K_FETCH_FACTOR = 4

#: ``content`` excerpt length (characters) carried by lean search items.
CONTENT_PREVIEW_CHARS = 240

#: The three declared ranking modes (BR6).
SEARCH_MODE_SEMANTIC = "semantic"
SEARCH_MODE_LEXICAL = "lexical"
SEARCH_MODE_RECENT = "recent"


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


class MemoryService:
    """Use-case orchestration for workspace memory entries."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        memories: MemoryRepo,
        workspaces: WorkspaceRepo,
        agents: AgentRepo,
        sessions: SessionRepo,
        event_emitter: EventEmitter,
        clock: Clock,
        config: Any = None,
        trust_mode: str = TRUST_MODE_OPEN,
        embedding_provider: EmbeddingProvider | None = None,
        memory_vectors: MemoryVectorStore | None = None,
        semantic_search_enabled: bool = False,
    ) -> None:
        self._cf = connection_factory
        self._memories = memories
        self._workspaces = workspaces
        self._agents = agents
        self._sessions = sessions
        self._emitter = event_emitter
        self._clock = clock
        # Live-tunable knobs (D6): read from the shared NexusConfig per call
        # when injected; the static parameter remains a direct-construction
        # fallback (the MessageService pattern).
        self._config = config
        self._static_trust_mode = str(trust_mode)
        # Embedding capability, resolved ONCE at bootstrap and injected as
        # plain values (the application never sees the adapter's resolution
        # object): provider+vectors drive best-effort generation on put;
        # ``semantic_search_enabled`` mirrors the resolution's search flag and
        # decides whether search may rank by cosine (BR6/BR10).
        self._embedding_provider = embedding_provider
        self._memory_vectors = memory_vectors
        self._semantic_enabled = bool(semantic_search_enabled)

    # ------------------------------------------------------------------ #
    # Shared gates / helpers
    # ------------------------------------------------------------------ #
    @property
    def _trust_mode(self) -> str:
        if self._config is not None:
            return str(self._config.trust_mode)
        return self._static_trust_mode

    def _feature_trace_on(self) -> bool:
        return bool(getattr(self._config, "feature_trace", False))

    def _require_feature_memory(self) -> None:
        """Fail-closed LIVE gate on the 3 agent-facing verbs (br_8af76e5d).

        The MCP composition root also hides the tools when feature_memory is
        OFF at bootstrap. This guard is the runtime fallback for an already
        registered server whose config is flipped off later. Data written while
        ON stays in the DB and becomes reachable again after re-enabling.
        """
        if not bool(getattr(self._config, "feature_memory", False)):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "Workspace memory is disabled on this server "
                "(feature_memory=false). An operator can enable the "
                "'feature_memory' setting on the dashboard.",
                {"feature_memory": False},
            )

    def _resolve_workspace(self, project_root: Any) -> tuple[str, str]:
        """Resolve ``project_root`` -> ``(workspace_id, root_realpath)``.

        Absent/blank -> ``WORKSPACE_REQUIRED``; present but irresolvable ->
        ``WORKSPACE_UNRESOLVED`` (no fallback to a default workspace).
        """
        if not _is_nonempty_str(project_root):
            raise OktoNexusError(
                ErrorCode.WORKSPACE_REQUIRED,
                "project_root is required to resolve the workspace.",
                {},
            )
        root_realpath = resolve_realpath(project_root)  # WORKSPACE_UNRESOLVED
        workspace_id = resolve_workspace_id(project_root)
        return workspace_id, root_realpath

    def _ensure_workspace(
        self, uow: UnitOfWork, workspace_id: str, root_realpath: str, now: str
    ) -> None:
        self._workspaces.upsert(
            uow,
            workspace_id=workspace_id,
            root_realpath=root_realpath,
            last_seen_at=now,
        )

    def _require_registered_agent(self, uow: UnitOfWork, agent_id: Any) -> str:
        """Authorship gate (BR1): ``agent_id`` REQUIRED and registered."""
        if not _is_nonempty_str(agent_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "agent_id is required: every memory has an author.",
                {"agent_id": agent_id},
            )
        aid = str(agent_id).strip()
        if self._agents.get(uow, aid) is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                f"Agent '{aid}' is not registered. Register it with "
                "agent_register before writing memory.",
                {"agent_id": aid},
            )
        return aid

    # ------------------------------------------------------------------ #
    # memory_put
    # ------------------------------------------------------------------ #
    def put_memory(
        self,
        *,
        project_root: Any,
        agent_id: Any,
        title: Any,
        content: Any,
        topics: Any = None,
        source_kind: Any = None,
        source_id: Any = None,
        supersedes: Any = None,
        trace_id: Any = None,
        from_session_id: Any = None,
        session_secret: Any = None,
    ) -> dict[str, Any]:
        """Persist a memory and emit ``memory.created`` atomically (FR1/FR5).

        With ``supersedes``: the target must exist in the SAME workspace
        (``NOT_FOUND {supersedes}`` otherwise - indistinguishable from a
        cross-workspace id, nothing leaks) and must still be live
        (``CONFLICT`` otherwise). The new row and the target's
        ``superseded_by`` stamp commit in ONE unit of work - WAL serialises
        writers, so two concurrent supersedes of the same target can never
        fork the chain (BR4). On ANY rejection nothing persists.

        Embedding is generated AFTER the commit, best-effort (BR10): a
        provider or vector-store failure never fails the put.
        """
        self._require_feature_memory()
        workspace_id, root_realpath = self._resolve_workspace(project_root)
        now = self._clock.now_iso()

        # Pure, write-free validation first (no row / event on rejection).
        clean_title = validate_memory_title(title)
        clean_content = validate_memory_content(content)
        clean_topics = normalize_memory_topics(topics)
        clean_kind, clean_source = validate_memory_provenance(source_kind, source_id)
        supersedes_id = (
            str(supersedes).strip() if _is_nonempty_str(supersedes) else None
        )
        feature_trace_on = self._feature_trace_on()
        if feature_trace_on and trace_id is not None:
            validate_trace_id(trace_id)

        memory_id = new_memory_id()
        with self._cf.unit_of_work() as uow:
            # Trust gate FIRST (M10, the message_create regime): a failed
            # credential check rolls everything back; a verified action also
            # advances the session heartbeat (presence tracks activity).
            verify_session_credentials(
                self._sessions,
                uow,
                trust_mode=self._trust_mode,
                tool="memory_put",
                agent_id=agent_id,
                session_id=from_session_id,
                session_secret=session_secret,
            )
            advance_session_presence(
                self._sessions, uow, session_id=from_session_id, at=now
            )
            author = self._require_registered_agent(uow, agent_id)
            self._ensure_workspace(uow, workspace_id, root_realpath, now)

            resolved_trace = resolve_trace(
                explicit=trace_id, inherited=None, feature_on=feature_trace_on
            )

            # Supersede target checks INSIDE the UoW (BR4): existence is
            # workspace-scoped; linearity rejects an already-superseded target.
            if supersedes_id is not None:
                target = self._memories.get(
                    uow, workspace_id=workspace_id, memory_id=supersedes_id
                )
                if target is None:
                    raise OktoNexusError(
                        ErrorCode.NOT_FOUND,
                        f"Memory '{supersedes_id}' does not exist in this "
                        "workspace, so it cannot be superseded.",
                        {"supersedes": supersedes_id},
                    )
                if target.superseded_by is not None:
                    raise OktoNexusError(
                        ErrorCode.CONFLICT,
                        f"Memory '{supersedes_id}' is already superseded by "
                        f"'{target.superseded_by}'. The chain is linear: "
                        "supersede the newest version instead.",
                        {
                            "supersedes": supersedes_id,
                            "superseded_by": target.superseded_by,
                        },
                    )

            memory = self._memories.create(
                uow,
                memory_id=memory_id,
                workspace_id=workspace_id,
                author_agent_id=author,
                title=clean_title,
                content=clean_content,
                topics=clean_topics,
                source_kind=clean_kind,
                source_id=clean_source,
                supersedes=supersedes_id,
                trace_id=resolved_trace,
                created_at=now,
            )

            if supersedes_id is not None:
                # Exactly-once stamp: the SQL guard (superseded_by IS NULL)
                # closes the race the read above cannot (WAL serialises
                # writers; a loser sees 0 rows and the whole put rolls back).
                stamped = self._memories.mark_superseded(
                    uow,
                    workspace_id=workspace_id,
                    memory_id=supersedes_id,
                    superseded_by=memory_id,
                )
                if stamped != 1:  # pragma: no cover - closed by the read above
                    raise OktoNexusError(
                        ErrorCode.CONFLICT,
                        f"Memory '{supersedes_id}' was superseded concurrently.",
                        {"supersedes": supersedes_id},
                    )

            self._agents.touch(uow, agent_id=author, at=now)

            # Audit events, metadata-only (BR5): NEVER title nor content.
            created_payload: dict[str, Any] = {
                "memory_id": memory_id,
                "workspace_id": workspace_id,
                "author_agent_id": author,
                "topics": clean_topics,
            }
            if supersedes_id is not None:
                created_payload["supersedes"] = supersedes_id
            if resolved_trace is not None:
                created_payload["trace_id"] = resolved_trace
            event_id = self._emitter.emit(
                uow,
                workspace_id=workspace_id,
                stream=MEMORY_STREAM,
                type=MEMORY_CREATED_EVENT,
                payload=created_payload,
                actor_agent_id=author,
                visibility="public",
            )
            if supersedes_id is not None:
                superseded_payload: dict[str, Any] = {
                    "memory_id": memory_id,
                    "superseded_memory_id": supersedes_id,
                    "workspace_id": workspace_id,
                    "author_agent_id": author,
                }
                if resolved_trace is not None:
                    superseded_payload["trace_id"] = resolved_trace
                self._emitter.emit(
                    uow,
                    workspace_id=workspace_id,
                    stream=MEMORY_STREAM,
                    type=MEMORY_SUPERSEDED_EVENT,
                    payload=superseded_payload,
                    actor_agent_id=author,
                    visibility="public",
                )

            data = self._memory_to_data(memory)
            data["event_id"] = event_id

        # Best-effort semantic index AFTER the commit (BR10 / D-EMB-4).
        self._maybe_generate_embedding(
            memory_id=memory_id,
            title=clean_title,
            content=clean_content,
            created_at=now,
        )
        return data

    def _maybe_generate_embedding(
        self, *, memory_id: str, title: str, content: str, created_at: str
    ) -> None:
        """Generate + persist the memory embedding, BEST-EFFORT (never raises).

        No-op when embedding is disabled (no provider / vector store wired).
        Encoding happens BEFORE the write transaction opens; EVERY failure is
        swallowed - the memory is already committed and lexical search covers
        rows without a vector (BR10).
        """
        provider = self._embedding_provider
        vectors = self._memory_vectors
        if provider is None or vectors is None:
            return
        try:
            vector = provider.encode(f"{title}\n{content}")
            with self._cf.unit_of_work() as uow:
                vectors.upsert(
                    uow,
                    memory_id=memory_id,
                    vector=vector,
                    model=provider.model,
                    dim=provider.dim,
                    created_at=created_at,
                )
        except Exception:  # noqa: BLE001 - best-effort: a failed embed never fails the put
            return

    # ------------------------------------------------------------------ #
    # memory_get
    # ------------------------------------------------------------------ #
    def get_memory(self, *, project_root: Any, memory_id: Any) -> dict[str, Any]:
        """Return one memory in FULL, superseded or not (FR3 / BR7).

        History is the point of supersede: a superseded entry stays readable
        by id forever (until the operator physically curates it away).
        """
        self._require_feature_memory()
        workspace_id, _ = self._resolve_workspace(project_root)
        if not _is_nonempty_str(memory_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "memory_id is required.",
                {"memory_id": memory_id},
            )
        with self._cf.unit_of_work() as uow:
            memory = self._memories.get(
                uow, workspace_id=workspace_id, memory_id=str(memory_id).strip()
            )
        if memory is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                f"Memory '{memory_id}' does not exist in this workspace.",
                {"memory_id": memory_id},
            )
        return self._memory_to_data(memory)

    # ------------------------------------------------------------------ #
    # memory_search
    # ------------------------------------------------------------------ #
    def search_memory(
        self,
        *,
        project_root: Any,
        query: Any = None,
        topics: Any = None,
        k: Any = None,
        include_superseded: Any = False,
    ) -> dict[str, Any]:
        """Rank memories and DECLARE the effective mode (FR4 / BR6).

        ``semantic`` (query + embeddings enabled): encode the query, cosine
        over an inflated candidate pool, then apply the workspace / superseded
        / topics filters POST-ranking and cut to ``k``; each item carries a
        4-decimal ``score``. ``lexical`` (query, no embeddings): substring
        match, newest first, NO score. ``recent`` (no query): newest first.
        The response always declares ``search_mode`` - the agent knows
        whether it may trust the ranking. Never fails on embedding
        unavailability (the 503 precedent of /messages/search deliberately
        does NOT apply here).
        """
        self._require_feature_memory()
        workspace_id, _ = self._resolve_workspace(project_root)
        limit = self._clamp_k(k)
        topic_filter = normalize_memory_topics(topics)
        with_superseded = bool(include_superseded)
        text = str(query).strip() if _is_nonempty_str(query) else None
        k_fetch = max(limit * SEARCH_K_FETCH_FACTOR, SEARCH_K_FETCH_MIN)

        if text is not None and self._semantic_search_ready():
            items = self._search_semantic(
                workspace_id=workspace_id,
                text=text,
                limit=limit,
                k_fetch=k_fetch,
                topic_filter=topic_filter,
                include_superseded=with_superseded,
            )
            mode = SEARCH_MODE_SEMANTIC
        elif text is not None:
            items = self._search_lexical(
                workspace_id=workspace_id,
                text=text,
                limit=limit,
                k_fetch=k_fetch,
                topic_filter=topic_filter,
                include_superseded=with_superseded,
            )
            mode = SEARCH_MODE_LEXICAL
        else:
            items = self._search_recent(
                workspace_id=workspace_id,
                limit=limit,
                k_fetch=k_fetch,
                topic_filter=topic_filter,
                include_superseded=with_superseded,
            )
            mode = SEARCH_MODE_RECENT
        return {"search_mode": mode, "count": len(items), "items": items}

    def _semantic_search_ready(self) -> bool:
        return (
            self._semantic_enabled
            and self._embedding_provider is not None
            and self._memory_vectors is not None
        )

    @staticmethod
    def _clamp_k(k: Any) -> int:
        """Resolve ``k``: absent -> 10; clamped INclusively into 1..50 (FR4)."""
        if k is None or (isinstance(k, str) and not k.strip()):
            return SEARCH_K_DEFAULT
        invalid = OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "k must be an integer.",
            {"k": k},
        )
        if isinstance(k, bool):
            raise invalid
        if isinstance(k, int):
            value = k
        elif isinstance(k, str):
            try:
                value = int(k.strip())
            except (TypeError, ValueError):
                raise invalid from None
        else:
            raise invalid
        return max(SEARCH_K_MIN, min(SEARCH_K_MAX, value))

    @staticmethod
    def _matches_topics(memory: Memory, topic_filter: list[str]) -> bool:
        """AND semantics: every requested topic must be on the memory."""
        if not topic_filter:
            return True
        have = set(memory.topics)
        return all(topic in have for topic in topic_filter)

    def _search_semantic(
        self,
        *,
        workspace_id: str,
        text: str,
        limit: int,
        k_fetch: int,
        topic_filter: list[str],
        include_superseded: bool,
    ) -> list[dict[str, Any]]:
        provider = self._embedding_provider
        vectors = self._memory_vectors
        assert provider is not None and vectors is not None  # _semantic_search_ready
        query_vector = provider.encode(text)
        with self._cf.unit_of_work() as uow:
            ranked = vectors.search(uow, query_vector=query_vector, k=k_fetch)
            rows = self._memories.get_many(
                uow,
                workspace_id=workspace_id,
                memory_ids=[memory_id for memory_id, _ in ranked],
            )
        items: list[dict[str, Any]] = []
        for memory_id, score in ranked:
            memory = rows.get(memory_id)
            if memory is None:
                continue  # other workspace: never leaks into this ranking
            if not include_superseded and memory.superseded_by is not None:
                continue
            if not self._matches_topics(memory, topic_filter):
                continue
            item = self._memory_to_item(memory)
            item["score"] = round(float(score), 4)
            items.append(item)
            if len(items) >= limit:
                break
        return items

    def _search_lexical(
        self,
        *,
        workspace_id: str,
        text: str,
        limit: int,
        k_fetch: int,
        topic_filter: list[str],
        include_superseded: bool,
    ) -> list[dict[str, Any]]:
        with self._cf.unit_of_work() as uow:
            rows = self._memories.search_lexical(
                uow,
                workspace_id=workspace_id,
                query=text,
                include_superseded=include_superseded,
                limit=k_fetch,
            )
        items = [
            self._memory_to_item(memory)
            for memory in rows
            if self._matches_topics(memory, topic_filter)
        ]
        return items[:limit]

    def _search_recent(
        self,
        *,
        workspace_id: str,
        limit: int,
        k_fetch: int,
        topic_filter: list[str],
        include_superseded: bool,
    ) -> list[dict[str, Any]]:
        with self._cf.unit_of_work() as uow:
            rows = self._memories.list(
                uow,
                workspace_id=workspace_id,
                include_superseded=include_superseded,
                limit=k_fetch,
            )
        items = [
            self._memory_to_item(memory)
            for memory in rows
            if self._matches_topics(memory, topic_filter)
        ]
        return items[:limit]

    # ------------------------------------------------------------------ #
    # Operator REST surface (NOT feature-gated: the dashboard always sees
    # the state for auditing, FR7/FR8)
    # ------------------------------------------------------------------ #
    def browse(
        self,
        *,
        workspace_id: str,
        query: Any = None,
        topic: Any = None,
        author: Any = None,
        include_superseded: Any = False,
        limit: Any = None,
        offset: Any = 0,
    ) -> dict[str, Any]:
        """Dashboard list/search over ONE workspace (GET /api/v1/memory).

        With ``query`` the ranking reuses the exact tool-mode selection (and
        declares ``search_mode``); without it this is a paginated recency
        browse. Single optional ``topic``/``author`` facets (the UI filters).
        """
        ws = str(workspace_id).strip()
        page = self._clamp_k(limit)
        with_superseded = bool(include_superseded)
        topic_token = (
            normalize_memory_topics([topic])[0] if _is_nonempty_str(topic) else None
        )
        author_id = str(author).strip() if _is_nonempty_str(author) else None
        text = str(query).strip() if _is_nonempty_str(query) else None

        if text is not None:
            topic_filter = [topic_token] if topic_token is not None else []
            if self._semantic_search_ready():
                items = self._search_semantic(
                    workspace_id=ws,
                    text=text,
                    limit=page,
                    k_fetch=max(page * SEARCH_K_FETCH_FACTOR, SEARCH_K_FETCH_MIN),
                    topic_filter=topic_filter,
                    include_superseded=with_superseded,
                )
                mode = SEARCH_MODE_SEMANTIC
            else:
                items = self._search_lexical(
                    workspace_id=ws,
                    text=text,
                    limit=page,
                    k_fetch=max(page * SEARCH_K_FETCH_FACTOR, SEARCH_K_FETCH_MIN),
                    topic_filter=topic_filter,
                    include_superseded=with_superseded,
                )
                mode = SEARCH_MODE_LEXICAL
            if author_id is not None:
                items = [i for i in items if i["author_agent_id"] == author_id]
            return {"search_mode": mode, "count": len(items), "items": items}

        try:
            start = max(0, int(offset or 0))
        except (TypeError, ValueError):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "offset must be a non-negative integer.",
                {"offset": offset},
            ) from None
        with self._cf.unit_of_work() as uow:
            rows = self._memories.list(
                uow,
                workspace_id=ws,
                include_superseded=with_superseded,
                topic=topic_token,
                author_agent_id=author_id,
                limit=page,
                offset=start,
            )
        items = [self._memory_to_item(memory) for memory in rows]
        return {"search_mode": SEARCH_MODE_RECENT, "count": len(items), "items": items}

    def get_raw(self, *, workspace_id: str, memory_id: str) -> dict[str, Any]:
        """Full detail for the dashboard (GET /api/v1/memory/{id})."""
        with self._cf.unit_of_work() as uow:
            memory = self._memories.get(
                uow, workspace_id=str(workspace_id).strip(), memory_id=memory_id
            )
        if memory is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                f"Memory '{memory_id}' does not exist in this workspace.",
                {"memory_id": memory_id},
            )
        return self._memory_to_data(memory)

    def delete_memory(self, *, workspace_id: str, memory_id: str) -> dict[str, Any]:
        """Operator curation: physically remove one entry, NO event (BR9).

        A raw port outside the protocol (the ADMIN-cancel S2 regime): the
        vector goes via ON DELETE CASCADE; dangling ``supersedes`` /
        ``superseded_by`` pointers on neighbours are tolerated by design.
        """
        ws = str(workspace_id).strip()
        with self._cf.unit_of_work() as uow:
            removed = self._memories.delete(uow, workspace_id=ws, memory_id=memory_id)
        if removed == 0:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                f"Memory '{memory_id}' does not exist in this workspace.",
                {"memory_id": memory_id},
            )
        return {"memory_id": memory_id, "deleted": True}

    # ------------------------------------------------------------------ #
    # Serialisation
    # ------------------------------------------------------------------ #
    @staticmethod
    def _memory_to_data(memory: Memory) -> dict[str, Any]:
        """FULL echo (put/get/detail): content included, conditionals non-NULL."""
        data: dict[str, Any] = {
            "memory_id": memory.memory_id,
            "workspace_id": memory.workspace_id,
            "author_agent_id": memory.author_agent_id,
            "title": memory.title,
            "content": memory.content,
            "content_bytes": utf8_byte_len(memory.content),
            "topics": list(memory.topics),
            "created_at": memory.created_at,
        }
        if memory.source_kind is not None:
            data["source_kind"] = memory.source_kind
            data["source_id"] = memory.source_id
        if memory.supersedes is not None:
            data["supersedes"] = memory.supersedes
        if memory.superseded_by is not None:
            data["superseded_by"] = memory.superseded_by
        if memory.trace_id is not None:
            data["trace_id"] = memory.trace_id
        return data

    @staticmethod
    def _memory_to_item(memory: Memory) -> dict[str, Any]:
        """LEAN search/list item: preview instead of content (FR4)."""
        item: dict[str, Any] = {
            "memory_id": memory.memory_id,
            "title": memory.title,
            "topics": list(memory.topics),
            "author_agent_id": memory.author_agent_id,
            "created_at": memory.created_at,
            "content_preview": memory.content[:CONTENT_PREVIEW_CHARS],
        }
        if memory.source_kind is not None:
            item["source_kind"] = memory.source_kind
            item["source_id"] = memory.source_id
        if memory.supersedes is not None:
            item["supersedes"] = memory.supersedes
        if memory.superseded_by is not None:
            item["superseded_by"] = memory.superseded_by
        return item
