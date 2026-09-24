# Dispatcher lane selection — isolated development

Parent43388c8f7298946c4a711850c25545925b58f01c. Detached worktree; not yet integrated
or committed. Main complete regressions remain on the parent implementation.

The outbox and administrative control queries applied LIMIT before the dispatcher
removed repeated endpoints. Three queued items A,A,B with capacity2 therefore
returned A,A and left an available slot unused. Real authenticated HTTP/MCP
reproduction is preserved in the main checkout's P12_REMAINING_GATE_AUDIT.md.

Both repository selectors now exclude later pending rows from the same endpoint
and lane before truncating. Existing busy-lane, control priority, ownership,
authorization, FIFO order and uncertainty fences remain in force. No process or
network call was added to the SQLite transaction. No new schema is required.

`tests/test_runtime_scheduler_fairness.py` exercises canonical approved endpoints,
real HTTP/MCP message/command admission and the real SQLite repository. Pausing
scans only stages the selection fixture; it does not grant authority. The third
test resumes actual dispatcher workers: one call remains blocked while the other
agent's native send must complete before release. No personal provider is involved.

Test development observations:

- First fixture quiesced admission as well as scans: delivery RED, close denied
  before enqueue,2 FAIL10.72s. The close denial was a fixture error, not the defect.
- Pausing scans left default close idempotency coalescing two calls:1 FAIL1 PASS8.84s.
- Distinct explicit close keys: **2 behavioral FAIL7.48s** before correction.
- Corrected Windows `pytest -q --tb=short tests/test_runtime_scheduler_fairness.py tests/test_runtime_commands.py tests/test_runtime_outbox.py`:
  **27 PASS84.96s** (before adding the third blocked-call test).
- Final three scheduler tests: **Windows3 PASS11.93s; Linux3 PASS15.51s**.
- Ruff and git diff --check: PASS.

Windows command prefix `rtk proxy D:/Projetos/Techridy/okto_labs_okto_nexus/.venv/Scripts/python.exe -m`;
Python3.13.1, workdirD:/Projetos/Techridy/okto_nexus_scheduler_worktree.
Linux prefix `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_nexus_scheduler_worktree -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m`.
These are isolated development selections; subprocess paths must be requalified
after integration into feature/v0.2.0. No commits belong on this detached checkout.

Seven files also contain corrections of stale surface51 expectations to52. The
selected metadata gate, `pytest -q --tb=short tests/test_comm_presets.py tests/test_feature_flags.py tests/test_handoff_dependencies.py tests/test_health.py tests/test_memory.py tests/test_replay_marker.py tests/test_verification.py -k "surface_revision or nexus_info_features"`, returned
**9 PASS245 deselected5.01s**, one Starlette deprecation warning. Keep that fixture
correction distinguishable from the dispatcher implementation when integrating.

## Repeated process cycles (partial P12 evidence)

`runtime_cycle_campaign.py` uses the production HTTP app and owned Python Codex
protocol peers, two turns then close per cycle. Every close asserts lifecycle
stopped and waits on that exact owned process instance; no arbitrary PID scanning.
Two warmups,12 measured cycles; explicit bounds fixed before the run: baseline+4
threads, baseline+16 handles/FDs, baseline+4MiB Python allocations after GC.
It records source SHA, dirty source diff hash and script hash. No credentials or
model/provider calls. The initial prototype used the wrong lifecycle spelling
stop_observed instead of stopped and aborted before measurement; no PASS claimed.

Windows command: `rtk proxy D:/Projetos/Techridy/okto_labs_okto_nexus/.venv/Scripts/python.exe plans/pr34-remediation/runtime_cycle_campaign.py plans/pr34-remediation/evidence/p12-owned-cycles-windows.json`.
Result PASS:13 threads throughout;243–248 handles versus248 baseline; Python
allocations18,267,905→18,445,790 bytes, within bounds. All owned children stopped.
Wire method names were initialize,thread/start,thread/unsubscribe,turn/start.
The test driver polls Nexus operation inspection; that is distinct from native
status polling, which is absent from the captured fixture method names.

This is not a native model trace, RSS measurement, crash-pressure campaign or
comparable before/after benchmark. The host also ran full suites concurrently;
cycle timings are descriptive only. Aggregate T-E2E-04/05 remain unfinished.
Linux campaign first stopped before setup because WSL Git cannot interpret a
Windows worktree gitdir pointer; rerun supplies explicit GIT_DIR/GIT_COMMON_DIR/
GIT_WORK_TREE paths. Result PASS:13 threads and13 FDs throughout; Python allocations17,422,227 to17,591,624 bytes. All owned children stopped; same four fixture method names. Linux result is independently recorded in evidence/p12-owned-cycles-linux.json.

Next: complete full-suite failure analysis, integrate and retest this correction,
then remaining per-agent fairness, bounded inbox transport backlog, proven-safe
retry/backoff/fallback and final matrix/stress/build gates. T-DISP-09 is not wholly
verified by this narrower lane-selection fix.
