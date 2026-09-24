# P11 — shutdown inventory failures migrated to current composition

Parent `39ac366`, branch `feature/v0.2.0`. PR34 rechecked with
`rtk proxy gh pr view 34 --repo OktoLabsAI/okto-nexus --json headRefOid,baseRefOid,headRefName,state,url`:
OPEN, HEAD `d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397`, base
`27b06fe48b9f95b35c94f50827fea83d178f4e12`, unchanged. No merge or PR rewrite.

## Findings and change

The completed full-suite inventory (2240 PASS,6 FAIL,92 SKIP) exposed six obsolete
shutdown fixtures. They opened an unknown agent without authentication or an
approved profile, then called POSIX-only killpg on Windows in cleanup. Thus their
403 and cleanup errors did not test actual runtime shutdown. Six leaked fixture
servers were previously cleaned with ownership validation; that incident remains
documented in the inventory manifest, not erased by this migration.

`runtime_serve_shutdown_fixture.ServeFixture` now executes the actual run_serve
composition in a disposable subprocess/home/project. It configures an existing
canonical agent, disposable authenticated operator, approved profile and endpoint
through the production APIs. Only the Pi process factory points to a real Python
RPC peer, using the production PiRpcConnector and approved isolated environment.
The fixture's stdin stop command sets uvicorn.should_exit for portable graceful
exit; actual POSIX SIGINT/SIGTERM and Popen.kill are separate tests. The ordinary
serve lifespan, owner dispatcher, journal, shutdown/finally and locking paths run.

The peer spawns a grandchild and deliberately remains alive after stdin EOF, so
incidental pipe closure cannot make the orphan proof pass. Witnesses hold Windows
process handles or Linux pidfds before stopping the owner. Linux also witnesses
the exact birth guardian. Cleanup acts only on the owned Popen; no arbitrary PID
scan, name match, process-group kill, psutil dependency or personal endpoint.

## Old → current coverage

| Old case | Current proof |
|---|---|
| SIGTERM with live session | Same case on Linux; exact child/grandchild/guardian death |
| SIGINT with live session | Same case on Linux; exact child/grandchild/guardian death |
| Explicit close then shutdown | Same case Windows/Linux; durable close completes and witnesses stop before owner exit |
| SIGKILL plus watchdog | Abrupt owner kill, birth-owned tree and guardian stop; historical scanner is not launched |
| Clean exit stops watchdog | Portable clean exit with live peer; Linux guardian also stops |
| SIGTERM stops watchdog | Linux SIGTERM case includes guardian witness |

The three pure historical watchdog regression tests are retained. The removed
duplicated process scanners are not the ownership mechanism used by production.
Windows POSIX signal tests are explicitly skipped, not counted as PASS; Windows
graceful and abrupt ownership cases run independently.

## Commands and observed results

- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_serve_harness_shutdown_reap.py tests/test_serve_harness_sigkill_reap.py -x`:
  initial1 FAIL/2 SKIP in4.16s because the new fixture attempted a Python argv in a
  Pi profile. Production correctly rejected it. Kept that control unchanged and
  moved the fixture executable into the trusted test factory only.
  Corrected run **7 PASS/2 SKIP in21.11s**.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_serve_harness_shutdown_reap.py tests/test_serve_harness_sigkill_reap.py -x`:
  **9 PASS in54.67s**, including SIGINT, SIGTERM and guardian termination.
- `rtk proxy ruff check tests/runtime_serve_shutdown_fixture.py tests/test_serve_harness_shutdown_reap.py tests/test_serve_harness_sigkill_reap.py`:
  initial unused pytest import corrected; final PASS.

No production implementation or native provider/model changed in this unit.
Pi native remains NOT_RUN. This resolves the six inventory failures in scoped
tests; a fresh immutable-SHA full regression remains required, along with effective
capability probes, cutover/backup, remaining admin parity and P12 acceptance.

Expanded Windows lifecycle/restart check: `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_serve_harness_shutdown_reap.py tests/test_serve_harness_sigkill_reap.py tests/test_runtime_shutdown.py tests/test_runtime_process_ownership.py tests/test_linux_process_ownership.py tests/test_runtime_relay_process_restart.py` returned **24 PASS/10 SKIP in78.17s**.

Expanded Linux check: `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_serve_harness_shutdown_reap.py tests/test_serve_harness_sigkill_reap.py tests/test_runtime_shutdown.py tests/test_runtime_process_ownership.py tests/test_linux_process_ownership.py tests/test_runtime_relay_process_restart.py` returned **31 PASS/3 SKIP,2 subtests PASS in118.95s**. No live test handles remain for this unit.
