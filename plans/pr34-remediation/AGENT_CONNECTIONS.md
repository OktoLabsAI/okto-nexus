# Agent connection management — implementation and qualification

Baseline: c692722301ddfe9b8d07abd04c36416c5ce2d233, feature/v0.2.0.
New user scope after the completed PR34 remediation. Prior qualification is
historical and does not qualify these changes.

Operator-approved default: 86400 seconds (24 hours). Per-agent null inherits,
zero explicitly means unlimited, positive seconds override. Expiration is
captured on issuance; changing a default affects future keys. Revocation and
disabling a method take effect independently of expiration.

Connection credentials authorize opening one approved endpoint, never choosing
an identity, executable, workspace or profile through the payload. They are
not canonical agent API keys or execution grants. Repeat requests use the same
durable open identity; an uncertain opening is never replayed automatically.
Native control/work keeps the existing grant/handoff authorization.

Pi RPC, Codex app-server and Claude stream start managed processes. A copied
HTTP request does not adopt the caller's existing interactive conversation.
Claude attach keeps its existing explicitly approved external target semantics.

Tasks: policy/key persistence; shared authorization; REST/MCP bootstrap;
Agents UI and global setting; focused security/integration tests; full relevant
regression; documentation/evidence/commit. Final affected acceptance at 12d352c: 85 PASS. Full regression: 2653 PASS /
1 FAIL / 122 SKIP; the fixture failure was corrected at 3ca5c55 and independently
verified by 20 PASS across 10 runs. This is not a full-suite PASS.
Unrelated static bundle edits and .nexus-policy-guardrail-test remain protected.

## Native connection defaults (subsequent user request)

Both `feature_harness_integrations` and `feature_harness_attach` now default to
true, in the config model and CLI/environment resolver. Stored settings and
explicit environment/CLI false overrides retain their precedence. This does not
change per-agent method policy, endpoint/profile approvals, boot approvals,
platform support or grant/handoff authorization. An existing process must be
updated/restarted to pick up the new build/defaults; a stored false is not reset.
See [default-change evidence](evidence/default-native-connections.json).

## Operator workflow and contract v1 (surface 59 / schema 065)

1. In Agents, use the Connection methods button on the existing agent card.
   MCP defaults to allowed. A native adapter without an approved endpoint is
   initially unavailable; existing approved endpoint configuration preserves
   its previous permission unless an explicit method override disables it.
   Enabling a method never creates an endpoint or approves a process profile.
2. Set the allowed methods and expiry: inherit, custom seconds, or unlimited.
   Save uses the policy revision; concurrent stale changes return CONFLICT.
3. For an approved endpoint, issue a key and copy the JSON HTTP request.
   The request contains POST URL, Authorization bearer and an empty JSON body.
   Pass that private template to the chosen harness's HTTP client. It must not
   add agent_id, workspace, executable, profile or command options.
4. The opening response gives the bound agent/endpoint/session, lifecycle state,
   durable request_id and reused flag. These are opening facts, not proof that
   a task ran. A repeated request returns the recorded opening, including a
   stopped historical session; issue a new key for a new opening after closure.
   Pending or uncertain openings require recovery, not blind retry with a new key.
5. Revoke an individual key in Agents. Disabling a method revokes its keys and
   blocks new opens, commands/work and conversation dispatch through that method.
   Re-enabling it does not resurrect revoked keys. Read, interrupt and close
   remain available for recovery. Already-started effects are not undone.

Global setting: Settings → Connection key TTL seconds, default 86400.
Environment/CLI equivalents: OKTO_NEXUS_CONNECTION_KEY_TTL_SECONDS and
--connection-key-ttl-seconds. Zero is explicit unlimited; per-agent null means
inherit. The setting applies to these scoped connection credentials, not to
legacy canonical nxs_ agent API keys. Boolean, fractional, string and null global
values are rejected; unlimited requires explicit integer zero. Expiration does not terminate an already
opened runtime or grant it additional execution authority.

REST:
- GET/PUT /api/v1/agents/{agent_id}/connections (operator)
- POST /api/v1/agents/{agent_id}/connection-keys (operator or self with open grant)
- DELETE /api/v1/agents/{agent_id}/connection-keys/{key_id} (operator)
- POST /api/v1/connections/open (connection bearer only, empty object body)

MCP: harness_list(view="connections", maintenance={...}) uses the same service,
with action list/configure/issue/revoke. Configure requires expected_revision,
methods and key_ttl_seconds. An authenticated self-bootstrap credential is capped
by its original grant's expiration and remains dependent on revocation, canonical
key binding, current canonical permissions, policy and endpoint/profile revisions.
Permissions are revalidated before native start, including after reservation.
When native integration is enabled after starting serve without a runtime owner,
opening returns 409 with a restart instruction instead of attempting a launch.

Secrets are SHA-256 hashes at rest and appear only in the issuance response
(Cache-Control: no-store) and transient UI state. Ordinary listings, audits and
subprocess environments never receive the plaintext. A connection key fails
canonical REST/MCP authentication and cannot send turns or complete handoffs.
It is a bearer capability, not device attestation or proof of possession of an
ephemeral asymmetric key. Logical identity uniqueness does not forbid multiple
explicitly configured endpoints; each endpoint retains its exclusive executor.

## Migration and recovery

Migration 065 is additive and idempotent through the existing runner. It does
not rewrite agent role, skills, metadata, permissions, existing endpoint approvals
or existing API keys. Keys bind endpoint/profile revisions; editing those
configurations invalidates old credentials. Update/restart all clients and the
serve owner before adopting this schema. Older code refuses a newer ledger at
startup; already-open old runtime writers are fenced once connection policy or
credentials exist. This extends the existing connection-factory capability
marker mechanism and is not a separate authentication mechanism.

Back up the store using the existing operational procedure before a production
upgrade. Recovery is forward-only: revoke keys, disable a method or disable
native admission, then inspect existing opening/session/operation records.
Do not reverse the migration, delete unknown operations, replay uncertain starts,
or reuse the fixture configuration from tests with a personal provider.

## Local build preservation

The three pre-existing modified static files were preserved byte for byte.
The new content-addressed assets were added separately. The generated index was
staged directly from the isolated build (git hash-object/update-index); the
working-tree index.html was not overwritten and its earlier local content stays
available. Consequently those pre-existing local files remain dirty after the
milestone commit. They are not part of the implementation's source changes.
A clean checkout of the milestone contains the new dashboard entry point.
The snapshot hashes remain private in .git/pr34-evidence/agent-connections.

## Evidence collected (source boundaries retained)

- Baseline reproduction on clean c692722 archive: expected failure because the
  connection-key request returns HTTP 404; no missing-import failure.
- Final affected acceptance at 12d352c: 85 PASS, including all four synthetic connectors, a fifth
  registered adapter, actual HTTP/MCP, authenticated stdio, concurrency, grants,
  revocation/expiry, migration preservation and isolated Edge UI. It also includes
  settings, PR34 authorization, grants and writer-contract regressions.
- Full Windows suite: 2653 PASS / 1 FAIL / 122 SKIP, 2915.84 seconds. It began
  at 0646a56 while later cbecfbe/12d352c changes landed; it is not an immutable
  full-suite run at final HEAD. Final affected acceptance independently qualifies
  the changed production paths at 12d352c.
- The single failure was PermissionError in a pressure-test snapshot reader
  during Windows atomic replacement. Test-only correction 3ca5c55 retries that
  transient read under the existing deadline and checks worker liveness. Ten
  independent actual-process runs passed (20 tests). No full-suite rerun or
  global PASS is claimed. Runtime/package source remains 12d352c.
- Intermediate suite: 2635 PASS / 11 FAIL / 121 SKIP. Failures were stale
  surface/migration expectations collected before updates; retained as failed
  intermediate evidence.
- Live MCP client: PASS; frontend TypeScript/Vite build: PASS; wheel/sdist and
  Twine checks: PASS; final 12d352c wheel HTTP/MCP/dashboard smoke with the
  installed production dependency set: PASS. No installed files were changed.
- Full Ruff: 862 diagnostics on baseline and current tree; new files PASS.
  This is unchanged baseline debt, not a clean full-tree lint result.
- Generated Vite shader text retains a third-party trailing space in the bundle;
  handwritten source passes diff whitespace checks. Generated JS was not hand-edited.
- Native providers: NOT_RUN in this follow-up. No earlier native counts reused.
- The [UI screenshot](evidence/agent-connections-ui.png) contains only disposable
  fixture identities, after credential revocation and removal from the UI.

Commands, hashes, test names and final statuses are recorded in
[evidence/agent-connections.json](evidence/agent-connections.json). Private raw
logs and XML remain under .git/pr34-evidence/agent-connections.

## Applying the build to the running local installation

An installed serve process was observed running during this follow-up. Its
installation and personal store were not changed. The new wheel was tested with
both development dependencies and the installed tool's dependency set, using a
separate import directory, disposable store and real HTTP/MCP surfaces. No native
process was launched by these packaging smokes.

For rollout, stop the current serve owner through the existing shutdown
procedure, preserve/backup the store, reinstall the built 0.2.0 wheel with the
existing Python/serve extra and pinned dependency versions, then start the owner
with its approved configuration. Run the installed smoke helper only against
its own disposable store. Do not use a still-running old process with files
replaced underneath it. No reverse migration or automatic uncertain replay.

## Regression evidence and source mapping

The clean baseline c692722 returns 404 for the new key request. Additional
behavioral reproductions recorded a missing-owner 500 at 0646a56, and at cbecfbe
both an opening after permission revocation and false silently becoming unlimited
expiry. The final tests reproduce each boundary and verify its correction;
these are behavior failures, not missing imports or private mock contracts.

- AgentConnectionService and connection_policy implement identity-bound issuance,
  expiry, policy revisions and grant-dependent validation; migration 065 persists
  these records without replacing agent identity or creating a second inbox.
- RuntimeAccessService, RuntimeOpenService and SqliteRuntimeRequestRepo apply
  admission checks through reservation and before the external start effect.
- REST connections routes and MCP harness_list share those use cases.
- AgentConnectionsPanel exposes policy, endpoint selection, one-time display of
  the credential, request copying and revocation.
- test_agent_connections.py and test_agent_connections_dashboard.py verify the
  composed surfaces; check_agent_connections_install.py verifies packaged assets
  and actual HTTP/MCP using a disposable store and no native launch.

Full symbols, reproduction commits, commands and result boundaries are in the
evidence JSON. Native provider execution remains NOT_RUN for this follow-up.
