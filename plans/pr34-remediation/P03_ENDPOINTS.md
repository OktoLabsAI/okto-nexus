# P03 — approved endpoint persistence (in progress)

Implementation parent: `8207e7b` on `feature/v0.2.0`. No personal store migrated.

Migration 030 adds runtime_profiles and agent_endpoints, binds harness_sessions to
canonical workspaces/presence, and retains runtime audit history on agent deletion.
029 is unchanged. Historical sessions remain legacy_unlinked, without invented
liveness or reconstructed agent capabilities. GET /api/v1/harness/diagnostics is
operator-only and explains recovery from trusted backups.

EndpointService and SqliteEndpointRepo implement approved profiles and bindings.
Production REST and MCP open use prepare_runtime before constructing connectors.
Bindings require a registered, active Agent and exact workspace. Ambiguity fails
closed unless an endpoint is explicitly selected. Per-call environment overrides
are rejected. Profiles default to isolated homes and minimal OS environment;
inherit_ambient is explicit. Environment secret references resolve outside SQLite
transactions. Nexus credentials are stripped even when aliased to another name.
Only profile ID/revision/inheritance diagnostics are returned. Native launch
arguments are constrained; Pi provider/model pairs remain configurable. Codex
starts with read-only sandbox and on-request approvals by default.

Supervisor records a separate canonical presence and updates it on native events.
Close detaches only that presence. `detached` records our connection ending; it
does not prove that an attached process exited. The runtime never upserts Agent.

Commands and observed evidence:

- `.venv/Scripts/python.exe -m pytest tests/test_runtime_endpoints.py tests/test_import_boundary.py -q`
  — **19 PASS**, evidence/p03-gate.log. Includes upgrade from 028/029, repeat
  runner, foreign-key integrity, backup integrity, old-writer rejection, exact
  profile preservation, canonical presence, role/capability/tag/broadcast routing,
  ambiguous bindings, approved environment and negative configuration checks.
- `.venv/Scripts/python.exe -m pytest tests/test_pr34_remediation.py -q -k 'not replay_keeps and not one_delivery and not forward_preserves and not terminal_storage and not expired_relay and not open_does_not_fabricate and not committed_delivery'`
  — evidence/p03-progress.log. Seven regressions belong to later phases and are
  explicitly deselected, not PASS.

Operational procedure: stop writers before upgrade; take SQLite online backup
including committed WAL state; run the forward-only packaged migration runner.
Older binaries reject the new ledger. Recovery uses an independently verified
backup with a matching binary; never run reverse migrations against live data.
Create profiles and endpoints through operator REST before opening runtimes.
Disable integrations to contain new admission; this is not the final feature gate.

Still pending: observed health for idle processes and restart reconciliation
(P06/P07), profile/endpoint administrative update parity (P04/P11), scoped grants,
durable dispatch, and full native campaign. Local Codex and Claude are authorized
by the operator; Pi native remains NOT_RUN. These fixture results are not native
connector evidence. P03 remains IN_PROGRESS until the dependent lifecycle checks.
