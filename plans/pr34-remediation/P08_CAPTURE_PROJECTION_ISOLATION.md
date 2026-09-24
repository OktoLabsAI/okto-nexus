# P08 — durable capture independent of SQLite projection

Parent: `82f7c7774b183a380aec3f5089d18592775c759e`, branch feature/v0.2.0.
Schema056 unchanged. This is a partial P07/P08 milestone, not the final gate.

## Defect and implementation

The real Codex steering campaign reached1067 text deltas without a terminal.
Native turn/start and turn/steer responses had no error. The owned disposable
database recorded a lifecycle event with `NativeEventOverflow`, stop observed,
and outcome_unknown. The supervisor's pump synchronously projected each captured
event through SQLite, blocking the bounded128-event native subscriber queue.

`HarnessSupervisor._pump` now asks `RuntimeEventIngress.capture` to defer database
projection. Capture still appends and fsyncs each record before returning; the
existing owner coordinator drains that journal. There is no new work queue,
unbounded thread, buffer expansion, weaker fsync or speculative replay.
Direct capture retains its synchronous default for internal callers. Lifecycle
shutdown still drains outstanding durable records before closing the journal.

`RuntimeEventIngress.recover` reads at most16 records outside the SQLite writer,
then projects the batch atomically in one write transaction. Terminal consumption,
results and checkpoints roll back together on any failure. Subscriber publication
occurs only after commit. A pending flag protected against concurrent append and
projection plus the dispatcher's existing generation wake drains remaining batches
without polling the harness or waiting for an additional native event.

## Evidence

- Initial deferred-capture regression selection:4 FAIL/17 PASS in50.89s. Three
  direct-capture callers assumed synchronous projection; one burst exceeded the
  fixture's5-second projection deadline. Corrected direct API compatibility and
  batched bounded projection; did not raise the deadline or native queue limits.
- Next selection:1 FAIL/20 PASS in55.40s. Capture, process survival and terminal
  durability succeeded; the new fixture incorrectly expected only the final text
  and omitted256 preceding streamed `x` fragments. Corrected its expected output
  to assert preservation of every fragment.
- Final Windows command:
  `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_capture_projection_isolation.py tests/test_runtime_event_journal.py tests/test_runtime_shutdown.py tests/test_runtime_restart.py tests/test_runtime_effective_controls.py tests/test_runtime_commands.py`
  **38 PASS in128.49s**.
- Final Linux command:
  `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short tests/test_runtime_capture_projection_isolation.py tests/test_runtime_event_journal.py tests/test_runtime_shutdown.py tests/test_runtime_restart.py tests/test_runtime_effective_controls.py tests/test_runtime_commands.py`
  **38 PASS in138.78s**.
- New real-pipe production-composition burst fixture blocks the projector while
  capturing256 deltas and terminal events; asserts no premature result, native
  process survival, then complete durable output after releasing projection.
- New batch failure fixture raises after projecting the second record: zero
  events/results/checkpoints commit and no publication occurs; subsequent replay
  projects both once. Existing fsync-outside-write, corruption, quota, restart,
  stale-attempt and shutdown tests remain in the passing selection.
- Real native Codex and Claude control commands/results are recorded in
  P07_EFFECTIVE_CONTROL_CONTRACTS.md. Pi and dedicated attach native NOT_RUN.
- Broader Windows regression:
  `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_result_correlation.py tests/test_runtime_result_publication.py tests/test_runtime_artifact_durability.py tests/test_runtime_result_maintenance.py tests/test_runtime_event_buffers.py tests/test_runtime_wake_generation.py tests/test_runtime_shared_connection.py tests/test_runtime_native_inputs.py tests/test_runtime_native_approvals.py tests/test_import_boundary.py`
  **88 PASS/2 FAIL in289.05s**. Both failures used an undeclared-version peer
  while requesting interrupt and correctly received `native_control_unverified`.
  The affected correlation and late-approval fixtures now explicitly emit the
  qualified initialize version; unknown-version denial tests remain unchanged.
  Isolated correlation rerun: **5 PASS in24.16s**. Initial diagnostic rerun with
  `tests/test_runtime_result_correlation.py -x`:4 PASS/1 FAIL in26.70s.
- Final affected-suite rerun:
  `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_native_approvals.py tests/test_runtime_result_correlation.py`:
  **21 PASS in83.14s**. Ruff on all changed Python modules and `git diff --check`
  passed. PR34 rechecked: OPEN at original d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397,
  base27b06fe48b9f95b35c94f50827fea83d178f4e12; no later changes overwritten.

Full immutable-SHA matrix, broad native stress campaign, power-loss qualification
and P12 remain pending. This evidence does not claim unlimited throughput.
