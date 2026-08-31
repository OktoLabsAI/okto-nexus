# Changelog

All notable changes to Okto Nexus are documented in this file.

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
