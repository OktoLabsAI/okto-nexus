# SVC-T06 / T12 / T13 — finite installed qualification

Final: **6 passed, 1 real product failure**, seven distinct execution identities.
Five new cases plus two reused exclusion/bootstrap regressions. Repeated runs
are not added to coverage. Preparation failures are retained separately.

T06 proves no fallback and preserved ownership but exposes a missing public bind
diagnostic: `STARTUP_FAILED` plus generic action, while the real child stderr
contains the occupied-port cause and production discards it. This case stays red.
T12 covers real invalid config, future migration ledger and blocked storage;
T13 injects KeyboardInterrupt only in a connect wait while observing a real,
birth-verified disposable owner, then confirms the same generation ready and
canonical DRAINED cleanup. No global signals, personal state, provider, native
service registration, or source-product changes occurred.

`tests.patch` adds only the new test file. The existing two tests are selected
unchanged from `tests/test_serve_lock.py`; their final copied hash is in the
inputs proof. All runtime imports came from noneditable Nexus wheel `9b18…`
(690 matching payload files), Core 0.0.14 and MCP 1.30.0 in the qualified CI venv.

The first collection had a missing optional test dependency, replaced with
native Windows read APIs. The first executable run had a fixture-only SystemRoot
case issue and a runner-only bytecode inventory comparison issue. Both raw XMLs
are preserved; no earlier failure was overwritten or counted as final success.

See assessment.json for exact boundaries; attempts.json for nominal cases;
artifact-manifest.json for original/public hashes and redactions. This is not
M1/M2, registered Task Scheduler, actual login/logout, or provider qualification.
