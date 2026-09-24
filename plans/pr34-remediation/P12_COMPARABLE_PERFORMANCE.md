# Comparable original/current performance

Parent536b993; completed bounded comparison. Final plan/release gate remains NOT PASSED.

The benchmark compares immutable git archives of PR34 d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397 and the current committed remediation source. Each platform uses the same interpreter, installed dependencies, machine, filesystem, synthetic peer source, payload size and SQLite settings. Three independent stores/processes per revision, five warmup turns per process, forty measured turns per round. Order is original/current/current/original/original/current. No outliers are discarded. Percentiles use nearest rank over120 measured turns per revision; individual rounds and all samples remain available.

Each process starts the production HTTP application on an ephemeral loopback socket, pre-registers the canonical worker, opens a real owned Codex adapter with a bounded synthetic Python protocol peer, sends authenticated sequential turns and observes persisted terminal events. New code additionally requires a durable result for the returned operation. Profiles/endpoints are created only in the new revision because the original had no such model. Native peer argv, payload and interpreter are identical. There are no installed provider/model calls, LAN endpoints, personal stores or operator credentials in the subprocess environment.

Both applications explicitly use `app.state.local_open=False`, the production listener setting that requires authentication, while their socket stays loopback. Invalid-key probes must fail; every measured turn must invoke authentication. The new revision must additionally perform runtime authorization and journal fsync. SQLite WAL/synchronous settings and dependency versions must match across all rounds. Nothing disables security, journaling, sandbox or approvals. Declared native capabilities are not upgraded by this benchmark.

Admission timing measures the HTTP response; its semantics differ by design: original response follows immediate transport send, whereas current response acknowledges durable command admission. The common end-to-end metric runs from request start through observation of its persisted terminal event. The observer queries the local disposable SQLite at1ms intervals on both revisions; it never queries the native harness. The new result is confirmed before the next turn. These are sequential local control-plane measurements, not inference latency, throughput capacity or a production SLA.

Instrumentation wraps and calls the original authentication, runtime authorization and Python os.fsync functions. It records calls and elapsed time without changing their results. SQLite's internal C fsync remains enabled and contributes to end-to-end latency, but is not counted by the Python wrapper. Nested/concurrent timings cannot be summed or subtracted as a causal decomposition. Observed fsync/policy cost is published rather than removed to obtain a faster result.

## Preparation evidence

- Current pilot5 measured turns passed.
- Original pilot failed because legacy HarnessEvent lacks public sequence. The final observer uses the same persisted SQLite event fields on both sides.
- Second original pilot rejected absent authentication calls in local-open mode. Both revisions now require keys as above; the check was preserved.
- Both revised pilots5 measured turns passed.
- First isolated runner failed before app startup because the sealed Windows environment had no home directory. The benchmark now supplies its own temporary HOME/USERPROFILE; no personal environment was restored.
- Ruff for both scripts passed before the full campaign. Pilots are diagnostics, not the final comparative dataset.

## Commands

```text
rtk proxy .venv/Scripts/python.exe -X utf8 plans/pr34-remediation/run_comparison_benchmark.py .git/pr34-evidence/benchmark-windows-final.json
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -X utf8 plans/pr34-remediation/run_comparison_benchmark.py .git/pr34-evidence/benchmark-linux-final.json
rtk proxy ruff check plans/pr34-remediation/runtime_comparison_benchmark.py plans/pr34-remediation/run_comparison_benchmark.py
```

The runner records exact source SHAs and campaign/peer hashes and holds each child with its Popen lifetime. Servers and peers must stop before a round is accepted. Execute platforms sequentially to avoid benchmark interference. Temporary stores are removed; raw results/logs and immutable source archives stay under `.git` until reviewed. Final evidence must include the hashes and full samples, not just displayed percentiles.

Both campaigns and their hash/configuration/cleanup verification are complete below. Other P12 and release gates remain open.

## Final results

Windows exec36799 and Linux exec71095 both terminated exit0/PASS. Each includes120 measured turns per revision plus15 warmups per revision. No rounds/samples were dropped. All credential probes were denied, all servers/owned peers stopped, dependency/configuration/hash equality checks passed. Both versions use SQLite WAL with synchronous=2 (FULL). Source revisions are recorded in each full manifest. Ruff and git diff --check PASS.

| Platform / metric (ms) | Original p50 | Current p50 | Original p95 | Current p95 | Original p99 | Current p99 |
|---|---:|---:|---:|---:|---:|---:|
| windows / admission_ms | 11.822 | 147.973 | 34.398 | 216.147 | 45.984 | 356.810 |
| windows / persisted_terminal_ms | 108.137 | 367.673 | 149.115 | 517.921 | 191.614 | 544.019 |
| linux / admission_ms | 58.833 | 78.407 | 68.931 | 104.948 | 69.156 | 114.580 |
| linux / persisted_terminal_ms | 59.861 | 182.096 | 70.025 | 245.818 | 70.264 | 290.732 |

| Platform / component (mean ms per turn) | Original | Current | Current calls per turn |
|---|---:|---:|---:|
| windows / authentication | 0.127 | 0.754 | 1.0 |
| windows / runtime_policy | 0.000 | 78.535 | 6.0 |
| windows / fsync | 0.000 | 2.153 | 5.0 |
| linux / authentication | 0.089 | 0.905 | 1.0 |
| linux / runtime_policy | 0.000 | 33.778 | 6.0 |
| linux / fsync | 0.000 | 6.759 | 5.0 |

The current implementation is measurably slower in this synthetic sequential workload. The figures include the additional durable admission, runtime authorization/revalidation, journal capture and projection. Original zero runtime-policy/Python-fsync counts describe mechanisms absent in that revision, not free equivalent guarantees or absent SQLite durability. The instrumentation does not prove which component causes the remaining latency; no causal attribution or optimization claim is made. Admission response semantics differ as explained above. This evidence does not validate saturation limits, tune the default worker quotas or promise native-provider performance.

T-E2E-05 is scoped PASS for this same-host before/after comparison including measured policy/fsync. No phase/final gate promotion. Full samples, per-round data and instrumentation/source hashes: [Windows](evidence/p12-benchmark-windows.json), [Linux](evidence/p12-benchmark-linux.json). Preparation failures: [diagnostic manifest](evidence/p12-benchmark-preparation.json). No production code changed. Next: exact WORK/lifecycle acceptance gaps, full original matrix mapping, final suites and packaging/reinstall.
