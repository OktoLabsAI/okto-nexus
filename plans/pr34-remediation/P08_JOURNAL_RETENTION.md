# Explicit journal retention and quota recovery

Parent `0eeb749`, `feature/v0.2.0`, 2026-09-23. Partial P08/P11 operational unit;
no phase or final-gate completion claim.

`FileRuntimeEventJournal.compact` removes only whole segments at or below the
committed projector checkpoint. The active segment is always retained. The
SQLite event history, materialized results and operation records are not deleted.
`RuntimeEventIngress.compact` reads the checkpoint under its projector lock and
ends the read transaction before filesystem operations.

The versioned retention manifest records store identity, the lowest retained
ordinal and first segment. It is flushed and atomically replaced before segment
deletion. A crash before that replacement keeps the old readable prefix; a crash
afterwards may leave obsolete files, which a subsequent compaction removes.
Ordinals and event IDs never restart at one. Recovery rejects a database
checkpoint older than the retained prefix. Restore SQLite and its matching
journal together; never delete the journal directory to clear a quota error.

An authorized operator uses either surface of `RuntimeMaintenanceService`:

- REST `POST /api/v1/harness/journal` with `{}` reports status; with
  `{"compact":true}` explicitly reclaims eligible segments.
- MCP `harness_list(view="journal")` reports status;
  `harness_list(view="journal", compact=true)` performs the same operation.
  The default view remains the adapter catalog. Stdio forwards maintenance to
  the authenticated existing serve owner and does not open a second writer.

The status includes retained bytes, quota, retained cursor, watermark and tail
repair count; it contains no event bodies or credentials. Compaction can clear
a quota admission fault but cannot clear an uncertain I/O/fsync fault. Reopen
and validate that journal before further writes. A full journal can now start
for projection/maintenance while normal admission remains blocked by its quota.

Validation:

- `rtk proxy .venv/Scripts/python.exe -m pytest -q
  tests/test_runtime_journal_retention.py tests/test_runtime_event_journal.py
  --tb=short --maxfail=3`: 16 passed in 10.55s (initial five new cases).
- Same initial selection on WSL Ubuntu, isolated Python 3.13 venv:
  16 passed in 14.54s.
- Expanded retention tests, including partial-segment checkpoint, unknown-write
  refusal and mismatched old database recovery:
  `rtk proxy .venv/Scripts/python.exe -m pytest -q
  tests/test_runtime_journal_retention.py --tb=short`: 7 passed in 4.09s.
- Ruff changed production modules: PASS.

These are injected crash cuts, not machine power-loss qualification. POSIX
directory fsync is implemented. Windows rename/metadata survival under actual
power loss remains NOT_RUN and must not be inferred from process restart tests.
Native connectors were not re-executed for this file-retention unit. Result
publication/artifacts, database history retention, and wider P08–P12 gates
remain pending.

Expanded compatibility command: `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_journal_retention.py tests/test_runtime_event_journal.py tests/test_runtime_restart.py tests/test_runtime_commands.py tests/test_runtime_shutdown.py tests/test_harness_tools.py tests/test_harness_routes.py tests/test_import_boundary.py --tb=short --maxfail=3`: **76 passed, 2 POSIX skips in 131.56s** (collected before the two additional retention cases). Final seven-case retention selection also passed on WSL Ubuntu: **7 passed in 7.39s**.
