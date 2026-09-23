# Legacy surface regression reconciliation

Execution: 2026-09-23, parent SHA 17cb43b plus this worktree; feature/v0.2.0.

The compatibility inventory expected implicit Agent registration, ambient backend
inheritance, unauthenticated captured MCP calls and fabricated ENDED after a fake
close. These expectations conflict with the approved contracts.

Updated test_harness_routes.py and test_harness_tools.py to use the real socket
serve fixture, authenticated MCP, canonical worker and approved isolated profiles.
Standalone test_harness_supervisor.py explicitly seeds canonical identities and
labels its no-journal compatibility scope. It is not production delivery evidence.
Fake close without process observation now asserts detached; repeated close is
idempotent. Terminal capture is durable and does not implicitly broadcast.

Two actual defects found: resolve_substrate discarded a supplied Pi substrate
before validation; live MCP backend/notify_target descriptions still advertised
ambient inheritance, overrides and broadcast. Regression run observed both fail.
Fixed substrate rejection before connector construction and corrected schema
descriptions/module documentation. The same initial run also had three fixture
assertion errors (runtime_session_id column and the internal environment sealing
marker); those were corrected, not counted as product defects.

Commands (all prefixed with rtk proxy):
- .venv/Scripts/python.exe -m pytest -q tests/test_harness_tools.py --tb=short
  Initial result: 5 failed, 19 passed, 2 skipped (29.12s).
- .venv/Scripts/python.exe -m pytest -q tests/test_harness_tools.py tests/test_harness_routes.py tests/test_harness_supervisor.py --tb=short
  Final: 59 passed, 2 skipped (48.88s).
- ruff check tests/test_harness_tools.py tests/test_harness_routes.py tests/test_harness_supervisor.py src/okto_nexus/adapters/inbound/mcp/tools/harness.py
  PASS.

Skipped cases are explicit POSIX attach capability cases on Windows. Native
providers NOT_RUN for this unit. Approved profile positive construction and
per-call override denial both covered. No final phase/gate promotion.
Next dependencies: stale session reconciliation/epoch stamping/stable boot;
durable controls, result publication, P09-P12 remain outstanding.
