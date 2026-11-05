# PR-02 — Nexus Windows user-task host adapter

Date: 2026-11-05. Windows 11 10.0.26300, Python 3.13.1. Nexus 0.3.3,
Core 0.0.14 candidate; no package publication or personal task registration.

## Implemented scope

The application facade and CLI now expose explicit user install/uninstall.
The Windows adapter preflights the native XML before drain, creates only the
instance-named task with `TASK_CREATE`, and records its actual exported XML and
fingerprint. A task without an ownership receipt, an edited native definition,
a changed execution context or a database claimed by another home is preserved
and reported as a conflict. Home/database launch guards serialize our callers;
Task Scheduler does not offer atomic fingerprint-conditional mutations against
concurrent external editors. No stronger native CAS guarantee is claimed.

Installed start uses the selected scheduler task, never a detached fallback.
Its consoleless isolated-Python entry validates the receipt, selected principal,
context and native definition, then remains in the same foreground Server.
Readiness still requires the application identity/generation/locks; native
queued/running is only a supervisor observation. A pending native start intent
is retained on response loss and is not blindly resubmitted.

Stop latches suppression of recovery before canonical drain; no Task Scheduler
Stop/terminate operation is called. A queued entry can be fenced before it owns
the database. A later logon is distinguished from a crash retry using the actual
token AuthenticationId plus logon time (LUID values alone may repeat after boot).
This login behavior is tested through the injected host boundary, not an actual
logout/login campaign. Uninstall requires drain and native inactivity, removes
only selected integration receipts/task, and preserves configuration and data.

Successful native creation responses are saved before final receipt completion.
Positive absence permits retry/recovery; a lost creation response with an
existing unconfirmed task requires explicit review. The original native XML is
retained for comparison. This increment deliberately does not adopt an unknown
task or overwrite user edits to make an operation appear successful.

## Validation and corrections

`pr02-nexus-user-service.xml`: **159 passed, 2 skipped**, covering the installer,
local lifecycle, readiness, locks, configuration, import boundary, serve args and
existing shutdown/signal tests. The skips are existing POSIX SIGTERM/SIGINT cases
on Windows. FastAPI emitted its existing Starlette/httpx deprecation warning.

Command (preceded by `rtk proxy .venv/Scripts/python.exe -m pytest`):

```
tests/test_service_process.py tests/test_user_service_installation.py
tests/test_service_start.py tests/test_service_inspection.py
tests/test_service_readiness.py tests/test_serve_lock.py tests/test_serve_args.py
tests/test_config.py tests/test_import_boundary.py
tests/test_serve_harness_shutdown_reap.py
tests/execution_r4/test_server_signal_shutdown.py
-q --tb=long --junitxml=plans/agent_ops/evidence/pr02-nexus-user-service.xml
```

The process regression initially exposed real races; these failures were not
treated as a passing campaign:

- Inspection could report stopped while another CLI held launch exclusion before
  publishing its launch receipt. It now observes that selection as starting.
- Metadata may be published while the readiness request is in flight. The
  response is now correlated with a fresh metadata/guard observation; an owner
  change remains unconfirmed rather than rejecting the new matching owner.
- ASGI shutdown released the lifetime lock before final receipt/cleanup. The
  foreground entry now retains ownership through cleanup and receipt persistence;
  the process test checks the final non-null generation matches the stopped owner.
- A passive Windows CRT reader can deny replacement of `service-launch.json`
  (`WinError 5`). This was reproduced deterministically with an open reader.
  Atomic JSON writes now retry only Windows sharing/access contention for at most
  one second, preserving the old receipt on persistent failure. Real-handle and
  bounded-failure tests cover both outcomes. Concurrent wheel-building IO made
  the startup race easier to expose; it was included in the final rerun.

After the final receipt fix and removal of temporary diagnostic instrumentation,
`pr02-nexus-user-service-final.xml`: **56 passed**. Command:

```
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_service_process.py
tests/test_user_service_installation.py tests/test_service_start.py
tests/test_service_inspection.py -q --tb=short
--junitxml=plans/agent_ops/evidence/pr02-nexus-user-service-final.xml
```

The real subprocess test uses only disposable homes/loopback endpoints and no
provider work. Three concurrent CLIs converge on one owner, survive launcher
exit, reuse the generation, restart explicitly, reject stale stop and drain.
Native host preflight uses `TASK_VALIDATE_ONLY`, asserting task absence before
and after and no home creation. Registration, start and delete unit tests use an
injected scheduler; no personal task is installed or removed by this suite.

Ruff and `git diff --check` passed. A final wheel was built with `python -m build
--wheel`; all **411 Python payloads** exactly match source, with no missing or
extra Python files. SHA-256 and local artifact location are recorded in
`pr02-nexus-user-service-wheel.json`. This is artifact-content verification,
not a fresh dependency environment or actual installed task qualification.

## Open acceptance

PR-01/02 and the full SVC tasks remain in progress. Connector supervisor/context
integration, operational logs, enable/disable/reconciliation UX, interrupted
detached pre-spawn recovery, upgrades, installed-package campaigns, actual
login/logout/crash/terminal closure, real credential availability and authorized
provider work remain open. POSIX adapters/platform qualification are not inferred
from this Windows implementation. No runtime work/approval/grant is replayed by
these host operations, and no M1 acceptance is claimed.

Native API references: [RegisterTask flags and logon types](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskfolder-registertask),
[Run semantics](https://learn.microsoft.com/en-us/windows/win32/taskschd/registeredtask-run),
[token AuthenticationId](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-token_statistics).
