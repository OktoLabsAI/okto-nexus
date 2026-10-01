# Binding replacement without executor-wide shutdown

Connector commit 2c84b529fa6cbb462916619e627b25dbd08d6cd5; Nexus and Core product code unchanged.

## Defect reproduced

The real Pi campaign completed its first handoff and closed its session, but the next opening after approved replacement returned executor_not_ready. Waiting for the new binding revision did not recover: the daemon entered STALE_GENERATION while retaining the old lane snapshot. A directed installed test also reproduced RECONCILIATION_REQUIRED for an idle reviewed replacement.

The first campaign separately timed out before control readiness, with another timeout during cleanup. That failure is retained and is not explained by the binding replacement fix.

## Implementation

The Connector adopts a replacement in the existing lane only when:

- The persisted APPLIED replacement identifies the exact previous binding snapshot and the complete new Server application result.
- Identity, Server, executor, agent, workspace, adapter, endpoint, authorization and configuration revisions are unchanged.
- The binding revision advances by exactly one.
- Every retained local session of the affected binding is observed CLOSED with released ownership.
- The selected binding, confirmation, connection and ticket deadline remain current after observation.

Only realization-related fields change. The existing connection, execution owner, ticket and original expiration deadline remain. Other bindings and native owners are not inspected or stopped by this path. Unknown or active target ownership, changed authority, incomplete confirmation, expired tickets or concurrent drift refuse adoption. A new native opening still performs normal Core preparation and qualification.

## Verification

- Initial installed reproduction: one failed positive replacement test and four passing refusal tests.
- Directed source regression: 112 passed before strengthening complete application-result matching.
- Final installed regression: 244 Connector cases and four Nexus TCP/HTTP/WSS journeys passed.
- Two additional installed tests passed: an unrelated active native handle survives idle replacement; a change during target observation refuses adoption. The native handle is a test adapter, not a second real provider.
- Real Pi passed in 446.79 seconds; Codex passed in 316.91 seconds; Claude passed in 292.88 seconds. Each performed two native sessions with approved replacement between them, completed both turns and closes, and removed campaign credentials.
- Campaigns used the same installed wheels on one Windows host over loopback HTTP/WSS. Server release readiness was overridden only for testing; Core native qualification was unchanged.
- Full commands, wheel hashes, retained failures and report hashes: [campaign index](test_runs_20261001_binding_lanes.json).

No release gate is closed by this increment. Final provider/platform acceptance, complete diagnostics and unrelated simultaneous real-provider continuity remain subject to the fixed delivery plan.
