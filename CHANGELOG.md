# Changelog

All notable changes to Okto Nexus are documented in this file.

## Unreleased

### 0.2.0 development

- Allow audited operator release of a proven pre-write conversation rejection
  to its original pull inbox, preserving attempt evidence and handoff authority.
- Surface53/schema058 bounds unresolved inbox transport backlog transactionally
  and prevents one agent's endpoints from occupying all normal dispatch workers.
  Native result observation no longer stands in for a blocked call returning.
- Surface52 exposes and enforces per-session capabilities qualified by trusted
  protocol probes and restricted by approved profiles, including connection reuse.
  Unknown contracts cannot inherit execution from advertised adapter capabilities.
- Surface51 enforces registered adapter conversation/control restrictions at
  admission and revalidation; unsupported transport leaves logical inbox delivery intact.
- Add a tested repository procedure for combined offline SQLite/journal/artifact
  backup and restore; strict snapshot validation never repairs incomplete tails.
- Surface50/schema057 fences incompatible writers and mismatched message producers
  at SQLite admission, including connections opened before runtime activation.
- Surface49 connects compatible Codex sessions through one live production
  connection while preserving per-session events, ownership and isolated profiles.
- Native event capture no longer waits on SQLite projection; bounded journal
  batches preserve durable output during streaming bursts and commit atomically.
- Surface 48 requires server-owned control compatibility at admission and dispatch;
  missing/unknown evidence cannot enable steering or interruption by declaration.
  Pi now observes its executable version through a bounded owned probe.
- Surface 47 requires exact integer cc-socks peerProtocol=1 at attach open and
  before send, and persists its redacted observation without inventing an ACK.
- Surface 46 observes Claude stream's approved executable version in a bounded,
  owned probe before readiness. Exact qualified request contracts satisfy explicit
  profile requirements; unknown versions never inherit compatibility by prefix.
- Surface 45 enforces required native request contracts before readiness and maps
  explicit rejection to Codex cancel-only choices without granting policy amendments.
- Surface 44 and migration056 persist redacted native compatibility observations
  separately from caller metadata; an observed version does not verify capabilities.
- Surface 43 and additive migration055 provide explicit operator recovery of managed
  handoffs, preserving attempt facts and fencing stale claim completion without replay.
- Surface 42 and additive migration054 add audited operator operation recovery.
  Cancel only before send-intent, explicitly release uncertain conversation
  delivery to its original inbox, or abandon uncertain command tracking. Current
  attempts are fenced; risk acknowledgement and idempotency are required. Native
  uncertainty/ACK and late captured results remain honest, without automatic replay.

- The operator Approvals dashboard accepts explicit native question/form answers
  for supported Codex and Claude requests. Opening a request submits no defaults.
  Permission decisions remain distinct from input and native delivery; expired
  requests expose their state without an answer control.

- Surface 41 adds scoped discovery through `harness_list(view="bindings")`
  and REST `/harness/bindings`. Endpoints and bounded session history group under
  the canonical agent; current grants and policy restrict visibility. Private
  configuration is omitted; declared capabilities and stored readiness do not
  claim native version verification or process liveness.

- Surface 40 adds revision-fenced profile and endpoint editing/deactivation.
  Changes atomically revoke affected grants and boot approvals; old runtimes
  retain history but cannot borrow the new profile's authority. Migration 053
  extends the existing access audit with redacted configuration change metadata.

- Runtime administration surface 39: `harness_list` endpoint/profile views
  reuse REST services, strict request validation and revision fences. Profile
  discovery on REST/MCP redacts launch paths, environment and secret references.
  Existing endpoint creation, notification updates, boot and reconciliation are
  available without adding per-adapter tools. Full release gates remain pending.

- Start the PR #34 remediation on `feature/v0.2.0`. Package metadata is
  0.2.0; implementation and acceptance gates are tracked in
  `plans/pr34-remediation/IMPLEMENTATION_STATUS.md`. This is not a release
  readiness claim.

### Added

- Added native, bidirectional, non-polling harness sessions (ADR 0004):
  Nexus can now spawn and hold live sessions with `pi`, `codex`, and
  `claude_code` (`stream` substrate), plus send-only injection into an
  already-running interactive Claude Code session via `cc-socks`
  (`claude_code`/`attach`). New MCP tools `harness_list`, `harness_open`,
  `harness_send`, `harness_steer`, `harness_interrupt`, `harness_close`,
  `harness_get`, `harness_event_list`, mirrored at full parity on
  `GET /api/v1/harness/kinds` and `/api/v1/harness/sessions/...`. A live
  session's `turn_completed`/`error` events are also delivered as ordinary
  messages through the existing per-recipient inbox (`notify_target`), and
  the existing routing grammar (`direct`/`capability`/`role`/`tag`) can now
  address a live session's turn input directly through `message_create`, as
  a best-effort hand-off (see the operator guide for its real limits).
  `harness_open`'s `backend` parameter lets a caller select the session's
  model provider/model explicitly instead of silently inheriting the
  operator's own ambient CLI config. New operator documentation:
  [`docs/harness-integrations/operator-guide.md`](docs/harness-integrations/operator-guide.md).

## 0.1.10 - 2026-09-16

### Fixed

- Standardized the message artifact cap at 20 across transports: the dashboard
  Meta-harness REST route no longer applies its own 10-attachment pydantic
  fence, so over-limit lists are rejected by the domain `MAX_ARTIFACTS` with
  the same `{count, max}` diagnostics on REST and MCP.
- Capped tag selector value lists at 20 values per key (`MAX_TAG_VALUES`,
  counted before de-duplication) and made the de-duplication set-based,
  removing the O(n²) scan reachable from `message_create`/`handoff_create`
  tag targets and agent tag registration.
- Added a 256-character ceiling (`MAX_TARGET_FIELD_LENGTH`) to the routing
  target grammar's identifier fields (`agent_id`, `role`, `capability`
  names), so a target can no longer persist an arbitrarily large string.
- Added a 128-character per-item ceiling (`MAX_DEPENDENCY_ID_LENGTH`) to
  `handoff_create`'s `depends_on` ids, mirroring `acceptance_criteria`'s
  per-item bound.
- Rejected exact-duplicate artifact references on `message_create` (a
  duplicate is a caller mistake, never silently deduped - mirroring the
  handoff bounded-list contracts); the error names the offending index and
  the duplicated reference.
- Capped message artifact references at 20 (`MAX_ARTIFACTS`); over-limit lists
  now fail validation with `{count, max}` details before anything is written.
  Note: a HITL approval created before the upgrade with more than 20 artifact
  references becomes un-executable (each approve attempt re-validates and
  reverts to pending); reject such pending approvals and resend within the cap.
- Resynced the dashboard ColorPicker draft text when the `value` prop changes
  while the component stays mounted, so opening another agent's edit form no
  longer shows the previous agent's color.

### Changed

- Bumped the package and distribution metadata from 0.1.9 to 0.1.10.
- Consolidated the duplicated bounded-list count check (acceptance criteria,
  dependencies, message artifacts, tag values) into the shared domain helper
  `check_list_size`.
- REST error envelopes now carry `VALIDATION_ERROR` details (e.g. the
  bounded-list `{count, max}` diagnostics) instead of the lean envelope.
- Documented the 20-artifact cap in the `message_create` MCP parameter
  description and in the `tool-docs/messages` reference resource (version
  bumped to 4 so clients invalidate their cached doc).

## 0.1.9 - 2026-09-03

### Added

- Added list/grid switching to the Artifacts catalog. The Explorer-style grid
  uses type-aware icons and places each artifact's name and size below it.
- Added aggregate acknowledgement flags to outgoing Meta-harness messages,
  with a per-recipient modal showing queued, received, and read timestamps.
- Added the `meta_harness_receipt_display` setting. Inline flags are the
  default; `timeline` preserves the previous separate receipt messages.

### Changed

- Bumped the package and distribution metadata from 0.1.8 to 0.1.9.
- Grey acknowledgement flags now identify messages still waiting on one or
  more targets; they turn green only after every target acknowledges.
- Meta-harness acknowledgement indicators now blend into the message footer
  instead of appearing as badges, and their detail modal opens only on click.
- Completed acknowledgement indicators use a stronger green treatment, image
  artifacts render directly in both preview sizes without Raw/Rich controls,
  and CSV artifacts gain a table renderer in the modal's Rich mode.

## 0.1.7 - 2026-09-02

### Added

- Added the Meta-harness dashboard chat, combining private and broadcast
  messages, direct and broadcast handoffs, agent replies, and terminal handoff
  outcomes in one chronological, agent-filterable timeline.
- Added the operator-only `POST /api/v1/meta-harness/send` surface. It delegates
  to the normal message and handoff use cases, so permissions, communication
  scope, policies, guardrails, and HITL remain enforced.
- Added guardrail assignment by agent capability while preserving explicit
  agent groups and direct agent assignments.

### Changed

- Reworked the Guardrails screen to separate agent-group composition from rule
  configuration, auto-populate agent choices, explain inspected content fields,
  and assist regular-expression authoring with examples and validation.
- Added agent completion results and rejection reasons to Handoff cards and
  details, clearly separated from the original request payload.
- Render structured Meta-harness content as readable fields and lists instead
  of raw JSON.
- Refined the Meta-harness composer to start at one line, grow up to eight,
  blend into the conversation background, and open its recipient menu upward.
- Added on-demand Meta-harness history in batches of 20 with scroll-position
  preservation when older messages are prepended.

### Fixed

- Corrected guardrail assignment and rule validation failures found during the
  usability review.
- Removed competing page-level scroll containers from the dashboard shell.
- Kept newly observed Meta-harness turns at the end of the live conversation,
  even when an existing producer reports a skewed timestamp.
- Prevented deletion of the reserved `operator` identity in both the dashboard
  and the HTTP management API.

### Validation

- Passed the complete suite with 1,594 tests passing and 2 skipped.
- Built the production dashboard and exercised private messages, broadcast
  handoffs, agent replies, result formatting, and agent filtering against an
  isolated live server.

## 0.1.6 - 2026-09-01

### Fixed

- Rebuilt the MCP v1 FastMCP settings model after import so
  `pydantic-settings` 2.15+ no longer reports an unresolved `lifespan`
  forward reference during stdio or HTTP server startup.

### Changed

- Constrained the MCP Python SDK dependency to the compatible v1 line
  (`mcp>=1.0,<2`), keeping the eventual v2 migration explicit.

### Validation

- Verified the installed `okto-nexus serve` executable with the local MiniLM
  embedding provider and a live `/healthz` request.
- Passed the complete test suite with 1,589 tests passing and 2 skipped.

## 0.1.5 - 2026-08-31

### Added

- Rendered `kind`-based message notifications as distinct semantic cards in
  the Graph conversation drawer, including read receipts and handoff outcomes.

### Fixed

- Restored the live MCP smoke test on clean stores by no longer announcing
  capabilities that have not been registered in the fail-closed catalog.

### Documentation

- Documented the live stdio MCP smoke-test workflow, its isolated temporary
  state, cross-platform commands, and successful completion signal.

### Validation

- Verified the real two-agent stdio flow and the complete test suite.

## 0.1.4 - 2026-08-23

### Added

- Detailed and compact activity-based graph representations for agents, with
  profile colours, live status badges, relationship context, and conversations.
- Event timeline visualization with time buckets and expanded filters for
  workspaces, streams, event types, agents, recipients, traces, and time ranges.
- Message-detail hydration and richer filtering for handoff and event APIs.
- Workspace display names and catalog import/export workflows in the dashboard.
- Repository ownership metadata for the main branch.
- Complete PyPI project URLs, keywords, and supported-Python classifiers.
- Contributor and security policies plus structured bug, feature, and
  integration issue forms.
- A dedicated documentation-assets directory for product screenshots.

### Changed

- Improved the Agents, Approvals, Communication, Events, Graph, Guardrails,
  Handoffs, Messages, Policies, and Workspaces dashboard views.
- Advanced the MCP guidance surface to revision 32 while retaining database
  migration 026 and the existing 43-tool default / 46-tool memory-enabled
  surface.
- Clarified that the role and communication profile returned by
  `agent_whoami` form the agent's default operating contract unless explicitly
  overridden for the current task.
- Defined handoffs as the traceable mechanism for executable work, broadcasts
  as shared informational alignment, and direct messages as conversational
  coordination.

### Validation

- Expanded coverage for conversations, HTTP observability APIs, resources,
  surface metrics, feature flags, memory, handoff dependencies, health, replay,
  and verification behavior.
- Added a focused package-metadata regression test.
