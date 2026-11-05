# PR-02 — Connector user-service host and serialized launch

Date: 2026-11-05. Windows 11 `10.0.26300`, Python 3.13.1.
Connector `0.0.12` on `feature/v0.0.12`; Core `0.0.14` remains pinned.
Connector implementation committed and pushed as `fc90370`.
Remote mains were fetched before continuation; all three feature branches
contain their current main bases. No reset or merge changed those bases.

## Implemented scope

- Production foreground and detached entrypoints acquire the instance OS lock
  before constructing state/vault/Core services. An independent launch guard and
  nonce receipt serialize concurrent parents and the child handoff. Timeout
  observes the same launch; it does not kill or spawn a replacement.
- Stable execution context persists resolved Python, environment prefix, state
  and working-directory references. Only explicitly selected OS variables are
  retained. Existing proxy references resolve at launch without persisting their
  values; vault selection does not grant fallback consent or copy provider keys.
- Windows install/start/stop/uninstall use the shared Core definition, scoped
  instance/principal and native-export fingerprint. Foreign/legacy definitions,
  changed contexts and unconfirmed effects are retained for explicit review.
  A recorded installation routes start through its OS task with no detached
  fallback. Stop persists same-login recovery suppression before canonical IPC
  drain. Uninstall preserves application state, vault, history and logs.
- `daemon restart` requires confirmed drain before another generation. Read-only
  `service`/`daemon status` resolve an absent directory without creating state.
  Native operation errors produce bounded structured diagnostics.
- Windows atomic receipt replacement retries only transient sharing/access
  contention, with a bounded deadline; persistent failure preserves the old file.

## Validation

From Connector, using the Nexus development venv:

```text
python -m pytest tests/integration/test_detached_service_lifecycle.py tests/unit/test_user_service_lifecycle.py tests/unit/test_service_readiness.py tests/unit/test_service_install.py tests/integration/test_service_readiness_process.py tests/integration/test_windows_job_daemon.py tests/unit/test_boundaries.py tests/unit/test_proxy.py -q --tb=short
72 passed

python -m pytest tests/unit/test_r4_daemon_control.py tests/unit/test_r4_daemon_execution.py tests/unit/test_transport_shutdown.py tests/unit/test_lock.py tests/unit/test_proxy.py -q --tb=short
90 passed

python -m pytest tests/e2e/test_packaging.py -q --tb=short
2 passed
```

JUnit artifacts: `pr02-connector-user-service.xml`,
`pr02-connector-user-service-regression.xml` and
`pr02-connector-user-service-packaging.xml`.
Ruff passes on all changed Python files; `git diff --check` is also required.

The real disposable-process test starts three concurrent CLIs, requires exactly
one selected launch and one PID/generation, observes survival after launcher
exit, reuses the generation, explicitly restarts, and checks the final canonical
`DRAINED` receipt. State and rotating logs remain. The packaging suite installs
the wheel/Core into a clean venv and exercises lifecycle outside the checkout.
It uses no provider, Server link, credential or personal service installation.

Fake-native tests exercise install idempotence, foreign/legacy-task refusal,
changed fingerprints, lost create/run/delete responses, stop-latch ordering,
retained uncertain state and data preservation. Native Windows checks only read
absence and call `TASK_VALIDATE_ONLY`, including from a worker thread; they do
not register or delete a task.

An early COM implementation uninitialized its thread while returned COM objects
were still referenced. That run printed access violations despite a successful
pytest count and was rejected as evidence. The final adapter returns plain data,
releases COM references and exception frames before balancing initialization on
the calling thread, and passes the subsequent native worker-thread test.

The final candidate contains 109 Python payloads, all byte-identical to source;
there are no missing/extra Python files. Metadata includes Core `0.0.14` and the
Windows-only runtime `pywin32` dependency. The same Core wheel remains in both
consumers. SHA-256 and payload checks are recorded in
`pr02-connector-user-service-wheel.json` and `vendor/ci/manifest.json`.

## Remaining fixed-plan requirements

This evidence covers narrower implementation subscopes, not full PR-02 or M1.
Native service installation/login/logout/crash and credential/provider campaigns
are NOT_RUN. Launcher exit is not proof of real terminal closure or logout.
Enable/disable/reconciliation UX, interrupted pre-spawn receipt recovery,
controlled upgrade, remaining passive diagnostics and remote productive work
remain open. Existing Linux systemd/macOS launchd global templates have not
received the R3 ownership contract and are not qualified by these results.

Task Scheduler provides no atomic fingerprint-conditional mutation against an
external editor; immediate preflight comparison cannot eliminate that race.
Ambiguous ownership remains a refusal rather than inferred adoption.

No schema/NXL change, release publication, merge or personal installation was
performed. Rollback requires canonical drain and removal of an owned native task
through its matching version before discarding its installation receipt.
