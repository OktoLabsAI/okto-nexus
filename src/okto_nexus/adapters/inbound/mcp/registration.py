"""MCP instructions, tools, resources, and HTTP server registration."""
from __future__ import annotations

import functools
import importlib
import importlib.metadata
import inspect
import pkgutil
import time
from typing import Any

from ....application.ports import ConnectionFactory as ConnectionFactoryPort
from ....application.telemetry.ports import TelemetryPort
from ....application.telemetry.schema import EVENT_MCP
from ....config import FEATURE_FLAG_FIELDS
from ....envelope import tool_envelope
from . import tools as _tools_pkg
from .resources import register_resources, resource_versions

from okto_nexus.bootstrap.dependencies import Deps, _package_version

#: Server-level guidance surfaced to connecting agents (FastMCP ``instructions``).
#: Covers the profile operating contract, intent-based channel selection, the
#: canonical pre-flight, inbox reception loop, and how a
#: monitoring-capable harness builds a listener: either a backgrounded
#: ``event_wait`` long-poll on THIS connection, or an EPT-backed remote
#: data-plane poller when the harness can run a wake-up background process
#: without carrying the permanent ``nxs_`` key.
SERVER_INSTRUCTIONS = """\nOkto Nexus - local agent coordination bus (workspace-scoped; pass project_root). Agents are global identities - discover them with agent_list and their advertised capabilities with capability_list. DEEP reference docs live in MCP resources (okto-nexus://reference/...); read them on demand. This inline block keeps only what you need to act correctly on the first try.

YOUR IDENTITY. You connect over MCP streamable HTTP; the nxs_ API key sent in your Authorization bearer header IS your agent identity, created by the operator on the dashboard. Use that agent_id consistently as from_agent_id / agent_id in every call. EVERYTHING you need is exposed as MCP tools on THIS connection - never shell out to the okto-nexus CLI, attach a stdio server, or spawn helper processes (sole exception: an EPT poller holding only a short-lived nxsept_ token, never your nxs_ key).

MANAGED SESSIONS. With an nxc4_ session bearer, call agent_whoami and use its session_scope.workspace_id as project_root. Use the bound agent and session only; do not open a legacy session or request another credential. Claim and complete work through authorized handoff tools, preserving claim_epoch. The following key-based pre-flight applies only to nxs_ connections.

PRE-FLIGHT - run on your FIRST turn, in order, BEFORE the user's task (cheap, idempotent):
  1. agent_whoami() - your agent_id, role, capabilities, permissions, and communication style when set. Use that agent_id everywhere.
  2. workspace_resolve(project_root=<cwd>) then session_open(agent_id=<you>, workspace_id=<resolved>). Store the returned session_secret. Pass session_id + session_secret on the verbs that accept them (message_create - named from_session_id there; handoff claim/complete/verify/reject/cancel; inbox pull/ack/extend; poll_token_*) - each validated call advances your heartbeat, keeping you in the broadcast audience. Read-only verbs (event_*, inbox count/peek, discovery) do NOT advance it: call session_heartbeat on idle or read-only stretches.
  3. inbox_count(agent_id=<you>); if unread > 0, inbox_pull and triage the backlog, then inbox_ack what you handled.
  4. event_cursor(project_root=<cwd>, agent_id=<you>, stream="workspace") to anchor at NOW, then monitor via event_wait with timeout_seconds>0 (background long-poll), an EPT remote poller (poll_token_issue -> /api/v1/events), or event_get polling, advancing the cursor.
Full detail: resource okto-nexus://reference/preflight. When finished for good, session_close.

PROFILE. Treat role and communication.content from agent_whoami as your default operating contract: role guides responsibilities and decision boundaries; communication.content guides tone, format, language, verbosity, structure and additional instructions. An explicit user instruction for the current task overrides conflicting profile guidance only for that task. It never grants permissions or bypasses governance, policies, guardrails, approvals, communication scope, safety rules, or higher-priority host instructions. Capabilities are routing claims, not authorization or persona.

COMMUNICATE - choose by intent:
  - HANDOFF (ALL EXECUTABLE WORK): any request asking another agent to perform work or produce a deliverable MUST use handoff_create, never message_create alone. Use a direct target for a named intended assignee, or a pool target (capability/role/tag/mixed/broadcast/direct_with_fallback) when the first eligible claimant should own it. One handoff has one claimant at a time and a trackable status/result.
  - BROADCAST MESSAGE (SHARED ALIGNMENT/INFORMATION): message_create with an explicit broadcast target or no target. Use it for shared context, decisions, announcements, discoveries, risks and alignment. It informs every reached recipient; it never assigns work. If action is required, create one or more handoffs.
  - DIRECT MESSAGE (CONVERSATION): use for status checks, questions, clarifications, acknowledgements and informal coordination. Reply directly when the answer belongs to that conversation. If new executable work emerges, create a handoff; if it is already in scope, reference the existing handoff.
IMPORTANT: a message broadcast fans information out to many recipients; a broadcast-target handoff is a claim pool for ONE executor.
HOW YOU RECEIVE: messages addressed to you land in your GLOBAL inbox - inbox_count -> inbox_pull -> inbox_ack. event_get/event_wait are OBSERVABILITY, not message delivery. Channels are organizational labels, not ACLs and not delivery - the message TARGET decides who receives it. Full detail (channels, delivery/read receipts, reception loop): okto-nexus://reference/communication. Monitoring/listener patterns, including EPT remote pollers that do not carry the permanent key: okto-nexus://reference/monitoring.

PERMISSIONS. The operator may restrict your identity (messaging, handoffs, channel/artifact writes, event/health reads, workspace listing/paths, shared.md render, self profile/capability updates, experimental memory, rate limits). A blocked call returns ok:false with code PERMISSION_DENIED and details.required_permission. Do NOT retry or work around it - adapt or report that the operator must grant the flag (dashboard Agents -> Permissions).

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
#: read-only ``features`` block ({feature_*: bool}, exactly the 7 flags)
#: reflecting the EFFECTIVE config (CLI > env > stored > default) at call
#: time. The original pattern was behaviour-only gating; revision 29 declares
#: memory as the explicit experimental exception whose tools are hidden unless
#: ``feature_memory`` is ON at bootstrap.
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
#: unavailability). Originally the tools stayed registered and flag OFF
#: returned VALIDATION_ERROR {feature_memory:false}; revision 29 moved memory
#: to an experimental registration-time surface gate so default clients do not
#: see the memory tools at all. Revision 30 added per-agent experimental
#: permissions (experimental.memory_write/read/search); the feature flag only
#: controls whether the surface exists.
#: Events ``memory.created``/``memory.superseded`` are metadata-only (NEVER
#: title/content); the projection promotes ``memory_id`` on every profile,
#: scoped by event type (the approval_id pattern). Migration 020. Operator
#: REST (browse/get_raw/DELETE, curation without event) is NOT gated. Zero
#: new error codes. Docs inline in the tool schemas (no new URI).
#: 24 = coordination health (R-I7, spec 7df9b1e0, gated by ``feature_health``,
#: default off): ONE new tool - ``coordination_health(project_root,
#: window="24h")`` - a PASSIVE read (no session/heartbeat, so the probe never
#: turns its observer "present" in the presence metric it reports). Revision
#: 30 added per-agent health.read permission when an actor is known. Windows
#: are a closed enum {1h, 24h, 7d}; the payload carries an
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
#: parity is unchanged. Growth ledger: ``policies_b3`` (+127 docstring chars, the measured value).
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
#: 28 = remote-only monitor data plane (migration 026): NEW MCP control-plane
#: tools poll_token_issue / poll_token_renew / poll_token_revoke issue short-
#: lived nxsept_ bearers bound to the caller's session/workspace. The bearer is
#: accepted only by read-only REST monitor endpoints (/api/v1/events[/cursor],
#: /api/v1/inbox/count, /api/v1/inbox/peek), never MCP/mutating routes.
#: 29 = memory is experimental at the SURFACE boundary: with
#: ``feature_memory=false`` (default) the ``memory_put`` / ``memory_get`` /
#: ``memory_search`` tools are not registered or advertised to agents at all.
#: Enabling/disabling this flag changes the MCP schema at server bootstrap, so
#: operators must restart serve/MCP clients for tool-list exposure to change.
#: 30 = permission surface hardening: authenticated ``session_open`` is
#: self-only; ``agent_register`` self-updates are gated by
#: ``identity.update_profile`` / ``identity.update_capabilities``; workspace
#: listing/path disclosure, shared.md render, coordination health and
#: experimental memory have explicit agent permissions. Handoff payloads are
#: no longer exposed by discovery/events/direct notifications, only by
#: handoff_claim and claimant handoff_get. Guardrail/group administration tools
#: were removed from MCP entirely; critical guardrail admin is UI/REST-only.
#: 31 = docs-accuracy sweep (análise 0003, doc-only - no tool/parameter/
#: semantics change): SERVER_INSTRUCTIONS corrected (full event_cursor call
#: shape; precise credential/heartbeat verb list - read-only verbs never
#: advance the session heartbeat; the helper-process ban now carries its one
#: sanctioned exception, the nxsept_ EPT poller; event_wait long-poll is an
#: explicit timeout_seconds>0 opt-in). Stale resources rewritten and bumped:
#: governance v2 (binding-driven always-on model, /api/v1/policies flow -
#: feature_governance no longer exists), hitl v2 (same flag fix),
#: tool-docs/inbox v2 (lease default now INTERPOLATED from config - was
#: hardcoded 120 vs real 300 - plus the profile enum semantics),
#: tool-docs/events v2 (trace_id filter key), tool-docs/identity v4
#: (reachability-scoped discovery + whoami conditional blocks),
#: tool-docs/artifacts v2 (audience-scoped reads), target-grammar v5
#: (broadcast-in-mixed rejection is universal), tool-docs/messages v2,
#: communication v2 + monitoring v5 + preflight v3 (dedup: reception loop /
#: receipts / event-tool semantics each live in ONE resource + pointers).
#: Params token cut (target cheat-sheets keep shapes + absence caution, deep
#: rules move to the grammar resource; project_root sha256 tail lives only on
#: workspace_resolve; handoff session_secret standardized to the bus-wide
#: wording; profile enums minimal) and family docs pointers standardized on
#: the entry tools (inbox_pull, event_get, artifact_put). surface_metrics:
#: memory_i6 discount now conditional on the experimental surface being
#: registered (the 40% gate no longer discounts phantom growth).
#: 32 = agent operating-contract + coordination-intent guidance (doc-only):
#: role and communication.content from agent_whoami are now explicit defaults,
#: scoped user overrides cannot bypass hard controls, every inter-agent request
#: for executable work uses a handoff, broadcasts are informational fan-out,
#: and direct messages are conversational coordination. The resident block and
#: reference docs now distinguish a broadcast message from a broadcast-target
#: handoff (ONE claimant). Bumped resources: preflight v4, communication v3,
#: tool-docs/messages v3, tool-docs/handoff v4, tool-docs/identity v5. Also
#: corrected stale payload-discovery and heartbeat wording. Growth ledger:
#: ``coordination_guidance_r32`` (+1221 resident chars, measured net).
#: 33 = artifact payload storage is adapter-backed instead of SQLite-backed;
#: path submissions are imported into managed storage, and ``html`` joins the
#: closed artifact_type enum for safe dashboard preview. Tool names and
#: parameters are unchanged; the artifact reference resource is now v4.
#: 34 = harness connectors (Phase 3.5, ADR 0004): NEW tools ``harness_list``
#: (kind/substrate capability catalog), ``harness_open``, ``harness_send``,
#: ``harness_steer``, ``harness_interrupt``, ``harness_close``,
#: ``harness_get``, ``harness_event_list`` (durable replay). Mirrored on REST
#: under ``/api/v1/harness/...`` (operator-gated for the mutating verbs, like
#: ``POST /agents``/``POST /sessions/{id}/close``). Boot-time declared
#: harnesses are NOT wired into ``serve`` yet - on-demand open only.
#: 39 = shared strict runtime admin inputs; MCP endpoint/profile views and redacted profile discovery.
#: 40 = revision-fenced profile/endpoint edits, revocation and atomic configuration audit.
#: 41 = scoped agent runtime binding discovery; declared capabilities and explicit liveness limits.
#: 42 = explicit operator attempt reconciliation; no automatic native replay.
#: 43 = explicit canonical handoff recovery with claim/attempt fencing.
# Native compatibility observations are separate from caller metadata.
#: 52 = per-session qualified capabilities intersect descriptor and approved profile.
#: 53 = bounded logical transport backlog and per-agent normal worker capacity.
#: 54 = durable delivery attempt observation history in operator detail inspection.
#: 55 = bounded proven-safe retry deadlines and explicit retry-wait cancellation.
#: 56 = approved equivalent-endpoint fallback with persisted admission/target binding.
#: 57 = canonical conversational command payload contract3.
#: 58 = authenticated external attach work v1 and separate Nexus acknowledgement/completion facts.
SURFACE_REVISION = 61


# Tool modules whose publication is controlled by a config flag. These gates
# are deliberately registration-time: a FastMCP tool list is a schema surface,
# not a per-call behaviour switch. Existing servers that already registered an
# experimental module still keep the service-level runtime guard as a fallback.
_EXPERIMENTAL_TOOL_MODULE_FLAGS = {
    f"{_tools_pkg.__name__}.memory": "feature_memory",
    f"{_tools_pkg.__name__}.harness": "feature_harness_integrations",
}


class TelemetryToolServer:
    """Proxy that instruments FastMCP tool handlers at registration time."""

    def __init__(self, inner: Any, telemetry: TelemetryPort) -> None:
        self._inner = inner
        self._telemetry = telemetry

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def tool(self, *args: Any, **kwargs: Any):
        register = self._inner.tool(*args, **kwargs)

        def _decorate(fn):
            register(_wrap_tool_for_telemetry(fn, self._telemetry))
            return fn

        return _decorate


def _wrap_tool_for_telemetry(fn, telemetry: TelemetryPort):
    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def _async_wrapper(*args: Any, **kwargs: Any):
            started = time.perf_counter()
            result = await fn(*args, **kwargs)
            _record_tool_result(telemetry, fn.__name__, result, started)
            return result

        return _async_wrapper

    @functools.wraps(fn)
    def _wrapper(*args: Any, **kwargs: Any):
        started = time.perf_counter()
        result = fn(*args, **kwargs)
        _record_tool_result(telemetry, fn.__name__, result, started)
        return result

    return _wrapper


def _record_tool_result(
    telemetry: TelemetryPort, tool_name: str, result: Any, started: float
) -> None:
    duration_ms = int((time.perf_counter() - started) * 1000)
    status = "ok"
    error_code: str | None = None
    if isinstance(result, dict) and result.get("ok") is False:
        status = "error"
        error = result.get("error")
        if isinstance(error, dict) and error.get("code"):
            error_code = str(error["code"])
    payload: dict[str, Any] = {
        "tool_name": tool_name,
        "status": status,
        "duration_ms": duration_ms,
    }
    if error_code:
        payload["error_code"] = error_code
    telemetry.record_event(EVENT_MCP, payload)


def register_tools(server: Any, deps: Deps) -> list[str]:
    """Discover and register every tool module; return the module names registered.

    A tool module participates by exposing ``register(server, deps) -> None``.
    """
    # Tool services get a request-aware transaction port, while transport
    # authentication and background owners retain the original factory.
    from ....application.execution_capabilities import ExecutionCapabilityService
    from ....application.execution_tools import ExecutionToolConnectionFactory
    from ....bootstrap.execution_authority import build_execution_access, ExecutionToolDependencies
    capabilities = ExecutionCapabilityService(factory=deps.connection_factory,
                                             access=build_execution_access(deps))
    deps = ExecutionToolDependencies(deps,
        ExecutionToolConnectionFactory(deps.connection_factory, capabilities))
    registered: list[str] = []
    prefix = _tools_pkg.__name__ + "."
    registration_server = (
        TelemetryToolServer(server, deps.telemetry)
        if deps.telemetry is not None
        else server
    )
    from .connection_gate import ConnectionGateServer
    registration_server = ConnectionGateServer(registration_server, deps)
    for module_info in pkgutil.iter_modules(_tools_pkg.__path__, prefix):
        flag = _EXPERIMENTAL_TOOL_MODULE_FLAGS.get(module_info.name)
        if flag is not None and not bool(getattr(deps.config, flag, False)):
            continue
        module = importlib.import_module(module_info.name)
        register = getattr(module, "register", None)
        if callable(register):
            register(registration_server, deps)
            registered.append(module_info.name)
    return registered


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

    from .connection_gate import ConnectionGateServer
    server = ConnectionGateServer(server, deps)

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


def _load_fastmcp() -> Any:
    """Load the v1 FastMCP class with its settings model fully rebuilt.

    MCP 1.29.0 defines ``Settings`` before ``FastMCP``.  That leaves the
    generic ``lifespan`` annotation as an unresolved forward reference and
    pydantic-settings 2.15+ warns every time a server is constructed.  Rebuild
    after both classes exist, using Pydantic's public hook; fixed SDK releases
    already report the model complete and take the no-op branch.
    """
    from mcp.server.fastmcp import FastMCP
    from mcp.server.fastmcp.server import Settings

    if not Settings.__pydantic_complete__:
        Settings.model_rebuild()
    return FastMCP


def create_server(deps: Deps) -> Any:
    """Create the MCP server, register tools, and return the server instance.

    Imports the MCP SDK lazily; raises ``ImportError`` if it is missing.
    """
    FastMCP = _load_fastmcp()  # lazy import: SDK only needed here
    server = FastMCP("okto-nexus", instructions=SERVER_INSTRUCTIONS)
    register_tools(server, deps)
    register_meta_tools(server, deps)
    register_resources(server)  # MCP resources: on-demand reference docs (Frente 1)
    return server


