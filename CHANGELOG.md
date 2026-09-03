# Changelog

All notable changes to Okto Nexus are documented in this file.

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
