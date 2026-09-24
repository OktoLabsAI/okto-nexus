# P05/P06 — durable delivery checkpoint (in progress)

Parent SHA: `2fb9f59`; branch `feature/v0.2.0`.

Migration 032 adds transport outbox, inbox consumer reservation, owner epoch,
open-request idempotency and the runtime's approved profile revision. MessageService
plans a transport intent in the same commit as the canonical message, delivery
and event. A verified sender and an operator-approved conversational endpoint are
required. Cooperative-trust internal messages retain their inbox delivery without
acquiring execution authority from a payload sender ID.

RuntimeDeliveryPlanner selects within the exact recipient/workspace, prefers a
ready binding, then explicit priority; ties require an interchangeable selection
group or fail with AMBIGUOUS_BINDING. Distinct endpoints can run for one Agent;
the temporary whole-Agent fence is now a per-endpoint fence. A push reservation
excludes pull claim/ack. Pre-send rejection can release the reservation; an
ambiguous external outcome cannot. The old supervisor inbox fanout is disconnected
in production, so it cannot run alongside the new dispatcher.

RuntimeDispatcher is owned by serve's real application lifespan, has two bounded
workers, short claim/send-intent transactions and epoch/attempt CAS. It rechecks
identity, current permissions, scope, binding/profile revisions and guardrails.
Canonical policy revision receipts avoid charging an already admitted message
against quotas a second time; a changed policy requires new admission.
After send-intent, failure or owner loss becomes OUTCOME_UNKNOWN, never PENDING.
Successful write is SENT_UNCONFIRMED / TRANSPORT_WRITE, not an invented ACK.

Local wakes use a coalescing event. Stdio writes the same SQLite transaction and
sends a bounded loopback-only UDP hint naming only the owner; the hint grants no
authority and carries no work or key. Recovery scans are indexed at 30 seconds by default. Configure the startup-only interval with `OKTO_NEXUS_RUNTIME_RECOVERY_INTERVAL_SECONDS` or `--runtime-recovery-interval-seconds` (CLI overrides environment; integer1..86400, default30). Zero/invalid values fail closed: this setting cannot silently disable recovery. The coordinator waits for the earliest recovery, retry or heartbeat deadline; a shorter recovery interval does not wait for the ten-second heartbeat tick. Transient store failure waits for the next interval instead of spinning. This is internal store recovery polling, not native peer status polling; commit/IPC wakes remain the normal path. See P12_DELIVERY_ACCEPTANCE.md for the reproduced deadline defect and correction.
Stdio controls proxy through the owner's existing authenticated REST surface;
they cannot become another runtime manager. The owner's address comes from its
current local descriptor, never historical LAN evidence. Proxy failure does not
automatically retry. Internal open/control use cases also require owner admission.

RuntimeOpenService reserves idempotency by authenticated actor and key before
factory/start. A repeated key cannot change parameters or start another process.
The request/session link commits with session persistence, so a lost reply can
reuse the proven session even when final request bookkeeping failed.

Evidence (all native peers synthetic; separate stdio Nexus processes are real):

- `.venv/Scripts/python.exe -m pytest tests/test_runtime_outbox.py -q`
  — 11 PASS at that checkpoint; evidence/p05-outbox.log.
- `.venv/Scripts/python.exe -m pytest tests/test_runtime_outbox.py tests/test_runtime_grants.py tests/test_import_boundary.py -q`
  — 24 PASS at that checkpoint; evidence/p06-dispatch.log.
- `.venv/Scripts/python.exe -m pytest tests/test_runtime_outbox.py tests/test_runtime_grants.py tests/test_runtime_endpoints.py tests/test_pr34_remediation.py tests/test_import_boundary.py -q -k 'not replay_keeps and not terminal_storage and not expired_relay'`
  — 77 PASS, three later-phase regressions deselected; evidence/p05-p06-gate.log.
- `.venv/Scripts/python.exe -m pytest tests/test_runtime_outbox.py -q -k 'stdio_open'`
  — one additional PASS; evidence/p06-owner-proxy.log. A deliberately absent
  fixture executable ensures this test cannot accidentally run local Pi.
- `.venv/Scripts/python.exe -m pytest tests/test_messages.py tests/test_message_delivery.py tests/test_inbox.py tests/test_inbox_service.py tests/test_governance.py tests/test_hitl.py -q`
  — 176 PASS, one pre-existing dependency deprecation warning;
  evidence/p05-canonical.log.

Initial development runs exposed a test-fixture import-order problem and a missing
bound-method argument in fault injection; both were corrected. A later owner-client
import error was corrected before the 77-test run. These were implementation/test
errors, not behavioral reproductions or native-protocol failures.

Pending: all-producer approval/projector receipts and work claims, transport
idempotency for direct commands, full result correlation, journal durability,
process birth ownership, safe on-demand/boot reconciliation, operation/admin UI,
real kill campaigns and causal budgets. Stdio proxy controls share authorization,
but direct controls still need the durable operation unification. This checkpoint
is not the final enabled gate and does not mark P05/P06 VERIFIED.

Operation: backup SQLite with WAL before forward-only upgrade; all writers must
upgrade. An old package rejects the newer migration ledger. Never reverse 032 on
a live store. Unknown intents retain their inbox reservation until explicit,
evidence-based reconciliation; stopping/restarting serve is not permission to
replay them. Codex/Claude native tests remain authorized but NOT_RUN; Pi remains
NOT_RUN by operator decision.
