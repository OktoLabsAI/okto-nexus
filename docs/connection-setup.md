# Connection setup

Connections keeps a browser draft while the operator advances through Host &
harness, Installation, Folders & login, Connection, Preferences, Authorization,
and Test. Next validates the current step; it does not save configuration.
Advancing Authorization consents to the test and the selected execution limits.

Active runtime connections automatically receive eligible Nexus messages. There
is no separate automatic-reply switch. Select MCP only to stop runtime delivery.
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
must be repeated after a server restart. Closing the panel discards the draft;
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
