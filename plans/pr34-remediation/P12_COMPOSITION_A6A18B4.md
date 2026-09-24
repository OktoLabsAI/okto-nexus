# P12 — actual composition gate at a6a18b4

Executed production/test selection from committed SHA `a6a18b4dfeaa0f8272ebf3ecb6b410c8af5a0946`. No selected source or test changed while either campaign was alive. A separate new mirror reproducer was written during this campaign but is absent from its selection and is not covered by its outcomes.

T-E2E-06 joins critical paths through the actual application composition:

- test_runtime_relay_process_restart: actual HTTP owners in separate processes use bootstrap/build_app and production MCP/auth/dispatch/journal/results; owned synthetic Codex protocol processes produce real wire events. Whole-owner deaths and restarts preserve lineage, captured terminal output and uncertain execution. Application clock offsets exercise persistent deadlines without host-clock changes.
- test_runtime_signal_drain: subprocess invokes production CLI run_serve with explicit feature flag and isolated home. Only the external Pi protocol peer and deterministic capture timing are fixtures. Active-turn shutdown drains captured journal bytes and proves exact owned process-tree exit; POSIX signal runs on Linux, graceful control on both platforms.
- test_runtime_disabled_acceptance: actual independent MCP stdio process and HTTP/REST agree on disabled surface/auth enforcement; logical inbox stays usable with no implicit runtime.
- test_runtime_binding_acceptance: actual authenticated surfaces create runtime-owned canonical presence; workspace isolation, close scope, heartbeat/broadcast eligibility and control affinity remain bound to the right session.
- test_runtime_capture_admission: REST/MCP/independent stdio reject executable admission after observed quota/fsync failure, and SQLite capacity rejects a canonical write atomically.
- test_runtime_owner_contention: competing actual server startup cannot become a second owner; the first continues processing through its owned native protocol fixture.

Exact commands and per-node PASS/SKIP identities: [index](evidence/p12-composition-a6a18b4-index.json). Windows27096 exited0: **20 PASS1 SKIP188.71s**. Linux35283 exited0 after its summary: **21 PASS451.02s**. The Windows skip is POSIX signal coverage, not PASS or NOT_APPLICABLE. Raw XML remains under .git/pr34-evidence; only reduced nonsecret manifests are committed.

This is an actual-composition fixture gate, not a native provider campaign or the final full suite. The pending positive mirror and external authenticated attach paths are not qualified by these counts. T-E2E-06 scoped PASS; original matrix124 PASS/5 NOT_RUN. Final gate remains NOT PASSED. Remaining implementation: CONS07 and WORK12; native E2E01/02 retain authorization/environment limits; final report E2E07, immutable-source full suites, release audit and local reinstall0.2.0 remain pending.
