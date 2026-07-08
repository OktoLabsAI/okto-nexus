"""MCP inbound tools for the workspace memory slice (spec 8928b320, I6).

Registers the three tools this slice owns, each returning the canonical
envelope via :func:`tool_envelope` so no exception ever crosses the adapter
boundary:

* ``memory_put``    - persist a durable memory entry (optionally superseding a
  previous one, bilaterally, in the same unit of work) and emit the
  metadata-only ``memory.created`` (+ ``memory.superseded``) events.
* ``memory_get``    - one entry in FULL by id, superseded included (history).
* ``memory_search`` - ranked retrieval that ALWAYS declares the effective
  ``search_mode`` (semantic when embeddings are enabled, else lexical; recent
  when no query is given).

The module itself is experimental: the MCP composition root registers it only
when ``feature_memory`` is ON at server bootstrap. The service still keeps a
LIVE guard (flag OFF -> VALIDATION_ERROR ``{feature_memory: false}``) for
already-running servers where the flag is flipped after registration. The
operator's REST reads/curation are NOT gated and live in the HTTP adapter.

This module is the slice's composition root: it wires the concrete SQLite
memory repo + vector store into ``deps.repos`` (reused if already present),
reuses the peer-owned workspace/agent/session repos and the shared Event Log
emitter, and injects the embedding capability resolved ONCE at bootstrap
(``deps.embedding``) as plain values. It does NOT import the MCP SDK; the live
FastMCP server is passed into :func:`register`, matching the
``register(server, deps)`` contract.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from okto_nexus.adapters.outbound.sqlite.events_repo import (
    SqliteEventEmitter,
    SqliteEventRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteSessionRepo,
    SqliteWorkspaceRepo,
)
from okto_nexus.adapters.outbound.sqlite.memory_repo import (
    SqliteMemoryRepo,
    SqliteMemoryVectorStore,
)
from okto_nexus.application.memory import MemoryService
from okto_nexus.envelope import tool_envelope

#: Reused parameter descriptions (kept DRY across the memory tools).
#: House style (mirrors okto-pulse): enums as "one of: a, b, c (default: x)";
#: optionals marked "(optional)"/"(default: ...)"; cross-refs to sibling tools.
_P_ROOT = (
    "Absolute path to the project; the server derives workspace_id = sha256(realpath)."
)
_P_AGENT = "Your agent_id (the author). REQUIRED - every memory has an author; must be registered (agent_register)."
_P_TITLE = "Short human-readable title (1..200 chars). REQUIRED."
_P_CONTENT = "The memory content (1..16384 UTF-8 BYTES). REQUIRED. Larger payloads: store an artifact (artifact_put) and keep content a short pointer."
_P_TOPICS = "Up to 10 topic labels for retrieval (optional; each <=50 chars, trimmed + lowercased, duplicates dropped silently; >10 DISTINCT topics rejected)."
_P_SOURCE_KIND = "Provenance kind - one of: event, message, handoff (optional; atomic PAIR with source_id: both or neither)."
_P_SOURCE_ID = "Id of the provenance record (1..128 chars; format-only, existence NOT checked). Atomic pair with source_kind."
_P_SUPERSEDES = "memory_id this entry replaces (optional). Target must exist in this workspace and still be live - the chain is LINEAR, supersede the newest version (else CONFLICT names the current successor)."
_P_TRACE = (
    "Trajectory trace_id to stamp on this memory (optional; non-empty string, "
    "max 128 chars). Needs the feature_trace flag ON, else accepted and ignored."
)
_P_FROM_SESSION = "Your session_id from session_open (optional in trust_mode=open; REQUIRED with session_secret in trust_mode=strict)."
_P_SESSION_SECRET = "session_secret from session_open for from_session_id (optional in open mode but VALIDATED if supplied; REQUIRED in strict mode)."
_P_MEMORY_ID = "The memory_id to fetch. REQUIRED. Superseded entries stay readable by id (that is the point of supersede: history)."
_P_QUERY = "Free-text query (optional). Ranks semantically when embeddings are on (items carry score), else lexical title/content/topics match; OMITTED = newest-first browse. The response declares search_mode."
_P_TOPIC_FILTER = "Topic filter, AND-combined - every listed topic must be on the entry (optional; same normalization as memory_put topics)."
_P_K = "Max results (default: 10; clamped into 1..50)."
_P_INCLUDE_SUPERSEDED = (
    "true to include superseded entries (default: false = live entries only)."
)


def build_service(deps: Any) -> MemoryService:
    """Wire the SQLite repos/emitter into ``deps`` and build the service.

    Idempotent: any repo / emitter already present is reused so this slice and
    its peers share a single concrete instance and a single event append path.
    The embedding capability resolved at bootstrap (``deps.embedding``) is
    unpacked into plain values - the application never sees the resolution
    object (provider drives best-effort generation on put; ``search_enabled``
    decides whether search may rank by cosine, BR6/BR10).
    """
    repos = deps.repos

    if getattr(repos, "memories", None) is None:
        repos.memories = SqliteMemoryRepo(deps.clock)
    if getattr(repos, "memory_vectors", None) is None:
        repos.memory_vectors = SqliteMemoryVectorStore(deps.clock)
    if getattr(repos, "workspaces", None) is None:
        repos.workspaces = SqliteWorkspaceRepo(deps.clock)
    if getattr(repos, "agents", None) is None:
        repos.agents = SqliteAgentRepo(deps.clock)
    if getattr(repos, "sessions", None) is None:
        repos.sessions = SqliteSessionRepo(deps.clock)
    if getattr(deps, "event_emitter", None) is None:
        if getattr(repos, "events", None) is None:
            repos.events = SqliteEventRepo(deps.clock)
        deps.event_emitter = SqliteEventEmitter(repos.events)

    embedding = getattr(deps, "embedding", None)
    return MemoryService(
        connection_factory=deps.connection_factory,
        memories=repos.memories,
        workspaces=repos.workspaces,
        agents=repos.agents,
        sessions=repos.sessions,
        event_emitter=deps.event_emitter,
        clock=deps.clock,
        config=deps.config,
        embedding_provider=embedding.provider if embedding is not None else None,
        memory_vectors=repos.memory_vectors,
        semantic_search_enabled=bool(
            embedding is not None and embedding.search_enabled
        ),
    )


def register(server: Any, deps: Any) -> None:
    """Register the memory tools on ``server`` (FastMCP ``@server.tool()``)."""
    service = build_service(deps)

    @server.tool()
    @tool_envelope
    def memory_put(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        agent_id: Annotated[str, Field(description=_P_AGENT)],
        title: Annotated[str, Field(description=_P_TITLE)],
        content: Annotated[str, Field(description=_P_CONTENT)],
        topics: Annotated[list[str] | None, Field(description=_P_TOPICS)] = None,
        source_kind: Annotated[str | None, Field(description=_P_SOURCE_KIND)] = None,
        source_id: Annotated[str | None, Field(description=_P_SOURCE_ID)] = None,
        supersedes: Annotated[str | None, Field(description=_P_SUPERSEDES)] = None,
        trace_id: Annotated[str | None, Field(description=_P_TRACE)] = None,
        from_session_id: Annotated[
            str | None, Field(description=_P_FROM_SESSION)
        ] = None,
        session_secret: Annotated[
            str | None, Field(description=_P_SESSION_SECRET)
        ] = None,
    ) -> dict[str, Any]:
        """Persist a durable workspace memory (optionally superseding one); emits memory.created. Requires the feature_memory flag ON."""
        return service.put_memory(
            project_root=project_root,
            agent_id=agent_id,
            title=title,
            content=content,
            topics=topics,
            source_kind=source_kind,
            source_id=source_id,
            supersedes=supersedes,
            trace_id=trace_id,
            from_session_id=from_session_id,
            session_secret=session_secret,
        )

    @server.tool()
    @tool_envelope
    def memory_get(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        memory_id: Annotated[str, Field(description=_P_MEMORY_ID)],
    ) -> dict[str, Any]:
        """Fetch one workspace memory in FULL by id (superseded entries included). Requires the feature_memory flag ON."""
        return service.get_memory(project_root=project_root, memory_id=memory_id)

    @server.tool()
    @tool_envelope
    def memory_search(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        query: Annotated[str | None, Field(description=_P_QUERY)] = None,
        topics: Annotated[list[str] | None, Field(description=_P_TOPIC_FILTER)] = None,
        k: Annotated[int | None, Field(description=_P_K)] = None,
        include_superseded: Annotated[
            bool, Field(description=_P_INCLUDE_SUPERSEDED)
        ] = False,
    ) -> dict[str, Any]:
        """Search workspace memories; the response DECLARES the effective search_mode (semantic|lexical|recent). Requires feature_memory ON."""
        return service.search_memory(
            project_root=project_root,
            query=query,
            topics=topics,
            k=k,
            include_superseded=include_superseded,
        )
