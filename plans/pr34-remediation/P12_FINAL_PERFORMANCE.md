# Final corrected-source performance comparison

Both sequential campaigns terminated exit0/PASS: Windows30445, Linux17569.
Current benchmark commit7560970 has no src/tests/scripts/frontend/config/lock
changes from implementationff905c4. Original is PR34d7d87d0. Exact full SHAs,
commands, source/instrument hashes and all samples are retained in
[evidence/p12-final-benchmark-index.json](evidence/p12-final-benchmark-index.json).

Both full suites and native/UI/installed smoke campaigns had terminated before
these comparisons. Windows completed before Linux started. Each platform uses
its own same-interpreter/dependency/filesystem original/current pair. Six rounds
alternate original/current/current/original/original/current, five warmups and
40 measured turns per round:120 measured turns and15 warmups per revision.
No round, outlier or sample was dropped. Dependency/configuration/peer equality,
required authentication, current policy/fsync and owned peer shutdown all passed.
SQLite WAL and synchronous=2 are retained. The source archives are disposable;
all stores/profiles are fresh, with synthetic peers and no provider accounts.

| Platform / metric (ms) | Original p50 | Current p50 | Original p95 | Current p95 | Original p99 | Current p99 |
|---|---:|---:|---:|---:|---:|---:|
| windows / admission_ms | 12.471 | 153.633 | 26.818 | 236.736 | 53.860 | 271.804 |
| windows / persisted_terminal_ms | 90.540 | 381.221 | 141.486 | 563.419 | 203.046 | 612.085 |
| linux / admission_ms | 58.739 | 81.739 | 68.658 | 109.297 | 69.235 | 115.980 |
| linux / persisted_terminal_ms | 59.730 | 207.075 | 69.637 | 264.753 | 70.364 | 308.487 |

| Platform / component (mean ms per turn) | Original | Current | Current calls per turn |
|---|---:|---:|---:|
| windows / authentication | 0.137 | 0.723 | 1.0 |
| windows / runtime_policy | 0.000 | 70.596 | 6.0 |
| windows / fsync | 0.000 | 1.967 | 5.0 |
| linux / authentication | 0.088 | 0.960 | 1.0 |
| linux / runtime_policy | 0.000 | 36.000 | 6.0 |
| linux / fsync | 0.000 | 6.797 | 5.0 |

The corrected implementation is slower in this synthetic sequential workload.
It retains durable admission, runtime authorization/revalidation and journal
capture/projection. Original zero runtime-policy/Python-fsync counts describe
mechanisms absent in that revision, not equivalent guarantees at zero cost.
SQLite internal C fsync remains part of end-to-end latency. Nested measurements
are not an additive causal explanation of overhead.

Admission semantics differ: original waits for immediate transport send, current
acknowledges durable command admission. The common terminal measure observes
persisted SQLite events, using the same1ms local test observer in both versions;
it never queries the native harness. Percentiles use nearest rank. These are
local synthetic control-plane measurements, not model latency, saturation
capacity, worker-quota tuning or a production SLO.

Earlier comparison results remain explicitly scoped to536b993 in
P12_COMPARABLE_PERFORMANCE.md and are not reused as this run's numbers. Detailed
boundary observations (commit/dispatch/first event/fsync/projection/state/resources)
remain the separate instrumented campaign in P12_OPERATIONAL_METRICS.md; those
concurrently measured timings are not mixed into this comparison.
