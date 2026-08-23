# Changelog

All notable changes to Okto Nexus are documented in this file.

## 0.1.4 - 2026-08-23

### Added

- Detailed and compact activity-based graph representations for agents, with
  profile colours, live status badges, relationship context, and conversations.
- Event timeline visualization with time buckets and expanded filters for
  workspaces, streams, event types, agents, recipients, traces, and time ranges.
- Message-detail hydration and richer filtering for handoff and event APIs.
- Workspace display names and catalog import/export workflows in the dashboard.
- Repository ownership metadata for the main branch.

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
