# P07 — process ownership checkpoint

Parent SHA: `62ef22b`. Branch: `feature/v0.2.0`. Windows, Python 3.13.
Partial implementation; **P07 and the final gate remain IN_PROGRESS**.

## Implementation

- `windows_process.OwnedWindowsPopen` creates a kill-on-close Job and supplies
  `PROC_THREAD_ATTRIBUTE_JOB_LIST` in `CreateProcessW`. Ownership precedes the
  child's first instruction; there is no create-then-assign interval. Standard
  handles are explicitly allowlisted and the Job handle is not inherited.
  Termination uses this owned kernel handle, never a process-name or PID search.
- Pi, Codex and Claude stream use `owned_process.spawn_owned_process` in their
  existing production transports. Claude attach does not use this launcher.
- `RuntimeLifecycle` registers owned cleanup callbacks before the native
  handshake. Startup timeout cancels registered resources, rejects late
  registration and quarantines the binding until the worker actually finishes.
  Four startup slots and four control helper slots remain occupied while calls
  are blocked; no replacement worker is created after timeout. Admission also
  caps live/starting runtimes at sixteen.
- Codex EOF now fails pending handshake requests immediately. Previously, the
  killed child left `initialize` waiting until its independent 30-second timeout.
- Post-start session validation and persistence failures cancel owned resources.
  This does not claim terminal session/result durability, which remains P08 work.
- Legacy Claude fixture stdin uses one raw reader and a bounded queue, replacing
  `select` on pipes (unsupported on Windows). Its EOF fixture uses the actual
  Python interpreter instead of the Windows venv redirector, which retains the
  child's stdout handle. The Codex handshake test waits on the captured process
  instance instead of invoking `os.kill(pid, 0)` on Windows.
- Native Claude tests now require explicit `OKTO_NEXUS_CLAUDE_LIVE=1`; merely
  finding the CLI on PATH no longer authorizes a real campaign.

## Evidence and exact commands

`tests/test_runtime_process_ownership.py` launches disposable Python processes,
not providers/models. It covers cancellation, bounded wedged workers, a real
Codex transport with a nonresponding fixture executable, the production REST
owner path, no RUNNING row after timeout, no replay with the same open key, and
three abrupt owner kills with live children and grandchildren. Windows process
handles are acquired before each kill and waited afterward, avoiding PID reuse.

- `.venv/Scripts/python.exe -m pytest tests/test_runtime_process_ownership.py -q`
  — **8 passed**, `evidence/p07-process-ownership.log`.
- `.venv/Scripts/python.exe -m pytest tests/test_harness_codex_connector.py tests/test_harness_pi_connector.py tests/test_runtime_process_ownership.py tests/test_runtime_outbox.py tests/test_runtime_grants.py tests/test_import_boundary.py -q`
  — initial run **92 passed, 1 failed, 2 skipped**. Failure: legacy Windows PID
  probe, subsequently corrected. One existing injected Pi reader exception
  warning. `evidence/p07-process-progress.log`.
- `.venv/Scripts/python.exe -m pytest tests/test_harness_codex_connector.py tests/test_runtime_process_ownership.py tests/test_harness_claude_code_connector.py -q -k 'not real_claude'`
  — initial fixture run **64 passed, 1 failed, 1 skipped, 7 deselected**. Failure:
  venv redirector retained stdout in the EOF fixture; subsequently corrected.
  `evidence/p07-connector-fixtures.log`.
- `.venv/Scripts/python.exe -m pytest tests/test_harness_claude_code_connector.py -q -k finish_never`
  — **1 passed, 34 deselected**, `evidence/p07-claude-eof.log`.
- An earlier combined Claude command was interrupted after discovering its
  PATH-based native-test activation. It retained no complete result and is not
  evidence of a native campaign (`p07-native-contract-progress.log`). Subsequent
  runs explicitly disable all live flags and/or deselect native Claude tests.
- The first REST test attempt reached the actual timeout but failed on an
  incorrect test UoW accessor; this is not a behavioral regression reproduction.
  `evidence/p07-rest-timeout.log`. The corrected full ownership suite is above.

## Limits and next dependencies

This supplies partial evidence for T-ID-06, T-DISP startup deadline cases and
T-LIFE-02/05. It does not certify their complete scenario matrices. Three quiet
owner-kill runs are **not** the scheduler-pressure campaign T-LIFE-04.

POSIX explicit group teardown remains available, but equivalent owner-crash
protection and replacement of the old snapshot watchdog are pending and NOT_RUN
on this host. Do not infer POSIX crash protection from Windows results. The
Windows launcher uses a narrow CPython Popen integration; validation across
supported Python versions is pending. Shared Codex connection reference counting,
boot/recovery, close state reconciliation and journal drain remain pending.

Native Codex, Claude stream and dedicated Claude attach campaigns have no
accepted results yet; Pi native stays NOT_RUN by user instruction. No safety
control was disabled. Fixtures use temporary stores/projects.

Platform basis: Microsoft's [Job Objects documentation](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
and [atomic assignment at process creation](https://devblogs.microsoft.com/oldnewthing/20230209-00/?p=107812).

Final unit gate: set `OKTO_NEXUS_PI_LIVE=0`, `OKTO_NEXUS_CODEX_LIVE=0`,
`OKTO_NEXUS_CLAUDE_LIVE=0`, then run:

```
.venv/Scripts/python.exe -m pytest tests/test_harness_codex_connector.py tests/test_harness_pi_connector.py tests/test_harness_claude_code_connector.py tests/test_runtime_process_ownership.py tests/test_runtime_outbox.py tests/test_runtime_grants.py tests/test_import_boundary.py -q
```

**122 passed, 9 skipped, 1 warning**, 129.54s. The warning is the existing
Pi test's intentionally raised reader callback exception. Skipped native cases
are NOT_RUN, not PASS. Evidence: `evidence/p07-process-gate.log`.
Ruff on all changed Python files: PASS.
