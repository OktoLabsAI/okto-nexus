# P06 — outbox backpressure (isolated work in progress)

Development checkout: `D:/Projetos/Techridy/okto_nexus_scheduler_worktree`, detached
43388c8f7298946c4a711850c25545925b58f01c. No commits there. Main implementation stays
frozen for Windows60009/Linux87041 complete regressions. Do not integrate until
those runs end and their results are preserved.

## Confirmed gap and change

`test_runtime_outbox_backpressure.py` reproduced an unbounded recipient transport
queue through authenticated production HTTP/MCP. The independent causal rate quota
was explicitly raised in the disposable fixture so it would not hide accumulation.
Thirty-two messages admitted; the next also admitted, violating the expected
transport capacity. **Behavioral RED1 FAIL6.26s**.

`SqliteRuntimeOutboxRepo.enqueue` now checks capacity inside the same write UoW,
after idempotency and before reserving logical consumption. Bounds follow the
existing command-queue budgets:256 total unresolved reservations,4MiB canonical
envelope bytes,32 per authenticated actor,32 per recipient,128 per workspace.
Both accepted/unconfirmed and unknown/rejected-but-still-reserved operations count.
No prior delivery is evicted, replayed or silently donated to another executor.

Exhaustion returns QUOTA_EXCEEDED/runtime_delivery_backpressure and rolls back the
new canonical message or managed claim/grant transaction. Already accepted intents
stay durable. Pure logical delivery without a transport executor remains usable.
Explicit safe cancellation can release capacity. There is no new queue or second
work authority. A retry of an existing operation is checked before charging capacity.

Additive migration058 adds a partial index on unread push reservations for this
capacity query. No row/backfill deletion or reverse migration. Main schema remains057
until integration. Public revision/docs must be advanced at that milestone.

## Results so far

- Initial one-case correction plus outbox/handoff selection:32 PASS94.28s.
  Migration058 was added during that development selection; this is not an
  immutable-SHA gate and is not claimed as final migration qualification.
- Expanded fixture initially:2 FAIL1 PASS13.59s. Quiescing admission also prevented
  the recovery call; pausing scans preserves authorization. The byte fixture omitted
  the required subject and failed MCP argument validation; fixed with a subject.
- Corrected three cases:3 PASS15.78s, including byte-budget rollback and managed
  claim/grant rollback.
- Added concurrent last-slot admission and unconfirmed-reservation capacity tests.
- Expanded68-case selection: Windows63 PASS5 FAIL161.19s; Linux63 PASS5 FAIL187.13s.
  All five failures were real stdio children loading the main editable package
  (schema057) against the isolated test store (schema058), correctly refusing a
  newer schema. This was a mixed-checkout fixture, not permission to weaken migration
  checks. `stdio_environment` now explicitly selects this checkout's `src` for the
  child Nexus writer. Native harness environments remain sealed and unmodified.
- Corrected same selection is currently running: Windows90836/Linux80706.

Exact selection (both platforms):
`python -m pytest -q --tb=short tests/test_runtime_outbox_backpressure.py tests/test_runtime_outbox.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_writer_contract.py tests/test_runtime_endpoints.py tests/test_migrations.py`.
Windows prefix `rtk proxy D:/Projetos/Techridy/okto_labs_okto_nexus/.venv/Scripts/python.exe`;
workdir is the isolated checkout. Linux prefix `rtk proxy wsl -d Ubuntu --cd
/mnt/d/Projetos/Techridy/okto_nexus_scheduler_worktree --
/var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python`.

## Next scheduler dependency

The lane-truncation correction is insufficient for per-agent fairness. A further
real-surface test queues direct turns for two endpoints of one agent and a third
endpoint of another. The two worker slots both select the first agent's endpoints.
`test_runtime_scheduler_fairness.py -k one_agent`: **1 FAIL3 deselected6.38s**.
That regression is intentionally still RED in the isolated checkout. Implement
agent-level normal-dispatch capacity without breaking independent control lanes,
native multiplexing, authorized parallel inference or uncertainty fencing. Then
complete safe retry/backoff/fallback and final matrix/stress/performance gates.

No native model campaign or aggregate final gate is claimed for this unit.
