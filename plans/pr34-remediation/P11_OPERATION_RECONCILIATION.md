# P11 — explicit recovery of uncertain transport operations

Parent `b906f0fac15a86d82dbfad1a4a6e0a7f129a57b9`, branch `feature/v0.2.0`,
2026-09-23. Package 0.2.0; additive migration **054**, surface **42**, identity
reference **9**. This is a partial P11 milestone, not the final phase gate.

## Behavior and implementation

`RuntimeOperationMaintenanceService` provides bounded, redacted operator inspection
and explicit recovery through the same strict REST/MCP model. HTTP GET/POST
`/api/v1/harness/outbox` and `harness_list(view="outbox", maintenance=...)` share
authorization, current-owner fencing and application behavior. Authenticated stdio
mutations proxy the serve owner. Payload identity never grants operator authority.

`cancel_pending` cancels only before send-intent. `release_to_inbox` releases the
original conversational delivery reservation; it creates neither a new message nor
a second work queue. `abandon_command` releases an uncertain administrative command
from lane blocking without creating inbox work. Uncertain recovery requires an
exact state/attempt/owner snapshot, explicit duplicate-risk acknowledgement and an
audit reason. Running external calls, ready runtimes, reserved starts, stale
snapshots and managed handoff bindings are rejected.

Migration054 stores one immutable decision per operation and per actor/idempotency
key, with nullable references on both source tables. Audit, inbox release and
endpoint quarantine commit atomically. Repeated identical requests return the same
decision; conflicting reuse fails. Uncertain transport state and ACK remain facts
of the original attempt. No native replay, synthetic ACK or completion occurs.
Recovery revokes old endpoint grants and boot approval. Subsequent use requires
explicit endpoint reconciliation and fresh authorization.

Exact late terminals remain journaled/materialized but cannot consume the released
inbox, publish or relay under abandoned authority. Original command idempotency
continues to resolve historical commands even after reconciliation.

Admission OFF does not disable operator recovery. `serve` starts a maintenance
owner when runtime history exists, with boot disabled and normal admission still
denied. An empty disabled installation retains its previous startup behavior.
Shutdown uses the production drain sequence before releasing the journal lock.

Key files/symbols: application/runtime_operation_maintenance.py (`run`, `_inspect`),
runtime_access.py (`authorize_maintenance`), inbox.py (`release_runtime_reservation`),
runtime_delivery/control/results admission fences, dispatcher in-flight checks;
sqlite messages/outbox/commands/journal repositories; migration054; inbound shared
runtime_admin.py model, REST routes, MCP harness facade and HTTP app lifespan;
tests/test_runtime_operation_reconciliation.py. Operational instructions are in
docs/harness-integrations/runtime-administration.md.

## Commands and observations

- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_operation_reconciliation.py -x`:
  initial behavioral **RED**, 1 FAIL in 3.41s: recovery route returned404 after an
  actual uncertain delivery. The first corrected run also exposed a fixture count
  including the close interrupt; assertions now count normal `send_turn` writes.
- Same file without `-x`: progressively **10 PASS** in28.27s and **14 PASS** in39.93s.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_operation_reconciliation.py tests/test_runtime_result_correlation.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_native_approvals.py tests/test_migrations.py`:
  **59 PASS**,154.95s, before the additional OFF-restart test/startup change.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_outbox.py tests/test_runtime_commands.py tests/test_runtime_result_publication.py tests/test_runtime_native_approvals.py tests/test_migrations.py`:
  **54 PASS**,151.89s, before late-terminal and OFF-restart additions.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_operation_reconciliation.py tests/test_runtime_outbox.py tests/test_runtime_commands.py`:
  **40 PASS**,121.59s, before stdio/migration/OFF-restart additions.
- Same WSL prefix with `-m pytest -q tests/test_runtime_operation_reconciliation.py -k 'stdio or migration'`:
  **2 PASS**,15 deselected,11.72s.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_operation_reconciliation.py -k restart`:
  behavioral **RED**,1 FAIL/17 deselected,4.24s: disabled restart lacked a recovery
  owner. After startup correction, the incomplete fixture shutdown hit the writer
  lock (1 FAIL,4.72s). Replacing fixture-only dispatcher.close with production
  `shutdown_runtime` preserved the lock invariant: **1 PASS**,17 deselected,5.09s.
  Existing Starlette/httpx deprecation warning is unrelated.
- `rtk proxy python plans/pr34-remediation/measure_surface.py b906f0f`:
  revision41→42, same eight optional tools; OFF43 tools/40448 total chars/28315
  cuttable unchanged; ON51 tools/47714 total(-4)/32172 cuttable(+14). No exemption.

## Final selection on this worktree

- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_operation_reconciliation.py tests/test_runtime_shutdown.py tests/test_runtime_restart.py tests/test_runtime_boot.py tests/test_feature_flags.py`: **81 PASS**,116.65s, one existing deprecation warning.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_operation_reconciliation.py tests/test_runtime_shutdown.py tests/test_runtime_restart.py tests/test_runtime_boot.py`: **38 PASS**,120.78s, same deprecation warning.
- `rtk proxy ruff check src/okto_nexus/application/runtime_operation_maintenance.py src/okto_nexus/adapters/inbound/http/app.py src/okto_nexus/adapters/inbound/runtime_admin.py src/okto_nexus/adapters/outbound/sqlite/runtime_outbox_repo.py tests/test_runtime_operation_reconciliation.py`: **PASS**.
- `rtk git diff --check`: **PASS**.

## Limits and next dependencies

All native interactions in this unit use disposable fixtures/protocol peers.
Real Codex/Claude provider campaigns: **NOT_RUN for this unit**; Pi and dedicated
Claude attach native remain **NOT_RUN**. No personal database was migrated.

Managed handoff recovery remains pending and is explicitly refused by generic
conversation recovery. Effective capability probes, remaining administration/UI,
full guide/ADR, cutover/backup/restore and P12 aggregate/native gates remain open.
No phase promoted to VERIFIED and no final gate claimed.
