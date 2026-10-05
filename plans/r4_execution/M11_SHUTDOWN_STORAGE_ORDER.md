# Containment before shutdown storage waits

Nexus db3e019; unchanged Core c2aed11 / 0.2.49.dev0 and Connector dca0863.

## Requirement and defect

NS14.03 requires native containment to proceed independently of blocked storage and requires stores to remain owned while producers can still use them. EmbeddedDispatchOwner previously waited for quiesce persistence and outbox/publication shutdown before requesting Core containment. EmbeddedRuntimeHost also waited for historical readers before calling Core shutdown.

Three fault-injection cases reproduced the defect with two sessions each: blocked quiesce, blocked outbox stop, and a held historical reader. Each baseline failed because native stop had not occurred within the observation window.

## Change

The dispatch owner fences its in-memory pump and starts a retained Core containment task before waiting for quiesce or publication cleanup. The host's containment pass preserves its journals, runtime references and shared ledger. After dispatch and renewal producers finish, the host joins history readers and closes only resources whose Core shutdown outcome is resolved. The failure-containment path uses the same store-retention rule.

The focused source cases now pass: both native sessions stop while cleanup remains blocked, both journals remain readable, and releasing the blocker completes cleanup without another native open. Existing cancellation semantics keep the close task owned after an observer stops waiting.

## Installed result

99 tests passed in 295.42 seconds. Source, wheel and installed package bytes matched; pip check passed. The three baseline failures and three focused source passes are retained in the [run manifest](test_runs_20261001_shutdown_order.json). The source cases overlap the installed regression.

## Scope

The test enters through real Nexus binding/admission/dispatch composition with actual Core and synthetic native handles. Additional installed regression includes the technical Pi subprocess bridge; neither campaign qualifies a real provider build.

This is one required part of NS14.03. The shared public deadline, per-resource DRAINING_PENDING projection, retained administrative recovery service, late-open/release fault matrix and second public recovery remain pending. No release gate is closed.
