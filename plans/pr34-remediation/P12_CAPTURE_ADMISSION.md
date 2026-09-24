# P12 — journal and storage exhaustion admission

Parent `3e875789b3d36843d13b7c2918cef314e20009b8`; exact changed-file hashes, commands and per-node outcomes for each generation are in [the evidence index](evidence/p12-capture-admission-index.json). Schema062 is additive; surface57 and identity25 are unchanged.

The defect was reproduced against the existing composition: after actual journal quota exhaustion or injected fsync ENOSPC, REST still accepted a durable command and MCP still committed a canonical message/outbox. Initial Windows RED had4 FAIL and4 teardown ERROR11.42s. Reopening only the disposable broken journal during fixture cleanup removed the teardown errors; clean RED remained4 behavioral FAIL14.46s. This cleanup is not evidence of automatic production recovery.

RuntimeEventIngress now serializes capture failure and health recovery. The current RuntimeDispatcher owner publishes capture health through an owner/epoch CAS on the existing runtime_writer_contract. SqliteRuntimeOutboxRepo, SqliteRuntimeCommandRepo and SqliteRuntimeRequestRepo check it inside canonical admission transactions. Migration062 also guards inserts with database triggers, including writers that bypass current repositories. Composition wires the callback; supervisor and dispatcher retain a final capture check before native execution. Health persistence happens after journal IO and outside any existing writer UoW. Bounded owner recovery retries a failed health update; it never replays an uncertain native operation.

Final cases cover quota/fsync across REST command, MCP message and a separate actual Nexus stdio process; all reject before intent or send, preserve the journal watermark, produce no durable runtime result and emit a fixed redacted ERROR. Additional cases prove projected-segment compaction restores quota admission without losing five captured events, old epochs cannot clear the fence, cached authorized replies survive, raw inserts and new opens are blocked, and real SQLite max_page_count exhaustion rolls back message/delivery/outbox before a subsequent successful send after capacity is restored.

The final nine cases passed on Windows29604 **9 PASS38.18s** and Linux3881 **9 PASS47.95s**. Earlier4-case and9-case green generations are retained separately. Regression through event journal, retention, shutdown, commands, outbox, writer contract, backup/restore, bounded buffers, artifact durability, migrations and import boundary: Windows93838 **103 PASS273.26s**, Linux17871 **103 PASS304.31s**, one existing Starlette deprecation warning each. No overlapping run counts are added together. All handles exited0.

The regression's test_runtime_event_buffers nodes supply the finite byte/count history, subscriber capacity, explicit overflow and production reap/unknown assertions in the T-JRN-09 join. The final new cases add admission, storage rollback and alert assertions.

Exact pytest commands are stored in each manifest. Additional validation:

```powershell
rtk proxy ruff check tests/test_runtime_capture_admission.py src/okto_nexus/application/runtime_event_ingress.py src/okto_nexus/application/runtime_dispatcher.py src/okto_nexus/application/harness_supervisor.py src/okto_nexus/adapters/inbound/mcp/tools/harness.py src/okto_nexus/adapters/outbound/sqlite/runtime_outbox_repo.py src/okto_nexus/adapters/outbound/sqlite/runtime_commands_repo.py src/okto_nexus/adapters/outbound/sqlite/runtime_requests_repo.py
rtk proxy .venv/Scripts/python.exe scripts/live_client.py
rtk git diff --check
```

Ruff/diff PASS. Required isolated live MCP smoke exited0, LIVE E2E RESULT:PASS8.25s; temporary stores removed. Raw logs/keys were not committed.

Limitations: no host disk was filled; journal quota and SQLite page limits are actual capacity mechanisms, fsync ENOSPC is injected. If SQLite cannot persist the health fence, recovery logs and retries it and the final native guard remains; this does not promise atomicity across two unavailable stores. Unknown fsync durability requires journal validation/recovery, not quota compaction or blind replay. No provider campaign ran in this unit. Original matrix123 PASS/6 NOT_RUN; final gate remains NOT PASSED. Next dependencies are positive mirror observation, authenticated external attach work, actual-composition final join/report, complete immutable-source suites and release/reinstall0.2.0. Native Pi/attach retain their explicit NOT_RUN limits.
