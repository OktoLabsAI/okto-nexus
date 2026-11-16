# E09 visibility revalidation

Two deterministic controller tests exposed a freshness gap. Returning from a
hidden tab left the previous snapshot `ready` while the fresh GET was pending.
After marking it stale on wake, a GET already started in background could still
publish `ready` before the post-wake read completed. Both failures are retained.

The controller now marks all sections stale synchronously on becoming visible.
If a read is active, it aborts and advances the generation but retains ownership
until that read's `finally`; only then can the queued fresh read start. Late
responses cannot clear the fence. The test verifies peak concurrency remains
one. Existing per-section stale consumers disable preference/continuation
controls while the old snapshot remains readable.

The final focused run has twelve passing controller/presentation cases,
including both new barriers and existing scope, authorization, pause, cursor,
fallback, source-TTL and reconnect regressions. This is a deterministic
controller qualification, not another browser or runtime campaign. No provider,
service, production credential or OS operation was involved.
