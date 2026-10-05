# Server shutdown coordinator and administrative client

## Contract and implementation

The Server owns one retained recovery task and one monotonic deadline, fixed by the first shutdown request (default 50 seconds, configurable from 0 to 300). Repeated requests observe the same task and never extend the deadline. Cancellation of an HTTP observer does not cancel recovery.

The coordinator closes the shared productive admission fence and signals passive discovery cancellation before starting embedded and legacy containment concurrently. The legacy owner lease remains held until embedded runtimes, their producers and inventory publication/release have completed. Failed inventory release is retried with the same owner. Only completed, failed inventory cleanup tasks are replaced; in-flight cleanup is retained.

The application sets the Uvicorn Server's should_exit flag only after coordinated drain. During a pending administrative shutdown, the existing transport and owner remain alive. Lifespan shutdown also joins the coordinator before releasing application resources.

### Administrative API

These are two additional maintenance routes supporting NS14.03. They do not replace or redefine the original 24-route R4 acceptance baseline.

- POST /v1/runtime/shutdown accepts a strict JSON object with timeout_seconds. An authenticated operator is required. The response is HTTP 202 while pending or HTTP 200 when drained.
- GET /v1/runtime/shutdown requires an authenticated operator and returns HTTP 200 with RUNNING, DRAINING_PENDING or DRAINED.
- Successful responses use Cache-Control: no-store. The report includes the fixed deadline_monotonic, retained resources and sanitized error_codes.
- Invalid budgets are rejected before closing admission. Ordinary agents cannot initiate or inspect administrative shutdown.
- Resources are conservatively reported as unknown with store_retained. This increment does not qualify the native-process-versus-durable-release distinction.
- After drain, the actual Server exits; a later GET can therefore fail to connect.

### CLI

Set OKTO_NEXUS_API_KEY to the existing operator credential, then invoke:

```text
okto-nexus admin shutdown --url http://127.0.0.1:8000 --timeout-seconds 50
okto-nexus admin shutdown-status --url http://127.0.0.1:8000
```

These commands call the running Server and do not bootstrap another owner or open its store. They do not follow redirects or inherit proxy settings. An accepted pending request returns JSON and client exit code 0 while the Server continues recovery. A transport failure returns OUTCOME_UNKNOWN and directs the operator to inspect status. Credentials are read from the environment, not command arguments.

## Verification

The focused tests cover operator authorization, invalid budgets, shared admission, first-deadline reuse, retained health and operation lookup, legacy lease retention, native recovery without reopening, a child CLI over real loopback TCP, and a canceled observer followed by recovery from an inventory release failure.

The TCP test runs Uvicorn on the same event loop as the fixture-owned application lifespan and executes the administrative CLI in a separate process. It proves actual HTTP transport retention and Uvicorn exit after recovery. It is not a standalone serve-process, operating-system-signal or actual-provider acceptance test.

The first expanded source run found an incorrect CLI authentication header and a stale legacy error code after successful recovery. Both were corrected; the failed XML remains preserved. An earlier test setup used the wrong fixture header key and was interrupted during cleanup; it is not counted as a completed test run.

See test_runs_20261001_server_shutdown.json for final installed results and artifact hashes. Source results overlap the installed cases.

## Remaining NS14.03 acceptance

SIGINT/SIGTERM still follow ordinary Uvicorn signal handling and need retained administrative-lifetime qualification. The complete two-runtime late-open/stuck-close/release matrix, qualified process-versus-release reporting, recovery when the authorization store is unavailable, full standalone Server-process acceptance and platform coverage remain pending. These requirements are unchanged. This increment does not close NS14.03 or any release gate.

Core and Connector artifacts are unchanged. Earlier Pi/Codex/Claude evidence remains tied to its original artifact tuple. Preexisting modified UI assets are present in the wheel but this campaign does not accept UI behavior or language.
