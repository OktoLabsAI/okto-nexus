# PR-02 — Connector local ownership/readiness and drain evidence

Implemented changes are described in the Connector's
`docs/service-lifecycle.md` and `plans/agent_ops/lifecycle-readiness.md`.
Commands below run through RTK using Nexus's repository Python, with Connector
installed editable for source verification. The installed-package campaign uses
an isolated venv and the built wheel from outside the checkout.

- **46 passed**: `python -m pytest tests/unit/test_service_readiness.py tests/integration/test_service_readiness_process.py tests/unit/test_lock.py tests/unit/test_sysinfo.py tests/unit/test_ipc_protocol.py tests/unit/test_boundaries.py -q -x --junitxml=<Nexus>/plans/agent_ops/evidence/pr02-connector-readiness.xml`.
- **75 passed**: `python -m pytest tests/integration/test_daemon_app.py tests/unit/test_r4_daemon_control.py tests/unit/test_r4_daemon_execution.py tests/unit/test_transport_shutdown.py -q -x --junitxml=<Nexus>/plans/agent_ops/evidence/pr02-connector-runtime-regression.xml`.
- **2 passed** (68.26s), including installed start/reuse/drain: `python -m pytest tests/e2e/test_packaging.py -q -x --junitxml=<Nexus>/plans/agent_ops/evidence/pr02-connector-packaging.xml`.
- Scoped Ruff passed; the candidate wheel's 104 Python files match source.

Candidate Connector wheel SHA-256:
`8763c243de9e51b443935f053c10944ed16b0472ca1a2d972a63aff7b0a07bbb`.

Real disposable foreground Connector: correct selected state directory, local
IPC proof, reuse, denial of stale-generation shutdown, confirmed DRAINED receipt
and preserved state after stop. No remote identity, provider or personal OS
service registration was involved. The packaging test additionally starts the
installed wheel in background, reopens/reuses it and drains it, without checkout
imports or a registered Server.

Observed failures and corrections: the first source test accidentally loaded the
previous installed candidate; the interpreter was switched to editable source.
Two new test assumptions were corrected (CLI JSON has no result envelope, and
the mock context manager must not suppress transport errors). Windows venv
python.exe is a redirector, so process qualification checks the actual OS-lock
owner rather than assuming the launcher PID is the daemon PID.

The broader suite stalled at fixture teardown. Read-only process/coroutine
inspection found an HTTP keep-alive connection left behind by double cancellation
of a transport attachment. Only the identified disposable test processes were
stopped; temporary diagnostic instrumentation was removed. A focused cleanup
regression now passes, as does the affected 75-test suite. The test was not
weakened or skipped to hide the leak.

A broader undefined-name check also found a pre-existing unreachable legacy
retry statement after an infinite observer loop. It was removed without changing
runtime behavior; the final source-matching wheel was rebuilt afterward. The
undefined-name check now passes. Connector commits `97c5e13` and `c4ad79d` were
pushed to `feature/v0.0.12`.

Open: instance-specific installed supervision, complete launch serialization,
saved Connector execution context, all passive diagnostics, detailed migration/
credential failures and actual remote/provider/login/logout/reboot campaigns.
No whole SVC scenario or M1 gate is promoted by this increment.
