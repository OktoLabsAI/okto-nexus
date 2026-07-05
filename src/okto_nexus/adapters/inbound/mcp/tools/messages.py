"""MCP inbound tools for the Channels & Messages slice.

Registers the tools this slice owns exclusively, each returning the canonical
envelope via :func:`tool_envelope` so no exception ever crosses the adapter
boundary:

* ``message_create`` - persist a message, resolve recipients, fan out one inbox
  delivery per recipient, and emit ``message.created`` - all atomically.
* ``channel_create`` - create a channel by name (idempotent).
* ``channel_list``   - the workspace channels (``general`` seeded by default).

Reading messages is the INBOX slice's job (``inbox_pull`` / ``inbox_peek`` /
``inbox_count`` / ``inbox_history`` in ``tools/inbox.py``), per ADR 0001.

It also registers the S3 clean-break MIGRATION SHIMS ``message_get`` /
``message_list`` / ``message_wait``: clients pinned to the pre-S3 surface get a
prescriptive ``{ok:false, error:{code:"MIGRATED"}}`` envelope naming the exact
replacement tool and parameters, instead of an opaque "Unknown tool" failure.

This module is the slice's composition root: it wires the concrete SQLite
:class:`SqliteChannelRepo` / :class:`SqliteMessageRepo` into ``deps.repos`` and
reuses (or lazily wires) the peer-owned workspace/agent repos and the Event Log
``EventEmitter`` so ``message.created`` flows through the same append path. It
does NOT import the MCP SDK; the live FastMCP server is passed into
:func:`register`, matching the ``register(server, deps)`` contract.
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
from okto_nexus.adapters.outbound.sqlite.embeddings_repo import (
    SqliteMessageVectorStore,
)
from okto_nexus.adapters.outbound.sqlite.capability_catalog_repo import (
    SqliteCapabilityCatalogRepo,
)
from okto_nexus.adapters.outbound.sqlite.tag_catalog_repo import (
    SqliteTagCatalogRepo,
)
from okto_nexus.adapters.outbound.sqlite.approvals_repo import (
    SqliteApprovalRepo,
)
from okto_nexus.adapters.outbound.sqlite.governance_repo import (
    SqliteGovernanceRepo,
)
from okto_nexus.adapters.outbound.sqlite.policy_repo import (
    SqliteAgentPolicyBindingRepo,
    SqlitePolicyRepo,
)
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteChannelRepo,
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from okto_nexus.application.approvals import ApprovalService
from okto_nexus.application.governance import GovernanceService
from okto_nexus.application.messages import MessageService
from okto_nexus.domain.governance import ACTION_BROADCAST, ACTION_MESSAGE_CREATE
from okto_nexus.envelope import err, require_json_object_param, tool_envelope
from okto_nexus.errors import ErrorCode

from ...http.identity_ctx import get_authenticated_agent

#: Error code emitted by the S3 migration shims. ``ErrorCode.MIGRATED`` is the
#: canonical catalogue entry; the literal fallback keeps this module importable
#: against an errors.py that has not landed the new code yet.
_migrated_member = getattr(ErrorCode, "MIGRATED", None)
_MIGRATED_CODE: str = (
    _migrated_member.value if _migrated_member is not None else "MIGRATED"
)

#: Reused parameter descriptions (kept DRY across the message/channel tools).
#: House style (mirrors okto-pulse): enums as "one of: a, b, c (default: x)";
#: optionals marked "(optional)"/"(default: ...)"; cross-refs to sibling tools.
_P_ROOT = (
    "Absolute path to the project; the server derives workspace_id = sha256(realpath)."
)
_P_FROM_AGENT = "Your agent_id (the sender); recorded as the author - recipients reply by targeting it."
_P_SUBJECT = "Short message subject/title (one line)."
_P_BODY = "Message body (inline text). For large content, attach an artifact and keep body a short pointer."
_P_CHANNEL = "Channel_id to post into (optional; omit = no channel). Organizational label only; does NOT decide recipients (the target does)."
_P_CHANNEL_NAME = "Channel name (REQUIRED; short topic label, max 64 chars, unique per workspace). Idempotent by name (existing -> created=false)."
_P_FROM_SESSION = "Your session_id from session_open (optional in trust_mode=open; REQUIRED with session_secret in trust_mode=strict)."
_P_SESSION_SECRET = "session_secret from session_open for from_session_id (optional in open mode but VALIDATED if supplied; REQUIRED in strict mode)."
#: Compact routing-target cheat-sheet: every strategy SHAPE stays inline (so a
#: harness without resources can still target correctly - S7), while the rules,
#: examples and edge cases live in okto-nexus://reference/target-grammar (shared
#: with handoff_create, eliminating the old duplication).
_P_TARGET_MSG = (
    "Routing target as a raw JSON object (optional; omit = broadcast to present "
    'agents). strategy one of: direct {"strategy":"direct","agent_id":"<id>"}; '
    'capability {"strategy":"capability","capability":"<cap>"}; role '
    '{"strategy":"role","role":"<role>"}; tag {"strategy":"tag","selector":'
    '{"<key>":["<value>",...]}} (flat: AND across keys, OR within values) or '
    'rich selector [{"key":"<k>","operator":"In|NotIn|Exists|DoesNotExist",'
    '"values":["<v>",...]}] (expressions ANDed; Exists/DoesNotExist take NO '
    "values; CAUTION: NotIn/DoesNotExist also match agents MISSING the key - "
    'compose with Exists to require it; values with "/" match by path segment, '
    "ENG covers ENG/BACKEND not ENGX; selector tags must be registered in the "
    'operator-managed tag catalog); broadcast {"strategy":"broadcast"}; '
    'mixed {"strategy":"mixed","rules":[<sub-target>,...]}. Rules/examples/'
    "edge-cases: read resource okto-nexus://reference/target-grammar."
)
_P_ARTIFACTS = "List of artifact_id strings to attach (optional; reference large content instead of inlining it in body)."
_P_PARENT = "Message_id this is a reply to, to thread the conversation (optional)."
_P_TRACE = (
    "Trajectory trace_id to stamp on this message (optional; non-empty string, "
    "max 128 chars). Needs the feature_trace flag ON, else accepted and ignored; "
    "omitted = inherit the reply parent's trace, or generate one."
)


def build_service(deps: Any) -> MessageService:
    """Wire the SQLite repos/emitter into ``deps`` and build the service.

    Idempotent: any repo / emitter already present is reused so this slice and
    its peers share a single concrete instance and a single event append path.
    The agents/sessions/deliveries repos back recipient resolution and the inbox
    fan-out performed by ``message_create`` (ADR 0001).
    """
    repos = deps.repos

    if getattr(repos, "channels", None) is None:
        repos.channels = SqliteChannelRepo(deps.clock)
    if getattr(repos, "messages", None) is None:
        repos.messages = SqliteMessageRepo(deps.clock)
    if getattr(repos, "workspaces", None) is None:
        repos.workspaces = SqliteWorkspaceRepo(deps.clock)
    if getattr(repos, "agents", None) is None:
        repos.agents = SqliteAgentRepo(deps.clock)
    if getattr(repos, "sessions", None) is None:
        repos.sessions = SqliteSessionRepo(deps.clock)
    if getattr(repos, "deliveries", None) is None:
        repos.deliveries = SqliteMessageDeliveryRepo(deps.clock)
    if getattr(repos, "message_vectors", None) is None:
        repos.message_vectors = SqliteMessageVectorStore(deps.clock)
    if getattr(repos, "tag_catalog", None) is None:
        repos.tag_catalog = SqliteTagCatalogRepo(deps.clock)
    if getattr(repos, "capability_catalog", None) is None:
        repos.capability_catalog = SqliteCapabilityCatalogRepo(deps.clock)
    if getattr(repos, "governance", None) is None:
        repos.governance = SqliteGovernanceRepo(deps.clock)
    if getattr(repos, "policies", None) is None:
        repos.policies = SqlitePolicyRepo(deps.clock)
    if getattr(repos, "policy_bindings", None) is None:
        repos.policy_bindings = SqliteAgentPolicyBindingRepo(deps.clock)
    if getattr(deps, "event_emitter", None) is None:
        if getattr(repos, "events", None) is None:
            repos.events = SqliteEventRepo(deps.clock)
        deps.event_emitter = SqliteEventEmitter(repos.events)

    # Policy enforcement (spec 80624c1a): per-slice service composing the
    # actor's attached policies; always-on and binding-driven - an actor with no
    # bindings passes untouched (BR2 zero-regression).
    governance = GovernanceService(
        connection_factory=deps.connection_factory,
        governance=repos.governance,
        clock=deps.clock,
        config=deps.config,
        agents=repos.agents,
        capability_catalog=repos.capability_catalog,
        event_emitter=deps.event_emitter,
        policies=repos.policies,
        policy_bindings=repos.policy_bindings,
    )

    # HITL approvals (spec 2948b2a2): the PROCESS-WIDE service built in
    # bootstrap; constructed here defensively for hand-rolled test Deps. It
    # must stay a single instance - the executors registered below are what
    # the operator decision path re-executes through.
    approvals = getattr(deps, "approvals", None)
    if approvals is None:
        if getattr(repos, "approvals", None) is None:
            repos.approvals = SqliteApprovalRepo()
        approvals = ApprovalService(
            connection_factory=deps.connection_factory,
            approvals=repos.approvals,
            clock=deps.clock,
            config=deps.config,
            event_emitter=deps.event_emitter,
        )
        deps.approvals = approvals

    # Embedding generation is wired ONLY when the resolved capability carries a
    # provider (off mode -> None -> generation is a no-op). The vector store is
    # always present; the provider gates whether anything is written.
    embedding = getattr(deps, "embedding", None)
    embedding_provider = embedding.provider if embedding is not None else None

    service = MessageService(
        connection_factory=deps.connection_factory,
        channels=repos.channels,
        messages=repos.messages,
        workspaces=repos.workspaces,
        agents=repos.agents,
        sessions=repos.sessions,
        deliveries=repos.deliveries,
        event_emitter=deps.event_emitter,
        clock=deps.clock,
        config=deps.config,
        embedding_provider=embedding_provider,
        message_vectors=repos.message_vectors,
        tag_catalog=repos.tag_catalog,
        capability_catalog=repos.capability_catalog,
        governance=governance,
        approvals=approvals,
    )

    # Approved re-execution (BR2): one executor per intercepted action key.
    # ``message_create`` policies also cover broadcast attempts, and intercept
    # persists the ATTEMPTED action - so both keys point at the same callable.
    def _execute_message(kwargs: dict[str, Any]) -> dict[str, Any]:
        return service.create_message(**kwargs, _approved_execution=True)

    approvals.register_executor(ACTION_MESSAGE_CREATE, _execute_message)
    approvals.register_executor(ACTION_BROADCAST, _execute_message)

    return service


def register(server: Any, deps: Any) -> None:
    """Register the message/channel tools on ``server`` (FastMCP ``@server.tool()``)."""
    service = build_service(deps)

    @server.tool()
    @tool_envelope
    def message_create(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        from_agent_id: Annotated[str, Field(description=_P_FROM_AGENT)],
        subject: Annotated[str, Field(description=_P_SUBJECT)],
        body: Annotated[str, Field(description=_P_BODY)],
        channel_id: Annotated[str | None, Field(description=_P_CHANNEL)] = None,
        from_session_id: Annotated[
            str | None, Field(description=_P_FROM_SESSION)
        ] = None,
        target: Annotated[Any, Field(description=_P_TARGET_MSG)] = None,
        artifacts: Annotated[list[str] | None, Field(description=_P_ARTIFACTS)] = None,
        parent_message_id: Annotated[str | None, Field(description=_P_PARENT)] = None,
        trace_id: Annotated[str | None, Field(description=_P_TRACE)] = None,
        session_secret: Annotated[
            str | None, Field(description=_P_SESSION_SECRET)
        ] = None,
    ) -> dict[str, Any]:
        """Persist a message and fan it out to recipient inboxes; emit message.created. The response confirms delivery (recipients + delivered_count). Full docs: okto-nexus://reference/tool-docs/messages."""
        require_json_object_param("target", target)
        return service.create_message(
            project_root=project_root,
            from_agent_id=from_agent_id,
            subject=subject,
            body=body,
            channel_id=channel_id,
            from_session_id=from_session_id,
            target=target,
            artifacts=artifacts,
            parent_message_id=parent_message_id,
            trace_id=trace_id,
            session_secret=session_secret,
        )

    @server.tool()
    @tool_envelope
    def channel_create(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        name: Annotated[str, Field(description=_P_CHANNEL_NAME)],
    ) -> dict[str, Any]:
        """Create a channel by name (idempotent; created=false if it already existed). Channels are organizational labels, not ACLs."""
        caller = get_authenticated_agent()
        return service.create_channel(
            project_root=project_root,
            name=name,
            agent_id=caller.agent_id if caller is not None else None,
        )

    @server.tool()
    @tool_envelope
    def channel_list(
        project_root: Annotated[str, Field(description=_P_ROOT)],
    ) -> dict[str, Any]:
        """Return the workspace channels (``general`` is seeded by default)."""
        return service.list_channels(project_root=project_root)

    # ------------------------------------------------------------------ #
    # S3 clean-break migration shims. Clients pinned to the pre-S3 surface
    # still call message_get/message_list/message_wait; instead of an opaque
    # "Unknown tool" they get a prescriptive MIGRATED envelope naming the
    # exact replacement call. Each shim declares NO parameters: FastMCP
    # ignores unknown arguments, so EVERY legacy call shape lands here
    # instead of failing schema validation.
    # ------------------------------------------------------------------ #

    def _migrated(message: str, replacements: list[str]) -> dict[str, Any]:
        return err(
            _MIGRATED_CODE,
            message,
            {"replacements": replacements, "removed_in": "S3"},
        )

    @server.tool()
    @tool_envelope
    def message_get() -> dict[str, Any]:
        """MIGRATED (S3): replaced by inbox_pull / inbox_peek / inbox_history. Always returns ok:false code=MIGRATED with the replacement call."""
        return _migrated(
            "message_get was replaced in S3 by the inbox surface. Read messages "
            "addressed to you with inbox_pull(agent_id=<you>) (unread -> "
            "in-flight, returns bodies; acknowledge with inbox_ack), "
            "inbox_peek(agent_id=<you>) for a non-destructive look, or "
            "inbox_history(agent_id=<you>, cursor=..., limit=...) for "
            "already-read messages. To fetch bus traffic by event instead, use "
            'event_get(project_root=..., agent_id=<you>, stream="workspace", '
            'filters={"type": "message.created"}).',
            ["inbox_pull", "inbox_peek", "inbox_history", "event_get"],
        )

    @server.tool()
    @tool_envelope
    def message_list() -> dict[str, Any]:
        """MIGRATED (S3): replaced by inbox_peek / inbox_history (your messages) and event_get (bus traffic). Always returns ok:false code=MIGRATED."""
        return _migrated(
            "message_list was replaced in S3. For YOUR messages use "
            "inbox_peek(agent_id=<you>) (pending: unread + in-flight) or "
            "inbox_history(agent_id=<you>, cursor=..., limit=...) (read "
            "archive, newest-first, paginated). To enumerate the workspace's "
            "message traffic use event_get(project_root=..., agent_id=<you>, "
            'stream="workspace", filters={"type": "message.created"}, '
            "cursor=..., limit=...).",
            ["inbox_peek", "inbox_history", "event_get"],
        )

    @server.tool()
    @tool_envelope
    def message_wait() -> dict[str, Any]:
        """MIGRATED (S3): replaced by inbox_count polling (cheap) or event_wait (explicit blocking). Always returns ok:false code=MIGRATED."""
        return _migrated(
            "message_wait was replaced in S3. Cheapest: call "
            "inbox_count(agent_id=<you>) between turns and inbox_pull when "
            "unread > 0 (then inbox_ack what you processed). To explicitly "
            "block for new traffic use event_wait(project_root=..., "
            'agent_id=<you>, stream="workspace", filters={"type": '
            '"message.created"}, timeout_seconds=<n>) - timeout_seconds '
            "omitted/0 is a non-blocking snapshot; >0 blocks your turn.",
            ["inbox_count", "inbox_pull", "event_wait"],
        )
