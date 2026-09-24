# P06 — bounded retry on typed pre-write proof

Parent de1dfa426cb6d16768ed65f789fda315b3eb1811, feature/v0.2.0.
Schema060, surface55, identity reference23. Final plan gate NOT PASSED.
This unit retries the same approved endpoint. Equivalent-endpoint fallback remains
the next dependency; generic startup failure is not automatically classified safe.

## Behavior and implementation

A trusted legacy/internal turn can occupy the native lane without a canonical
outbox operation. The final EnvelopeConnector fence prevents writing a concurrent
delivery, but the previous dispatcher permanently rejected that transient refusal.
The real HTTP/MCP/adapter regression returned REJECTED instead of RETRY_WAIT:
**1 FAIL8.64s**. No new import, column access or invented corrected mock caused RED.

RuntimeLaneBusyBeforeWrite is a typed subclass of RuntimeCommandNotSent, emitted
only before EnvelopeConnector calls native.send. Permanent capability/fence
rejections retain their previous classification. RuntimeDispatcher retries only
this transient type; exception text, payload identity or caller flags cannot opt in.
RuntimeCommandDispatcher still rejects controls/direct commands without retry.

Migration060 adds delivery next_attempt_at/retry_basis and an indexed deadline
scan, and extends immutable attempt observations with those fields. The existing
059 trigger is replaced forward-only to capture them atomically; no history is
rewritten. Three total attempts maximum,1s then2s exponential delay plus0..25%
jitter, injected clock/jitter in tests. The same operation/message/delivery/hash,
causal admission and managed claim binding survive; only attempt identity changes.
Each claim/send revalidates current authorization. No native I/O, process or secret
resolution enters the write transaction; no extra worker or native status polling.

The coordinator waits for the next persisted deadline or existing wake/heartbeat.
Overdue blocked lanes wait for completion wakes or bounded recovery rather than
zero-timeout spinning. Using the iteration's original time keeps a deadline that
expires during scanning observable. Pending selectors and direct-command admission
preserve earlier RETRY_WAIT lane order. Other agents retain bounded worker fairness.

An exact authorized cancel_pending can cancel a RETRY_WAIT only while its complete
non-delivery proof remains valid. Exhaustion stores REJECTED/native_write_not_started
and retains the reservation for explicit safe recovery; it never donates work to
pull automatically. Unknown/write/accepted outcomes remain fenced. Losing the
proof transaction leaves SENDING, survives worker cleanup and becomes UNKNOWN on
owner replacement; no automatic replay is permitted from that lost proof.

Operation detail/list exposes current deadline/basis; history retains the deadline
and proof for each failed attempt. Existing MCP/REST maintenance use the same service.
The predecessor migration test now seeds a schema058 persistence fixture directly:
current dispatcher code requires its new columns and is not presented as executable
against the old schema. This changes fixture setup, not the earlier059 observations.

## Commands and evidence

All commands use rtk proxy. Windows Python .venv/Scripts/python.exe; Linux WSL
Ubuntu cwd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus and interpreter
/var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python.

- RED: `-m pytest -q --tb=short tests/test_runtime_safe_retry.py`:1 FAIL8.64s.
- Initial retry plus proven-not-sent recovery: `-m pytest -q --tb=short tests/test_runtime_safe_retry.py tests/test_runtime_not_sent_recovery.py`:10 PASS35.65s.
- Expanded retry5 PASS15.35s; then timer-expanded retry6 PASS20.37s. These are
  overlapping development selections, not independent totals.
- Windows broad development selection: `-m pytest -q --tb=short tests/test_runtime_attempt_history.py tests/test_runtime_safe_retry.py tests/test_runtime_outbox.py tests/test_runtime_operation_reconciliation.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_commands.py tests/test_runtime_scheduler_fairness.py tests/test_migrations.py`:
  **79 PASS213.77s**, one Starlette warning. The coordinator deadline cutoff was
  refined while this selection was running; this is not an immutable final gate.
- Subsequent Windows selection: `-m pytest -q --tb=short tests/test_runtime_safe_retry.py tests/test_runtime_attempt_history.py tests/test_runtime_not_sent_recovery.py tests/test_runtime_worker_capacity.py`:
  **20 PASS69.15s**, before final incomplete-proof cancellation hardening.
- Linux broad development selection uses those four files plus tests/test_runtime_outbox.py,
  tests/test_runtime_operation_reconciliation.py, tests/test_runtime_handoff_dispatch.py,
  tests/test_runtime_commands.py, tests/test_runtime_scheduler_fairness.py and tests/test_migrations.py:
  **91 PASS269.60s**, one Starlette warning. It collected before the final cancellation-proof tests.
- Final cancellation-proof selection: `-m pytest -q --tb=short tests/test_runtime_safe_retry.py tests/test_runtime_not_sent_recovery.py tests/test_runtime_attempt_history.py tests/test_frente1_resources.py tests/test_import_boundary.py`:
  **Windows37 PASS72.82s; Linux37 PASS87.03s**. Includes exact jitter/clock, maximum
  attempts, native write count, same hash/inbox, FIFO across normal commands,
  authorization revocation, timer without external wake, owner replacement,
  cancellation and rejection of three incomplete stored proofs.
- Additional lost-proof commit test: `-m pytest -q --tb=short tests/test_runtime_safe_retry.py::test_lost_non_delivery_proof_commit_never_enables_replay`:
  **Windows1 PASS4.15s; Linux1 PASS7.02s**. Native refusal is real adapter behavior;
  only persistence commit failure is injected, and the retry/history update rolls back.
- Metadata selection (same seven surface-test files as prior unit, `-k "surface_revision or nexus_info_features"`):
  **9 PASS245 deselected4.49s**, one Starlette warning.
- Ruff changed Python files and git diff --check: PASS.
- `rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/measure_surface.py de1dfa4`:
  unchanged OFF43 tools40448 characters10112 estimated tokens; ON51 tools47730
  characters11932 estimated tokens. Surface54 to55; identity22 to23.

No provider/model called in this unit. Latest real Codex/Claude campaign remains
on d76b78c; Pi and dedicated attach native NOT_RUN. Personal stores/assets untouched.
Next: safe approved equivalent-endpoint fallback with immutable logical identity,
original context/claim/grant revalidation and no replay after ambiguous writes;
then the remaining matrix/crash/performance and final installation gates.
