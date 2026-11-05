# PR-01 — local instance readiness and passive status

Implemented pure identity/readiness contracts, a local-operator HTTP projection
and `okto-nexus service status [--json]`. The identity includes canonical home,
database, component and effective OS principal (Windows token SID / POSIX UID).
Active version is captured at startup; status correlates generation and PID
against held OS guards and rejects version/protocol mismatch. Status is bounded,
does not follow redirects/proxies and does not initialize absent storage.

Validation on Windows 11 / Python 3.13.1:

- `python -m pytest tests/test_service_readiness.py tests/test_service_inspection.py tests/test_serve_lock.py tests/test_import_boundary.py tests/execution_r4/test_cli_http_only.py -q -x --junitxml=plans/agent_ops/evidence/pr01-readiness.xml`: **36 passed**.
- `python scripts/measure_agent_ops_baseline.py --inspect-service --output plans/agent_ops/evidence/pr01-readiness-process.json`: real disposable foreground Server reached ready; CLI and HTTP agreed on generation; canonical shutdown reached DRAINED and passive CLI then reported stopped.
- Scoped Ruff check passed. Commands use the repository interpreter and RTK.

Tests cover local operator access, denial to remote/participant/cross-origin
requests, drain without reopening admission, absent ownership, version changes,
wrong instance/generation, redirects and unreachable live ownership. The process
exercise uses only a synthetic operator key in a disposable home, in memory.
No real credentials, providers or personal service registrations were used.

Limits: no detached startup/reuse, installed supervisor routing, Connector
readiness or harness/provider readiness is claimed. SVC-01/02/04 remain in
progress for the complete multi-component lifecycle contract. No acceptance
scenario is promoted solely from these narrower tests.
