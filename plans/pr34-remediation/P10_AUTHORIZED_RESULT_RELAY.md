# P10 — explicitly authorized result relay

Date: 2026-09-23. Parent SHA: `cc1c126`, branch `feature/v0.2.0`.
The containing commit identifies this tested unit. P10 remains IN_PROGRESS.

## Behavior and authority

Operator-created endpoints may now opt into `public_config.relay_results=true`
with `response_policy=conversation`. The source adapter must advertise correlated
results. Defaults remain false; attach still accepts conversational injection but
cannot originate result relay because it provides no correlated result. Setting
the flag never changes the canonical Agent profile or authorizes handoff work.

For a successful, correlated result, the existing canonical result publication
still performs permissions, audience, governance, HITL and guardrails. Only after
that admission may its inbox delivery obtain an exclusive outbox reservation for
one eligible endpoint of the recipient. The source parent/root is inherited.
There is no second message queue or second forwarded copy.

`RuntimeResultService.enqueue_relay/validate_relay` obtain authority from the
captured result, current serve owner, exact source operation and original
authenticated actor binding. The internal context is labelled `captured_result`,
not falsely authenticated as the outputting worker. No worker/operator key is
issued or passed to a process. Source/recipient policies, endpoint/profile
revisions and the bounded ancestry of prior relays are checked before dispatch;
managed-work origins additionally retain their canonical grant/claim validation.

`RuntimeCausalityService.admit_result_relay` reserves the generated-message budget
before `reserve_execution`. A savepoint rolls back only relay admission on a
denial, retaining the result publication and observation. Depth/deadline/quota
denials persist `BLOCKED` and a reason without generating another error message.
The resulting `ENQUEUED` means transport intent admitted, not externally accepted.
Publication retries return the same canonical response and do not charge again.
Automatic self-agent loops are rejected. A→B→A is allowed within the same budget.

Migration 051 adds an explicit result source FK to outbox and result relay status.
It also adds nullable normalized `delivery_outcome` to journal projection/result
and event replay. Existing journal records deserialize with None; old results are
not retrospectively asserted successful. Optional HarnessEvent field is appended
to preserve positional constructor compatibility. Surface revision remains 38:
existing tools/schema inputs are unchanged, result/event outputs gain fields.

Adapter normalization stays at the protocol edge:

- Codex: completed/failed/interrupted native turn status.
- Claude stream: result subtype and connector-observed interruption/error flag.
- Pi: assistant message stopReason, carried to the correlated settled event.
- Unknown outcome or attach without a result never becomes successful by inference.

The envelope adapter clears any prepopulated outcome and derives it through the
adapter contract. Journal durability carries the derived value. Runtime operation
inspection exposes `delivery_outcome`, `relay_state` and `relay_reason` under the
existing read authorization. Native text is not parsed for permissions or routing.

## Test commands and observations

Disposable native-protocol subprocess fixtures only; no provider/model calls in
this unit. Counts are separate runs, not totals of distinct scenarios.

1. `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_relay.py -x`
   initially 1 FAIL, 2.55s: registry had not advertised already implemented result
   correlation. Descriptor corrected for the three duplex built-ins (attach false).
   Next run 1 FAIL, 6.52s: all relay assertions passed, last assertion named a
   nonexistent claims table; corrected to real `runtime_handoff_bindings`.
   These are implementation/test development failures, not baseline behavioral REDs.
2. `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_relay.py tests/test_runtime_result_publication.py tests/test_runtime_causality.py`
   — 26 PASS, 58.56s (initial relay case plus established result/causal suite).
3. `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_relay.py`
   — 8 PASS, 43.72s (Codex positive/negative, self-loop, budgets, idempotency and revocation).
4. `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_relay.py -k bidirectional -x`
   — 3 PASS, 7 deselected, 15.84s. Actual Pi/RPC, Codex/JSON-RPC and Claude/stream
   adapters talk to disposable protocol subprocesses through production serve/MCP/REST.
   Three operations share one root, execute worker/caller/worker, then stop at
   depth 2 while retaining the final result. These are NOT real-model campaign results.
5. `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_relay.py tests/test_runtime_result_publication.py tests/test_runtime_work_results.py tests/test_runtime_causality.py`
   — 49 PASS, 159.16s. Includes current bounded ancestry validation.
6. `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_relay.py -k 'interleaved or configuration or human'`
   — 5 PASS, 10 deselected, 23.61s. Independent roots, operator-only opt-in,
   attach capability rejection, approve/reject through canonical HITL.
7. `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_relay.py tests/test_runtime_result_publication.py`
   — Linux 24 PASS, 106.72s (15 relay cases before six small outcome mapping cases).
8. `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_event_journal.py tests/test_runtime_result_correlation.py tests/test_harness_domain.py tests/test_runtime_relay.py -k 'not bidirectional and not interleaved and not result_relay_obeys and not execution_budget and not repeated_publication and not source_relay_revocation and not failed_interrupted and not self_loop'`
   — 50 PASS, 13 deselected, 35.33s. Journal/correlation/domain compatibility,
   configuration and explicit Pi/Claude error/interruption/unknown mappings.
9. Ruff on all changed Python files and `rtk git diff --check` — PASS.
10. Final `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_relay.py`
    — 21 PASS, 68.25s, including persisted event outcome assertions for all three
    duplex adapters and the six explicit error/unknown mapping cases.

## Operation and pending work

Create an approved endpoint using the existing operator REST endpoint API, with
the existing approved profile/workspace and the optional configuration:

```json
{"response_policy":"conversation","public_config":{"relay_results":true}}
```

This fragment is configuration, not a complete creation request; the identity,
adapter, endpoint ID, workspace and profile remain mandatory as before. The
recipient needs an eligible conversation endpoint. Existing default endpoints do
not silently enable relay. A result remains private to its canonical reply target.
No broadcast notify-target is implemented by this unit.

Apply migration 051 with the ordinary forward runner; no personal store was
migrated. Preserve source results, causal roots, outbox and journal together when
backing up. Do not replay blocked/uncertain executions or delete fences to refill
quotas. Disabling integration/source endpoint or changing revisions prevents new
dispatch; it cannot undo an accepted external turn. A blocked relay does not erase
the result and does not automatically retry after changing settings.

Remaining P10: explicit authorized notify-target/broadcast, further fanout and
process-restart/cut coverage, ancestry revocation at deeper hops, dynamic policy
configuration via P11 admin updates, aggregate acceptance matrix. P11/P12 and
build/reinstall remain pending. Native Codex/Claude relay NOT_RUN; Pi/attach native
NOT_RUN under the existing user configuration. Final gate NOT PASSED.
