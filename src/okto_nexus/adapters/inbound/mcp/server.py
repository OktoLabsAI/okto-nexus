"""MCP stdio server (inbound adapter).

Bootstrap is FAIL-CLOSED and ordered:

1. ``load_config``        - resolve config (CONFIG_ERROR on bad input)
2. ensure home dir        - via ``ConnectionFactory`` construction
3. ``ConnectionFactory``  - configured SQLite connections
4. ``MigrationRunner``    - apply pending migrations (MIGRATION_ERROR on failure)
5. register tools         - ONLY after the store is migrated and healthy

Tools are AUTO-DISCOVERED: every module under
``okto_nexus.adapters.inbound.mcp.tools`` that exposes
``def register(server, deps) -> None`` is invoked with the live MCP server and
a :class:`Deps` container. With zero tool modules present, the server still
starts and registers nothing. Server-level meta tools (``nexus_info``) are
registered separately by :func:`register_meta_tools`.

The MCP SDK (``mcp``) is imported LAZILY (only inside :func:`main` /
:func:`create_server`) so that importing this module - and the domain /
application layers - never requires the SDK to be installed.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import os
import pkgutil
import sys
from dataclasses import dataclass, field
from typing import Any, Mapping

from ....application.approvals import ApprovalService, seed_operator_agent
from ....application.capabilities import seed_capability_catalog
from ....application.comm_preset_catalog import seed_comm_presets
from ....application.ports import Clock, ConnectionFactory as ConnectionFactoryPort
from ....application.ports import EventEmitter, Repos
from ....config import FEATURE_FLAG_FIELDS, NexusConfig, load_config
from ....envelope import tool_envelope
from ....errors import OktoNexusError
from ...outbound.clock import SystemClock
from ...outbound.embedding import EmbeddingResolution, resolve_embedding_provider
from ...outbound.file.store import WorkspaceFileStore
from ...outbound.sqlite.approvals_repo import SqliteApprovalRepo
from ...outbound.sqlite.artifacts_repo import SqliteArtifactRepo
from ...outbound.sqlite.capability_catalog_repo import SqliteCapabilityCatalogRepo
from ...outbound.sqlite.connection import ConnectionFactory
from ...outbound.sqlite.embeddings_repo import SqliteMessageVectorStore
from ...outbound.sqlite.events_repo import SqliteEventEmitter, SqliteEventRepo
from ...outbound.sqlite.governance_repo import SqliteGovernanceRepo
from ...outbound.sqlite.guardrails_repo import (
    SqliteAgentGroupRepo,
    SqliteGuardrailAssignmentRepo,
    SqliteGuardrailRepo,
)
from ...outbound.sqlite.handoff_repo import SqliteHandoffRepo, SqliteTaskRepo
from ...outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteSessionRepo,
    SqliteWorkspaceRepo,
)
from ...outbound.sqlite.memory_repo import (
    SqliteMemoryRepo,
    SqliteMemoryVectorStore,
)
from ...outbound.sqlite.messages_repo import (
    SqliteChannelRepo,
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from ...outbound.sqlite.comm_preset_repo import (
    SqliteAgentCommBindingRepo,
    SqliteCommPresetRepo,
)
from ...outbound.sqlite.migrations import MigrationRunner
from ...outbound.sqlite.permissions_repo import SqlitePresetRepo
from ...outbound.sqlite.policy_repo import (
    SqliteAgentPolicyBindingRepo,
    SqlitePolicyRepo,
)
from ...outbound.sqlite.tag_catalog_repo import SqliteTagCatalogRepo
from . import tools as _tools_pkg
from .resources import register_resources, resource_versions

#: Server-level guidance surfaced to connecting agents (FastMCP ``instructions``).
#: Covers how to choose a communication channel, replying directly by default,
#: the canonical pre-flight, the inbox reception loop, and how a
#: monitoring-capable harness (e.g. Claude Code) builds a listener - a
#: backgrounded ``event_wait`` long-poll on THIS connection - plus the
#: anti-patterns it must avoid (curl at the REST API, ``okto-nexus tail``, a
#: standalone monitor process).
SERVER_INSTRUCTIONS = """\nOkto Nexus - local agent coordination bus (workspace-scoped; pass project_root). Agents are global identities - discover them with agent_list and their advertised capabilities with capability_list. DEEP reference docs live in MCP resources (okto-nexus://reference/...); read them on demand. This inline block keeps only what you need to act correctly on the first try.

YOUR IDENTITY. You connect over MCP streamable HTTP; the API key in your URL (/mcp?api_key=nxs_...) IS your agent identity, created by the operator on the dashboard. Use that agent_id consistently as from_agent_id / agent_id in every call. EVERYTHING you need is exposed as MCP tools on THIS connection - never shell out to the okto-nexus CLI, spawn helper processes, or attach a stdio server.

PRE-FLIGHT - run on your FIRST turn, in order, BEFORE the user's task (cheap, idempotent):
  1. agent_whoami() - your agent_id, role, capabilities, permissions. Use that agent_id everywhere.
  2. workspace_resolve(project_root=<cwd>) then session_open(agent_id=<you>, workspace_id=<resolved>). Pass your session_id + session_secret on every authenticated verb - each advances your heartbeat, so working keeps you present (only heartbeat-fresh sessions receive broadcasts and show online); reserve an explicit session_heartbeat for IDLE turns. Store the returned session_secret.
  3. inbox_count(agent_id=<you>); if unread > 0, inbox_pull and triage the backlog, then inbox_ack what you handled.
  4. event_cursor(stream="workspace") to anchor at NOW, then monitor via event_wait (background long-poll) or event_get polling, advancing the cursor.
Full detail: resource okto-nexus://reference/preflight. When finished for good, session_close.

COMMUNICATE - prefer the most targeted, least noisy channel:
  - DIRECT (default, preferred): message_create with target={"strategy":"direct","agent_id":"<recipient>"}. ALWAYS reply directly to whoever messaged you (target their from_agent_id).
  - HANDOFF: handoff_create with a capability/role/broadcast target when exactly ONE free agent should claim dispatchable work (first to handoff_claim wins).
  - BROADCAST (last resort): message_create with NO target - announcements or open-ended discovery only, NEVER actionable work (it triggers unwanted parallel work).
HOW YOU RECEIVE: messages addressed to you land in your GLOBAL inbox - inbox_count -> inbox_pull -> inbox_ack. event_get/event_wait are OBSERVABILITY, not message delivery. Channels are organizational labels, not ACLs and not delivery - the message TARGET decides who receives it. Full detail (channels, delivery/read receipts, reception loop): okto-nexus://reference/communication. Monitoring/listener patterns + anti-patterns (no curl, no CLI tail, no separate monitor process): okto-nexus://reference/monitoring.

PERMISSIONS. The operator may restrict your identity (direct sends, broadcasts, channel posts, handoff create/work/cancel, rate limits, peer allowlists). A blocked call returns ok:false with code PERMISSION_DENIED and details.required_permission. Do NOT retry or work around it - adapt (e.g. reply directly instead of broadcasting) or report that the operator must grant the flag (dashboard Agents -> Permissions).

ERRORS & RETRIES. Every tool answers {ok:true,data} or {ok:false,error:{code,message,...}}. A DB_ERROR with retryable=true is transient - retry the SAME call after a short backoff (~0.5-2s). A MIGRATED error means the tool was replaced; the message names the exact replacement - switch to it, do NOT retry the old call. PERMISSION_DENIED is a policy decision, not a retryable error.
"""

#: Monotonic revision of the MCP tool SURFACE (tool names, parameters,
#: defaults, semantics). Bump by 1 on EVERY surface change so agents can
#: detect stale cached schemas via ``nexus_info``. Started at 2 with the
#: post-S3 safe-by-default surface. 3 = M9 unified target grammar (mixed
#: requires non-empty rules, no null/broadcast sub-rules - everywhere) +
#: shared pagination grammar (integer-string cursor/limit now accepted).
#: 4 = M6 presence (session_open returns session_secret; broadcast audience is
#: heartbeat-fresh sessions with explicit excluded_stale) + M10 trust
#: (session_id/session_secret parameters on message_create,
#: handoff_claim/complete/reject, inbox_pull/ack/extend; trust_mode knob).
#: 5 = event_get/event_wait ``stream`` description no longer advertises the
#: removed ``task`` stream (doc-only fix; ``VALID_STREAMS`` semantics
#: unchanged - a cached schema saying "task" was prescribing INVALID_STREAM).
#: 6 = v2 documentation overhaul: SERVER_INSTRUCTIONS now describe the
#: streamable-HTTP connection (key = identity), the bootstrap sequence, the
#: listener patterns (event_wait long-poll / event_get polling - explicitly
#: NOT `okto-nexus tail`, which older docs prescribed and agents were trying
#: to spawn), and the PERMISSION_DENIED policy envelope (migration 011).
#: 7 = identity lockdown: NEW agent_whoami tool (profile derived from the
#: API key); agent_register is now SELF-ONLY on authenticated connections
#: (minting new identities / rewriting another agent's profile returns
#: PERMISSION_DENIED; identities are created on the dashboard).
#: 8 = delivery/read receipts: inbox_pull emits ``message.delivered`` and
#: inbox_ack emits ``message.read`` (sender-visible, atomic with the lane
#: transition); inbox_ack's response gains ``read_message_ids``.
#: 9 = canonical PRE-FLIGHT: the instructions now prescribe one exact
#: bootstrap (identity -> presence -> backlog -> monitor) so every agent
#: initialises uniformly; NEW event_cursor tool (O(1) end-of-stream anchor
#: so a monitor starts from NOW instead of paging history).
#: 10 = inbox read receipts (opt-out): inbox_ack additionally lands a
#: "message.read_receipt" notification in each sender's inbox (grouped per
#: sender; receipts never generate receipts; disable with the
#: inbox_read_receipts setting).
#: 11 = monitoring guidance for capable harnesses: SERVER_INSTRUCTIONS now
#: spell out that a listener is just a BACKGROUNDED event_wait long-poll on
#: THIS MCP connection (Claude Code & friends) and enumerate the anti-patterns
#: to avoid - curl/raw HTTP at /api/v1, /mcp or the dashboard SSE; `okto-nexus
#: tail` or any CLI; a standalone Python/Node monitor process; spawning any
#: helper process. Doc-only (no tool/parameter/semantics change).
#: 12 = token-reduction Frente 1 (residente): the long prose moved OUT of
#: SERVER_INSTRUCTIONS into MCP resources (okto-nexus://reference/preflight,
#: /communication, /monitoring), read on demand; the inline block keeps only
#: the actionable minimum (identity, 4-step pre-flight, the 3 comm modes,
#: permissions, errors) + pointers. nexus_info now also reports
#: resource_versions for stale-cache detection. Descriptions/instructions only
#: - no tool/parameter/semantics change.
#: 13 = tag scoping F1: NEW read-only tag_list tool (the central tag catalog);
#: NEW routing strategy "tag" on message_create/handoff_create targets
#: (selector validated in FORM and against the catalog, fail-closed);
#: senders/creators with a comm_scope.outbound selector have their direct
#: sends, fan-outs and handoff claims bounded by it. BREAKING: the
#: messages.allowed_peers permission flag is REMOVED (writes with it are
#: rejected as unknown; stored rows are inert) - recreate allowlists as an
#: outbound audience selector over registered tags.
#: 14 = tag scoping F2 (inbound + "visible = reachable"): comm_scope.inbound
#: ships (operator-set; "who may reach me") - reach is now the DOUBLE
#: intersection sender.outbound AND recipient.inbound, enforced on direct
#: sends (opaque PERMISSION_DENIED identical to the outbound denial), fan-outs
#: (inbound drops are SILENT - recipient policy is never a sender warning or
#: metric), handoff claim/list_available/notifications. Discovery is scoped:
#: agent_list/capability_list list only agents REACHABLE from the caller
#: (anonymous callers see all); agent_get of an unreachable agent reads as
#: NOT_FOUND. event_get/event_wait omit events whose actor is unreachable
#: (own events + system events always show). Operator surfaces (REST +
#: dashboard SSE) stay unfiltered.
#: 15 = tag scoping F3 (rich selector grammar): every selector (comm_scope
#: outbound/inbound and the tag strategy's target.selector) also accepts a
#: Kubernetes-style matchExpressions list [{key, operator: In|NotIn|Exists|
#: DoesNotExist, values}] - expressions AND, multi-value intersection, the
#: flat F1 map stays valid as In sugar (no migration). K8s absence parity:
#: NotIn/DoesNotExist MATCH agents missing the key (compose with Exists to
#: require it). Values match hierarchically by "/" segment (ENG covers
#: ENG/BACKEND, never ENGX). Exists/DoesNotExist forbid values; In/NotIn
#: require them. The catalog existence gate covers expressions fail-closed
#: (keys of every operator; values of In/NotIn) and TAG_IN_USE counts
#: expression references. No enforcement point changed (same predicates).
#: 16 = central capability catalog (migration 014): capability names become a
#: pre-defined, GLOBAL, operator-managed vocabulary (REST /api/v1/capabilities
#: + dashboard Registry; agents never define names). Fail-closed EXISTENCE
#: gate on every write path that references a capability - agent_register /
#: POST / PATCH ``capabilities`` and ``strategy: "capability"`` targets on
#: message_create/handoff_create (incl. sub-rules inside ``mixed`` and the
#: fallback of ``direct_with_fallback``) reject unregistered names with
#: VALIDATION_ERROR listing them. Deleting a name still OWNED by any agent
#: (active or inactive) is CAPABILITY_IN_USE (409 on REST) with the owner
#: list; historic targets never count. Idempotent bootstrap seed absorbs
#: every already-announced name, so existing agents keep working unchanged.
#: capability_list is now CATALOG-COMPLETE: entries gain ``description`` and
#: zero-owner names list with agent_count 0. Matching semantics unchanged
#: (normalize_capabilities and runtime routing untouched).
#: 17 = meta-harness feature flags (R-I0): the ``nexus_info`` envelope gains a
#: read-only ``features`` block ({feature_*: bool}, exactly the 8 flags)
#: reflecting the EFFECTIVE config (CLI > env > stored > default) at call
#: time. No new tool, no tool removed: a flag that is off never hides
#: surface - behavioural gating belongs to the consuming features (I1-I8).
#: Flags are operator-managed via Settings (group ``features``) / env
#: ``OKTO_NEXUS_FEATURE_*`` / CLI ``--feature-*``; all default off (opt-in).
#: 18 = trajectory traces (R-I1, gated by ``feature_trace``, default off):
#: message_create / handoff_create accept an optional ``trace_id`` (non-empty
#: string, max 128 chars). Flag OFF accepts-and-ignores the parameter -
#: byte-identical pre-feature behaviour (the canonical gating pattern). Flag
#: ON resolves explicit > inherited (reply parent) > generated ('trc_' +
#: uuid4 hex), persists the id on the message/handoff row (migration 015),
#: echoes it in create responses and inbox items, and stamps it into the
#: payload of message.created and every handoff.* lifecycle event.
#: event_get/event_wait filters gain the payload-level ``trace_id`` key and
#: event_to_dict surfaces it top-level; REST adds GET /events?trace= plus
#: trace_id on the /messages, /handoffs and /events serializers.
#: 19 = governance policies (R-I2, gated by ``feature_governance``, default
#: off): operator-set GLOBAL deny rules and quotas (deny / max_count with
#: 1h|24h windows / max_bytes / max_open_handoffs) over subjects (agent /
#: role / capability / star) and actions (message_create - which also covers
#: broadcast -, broadcast, handoff_create, artifact_put), enforced
#: PRE-persistence inside each write path's unit of work. New error codes
#: POLICY_DENIED (REST 403) and QUOTA_EXCEEDED (REST 429); denials audited as
#: ``governance.denied`` (payload never carries subject/body). agent_whoami
#: gains a conditional ``governance`` block (caller-matched policies) ONLY
#: when the flag is ON and a policy matches - flag OFF stays byte-identical
#: (no tool added or removed). New reference resource
#: okto-nexus://reference/governance. CRUD is operator-only over REST
#: (/api/v1/governance/policies) and works with the flag OFF.
#: 20 = HITL approvals (R-I3, spec 2948b2a2, gated by ``feature_hitl``, default
#: off): governance policies gain limit_kind ``require_approval``. With
#: feature_governance AND feature_hitl ON, a matching message_create /
#: broadcast / handoff_create that would otherwise PASS is intercepted
#: PRE-execution into the ``approvals`` queue (migration 017) and the tool
#: returns the ``pending_approval`` envelope ({approval_id, action, policy_id,
#: watch{stream,types,approval_id}, trace_id?}) instead of executing - flag
#: OFF stays byte-identical (accept-and-ignore; no tool added or removed).
#: Decisions are operator-only over REST (GET /approvals, GET+POST
#: /approvals/{id}[/decision], POST /steering/messages) and work with the
#: flag OFF; approve re-executes the persisted request verbatim via a
#: one-shot bypass, reject notifies the requester by direct inbox message
#: from the first-class seeded ``operator`` agent (reserved id, fail-closed
#: on registration). approval.requested/granted/denied events carry metadata
#: only (never subject/body); ``approval_id`` is promoted on every projection
#: profile. New error code CONFLICT (REST 409) for an already-decided
#: approval. New reference resource okto-nexus://reference/hitl (12th URI).
#: 21 = handoff verification (R-I4, spec c692da7e, gated by
#: ``feature_verification``, default off): handoff_create accepts optional
#: ``acceptance_criteria`` (1..20 non-empty strings, <=500 chars each, no
#: exact duplicates, IMMUTABLE) + ``verify_by`` ({kind: creator|agent|
#: capability}; default {kind: creator} MATERIALISED at creation; agent must
#: be registered, capability must be in the catalog; statically unsatisfiable
#: self-claim contracts rejected). Flag OFF REJECTS the new params with
#: VALIDATION_ERROR (fail-closed - the deliberate exception to
#: accept-and-ignore: a verification contract is never silently dropped);
#: without them behaviour is byte-identical ON or OFF. A verifiable handoff's
#: ``handoff_complete`` parks it in the new non-terminal ``VERIFYING`` status
#: (emits metadata-only ``handoff.verification_requested`` + notifies a
#: statically resolvable verifier). New tool ``handoff_verify`` (verifier-only,
#: resolved DYNAMICALLY at verify time; the claimant can never verify their
#: own delivery): 'pass' -> COMPLETED emitting the CANONICAL
#: ``handoff.completed`` enriched with ``verified_by``; 'fail' -> CLAIMED for
#: rework with ``verification_feedback`` (<=2000 chars, overwritten per fail)
#: + renewed lease, emitting ``handoff.verification_failed``. VERIFYING is
#: protected: cancel/reject refuse it and lease expiry never touches it; it
#: still counts as an OPEN handoff for governance quotas (I2). handoff_get
#: exposes acceptance_criteria/verify_by/verification_feedback top-level when
#: non-NULL (trace_id pattern). Migration 018; docs updated in the existing
#: tool-docs/handoff resource (no new URI).
#: 22 = handoff dependencies (R-I5, spec 6522ad1f, gated by ``feature_dag``,
#: default off): handoff_create accepts an optional ``depends_on`` (1..20
#: unique ids of PRE-EXISTING same-workspace handoffs; IMMUTABLE - acyclicity
#: by construction). Flag OFF REJECTS the param with VALIDATION_ERROR
#: (fail-closed, the verification precedent - a dependency edge is never
#: silently dropped); ON gates existence (DEPENDENCY_NOT_FOUND with
#: ``{missing}``, cross-workspace indistinguishable from nonexistent) and
#: state (an already-REJECTED/CANCELLED dependency makes the create
#: statically unsatisfiable -> VALIDATION_ERROR; an already-COMPLETED one is
#: born satisfied). A dependent whose edges are not all COMPLETED is
#: OPEN-but-blocked, DERIVED ON-READ from the migration-019 edge table (no
#: new status): excluded from handoff_list_available and refused at claim
#: with the new DEPENDENCY_NOT_MET (details carry aggregate {pending, failed}
#: counts ONLY - dependency ids never leak to claimants). Post-creation gates
#: read the TABLE, never the flag, so flipping feature_dag OFF keeps existing
#: dependents decidable. Both producers of COMPLETED (plain complete + verify
#: 'pass') run a synchronous exactly-once unblock scan in the SAME UoW,
#: emitting ``handoff.unblocked`` ({handoff_id: the dependent, unblocked_by},
#: actor = the completer, the DEPENDENT's trace/visibility) and waking a
#: DIRECT dependent's named agent by inbox; REJECTED/CANCELLED emit
#: ``handoff.dependency_failed`` + notify each non-terminal dependent's
#: creator - NO cascade (the dependent stays OPEN for an explicit decision).
#: handoff_create echoes ``depends_on`` + the ``dependencies`` aggregate;
#: handoff_get exposes both when non-NULL (trace_id pattern); the projection
#: summary promotes ``handoff_id`` for the 2 new event types. No new tool.
#: Caveat S2: the raw ADMIN REST cancel (port-level update_status) does not
#: emit dependency_failed. Docs in the existing tool-docs/handoff resource
#: (v3, no new URI).
#: 23 = workspace memory (R-I6, spec 8928b320, gated by ``feature_memory``,
#: default off): THREE new tools - ``memory_put`` (persist a durable entry:
#: title <=200 chars, content <=16384 UTF-8 bytes, <=10 normalised topics,
#: optional atomic provenance pair source_kind {event,message,handoff} +
#: source_id (format-only), optional LINEAR ``supersedes`` stamped
#: bilaterally in the same UoW - NOT_FOUND/CONFLICT on a missing/already-
#: superseded target; authorship REQUIRED under the message_create session
#: regime), ``memory_get`` (full read by id, superseded included) and
#: ``memory_search`` (k default 10 clamped 1..50, AND-combined topics; ranks
#: semantic when embeddings are enabled, degrades lexical -> recent and
#: ALWAYS declares the effective ``search_mode`` - never fails on embedding
#: unavailability). Flag OFF -> VALIDATION_ERROR {feature_memory:false} on
#: all three (reads included): the whole primitive is absent, the DECLARED
#: exception to D4 accept-and-ignore (which governs new params on
#: pre-existing tools); tools stay registered, data written while ON stays.
#: Events ``memory.created``/``memory.superseded`` are metadata-only (NEVER
#: title/content); the projection promotes ``memory_id`` on every profile,
#: scoped by event type (the approval_id pattern). Migration 020. Operator
#: REST (browse/get_raw/DELETE, curation without event) is NOT gated. Zero
#: new error codes. Docs inline in the tool schemas (no new URI).
#: 24 = coordination health (R-I7, spec 7df9b1e0, gated by ``feature_health``,
#: default off): ONE new tool - ``coordination_health(project_root,
#: window="24h")`` - a PASSIVE read (no agent_id/session/heartbeat, so the
#: probe never turns its observer "present" in the presence metric it
#: reports). Windows are a closed enum {1h, 24h, 7d}; the payload carries an
#: aggregated ok|warn status, 7 metric blocks (message/event volume,
#: unclaimed handoffs, claim->complete average by EVENT correlation per
#: handoff_id, rejection rate, per-agent inbox backlog, presence buckets)
#: each declaring scope windowed|snapshot, and ALWAYS echoes the fixed V1
#: thresholds. Flag OFF -> VALIDATION_ERROR {feature_health:false} (tool
#: stays registered). Operator REST (GET /workspaces/{id}/health) is NOT
#: gated. Migration 021 (index-only). Zero new error codes; no new resource.
#: 25 = attachable policies (spec 80624c1a, migration 022): NO new tool - the
#: SEMANTICS of two existing tools evolved for the unified-policy surface.
#: ``agent_whoami`` now returns ``effective_policies`` (``<policy_id>@<version>``
#: / ``inline``) plus the resolved ``governance`` block when the caller has
#: bindings (audience selectors NEVER leaked; absent with no bindings - BR2).
#: ``artifact_get`` now captures the caller and filters by the artifact's frozen
#: audience (a reader outside it gets NOT_FOUND, AC8). Enforcement is always-on
#: and binding-driven (``feature_governance`` removed). One new error code
#: (``POLICY_IN_USE``, REST-only 409). Operator REST surfaces (``/policies``,
#: ``PUT /agents/{id}/policies``) are NOT MCP tools, so the stdio/http tool
#: parity is unchanged. Growth ledger: ``policies_b3`` (+233 docstring chars).
#: 26 = communication presets (spec 6f961722, migration 023): NO new tool - only
#: the SEMANTICS of ``agent_whoami`` grew. It now returns a SELF-ONLY
#: ``communication`` block ({source, content}) - the caller's resolved style
#: guidance (tone/format/language/verbosity/structure + additional_instructions)
#: - present ONLY when the caller has a resolvable binding (absent otherwise, so
#: an agent with none is byte-identical to rev 25 - BR11/D-CP-6). NEVER on
#: ``_agent_to_data`` / discovery. One new error code (``COMM_PRESET_IN_USE``,
#: REST-only 409). Operator REST surfaces (``/comm-presets``,
#: ``PUT /agents/{id}/communication``) are NOT MCP tools, so the stdio/http tool
#: parity is unchanged. The whoami docstring was reworded net-neutral (no
#: resident growth): ledger ``comm_presets_c5`` (0 chars).
#: 27 = guardrail/group administration tools (migration 025): operator-only MCP
#: tools for explicit groups, memberships, guardrail headers, versions,
#: assignments and scrubbed denial reads. Runtime enforcement semantics are
#: unchanged; the new tools expose staging/admin surfaces and parity holds by
#: auto-discovery across stdio/http.
SURFACE_REVISION = 27


@dataclass
class Deps:
    """Dependency container handed to every tool's ``register`` function.

    Attributes
    ----------
    config:
        The resolved :class:`NexusConfig`.
    connection_factory:
        Factory for configured SQLite connections / units of work.
    clock:
        :class:`Clock` implementation (``SystemClock`` in production).
    repos:
        :class:`Repos` registry; fields are populated as slices land.
    event_emitter:
        :class:`EventEmitter` facade (``None`` until the events slice lands).
    """

    config: NexusConfig
    connection_factory: ConnectionFactoryPort
    clock: Clock
    repos: Repos = field(default_factory=Repos)
    event_emitter: EventEmitter | None = None
    # Resolved embedding capability (provider + search/degraded flags) for the
    # configured ``embedding_mode``. ``None`` until bootstrap wires it.
    embedding: EmbeddingResolution | None = None
    # Shared HITL approval service (spec 2948b2a2): ONE instance per process so
    # the executors each slice registers (messages/handoff) are visible to the
    # decision path regardless of transport. ``None`` until bootstrap wires it.
    approvals: ApprovalService | None = None


def build_repos(clock: Clock) -> tuple[Repos, EventEmitter]:
    """Instantiate every concrete outbound adapter and the event emitter.

    This is the single composition root for the persistence layer. Each slice's
    tool module ALSO knows how to wire its own repos idempotently, but doing it
    here once - BEFORE any tool registers - guarantees that:

    * every service shares ONE concrete instance per port, and
    * the :class:`EventEmitter` is already present when slices that emit audit
      events (artifacts/handoff/identity/messages) build their services,
      regardless of the alphabetical tool-discovery order.

    Returns the populated :class:`Repos` registry and the shared emitter.
    """
    events_repo = SqliteEventRepo(clock)
    repos = Repos(
        workspaces=SqliteWorkspaceRepo(clock),
        agents=SqliteAgentRepo(clock),
        sessions=SqliteSessionRepo(clock),
        events=events_repo,
        channels=SqliteChannelRepo(clock),
        messages=SqliteMessageRepo(clock),
        deliveries=SqliteMessageDeliveryRepo(clock),
        tasks=SqliteTaskRepo(clock),
        handoffs=SqliteHandoffRepo(clock),
        artifacts=SqliteArtifactRepo(clock),
        files=WorkspaceFileStore(),
        presets=SqlitePresetRepo(clock),
        message_vectors=SqliteMessageVectorStore(clock),
        memories=SqliteMemoryRepo(clock),
        memory_vectors=SqliteMemoryVectorStore(clock),
        tag_catalog=SqliteTagCatalogRepo(clock),
        capability_catalog=SqliteCapabilityCatalogRepo(clock),
        governance=SqliteGovernanceRepo(clock),
        policies=SqlitePolicyRepo(clock),
        policy_bindings=SqliteAgentPolicyBindingRepo(clock),
        agent_groups=SqliteAgentGroupRepo(clock),
        guardrails=SqliteGuardrailRepo(clock),
        guardrail_assignments=SqliteGuardrailAssignmentRepo(clock),
        comm_presets=SqliteCommPresetRepo(clock),
        comm_bindings=SqliteAgentCommBindingRepo(clock),
        approvals=SqliteApprovalRepo(),
    )
    emitter = SqliteEventEmitter(events_repo)
    return repos, emitter


def bootstrap(
    env: Mapping[str, str] | None = None,
    argv: list[str] | None = None,
) -> Deps:
    """Run the fail-closed bootstrap and return a ready :class:`Deps`.

    Does NOT import the MCP SDK, so it is safe to call from tests. All concrete
    repositories and the shared event emitter are wired here so that tool
    auto-discovery only ever REUSES these instances (its idempotent guards see
    them already present), giving every slice a single coherent backing store.
    """
    env = env if env is not None else os.environ
    config = load_config(env, argv)
    factory = ConnectionFactory(config)  # ensures home_dir exists
    MigrationRunner(factory).apply()  # idempotent; MIGRATION_ERROR on failure
    clock = SystemClock()
    repos, emitter = build_repos(clock)
    # Transition seed (migration 014): absorb every announced capability into
    # the central catalog, idempotently, BEFORE any fail-closed gate can run -
    # the invariant "owned => registered" is what keeps existing agents
    # (re-)registering without error under the new regime.
    with factory.unit_of_work() as uow:
        seed_capability_catalog(
            uow, catalog=repos.capability_catalog, agents=repos.agents
        )
        # First-class operator identity (spec 2948b2a2 FR6/BR4): seeded
        # unconditionally BEFORE any tool registers; create-if-missing only,
        # so an existing operator (role, permissions, key) is never touched.
        seed_operator_agent(uow, agents=repos.agents)
        # Built-in communication presets (spec 6f961722): a starter style
        # vocabulary, create-if-missing only, so an operator's edits/renames
        # survive a restart and re-running never duplicates or bumps a version.
        seed_comm_presets(uow, presets=repos.comm_presets)
    # Resolve the embedding capability ONCE from the configured mode (off /
    # stub / local). The model singleton is lazy, so this stays cheap even for
    # ``local``; an absent extra degrades to the stub with search disabled.
    embedding = resolve_embedding_provider(config.embedding_mode)
    # ONE approval service per process (spec 2948b2a2): every slice injects
    # this instance, so the executors registered by messages/handoff wiring
    # are the ones the operator decision path re-executes through.
    approvals = ApprovalService(
        connection_factory=factory,
        approvals=repos.approvals,
        clock=clock,
        config=config,
        event_emitter=emitter,
    )
    return Deps(
        config=config,
        connection_factory=factory,
        clock=clock,
        repos=repos,
        event_emitter=emitter,
        embedding=embedding,
        approvals=approvals,
    )


def register_tools(server: Any, deps: Deps) -> list[str]:
    """Discover and register every tool module; return the module names registered.

    A tool module participates by exposing ``register(server, deps) -> None``.
    """
    registered: list[str] = []
    prefix = _tools_pkg.__name__ + "."
    for module_info in pkgutil.iter_modules(_tools_pkg.__path__, prefix):
        module = importlib.import_module(module_info.name)
        register = getattr(module, "register", None)
        if callable(register):
            register(server, deps)
            registered.append(module_info.name)
    return registered


def _package_version() -> str:
    """Installed distribution version; ``"dev"`` for a plain source checkout."""
    try:
        return importlib.metadata.version("okto-nexus")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


def _schema_version(connection_factory: ConnectionFactoryPort) -> int:
    """Highest applied migration version per the ``schema_migrations`` ledger.

    ``0`` means no migration has been applied (bootstrap guarantees this never
    happens on a healthy server, as migrations run before tools register).
    """
    conn = connection_factory.get_connection()
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return int(row[0]) if row is not None and row[0] is not None else 0
    finally:
        conn.close()


def register_meta_tools(server: Any, deps: Deps) -> None:
    """Register server-level meta tools (currently ``nexus_info``).

    These live in the composition root rather than a ``tools/`` module because
    they describe the WHOLE server (surface revision, schema ledger), not any
    one slice.
    """

    @server.tool()
    @tool_envelope
    def nexus_info() -> dict[str, Any]:
        """Report server versions: package_version, schema_version, surface_revision, resource_versions, features (read-only {feature_*: bool}). Call when behaviour disagrees with cached schemas."""
        return {
            "package_version": _package_version(),
            "schema_version": _schema_version(deps.connection_factory),
            "surface_revision": SURFACE_REVISION,
            "resource_versions": resource_versions(),
            # Effective (post-precedence) values read from the LIVE config at
            # call time - a PATCH that flips a flag shows up without restart.
            "features": {
                name: bool(getattr(deps.config, name)) for name in FEATURE_FLAG_FIELDS
            },
        }


def maybe_auto_prune(deps: Deps) -> dict[str, Any] | None:
    """Opportunistic retention reaper, gated by ``auto_prune_on_start``.

    When the knob (default ``False``; env ``OKTO_NEXUS_AUTO_PRUNE_ON_START`` /
    ``--auto-prune-on-start true``) is enabled, server startup runs ONE
    bounded, incremental retention pass (``AUTO_PRUNE_MAX_BATCHES`` batches
    per table) using the configured windows - cheap and predictable, never a
    full drain; backlog converges across restarts or via ``okto-nexus admin
    prune``. BEST-EFFORT by design: a failure is reported to stderr and
    startup proceeds (retention must never keep the bus down). Returns the
    prune report, or ``None`` when disabled/failed.
    """
    if not deps.config.auto_prune_on_start:
        return None
    from ....application.retention import AUTO_PRUNE_MAX_BATCHES, RetentionService

    try:
        report = RetentionService.from_deps(deps).prune(
            max_batches=AUTO_PRUNE_MAX_BATCHES
        )
    except OktoNexusError as exc:
        print(
            f"[okto-nexus] auto-prune skipped: {exc.code}: {exc.message}",
            file=sys.stderr,
        )
        return None
    print(
        f"[okto-nexus] auto-prune deleted {report['total_deleted']} row(s)",
        file=sys.stderr,
    )
    return report


def create_server(deps: Deps) -> Any:
    """Create the MCP server, register tools, and return the server instance.

    Imports the MCP SDK lazily; raises ``ImportError`` if it is missing.
    """
    from mcp.server.fastmcp import FastMCP  # lazy import: SDK only needed here

    server = FastMCP("okto-nexus", instructions=SERVER_INSTRUCTIONS)
    register_tools(server, deps)
    register_meta_tools(server, deps)
    register_resources(server)  # MCP resources: on-demand reference docs (Frente 1)
    return server


def main(argv: list[str] | None = None) -> int:
    """Console-script entry point. Returns a process exit code.

    The first token selects the mode: ``tail`` dispatches to the line-delimited
    event-log follower and ``admin`` to the maintenance commands (CLI
    subcommands); anything else runs the MCP stdio server. The dispatch happens
    BEFORE ``load_config`` because the config parser is flags-only and rejects
    positionals by design.
    """
    args = list(sys.argv[1:]) if argv is None else list(argv)

    if args and args[0] == "tail":
        from ..cli.tail import run_tail  # lazy: avoids an import cycle with this module

        return run_tail(args[1:])

    if args and args[0] == "admin":
        from ..cli.admin import run_admin  # lazy: avoids an import cycle too

        return run_admin(args[1:])

    if args and args[0] == "serve":
        from ..cli.serve import run_serve  # lazy: FastAPI/uvicorn optional

        return run_serve(args[1:])

    if args and args[0] in ("-h", "--help", "help"):
        print(
            "okto-nexus - local agent coordination bus\n\n"
            "Usage:\n"
            "  okto-nexus serve [options]   Start the HTTP hub "
            "(MCP + REST + dashboard); see `okto-nexus serve --help`\n"
            "  okto-nexus tail [options]    Stream the event log as NDJSON "
            "(operator console)\n"
            "  okto-nexus admin <cmd>       Maintenance (prune, issue-keys)\n"
            "  okto-nexus [options]         Run the legacy stdio MCP server "
            "(prefer `serve`)\n"
        )
        return 0

    try:
        deps = bootstrap(os.environ, args)
    except OktoNexusError as exc:
        print(
            f"[okto-nexus] bootstrap failed: {exc.code}: {exc.message}",
            file=sys.stderr,
        )
        return 1

    # Optional stdio identity-by-key (FR8): when OKTO_NEXUS_API_KEY is set,
    # the session's identity derives from the key exactly as on HTTP, and an
    # invalid key FAILS CLOSED (no silent fallback to the open V1 mode). The
    # env absent keeps the V1 contract byte-for-byte (rule br_b89c1d77).
    stdio_key = os.environ.get("OKTO_NEXUS_API_KEY")
    if stdio_key:
        from ....application.auth import AgentKeyAuthService
        from ..http.identity_ctx import current_agent

        auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
        with deps.connection_factory.unit_of_work() as uow:
            agent = auth.resolve(uow, stdio_key)
        if agent is None:
            print(
                "[okto-nexus] OKTO_NEXUS_API_KEY is set but does not resolve "
                "to an active agent. Fix or unset the variable (fail-closed; "
                "the open V1 mode is NOT used as a fallback).",
                file=sys.stderr,
            )
            return 1
        current_agent.set(agent)
        print(
            f"[okto-nexus] stdio session authenticated as agent "
            f"'{agent.agent_id}' via OKTO_NEXUS_API_KEY.",
            file=sys.stderr,
        )

    maybe_auto_prune(deps)  # no-op unless auto_prune_on_start=true; best-effort

    try:
        server = create_server(deps)
    except ImportError:
        print(
            "[okto-nexus] The 'mcp' SDK is not installed. "
            "Install it with: pip install 'mcp>=1.0' (or 'pip install okto-nexus').",
            file=sys.stderr,
        )
        return 1

    server.run()  # stdio transport by default
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
