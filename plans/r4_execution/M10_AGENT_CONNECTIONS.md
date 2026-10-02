# Agent connections and contextual execution

User-approved scope, updated 2026-10-02:

- Remove legacy connection setup and scoped opening credentials. Keep original
  MCP HTTP authentication with the existing agent API key and canonical execution.
- Agents > Connections is an icon with tooltip. Its Local / Remote / All policy
  restricts execution; selecting a location grants neither identity nor execution.
- Complete local configuration stays in Agents > Connections: integration,
  installation discovery/version check, provider environment, workspace mappings,
  binding consent and explicit bounded execution permission. The Connector owns
  remote profile/identity, installation and integration configuration.
- Workspace is message/task context, not an agent identity setting. Authorizing a
  host directory creates a workspace mapping, not an agent default. Dashboard
  operations/history use the message's workspace and selected recipient.
- Remote browser choices are existing Connector bindings. The browser does not
  prepare a remote installation or offer remote integration configuration.

Implementation adds an operator-only, revision-checked execution policy API and
an additive policy table. Existing agents initially retain All and their existing
canonical authorizations; migration issues no grants. Saving Local or All requires
a selected local integration. Existing historical bindings remain inspectable.
The source guard includes the policy revision, invalidating earlier proposals,
resolutions and pending dispatches. Runtime access rechecks location/integration
for effects and grant issuance. Containment remains possible under an already
applied lease; policy changes do not invent a replacement lease identity.
The migration also fences writes by older Server processes, using an additive
SQLite connection capability on operation, dispatch, lease, policy and retired
runtime tables. Current writers register that capability; old connections may
read history but cannot bypass the policy by dispatching through older code.

Legacy key issuance/opening HTTP routes and MCP issue/configure actions are
removed. The legacy opener and profile/endpoint creation refuse new connections.
Historical records and credential revocation remain available. New canonical
setup still passes the existing consent, grant, credential, host and workspace
checks. Browser grant expiry is normalized into the database's fixed-width UTC
format before validation/persistence.

Verification before the installed campaign: 21 source/backend/browser checks
passed for policy, local setup and message operations. The broader source run
retained three failures (27 passes): two exposed browser timestamp rejection,
and one expected a completed inventory request to remain pending after reload.
The corrected focused run passed 10 cases, including policy change between
admission and dispatch, bounded local permission and refresh recovery. Evidence:
`evidence/agent-connections-source.xml` and
`evidence/agent-connections-source-corrected.xml`.

The first installed campaign retained 73 passes and one failure, with unchanged
inputs, on wheel `84dd7024a443c589ff6838456f2b7b278e113dbf62d3136a023e8142f717e3a2`.
The failure was the refusal status for an implicit disabled endpoint falling
through to the retired opener (422 instead of the expected conflict). It has
been corrected. Four focused source checks then passed for that refusal,
old-writer fencing, additive migration/history preservation and complete local
configuration with a saved integration. MCP surface revision is 65 and identity
documentation version is 31.

Final installed validation passed **87 tests in 490.45 seconds**, with
`changed_inputs=[]`. The isolated Windows/Python 3.13.1 environment loaded Nexus,
Core and Connector from installed distributions, with bytes checked against their
wheels. Edge exercised local setup, permission issuance, message-scoped actions,
lost-response recovery, remote binding visibility and policy editing. Backend
coverage included stale reviews/dispatch, old-writer refusal, preserved close,
legacy credential refusal, migration history, original MCP HTTP and NS15.05.

- Nexus wheel: `a303388da14cbfe2efc848f833046f0274c50bb92bf45596d998c3b527705265`.
- Nexus sdist: `41a0e54aac80a1e10a14169c15a01883bbe3077b4cce1d2264afd0e66981a564`.
- Core wheel: `7f19885f28b16dbfce66b969ab42c79b9947246416c71147315006b6e618b1f6`.
- Connector wheel: `93d78a75c5ad81bbdd96e648be136f0f6b2cfd0a53f350266a1c9f96fc449104`.
- Final campaign: [manifest](evidence/agent-connections-final-installed/campaign.json),
  [JUnit](evidence/agent-connections-final-installed/tests.xml),
  [build](evidence/agent-connections-final-build/manifest.json).

The same validated Nexus wheel is now installed in the user's global uv tool
environment with the existing serve extras. All 72 dependency versions were
preserved; dependency validation passed. Byte comparison verified 385 Nexus
files and 96 Core files against their wheels. See the
[global installation verification](evidence/agent-connections-global-install.json).
The running Server was not restarted; restart it to load the application/UI.

Synthetic peers do not qualify providers or independent hosts. CI remains
deferred, cross-machine acceptance requires manual user participation, and the
macOS production implementation remains queued behind these architecture changes.
No product gate is closed by this increment.
