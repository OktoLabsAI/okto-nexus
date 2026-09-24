# Agent connection management — execution in progress

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
regression; documentation/evidence/commit. All new tests currently NOT_RUN.
Unrelated static bundle edits and .nexus-policy-guardrail-test remain protected.

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
legacy canonical nxs_ agent API keys. Expiration does not terminate an already
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
key binding, policy and endpoint/profile revisions.

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
