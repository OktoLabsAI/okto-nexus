# Connection setup

Connections keeps a browser draft while the operator advances through Host &
harness, Installation, Folders & login, Connection, Preferences, Authorization,
and Test. Next validates the current step; it does not save configuration.
Advancing Authorization consents to the test and the selected execution limits.

Active runtime connections automatically receive eligible Nexus messages. There
is no separate automatic-reply switch. Selecting MCP only in this managed
connection editor disables the agent's runtime policy. Adding another external
MCP client to an existing identity is a separate operation and must not change
that runtime policy.
Execution grants, tool approvals and loop protection still apply. Legacy JSON
`automatic_reply` values are accepted for compatibility and normalized to true.
Existing canonical connections are upgraded without changing their grant limits.

Installation automatically selects a single available candidate and checks the
selected candidate against current inventory. When needed, its version command
runs automatically without provider credentials. Existing verified observations
are reused. The spinner blocks Next until verification completes. Retry reads the
latest inventory first, so a lost successful response does not repeat the probe.
Refresh rediscovers installations; Details exposes paths and diagnostic errors.
These checks do not save a connection or grant runtime execution permission.

Test connection opens a temporary Core session with the selected installation,
workspace, login directory, model and native preferences. It requires a successful
model response containing `NEXUS_CONNECTION_OK` and confirmed cleanup. The test
does not create a Nexus binding, delivery grant or automatic reply policy, and
does not verify agent messaging or Nexus tools. Details shows actual test stages.

Finish applies policies, folders, binding, preferences and the execution grant
inside one database transaction. Failed validation rolls back the complete change.
Endpoint revisions are handled inside that transaction. An external configuration
change requires reopening the setup; it is never silently overwritten. Successful
Finish requests have durable idempotent receipts. Tests expire after one hour and
their in-memory results are lost after a server restart. Without a committed
Finish receipt, another test requires a new explicit review and consent; absence
of a result does not prove that no model turn ran. Closing the panel discards the draft;
an already started test completes and closes its temporary session.

Import JSON and Export JSON appear at the top of Host & harness. The Core-owned
`okto-nexus-connection`, version 2 includes portable harness preferences, policies
and requested authorization limits. It excludes credentials, agent identity,
execution-host selection, installation identifiers, workspace/login paths,
workspace names, secret references, active grants and test receipts. Legacy version
1 imports discard these destination fields too. Import never authorizes execution.
Select an installation and enter folders on the destination host.
Reopening a single saved connection loads its complete settings for export.
When several connections exist, select the existing connection on Host & harness.
`runtime_enabled: null` and `session_policy: null` preserve inheritance from the
destination Server's global defaults.

Workflow steps show green for complete, amber for partial and muted for pending.
Imported preferences cannot complete installation checks, destination folder
selection, consent or a connection test.

The Connector accepts the same document with `configure --file` for guided local
provisioning. `configure` also works without JSON. Operator approval and execution
authorization remain Server-controlled. `connection-config apply` remains the
explicit Server-local automation path, with folders supplied as separate flags.

## Recover an interrupted Server-hosted setup

The Connector persists the exact request and baseline before testing and records
the submission checkpoint before each Test or Finish call. Reusing the same
request ID first asks Nexus for its durable Finish receipt. A matching receipt
returns the original binding and grant result without retesting or reapplying
configuration. If Finish has not committed, an already submitted test is only
observed. A missing test result is reported as `SETUP_TEST_UNCONFIRMED`, including
after a Server restart; no automatic model turn is sent.

Operators can inspect `GET /v1/connections/setup-commits/{setup_run_id}` or match
the saved complete request with `POST /v1/connections/setup:recover`. Both are
read-only and require current operator authorization. Matching uses the same
configuration normalization and request hash as Finish. A changed request is a
conflict. A missing receipt is `NOT_FOUND` at stage `connection.setup_commit`;
it does not assert absence of test or host effects. The dashboard management
prefix exposes the same handlers for its existing operator authentication.

An older Server without recovery support leaves the attempt unconfirmed; the
Connector does not silently repeat setup. `saved: true` confirms the configuration
commit only, not a live harness session or completed work. This recovery path
does not change the Connector-hosted proposal workflow.

## Connector and Server version compatibility

The Connector checks the public `/v1/connections/protocol` contract before using
R4 execution. This check requires the advertised Core version to equal the Core
installed with that Connector, in addition to the management revision, protocol
major, snapshot format and advertised R4 support. Equal wire revision names alone
do not make different Core package versions compatible.

The following exact pairs have been checked through the installed Connector's
`NexusHTTPClient.r4_protocol()` and the installed Server's public HTTP endpoint:

| Connector / its Core | Nexus Server / its Core | Public protocol result |
| --- | --- | --- |
| 0.0.11 / 0.0.13 | 0.3.2 / 0.0.13 | Compatible |
| 0.0.11 / 0.0.13 | 0.3.3 / 0.0.14 | Refused: `VERSION_INCOMPATIBLE` |
| 0.0.12 / 0.0.14 | 0.3.2 / 0.0.13 | Refused: `VERSION_INCOMPATIBLE` |
| 0.0.12 / 0.0.14 | 0.3.3 / 0.0.14 | Compatible |

Both crossed pairs refuse at stage `protocol`, with `possible_effect=false`.
The compatibility check sends one uncredentialed GET and does not register an
executor, issue a ticket or grant, create a binding/session, or submit work.
Use an explicitly coordinated compatible installation when a pair is refused;
do not bypass the version check or downgrade an existing database to obtain a
connection. Connection attempts do not authorize implicit upgrades or stopping
current work.

“Compatible” here qualifies public protocol negotiation, not authenticated
execution, provider credentials, daemon lifecycle, remote TLS or a two-host
deployment. The historical artifacts were built from Nexus
`c1e78e26fb2bd57ace3370417a2cb7529856b603` and Connector
`a3017d97b6a295cb2b46b9dd391b4c04ed121ee2`; the qualification manifest pins all
wheel hashes, including the current 0.3.3/0.0.12 artifacts.

This R4 check is separate from external MCP client compatibility. New
[terminal coordination](terminal-coordination.md) features require their
advertised receipt/passive-observation capabilities and refuse Servers lacking
them; they do not silently fall back to unsafe legacy replay. The table does not
claim to qualify specific external Claude/Codex client versions.

Evidence: [installed version-pair qualification](../plans/agent_ops/evidence/r3-compatibility-boundaries/compatibility/qualification.json).
