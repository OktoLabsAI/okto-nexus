# Operational measurement completion

Runtime sourceff905c433e1a92ae35993b2189919f75ad07dd51. A final operational
audit found the previous comparative benchmark recorded admission and persisted
terminal latency, but did not separately measure commit-to-dispatch, first event,
terminal capture/fsync and terminal projection. This was an evidence gap, not a
new claim that the implementation lost events or used polling.

The optional `--operational-metrics` mode in runtime_comparison_benchmark.py now
installs a bounded in-memory probe around actual command enqueue, SQLite COMMIT,
command execution, native journal append/fsync and projection commits. Original
methods, return values and exceptions remain in use. Hooks perform no network,
process, secret, logging or additional database work inside a writer transaction.
Aggregate DB reads, journal diagnostics and current-process resource observations
occur only in explicit outside-transaction snapshots. This is a test instrument,
not a new production exporter or public API.

Windows and Linux final campaigns exited0. Each observed10 real fixture turns
(5 warmup plus5 measured workload iterations), ten repeated HTTP requests with
identical keys and exactly one actual dispatch per operation. Both had every
required timing observation, no probe overflow, no remaining owned native process
or live binding after shutdown, and a fully projected journal (52 records,
73233 retained bytes). Windows shutdown1820.36ms; Linux2023.53ms. These times include
probe/concurrent-suite effects and are not comparative performance claims.

| Required measurement | Evidence/source and scope |
|---|---|
| Enqueue/admission latency | Actual authenticated HTTP command request to admission response; persisted enqueue commit observed independently |
| Commit to dispatch | Interval bounded by COMMIT call/return and RuntimeControlService.execute entry; no false exact timestamp if another thread runs before commit wrapper returns |
| First event; accepted to terminal | Native journal-ingress observations correlated in memory to the operation; acceptance uses native started evidence, not a successful socket write |
| Terminal to durable/projected | Successful journal append return and subsequent SQLite projection commit; missing/failed commit never becomes a complete sample |
| State/backlog per lane | Aggregate delivery_outbox/runtime_commands state counts and queued/dispatching endpoint-lane distribution, including pending fallback binding; no IDs exported as metric labels |
| Retry; unknown/unconfirmed; authorization | Stored attempt/state/audit aggregates; this successful workload observed zero retries/uncertainty/runtime-policy denials. A separate invalid-credential request returned401 before runtime policy. Zero does not qualify fault paths |
| Duplicate suppression | Ten repeated HTTP requests reused exactly ten operation IDs and ten actual dispatches, without storing IDs in the metric report |
| Budgets | Stored root/admission/message aggregates; command-only workload observed zero causal roots. Relay budget behavior remains in P10_MATRIX_COMPLETION, not inferred from these zeros |
| Journal bytes/lag; uncorrelated events | Explicit journal and read-snapshot checkpoint observations; idle checkpoints matched52/52 and uncorrelated native count0 |
| Active runtimes/processes/resources/shutdown | Owned binding/Popen observations, RSS and OS threads plus Windows handles/Linux FDs at three phases; exact cleanup only claims these owned fixture processes. Repeated leak/crash bounds remain in P12_CRASH_PRESSURE and P12_RECOVERY_PRESSURE |

Only bounded categories/numeric values reach reports. Operation IDs are transient
in-memory correlation keys, never labels or persisted payloads. The probe bounds
operations to256 and fails qualification if incomplete or overflowed. Three
integrity tests PASS on each platform: absent capture is not promoted, failed
real SQLite COMMIT cannot mark durability, and a commit-return race retains an
interval. Ruff PASS. No runtime/test-source or migration contract changed.

Initial Windows observation succeeded. The first Linux probe failed before turns
because its Python environment lacks psutil; owned peer cleanup had completed.
The final Linux resource branch reads /proc/self directly, consistent with the
existing pressure procedure, without changing the running suite's dependencies.
Windows uses installed psutil. All preparation outcomes/hashes are preserved in
[evidence/p12-operational-metrics-index.json](evidence/p12-operational-metrics-index.json).

Exact commands, instrument hashes and observations are in the linked final
[Windows](evidence/p12-operational-metrics-windows.json) and
[Linux](evidence/p12-operational-metrics-linux.json) manifests. The fixture uses
fresh homes/loopback HTTP, Python Codex protocol peers and allowlisted child
environments. No installed provider, personal account configuration or operator
credential is passed to a native child. The script's output SHA describes runtime
source; separate instrument hashes identify this plan-only working generation.
Historical comparative results remain scoped to their original SHA/configuration.
