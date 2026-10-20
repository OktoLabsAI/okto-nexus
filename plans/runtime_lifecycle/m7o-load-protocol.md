# M7o: fixed installed load protocol

This protocol was fixed before the load run on 2026-10-18. It closes only the M7 latency-distribution criterion. It does not expand M5, M6, M8 or publication scope.

## Environment and budget

- Disposable installed Nexus 0.3.1 / Connector 0.0.10 / Core 0.0.12 at `127.0.0.1:8204`, workspace M6D; global Nexus remains stopped.
- Real installed harnesses: Pi 0.87.1, Claude Code 2.1.301, Codex CLI 0.162.1. The host has 16 logical cores and 31.7 GiB physical memory; 10.8 GiB was free before the campaign.
- Run one harness at a time. Each agent uses embedded one-shot with maximum 2 parallel instances, 1 warm instance, queue capacity 1, and a 300-second start deadline. At most three test calls are submitted in a burst; no other synthetic load is introduced. Abort and report rather than silently reduce the workload if free physical memory falls below 4 GiB, the harness becomes unavailable, or a provider refuses service.

## Workload and observations

- For each harness, submit **six bursts of three** short, unique exact-marker requests through three independent Meta-harness tabs. Wait for all three terminal results and for the pool to return to 1/2 available before the next burst. This is 18 attempted calls per harness and 54 total. A refusal, timeout or incorrect response remains in the denominator and is reported; it does not cause a replacement call.
- Capture browser send-start and send-finish timestamps; durable message, outbox, one-shot call, runtime.open, turn.submit and terminal receipt timestamps; and the temporary QUEUED/ADMITTED/RUNNING transitions by read-only SQLite polling. The poller is observational and does not mutate scheduling state.
- Report per harness the count of attempted/admitted/succeeded/failed/rejected calls, distinct native sessions, pool recovery, and empirical p50/p95/p99 with sample count for: (1) browser send duration as the admission observation, (2) enqueued-to-start for calls on a pre-existing warm session, (3) runtime.open-to-start for newly opened cold sessions, and (4) QUEUED-to-ADMITTED duration from observed state transitions. The queue transition metric has polling-resolution uncertainty; also report durable enqueued-to-start as the user-visible upper bound. Use linear interpolation over sorted samples and report maxima. Do not infer population percentiles or a performance guarantee from six bursts.
- Preserve exact errors and effect/retry flags. Verify no admitted call lacks a terminal outcome and no pool exceeds two instances. Stop the scoped fixture and check port/process cleanup after the campaign.

The earlier M7n pairwise Claude/Codex calls are separate smoke evidence and are not added to this fixed load sample.
