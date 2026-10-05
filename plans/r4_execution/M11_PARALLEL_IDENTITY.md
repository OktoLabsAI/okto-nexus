# Bounded parallel Pi build identity reads

Core c2aed11; Connector dca0863; Nexus 43711b8.

## Implementation

Core 0.2.49.dev0 reads at most four manifest files concurrently. It reserves the existing entry and byte budgets before scheduling each read, appends digests in the original order, and propagates discovery cancellation to every reader. All started readers are joined before the discovery call returns. The algorithm remains core.build_identity.v3; full content, dependency topology, optional-relation absence and size-change checks remain covered.

Three focused tests prove the published Core 0.2.48 golden identity despite out-of-order completion, cancellation and reader ownership, and rejection before reading beyond the byte budget. The source regression passed 142 cases.

## Measurement

The source profile completed real Pi 0.87.1 discovery in 12.51 seconds; the preceding installed sequential profile took 66.18 seconds on this host. Both produced sha256:caf8bfad84ea26a7c8eaee06e0cde3dd7e34ef05e00dbebc348dfb3f22de487b. These are individual measurements, not a latency guarantee or a controlled benchmark. Caller-thread profiling does not include worker bodies.

The source profile initially read stale source egg-info metadata; its report explicitly distinguishes that observation from the imported implementation hash and source version.

## Acceptance

Installed regressions passed: 142 Core, 165 Connector and 89 Nexus cases. The real Pi discovery-stop campaign passed with 0.0158 seconds stop latency. The normal Pi journey passed in 448.42 seconds total: readiness, handoff completion through native tools, one work claim, close, approved binding replacement, second native turn and close. Both processes exited with zero and campaign credentials were removed. The existing 120-second readiness deadline is unchanged.

See [run manifest](test_runs_20261001_parallel_identity.json). Source, wheel and installed package bytes matched. The identical Core wheel is present in both consumers; pip check, uv lock check and both contract generators passed. The earlier Core 0.2.48 readiness failure remains recorded separately.

Cooperative cancellation does not preempt an OS read that has not returned. Full shutdown deadlines, per-resource DRAINING_PENDING recovery, Linux, separate hosts, UI acceptance and the final artifact matrix remain pending. This increment does not close M11 or any release gate.
