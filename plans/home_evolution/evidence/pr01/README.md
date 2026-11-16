# HOME-R1 PR01 backend qualification

The Home read model uses one operator-authorized read transaction. Work,
results and Attention share one statement-local canonical occurrence relation.
Pages bind their cursor to scope and structural revision; no stored Home
snapshot, per-agent requests, migration or runtime/provider call was added.

`qualification.json` records source hashes, commands and retained fixture
failures. The XML files contain 30 distinct passing cases: 28 Home cases and
two existing Attention authorization regressions. The five final delta cases
overlap four cases from the full 27-case Home run.

Coverage includes current started-event evidence rather than SUBMITTED as
running; handoff/delivery/attempt deduplication; old claim separation; direct
delegation; canonical titles; scoped and bounded result/artifact references;
canonical result viewing preferences; pending recipient classification;
pagination; unavailable sources; and real ASGI operator/agent boundaries.

The active-artifact HTTP header fix is also exercised independently by the
PR06 boundary qualification. The body and existing authorization stay intact.

This is source, SQLite and in-process HTTP evidence. It is not live provider,
Windows service or operating-system-event evidence. Performance measurements
are retained separately under `pr05-performance`; the measured large-case
latency remains above the 500 ms target and is not presented as meeting it.
Root selects task/scenario acceptance; this handoff does not update ledgers.
