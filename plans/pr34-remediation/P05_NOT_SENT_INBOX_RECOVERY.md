# P05/P06 — proven non-delivery can return to canonical pull

Source parent eb608078a30c5d34b9c4a374fabe6847632d17c1, feature/v0.2.0.
Schema058 and resident surface53 unchanged; identity reference20 to21.
Final plan gate NOT PASSED; automatic safe retry/backoff/endpoint fallback remain pending.

## Reproduction and implementation

T-CONS-03 previously remained NOT_RUN. An actual owned Codex Python protocol peer
with an unknown version starts a thread, but qualified transport refuses turn/start.
The owner records REJECTED/native_write_not_started/ACK NONE and retains the unread
push reservation. Both REST and MCP release_to_inbox then rejected the exact
operator snapshot as uncertain; neither the native session nor pull could process
that original delivery. Behavioral RED: **2 failed in9.12s**, both CONFLICT from
the actual shared maintenance service, not missing imports or corrected mocks.

RuntimeOperationMaintenanceService.run now recognizes only this narrow stored
proof: delivery_outbox, REJECTED, native_write_not_started, ACK NONE, attempt ID,
no observed native thread/turn or terminal. Generic rejection/error text/NONE alone
cannot establish proof. The operator explicitly uses release_to_inbox with false
duplicate-risk acknowledgement. Current owner, exact snapshot, no in-flight call,
operator authorization, idempotency and canonical handoff exclusion still apply.

The existing migration054 audit and canonical inbox release commit together.
Original status/reason/attempt/ACK are preserved. No native request, new delivery,
receipt, endpoint quarantine or grant revocation is invented. Uncertain recovery
keeps all existing controls. Managed work still requires canonical claim recovery.
No new table, action or network/process call inside a write transaction is added.

## Evidence

All commands use rtk proxy; Windows interpreter .venv/Scripts/python.exe.
Linux uses WSL Ubuntu, cwd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus, interpreter
/var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python.

- RED: `-m pytest -q --tb=short tests/test_runtime_not_sent_recovery.py`:
  2 FAIL9.12s, REST and MCP return409/CONFLICT despite proven non-delivery.
- Expanded focused suite, same command: **9 PASS36.82s** Windows. Includes both
  surfaces, operator-only access, idempotent replay, unchanged transport history,
  original message returned by authenticated inbox_pull, six incomplete-proof
  denials, and atomic rollback of audit/inbox/source on an injected commit cut.
- Initial Windows integration:
  `-m pytest -q --tb=short tests/test_runtime_not_sent_recovery.py tests/test_runtime_operation_reconciliation.py tests/test_runtime_handoff_recovery.py`:
  **33 PASS1 FAIL105.40s**, one Starlette warning. This run collected the initial
  two new tests before the later seven were added.
- Linux expanded integration, same command: **40 PASS1 FAIL144.09s**, one warning.
  Both failures were the existing migration assertion expecting only54..57;
  migration058 had already landed in d76b78c. Updated that exact expectation.
  Linux had already collected the old assertion when its source line changed;
  its failure is retained, not relabeled as a pass.
- Linux corrected migration plus reference/import checks:
  `-m pytest -q --tb=short tests/test_runtime_operation_reconciliation.py::test_reconciliation_migration_is_additive_and_repeatable tests/test_frente1_resources.py tests/test_import_boundary.py`:
  **16 PASS13.62s**.
- Final Windows expanded integration, same three files plus tests/test_frente1_resources.py and tests/test_import_boundary.py: **56 PASS131.78s**, one Starlette warning.
- `rtk proxy ruff check` on the five changed Python files: PASS. The first
  `.venv/Scripts/python.exe -m ruff` invocation could not run (module absent);
  installed ruff executable completed the actual check.
- `rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/measure_surface.py eb60807`:
  unchanged OFF43 tools/40448 characters/10112 estimated tokens;
  ON51 tools/47730 characters/11932 estimated tokens. Only fetched identity
  documentation changed; no resident schema revision increment required.

No provider/model was called for this recovery unit. The preceding d76b78c real
Codex/Claude campaign remains separately recorded in p06-capacity-native.json.
Pi and dedicated attach native remain NOT_RUN.

Next dependency: distinguish transient pre-write proof from permanent rejection,
persist per-attempt history and retry deadlines, then implement bounded backoff
and approved equivalent-endpoint fallback without changing canonical work authority.
