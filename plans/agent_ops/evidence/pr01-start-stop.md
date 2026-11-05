# PR-01 — detached start/reuse and canonical local stop

Implemented the application lifecycle facade and local OS/HTTP adapter. Saved
context contains resolved non-secret configuration, interpreter/venv, working
directory and allowlisted environment references. OS locks and durable launch
token fence concurrent starts before the child takes canonical Server ownership.
No shell is interpolated, terminal streams inherited, provider invoked or real
credential copied. Stop names instance/generation and uses the same coordinator
as `/v1/runtime/shutdown`; a durable generation-correlated shutdown receipt
distinguishes completed drain from uncertain disappearance.

Validation uses RTK and the repository Python on Windows 11 / Python 3.13.1:

- `tests/test_service_process.py`: **1 passed** (19.36s). Three actual concurrent
  launcher processes converged on one Server, survived launcher exit, reused
  saved configuration, restarted with a new generation, rejected an old stop
  request, then drained and preserved the database. XML: `pr01-detached-process.xml`.
- Focused lifecycle/config/import and existing real signal-shutdown regression:
  **66 passed** (49.42s); results captured in `pr01-start-stop.xml`. Command:
  `python -m pytest tests/test_service_start.py tests/test_service_readiness.py tests/test_service_inspection.py tests/test_serve_lock.py tests/test_serve_args.py tests/test_import_boundary.py tests/execution_r4/test_cli_http_only.py tests/execution_r4/test_server_signal_shutdown.py -q -x --junitxml=plans/agent_ops/evidence/pr01-start-stop.xml`.
- Scoped Ruff and whitespace checks passed.

The initial focused run (45 tests) passed. An earlier collection command used
an incorrect existing shutdown test filename and collected no tests; the corrected
regression uses `tests/execution_r4/test_server_signal_shutdown.py`.

Remaining scope: installed supervisor routing, user-service registration,
operational logs/rotation, more specific startup diagnostics, explicit recovery
of an interrupted launch before a child PID was recorded, Connector lifecycle,
installed wheels and platform/provider campaigns. A stalled pre-spawn receipt
is deliberately retained as unresolved; it is never automatically timed out
into a second launch. No whole SVC scenario or M1 acceptance is promoted here.
