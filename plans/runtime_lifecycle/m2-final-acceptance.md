# M2 final acceptance — local runtime lifecycle

The M2 launch contract, pre-spawn intent, container identity, monotonic producer
fence, and Core-backed physical containment were implemented in the Core and
consumed by the embedded Nexus and Connector adapters in M2a–M2e. Installed
tests for the Windows owner and both consumers are recorded in the milestone
ledger and [M2d](m2d-validation.md)/[M2e](m2e-validation.md).

The Linux launch cuts (`okto-nexus-connector-core/plans/runtime-lifecycle-m2f-linux-crash.md`)
and macOS guardian cuts in the Core qualified physical recovery before and after
intent, claim, spawn, and birth. [M2h](m2h-late-crash-cuts.md) then exercised
installed local wheels at the native handshake, native-write ACK, Core receipt,
Server receipt/projection, and late-producer boundaries. The native-write ACK
case actually killed its owner after the write; the separate event-ACK case
used a controlled lost ACK and owner replacement, without a process kill at
that exact instant. Neither case replayed a native effect or released an
uncertain slot without proof.

The final CI runs passed: [Core 39336889894](https://github.com/OktoLabsAI/okto-nexus-connector-core/actions/runs/39336889894)
8/8 jobs, [Connector 39343006146](https://github.com/OktoLabsAI/okto-nexus-connector/actions/runs/39343006146)
8/8, and [Nexus 39472894540](https://github.com/OktoLabsAI/okto-nexus/actions/runs/39472894540)
24/24 installed jobs. The [UI-A restart gate](ui-a-installed-restart-evidence.md)
showed all three local harnesses recover and answer after an abrupt disposable
Server stop. The [global CI-wheel rollout](m8-global-ci-wheel-rollout.md)
preserved the home, retired a completed Pi session with proof, and left only
the configured four warm native processes under one Server.

This closes M2 for the local embedded and same-host Connector scope of the
plan. It does not claim a physical remote Connector host or establish the
cause of the earlier unrelated global Server stop.
