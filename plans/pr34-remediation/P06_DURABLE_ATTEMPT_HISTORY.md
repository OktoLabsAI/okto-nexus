# P06 — durable transport attempt observations

Parent fd9ea1692d40a763b7ae03ce8832d06d0c74405a, feature/v0.2.0.
Schema059, resident surface54, identity reference22. Final gate NOT PASSED.
This is the persistence prerequisite for safe retry/backoff and endpoint fallback;
those algorithms are still pending and are not claimed by this unit.

## Reproduction and code

An actual serve dispatcher claimed a canonical message and paused before
send-intent. Quiescing/releasing that owner and starting the replacement safely
sent exactly once, but discarded the prior attempt identity from inspection.
The production HTTP/MCP regression failed on the missing history:1 FAIL3.12s.
No test import or proposed table name was required to reproduce the loss.

Migration059 adds runtime_delivery_attempt_events as append-only observations,
not an additional queue. A SQLite trigger captures attempt/state/ACK/binding/native
reference changes in the same transaction as delivery_outbox, including old attempt
identity when recovery resets CLAIMED to PENDING. Heartbeat-only updated_at changes
do not grow history. UPDATE/DELETE are rejected; rollback rolls back observations.
Migration snapshots only the current known attempt, explicitly labeled
migration_snapshot; it never fabricates older attempts or transition timestamps.

RuntimeOperationMaintenanceService._inspect returns the latest64 observations in
sequence order only for exact delivery operation detail, with a truncation flag.
Full data remains stored. List pages and runtime_commands do not claim this history.
Existing operator-only REST/MCP authorization, inbox/claim ownership and recovery
are unchanged. No prompt, key or native environment is copied into the history.
No external call is introduced inside a SQLite write transaction.

## Tests and evidence

All commands below use rtk proxy; Windows .venv/Scripts/python.exe; Linux WSL
Ubuntu at /mnt/d/Projetos/Techridy/okto_labs_okto_nexus with
/var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python.

- RED: `-m pytest -q --tb=short tests/test_runtime_attempt_history.py`:
  **1 FAIL3.12s** (missing prior attempt in real operator inspection).
- Initial implementation plus prior safe-release regression:
  `-m pytest -q --tb=short tests/test_runtime_attempt_history.py tests/test_runtime_not_sent_recovery.py`:
  **10 PASS34.78s**, collected before adding the next two history tests.
- Expanded history/migration checks:
  `-m pytest -q --tb=short tests/test_runtime_attempt_history.py tests/test_migrations.py tests/test_runtime_operation_reconciliation.py::test_reconciliation_migration_is_additive_and_repeatable`:
  **11 PASS9.76s**. Includes immutable history, no heartbeat growth, atomic
  rollback, and populated schema058 to059 upgrade using the actual HTTP fixture.
- Final expanded selection: -m pytest -q --tb=short tests/test_runtime_attempt_history.py tests/test_runtime_outbox.py tests/test_runtime_operation_reconciliation.py tests/test_runtime_not_sent_recovery.py tests/test_runtime_writer_contract.py tests/test_runtime_backup_restore.py tests/test_migrations.py tests/test_frente1_resources.py tests/test_import_boundary.py: **Windows84 PASS196.20s**, one Starlette warning. **Linux84 PASS221.90s**, one Starlette warning. Source implementation stayed fixed during both selections.
- Metadata:
  `-m pytest -q --tb=short tests/test_comm_presets.py tests/test_feature_flags.py tests/test_handoff_dependencies.py tests/test_health.py tests/test_memory.py tests/test_replay_marker.py tests/test_verification.py -k "surface_revision or nexus_info_features"`:
  **9 PASS245 deselected6.44s**, one Starlette warning.
- Ruff on changed Python files: PASS.
- `rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/measure_surface.py fd9ea16`:
  OFF43 tools40448 characters10112 estimated tokens; ON51 tools47730 characters11932
  estimated tokens. No resident schema growth; surface53 to54 reflects the new
  operator detail response, fetched identity documentation21 to22.

No native provider/model run for this unit. Latest real campaigns remain tied to
d76b78c; Pi and dedicated attach native NOT_RUN. No migration of personal stores.
Next: typed transient pre-write proof, durable retry deadline and bounded jitter/
backoff with injected clock, then equivalent-endpoint selection and authority checks.
