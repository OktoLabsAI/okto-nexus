# M03/M05/M09 - Local discovery and real embedded Pi

The serve CLI now accepts repeated --harness-root directories plus --pi-install-root and --pi-node. Paths must exist and be absolute, roots are deduplicated and bounded, and the Pi options must be supplied together. These are local owner arguments. They are not accepted in an execution intent or added to the public inventory projection.

EmbeddedInventoryOwner passes this configuration to the existing passive Core discovery API at startup and on scheduled refresh. No wrapper is executed for discovery. Core still verifies trusted roots, package identity and the native build allowlist. Approval of a discovered installation/workspace still uses the canonical realization and binding flow.

Example for a local Windows installation (replace the user path):

    okto-nexus serve --harness-root "C:/Program Files/nodejs" --harness-root "C:/Users/USER/.pi/agent/install" --pi-install-root "C:/Users/USER/.pi/agent/install" --pi-node "C:/Program Files/nodejs/node.exe"

For PATH discovery, approve the actual binary's installation directory with --harness-root. Empty trust remains empty; the application does not silently trust every PATH entry.

## Real Pi journey

The opt-in test uses a disposable Nexus store and workspace, the actual local Pi 0.87.1 installation, existing provider login under the approved user HOME, and Windows Credential Manager. Real Core discovery, native build qualification, production native factory, owned Pi socket and extension remain enabled.

Using public HTTP binding/grant/admission routes and the normal application lifespan, the test starts Pi through the serve dispatcher, waits for automatic applied lease renewal, then asks the real model to get, claim and complete a disposable handoff through the native tools. It verifies canonical work completion, three native actions, successful turn/close receipts, no WSS tickets, and removal of the session credential after confirmed cleanup. Credentials and model response text are not written to the evidence report.

Existing agents and disposable domain work are fixture prerequisites. The test overrides only the Server's overall R4 release-readiness check, which remains false in production. HTTP is exercised through TestClient in the application process. This proves real local provider integration; it does not prove independent-process serve CLI, browser, remote Connector, or complete release acceptance.

## Development evidence

- A test bootstrap initially attempted to reinsert the preexisting operator; it now uses the existing identity.
- The first cold discovery observation took 207.290 seconds and exceeded the existing 120-second freshness limit. Realization correctly refused stale evidence. An independent profile measured about 20 seconds. The journey now waits for FRESH through the public inventory route and scheduled refresh. Neither content hashing nor the TTL was weakened.
- A test-only 20-second lease expired during real preparation. The real campaign now uses the production default of 120 seconds and still requires renewal before the turn.
- The test initially supplied the Pi configuration directory as provider_home. That option sets HOME/USERPROFILE; using the approved user HOME allows Pi to find its existing .pi/agent login without reading or exporting provider secrets.

The failed XML records are retained. The source campaign passed after these test corrections. The installed real-provider case passed in 109.03 seconds. The normal and no-Connector regression campaigns each passed the same 38 cases; pip check passed in both environments. All package source/wheel/installed bytes were verified before testing. Exact package/command evidence is recorded in test_runs_20260930_local_discovery.json.

## Remaining fixed-plan work

Codex and Claude automatic managed tool journeys, the real remote Connector journey, live recovery, decisions/input, UI/CLI, platform/failure/migration and release gates remain open. Core and Connector packages are unchanged in this increment. Preexisting user UI bytes remain in the Nexus wheel but outside this change and its acceptance.
