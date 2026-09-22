# Contract and composition map

Specification versions: supplied 01/02 v1.0; current implementation below is
the P00 legacy baseline, not the target design.

| Boundary | Existing symbols | Evolution rule |
|---|---|---|
| Auth | http.app.ApiKeyAuthMiddleware, identity_ctx.current_agent; application.auth.AgentKeyAuthService | Construct trusted request context from authentication, never payload. Preserve keyless local REST only when no credential is supplied. |
| MCP | server.register_tools → tools.harness.register; envelope decorators only normalize errors | Optional façade; shared application authorization, including cached tools. |
| REST | routes.harness_* → same factory/supervisor helpers, separate _require_operator | Replace duplicated authorization decisions with shared use cases. |
| Canonical identity | IdentityService, SqliteAgentRepo, SqliteSessionRepo | Connection lifecycle reads profile, never upserts it. Presence belongs to a specific binding. |
| Message | MessageService.create_message → _send_uow → delivery/event → commit → _maybe_notify_inbox_subscribers | Reuse transaction for intent; callback becomes wakeup only. |
| Inbox | SqliteMessageDeliveryRepo + inbox services | Add consumption arbitration; retain logical delivery/receipt authority. |
| Work | HandoffService claim/complete/verification/dependencies, governance/approvals | Dispatch must derive from existing authorized claim; native terminal alone is not completion. |
| Runtime | HarnessSupervisor.open/send/close/open_declared, HarnessBootSpec | Preserve existing session table; add endpoint/operation ownership instead of second session entity. |
| Transport | PiRpcConnector, CodexAppServerConnector, ClaudeCodeStreamConnector, ClaudeCodeAttachConnector | Preserve real protocol capability distinctions; registry and versioned façade. |
| Persistence | SqliteHarnessSessionRepo, SqliteHarnessEventRepo; migrations 029 | Additive migration only. MigrationRunner rejects newer schemas; record writer compatibility in target. |
| Outputs | supervisor._handle_event/_persist_event/_deliver_notable_message | Journal first for durable terminal; atomic idempotent projection; ACL-controlled publication. |
| Serve | http.app.build_app; cli.serve.run_serve + watchdog | One owner for runtime/dispatcher. Stdio remains writer/client, not implicit process owner. |
| Artifacts | existing external artifact storage introduced in 028 | Reuse managed storage; no confirmed refs before durable write. |

Historical ADR 0004 freezes ports and prescribes publish-before-best-effort DB.
The current user specification explicitly supersedes those restrictions.
Layering rules remain: no sqlite3/mcp imports in domain/application.

Full legacy schemas, flags, SQLite definitions and measured surface are in
`evidence/p00-contracts.json`. OFF surface must match merge-base's 43-tool
legacy set, allowing explicitly recorded version/flag/schema metadata changes.


## Additive runtime event/lifecycle mapping (0.2.0)

- Event ingress port: `application/runtime_event_ingress.RuntimeEventJournal`;
  file adapter: `adapters/outbound/harness/event_journal.FileRuntimeEventJournal`.
- Captured result and checkpoint: migration 033 `runtime_results` /
  `runtime_journal_checkpoint`, projected atomically with existing `harness_events`.
- `HarnessEvent.event_id` / `sequence` expose existing persistence identities;
  optional `origin` defaults to native for old records. Migration 034 stores
  origin explicitly; peer payload strings cannot set the Nexus event origin.
- Shared process ownership: `RuntimeConnectionLifecycle` leases. Persisted
  connection IDs reuse migration 030's `harness_sessions.connection_id`.
- Runtime lifecycle vocabulary uses `protocol_ready`, `stop_requested`, `stopped`,
  `detached`, `outcome_unknown`. Legacy session `status` is not used to infer
  observed process exit; in particular a detached runtime can retain its last
  RUNNING value while its lifecycle truth is detached.
- Native per-connection/thread IDs remain distinct from canonical agent and
  runtime-session IDs. No new identity registry was introduced.
