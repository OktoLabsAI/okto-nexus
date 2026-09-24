# External IO outside SQLite write units

2026-09-24; parent e18cf69482461ffb407d770f72d1b2871ce824f8 plus the new acceptance-test hash. Production unchanged.

T-TX-07 combines the existing native-send, journal/fsync and artifact writer-isolation checks with new test_runtime_io_boundaries.py. The new test instruments SqliteUnitOfWork entry/exit with a per-thread nested writer depth, including commit/rollback. It observes the production profile resolver resolving an explicit disposable environment reference, production owned-process spawn, actual Codex pipe writes, and the canonical REST steering-message embedding callback. Each path must actually execute with no write depth; violations are retained independently so a best-effort exception handler cannot produce a false PASS.

The explicitly configured model is the repository's deterministic StubEmbeddingProvider with a local fixture transport. Each encode owns a short-lived TCP listener/connection bound exclusively to127.0.0.1, exchanges seven fixture bytes, then generates the deterministic vector. Positive embedding persistence is asserted. This is actual loopback network IO at the model callback boundary, not an external model/provider call or proof about an unavailable remote SDK. The native peer is an owned Python protocol fixture; no ambient provider/configuration or operator key is inherited. Sockets have deadlines and reject premature EOF.

Initial Windows34109:1 PASS7.47s, eventually exit0 after tool-observed process drain. Expanded Windows45214:4 PASS18.25s/Linux30999:4 PASS22.23s, exit0. Before final qualification the synthetic model's sockets were changed from one test-shared connection to per-callback ownership to avoid concurrent receipt-embedding/teardown lifetime races; no such product defect was asserted. Final commands below qualify that exact new-file hash.

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short --junitxml=.git/pr34-evidence/io-e18cf69-final-windows.xml tests/test_runtime_io_boundaries.py tests/test_runtime_outbox.py::test_p06_native_send_is_outside_sqlite_write_transaction tests/test_runtime_event_journal.py::test_journal_io_outside_write_uow_and_full_sync tests/test_runtime_artifact_durability.py::test_artifact_storage_does_not_hold_sqlite_writer
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short --junitxml=.git/pr34-evidence/io-e18cf69-final-linux.xml tests/test_runtime_io_boundaries.py tests/test_runtime_outbox.py::test_p06_native_send_is_outside_sqlite_write_transaction tests/test_runtime_event_journal.py::test_journal_io_outside_write_uow_and_full_sync tests/test_runtime_artifact_durability.py::test_artifact_storage_does_not_hold_sqlite_writer
rtk proxy ruff check tests/test_runtime_io_boundaries.py
```

Ruff PASS. Terminal final counts and sanitized per-node manifests below. Scope is the exercised production UoW/callback paths plus the specified fixture network/model. This does not qualify arbitrary future adapters, full-suite performance or scheduler-pressure/leak gates.

Final Windows82635:4 PASS15.33s/Linux26764:4 PASS19.78s, both terminal exit0. Persistent XMLs reduced; every mapped node matched PASS on both. T-TX-07 scoped PASS. Source/test unchanged during final selections. No live test processes remain.
