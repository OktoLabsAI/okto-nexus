# Approved endpoint boot and explicit reconciliation

2026-09-23; parent 2f760b0 plus this worktree; feature/v0.2.0.
Migration 039 is additive. F04/F11/F13, T-LIFE-01, T-ID-03/06 and
T-DISP-05/07 are partially covered; native boot campaign NOT_RUN.

Boot is an operator-approved persistent binding to endpoint/profile revisions.
The real HTTP lifespan runs it after journal/session recovery using the SAME
RuntimeOpenService as on-demand opens. Its internal runtime_boot context only
authorizes opening that endpoint under the current owner/epoch; it cannot send,
administer or open another binding. No operator key enters the child.
Revocation, issuer key rotation, inactive issuer, profile revision or quarantine
blocks startup before effects. The boot identity is endpoint ID, not a PID.

At most 16 boot approvals and a 30-second global native-start admission budget.
Remaining starts are deferred; failed adapters are isolated. Startup helpers that
cannot finish retain existing bounded slots and quarantine, without replacement
threads. Budget is deducted before native start; filesystem/database operations
are synchronous and their latency is not a hard realtime guarantee.
Same owner/endpoint boot uses a deterministic idempotency key. A clean new owner
may create a fresh runtime, never replaying a prior prompt. Uncertain old owners
remain quarantined until explicit reconciliation. Attach cannot boot from a PID
alone: select the approved current external target explicitly; on-demand attach
remains supported on POSIX with its separate opt-in.

POST /api/v1/harness/endpoints/{endpoint_id}/reconcile requires operator authority,
expected_revision, idempotency_key, reason and acknowledge_uncertain_effects=true.
It records audit and clears endpoint quarantine with a new revision. It does NOT
kill processes, claim observed exit, reclassify unknown operations, clear their
logical reservations, retry a prompt or start a runtime. Review prior effects
before using this action. Repeated identical requests return the same audit ID.
The changed revision requires renewing boot approval.

PUT /api/v1/harness/endpoints/{endpoint_id}/boot accepts enabled and
expected_revision. It starts nothing in that request; activation is on the next
serve startup. DELETE is not needed: enabled=false revokes the approval.
GET /api/v1/harness/diagnostics shows redacted boot revisions and uncertain starts.
MCP administrative parity/UI are pending P11; no claim that those paths exist yet.

A behavioral regression found failed native start only quarantined RAM: after
restart boot could try again. RED: 1 failed in 2.92s. Durable effects_started is now
written before native start. An ambiguous failure persists endpoint quarantine;
a constructor/admission rejection before effects records FAILED_FINAL. A session
already durably ready remains reusable if only reply bookkeeping failed (the
existing lost-reply regression caught and corrected an overly broad quarantine).

Executed commands, all prefixed rtk proxy:
- .venv/Scripts/python.exe -m pytest -q tests/test_runtime_boot.py --tb=short
  Initial nine boot/config/auth/restore cases: 9 PASS, 18.14s.
- .venv/Scripts/python.exe -m pytest -q tests/test_runtime_boot.py::test_failed_native_start_persists_quarantine_and_boot_cannot_replay --tb=short
  Behavioral RED described above.
- .venv/Scripts/python.exe -m pytest -q tests/test_runtime_boot.py tests/test_runtime_session_recovery.py tests/test_runtime_shutdown.py tests/test_runtime_endpoints.py tests/test_runtime_grants.py tests/test_pr34_remediation.py::test_p01_duplicate_executor_is_rejected --tb=short --maxfail=4
  51 PASS, 70.84s (before adding global-budget case).
- .venv/Scripts/python.exe -m pytest -q tests/test_runtime_boot.py tests/test_runtime_outbox.py tests/test_runtime_session_recovery.py --tb=short --maxfail=4
  Initial 28 PASS / 1 lost-reply regression FAIL (47.98s); corrected final:
  29 PASS, 51.42s.
- wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_boot.py tests/test_runtime_session_recovery.py --tb=short
  15 PASS, 43.16s. All external peers synthetic; native providers NOT_RUN.
- Ruff on changed Python files: PASS.

Next: durable send/control intents with expected turn/epoch and bounded priority,
then authorized result publication/artifacts, P09-P12. No final gate promotion.
