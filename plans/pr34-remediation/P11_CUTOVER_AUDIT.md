# P03/P11/P12 — outstanding cutover and backup audit

Current update (2026-09-24): writer defect corrected in c27223b (P03_WRITER_CONTRACT.md); combined backup/restore evidence now in P12_COMBINED_BACKUP_RESTORE.md. Historical suite session15489 is terminal:2296 PASS/4 FAIL/117 SKIP; see P12_SUITE_FEEB14D.md. The audit below is preserved as historical evidence, not the current resume instruction.

Inspected implementation/test SHA `feeb14d`, while its full Windows suite runs.
This document records findings, not a completed gate or a proposed replacement
for the remediation requirements. No production source was edited during the run.

## Writer-mode inconsistency reproduced

`ConnectionFactory.get_connection` configures SQLite and checks synchronous=FULL
when the caller's integration flag is enabled. `MigrationRunner` rejects a ledger
newer than the package during bootstrap. Neither establishes a store-wide writer
capability requirement for an already running process or a same-version process
with a different integration flag.

The production message service conditionally creates runtime causal/outbox records
from its process-local `feature_harness_integrations`. The canonical message and
inbox rows can therefore commit through a feature-OFF producer while another
feature-ON owner has approved, ready runtime bindings on that same store.

Executed reproduction:

```powershell
rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/evidence/p11_writer_mode_probe.py
```

The captured run used the identical source through Python `-c`; the checked-in
script preserves it for reproduction. It starts an isolated authenticated HTTP
owner with a synthetic Pi peer and approved binding, then an authenticated real
stdio MCP subprocess with the feature explicitly OFF against that disposable
store. It creates one fixture message using the normal `message_create` tool.
No native provider, personal endpoint or existing session is accessed.

Observed at feeb14d:

- Request accepted (`ok=true`).
- One canonical delivery: unread, consumer_kind=null.
- Zero delivery_outbox rows and zero synthetic peer sends.

Evidence: `evidence/p11-writer-mode-audit.json`. This is a demonstrated gap in
transport admission consistency, not identity impersonation or an observed double
execution. The probe is diagnostic; its zero exit status is not an acceptance PASS.
An earlier probe reached the request but its evidence query used the wrong logical
table name (`runtime_outbox` instead of `delivery_outbox`); that probe failed and
was corrected in a fresh disposable store. No uncertain real operation was retried.

Next required implementation must establish and enforce the active store's writer
contract at transactional admission, including already-open incompatible writers
and current feature-OFF producers. Preserve ordinary legacy behavior when no
integration contract is active. Do not merely add another bootstrap-only check or
silently reclassify committed deliveries after the fact. Qualify enabling, draining,
disabling, stale writers and rollback through actual MCP/REST/serve composition.

## Backup evidence is incomplete

`test_p03_additive_upgrade_preserves_agent_and_legacy_history` exercises SQLite's
backup API and validates a restored database after schema028/029 upgrade. It does
not include the runtime journal or artifact payloads. Existing journal corruption,
artifact durability and runtime restart tests cover component failures but do not
prove a consistent combined backup/restore point.

Required remaining evidence for T-MIG-08/P03-T05/P12:

- Quiesce/drain admissions and verify the previous owner and owned effects have
  stopped before a restored owner can run. Never treat a timeout as observed stop.
- Back up SQLite consistently, together with journal store identity, retention
  manifest/segments and artifact manifests/payloads corresponding to database refs.
- Restore into a fresh temporary store, initially with admission disabled; validate
  integrity/FKs, journal/checkpoint consistency and every confirmed artifact ref.
- Preserve pending/unknown operation fences, canonical identity and dedupe; no
  automatic replay of uncertain effects or resurrection of historical processes.
- Demonstrate mismatch/missing-file refusal and interrupted migration recovery.

The existing schema-ahead startup guard remains useful but is not sufficient for
the live writer-mode finding above. Rollout documentation must state the actual
verified procedure and limitations; no real user store has been migrated/restored.

## In-flight complete regression

The full suite started on feeb14d with all native campaign flags removed and legacy
live flags zero. Poll exec session15489 until authoritative completion; never start
a replacement merely because observing it times out. Its wrapper writes redacted
`evidence/p12-suite-feeb14d.json`; raw XML remains in a unique temporary directory.
Production code/tests remain unchanged while that run proceeds. P12 final gate is
NOT PASSED regardless of that suite's eventual result while the above gaps remain.

Archive note2026-09-24: the original diagnostic artifact is preserved byte-for-byte as evidence/p11_writer_mode_probe.py.txt (SHA256 2844bffcddc261f5054acaea8f5d794c288a557844f9aeed079db4af8e033f9f). It contains a leading plus and is not a supported runnable utility. The command above is historical, not a current operation instruction. Current writer/cutover acceptance uses tests/test_runtime_writer_contract.py and P12_MIGRATION_ROLLOUT_INTEGRATION.md. No historical test result is reclassified by this archival correction.
