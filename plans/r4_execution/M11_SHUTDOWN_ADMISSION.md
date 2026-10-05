# Shared in-memory shutdown admission fence

Nexus a389087; unchanged Core c2aed11 / 0.2.49.dev0 and Connector dca0863.

## Implementation

One RuntimeAdmissionFence belongs to the dependency container and is shared by the R4 and legacy MCP/REST authorization compositions. Closing it performs no database or native wait. Productive authorization checks it before storage access; authorized read, events, interrupt, close and maintenance continue through their existing policy checks.

The R4 resolver projects runtime_draining for new productive intents. Submission checks the fence again for an operation that has not already been admitted, so a resolution prepared before shutdown cannot bypass the stop. Existing admitted R4 operation replay and history remain available without another native write.

The canonical legacy authorizer refuses open, send, steer and new execute_work authority while fenced. The trusted external-work return path exempts only execute_work completion, with all existing identity, grant and receipt checks preserved. It does not exempt a new opening.

The Server lifespan closes the shared fence before awaiting embedded shutdown or storage cleanup. A fresh dependency container is required for a new Server lifetime; the closed fence cannot be reopened by an application request.

## Evidence

Focused source tests verified a pre-resolved R4 turn refused without an operation row or native send, existing-operation replay/history, disabled fresh opening, authorized close, cached authorizers sharing the fence before any storage access, real legacy REST/MCP turn refusal and close, and external work returned after detach/quarantine while draining. The lifespan ownership test now verifies the fence is already closed at the pending report.

Installed results: 52 R4 cases and 26 legacy cases passed on the same final artifact tuple. Package bytes matched source/wheel/installation, and pip check passed. See the [manifest](test_runs_20261001_shutdown_admission.json). The seven focused source cases overlap this installed coverage.

## Remaining contract

This implements the shared admission mechanism and its lifespan trigger. The public shutdown coordinator/command must set this same fence before starting its owners, keep administrative HTTP available during pending recovery, and apply the single Server-wide budget. Previously admitted/in-flight work still requires the existing dispatcher/Core shutdown ownership handling.

The complete late-open/release fault matrix, qualified process-versus-durable-release report and platform acceptance remain pending. This increment does not close NS14.03 or a release gate.
