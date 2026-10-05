# M05/M09 — Serve-owned tool credentials and launch configuration

Status: automatic local tool composition integrated; complete M05/M09 acceptance remains open.

When serve owns its advertised API address, the embedded dispatcher prepares session tools before acquiring the native runtime. Approved local configuration is checked before issuance and again before configuration. Migration 086 records the request identity before the canonical capability service runs. That service verifies the live embedded owner inside its issuance transactions, in addition to its existing agent, binding, grant and scope checks.

The one-time secret is written to the protected OS credential store before launch material becomes available. SQLite retains only request identity and non-secret capability metadata. A canceled observer cannot cancel the issuance/vault producer. Reopening a durable reservation through a different owner does not silently reissue material or infer a new lifetime; it requires explicit recovery. Tool reservations are bounded to 128 retained producers/configurations.

Codex and Claude use per-session MCP homes containing public configuration and an environment-variable reference, with directory identity and file-content checks before/after environment construction. Core resolves the precise prepared capability reference into the child environment. The Pi branch composes the existing Core native-action owner using a session-scoped grant; its secret stays in the host. Native build qualification remains enforced separately.

Applied lease renewal already extends the canonical session capability validity, preserving the same secret. Explicit confirmed close removes the OS material and releases the local reservation. Serve shutdown joins issuance producers and removes known stored material only after Core reports no uncertain resources. An uncertain shutdown retains material. Failed database cleanup can retry the metadata mark without deleting the OS value twice.

The normal serve CLI supplies the advertised origin. Lower-level embedders without an advertised address keep the preceding provider-only path; that path is not evidence of full tool integration.

## Verification

The automatic Codex technical-native flow uses public binding/grant/admission, the real serve dispatcher, canonical capability/lease services and real HTTP MCP handlers. The resulting configuration identifies the session, claims and completes domain work, rejects calls after close and cleans its secret. Negative cases cover vault failure before native opening and a canceled issuance waiter whose producer remains owned. The final installed test also waits for lease renewal and calls MCP again with the same secret.

A separate isolated installed-module probe exercised SessionToolVault against Windows Credential Manager with a disposable session-format credential: write/read matched, removal was verified, and the disposable home contained no plaintext file. Its evidence is embedded-tools-os-vault.json. This probe does not constitute a native provider journey.

Development fixes corrected a tuple passed to canonical JSON and changed the MCP test's project_root to the required workspace ID. Final installed results and artifacts are recorded in test_runs_20260930_embedded_tools.json. The native factory, qualification and session-vault backend in these integration tests are technical fixtures. Actual Windows protected storage was qualified in M05_PROVIDER_VAULT.md; that evidence is not a real-provider or full MCP/Pi acceptance campaign.

Final installed results: 133 passed in the normal environment and 70 overlapping cases passed in the actual no-Connector environment, with pip check. The earlier source regression passed 66 cases before final cleanup/renewal assertions; the installed results verify the final package.

## Remaining fixed-plan work

Full automatic Claude and Pi journeys, refreshing the Pi bridge's capability deadline across renewals, restart/adoption of live tool configuration, material-loss recovery and uncertain native ownership remain required. Complete real Pi/Codex/Claude journeys, approval/input, platform/pressure and final release qualification also remain open. No milestone or gate closes here.

Core and Connector artifacts are unchanged. Preexisting user UI bytes remain in the Nexus wheel but outside this commit and UI acceptance. The existing Starlette/httpx warning remains.
