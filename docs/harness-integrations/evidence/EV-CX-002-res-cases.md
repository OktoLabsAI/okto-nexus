# EV-CX-002 — Codex (H-CX) RES cases (resilience suite)

Captured: 2026-09-20. All runs against `tests/test_harness_codex_connector.py` (fake-server-backed
unit level — RES is explicitly permitted to use a fake connector per the task's rules, as long as
the fake can FAIL, not only succeed — see RES-C3 below).

> **UPDATE — Phase-4 campaign follow-up pass, same day.** `adapters/outbound/harness/codex.py` was
> NOT frozen for this follow-up task (only `domain/harness.py` and the `HarnessConnector`/
> `HarnessSubscriberRegistry` Protocols in `application/ports.py` were). Both defects below (RES-A2,
> RES-A4) and the RES-C2 fake divergence were FIXED this pass, following `harness/pi.py`'s own
> remediated pattern (its C2/C3 fixes) exactly, per the follow-up task's explicit instruction. The
> narrative below is left INTACT as the failing-first record; each defect section now also carries
> the fix and the re-run showing it passing. See codex.py's own mismatch note 14 for the
> in-module fix writeup.

## ⚠️ TWO REAL, REPRODUCIBLE DEFECTS FOUND — FIXED in the Phase-4 follow-up pass (see update above)

Both are logic bugs (not timing-sensitive races); each was re-run in isolation 3× and failed
identically all 3 times — not contention artifacts from the loaded shared machine.

### Defect 1 — RES-A2 FAILS: `events()` splits the stream across concurrent consumers

**File:** `src/okto_nexus/adapters/outbound/harness/codex.py`, `CodexAppServerConnector.events()`
(backed by the single `self._event_queue: queue.Queue`, set in `__init__`).

This is the SAME defect class `pi.py` shipped and was remediated for (EV-REV-002/EV-REV-003 Class
A / "C2"): "two concurrent consumers split the stream, each seeing an unpredictable subset... Pi's
fake fake server's own reproduction: thread A got all 17 events through `agent_settled`, thread B
got zero." `pi.py` was fixed to give each `events()` call its OWN subscriber queue, seeded from a
shared history under a lock (see `pi.py`'s own mismatch note 9(b)/C2 and `EV-REV-003`'s "C2
events() fan-out: CLOSED"). `codex.py` was never given the equivalent fix — it still has exactly
ONE shared `queue.Queue`, and `events()` does `self._event_queue.get(timeout=...)` against it, so
two concurrent callers race for the same items.

New test `test_two_concurrent_events_consumers_split_the_stream_instead_of_each_getting_the_full_
stream`: two consumer threads are started and given 0.3s to genuinely park on the blocking `get()`
BEFORE any event is produced (eliminating "late start" as an alternative explanation), then a
5-event turn (`turn_started`, `item/started`, `item/agentMessage/delta`, `item/completed`,
`turn/completed`) is sent. Deterministic proof, independent of scheduling: with correct
per-consumer fan-out the total item count across both consumers of an N-event stream is 2N; with a
shared-queue split it is exactly N.

    $ timeout 30 uv run python -m pytest -q tests/test_harness_codex_connector.py::test_two_concurrent_events_consumers_split_the_stream_instead_of_each_getting_the_full_stream
    FAILED ... AssertionError: expected each of 2 concurrent events() consumers to receive the FULL
    5-event stream (total=10); got total=5 (A=5, B=0) - the stream was SPLIT between them.
    1 failed in 9.11s

Re-run 3× in isolation: **FAILED all 3 times**, identically (`total=5, A=5, B=0` in every run —
the OS scheduler consistently starved consumer B on this machine, which is itself further evidence
of a real starvation bug, not a 50/50 coin-flip race that happened to land badly).

    run 1: FAILED (9.11s)   run 2: FAILED (9.13s)   run 3: FAILED (9.13s)

**Why it matters:** identical failure signature to the class the project has already been burned by
twice (Class A). A supervisor with more than one internal consumer of a codex session's `events()`
(or a caller that legitimately calls `events()` a second time while a first call is still draining
mid-stream, distinct from the ALREADY-covered "call after close" case in RES-A1) silently loses
events with no exception, no crash, nothing logged.

**FIXED, Phase-4 follow-up pass.** `events()`/`_push_event` now carry the same fan-out shape as
`pi.py`'s own C2 fix: `_event_history` (an append-only record of every event ever pushed) plus one
subscriber `queue.Queue` per `events()` call, both under one `_history_lock` so a push can never
land in the gap between a new subscriber's backlog snapshot and its registration (see codex.py's
mismatch note 14a). `_event_queue` is gone. Re-run 3× in isolation, same test, same command:

    run 1: PASSED (0.36s)   run 2: PASSED (0.34s)   run 3: PASSED (0.36s)

**Caveat disclosed, not silently inherited:** `pi.py` justifies never trimming its own equivalent
history by "one connector IS one session" (`multiplexes_sessions=False`). That premise is false for
codex (`multiplexes_sessions=True`), so `_event_history` can in principle grow across MANY
sessions' worth of events over one connector's WHOLE process life, not just one session's — not
reachable at today's actual wiring (`adapters/inbound/mcp/tools/harness.py`'s `_codex` factory
spawns a fresh connector, and therefore a fresh child process, per `harness_open` call;
grep-confirmed no other call site in `src/` re-uses a connector across sessions or re-subscribes to
`events()`), but a real latent gap the moment multiplexing is ever actually wired up. See codex.py's
own mismatch note 14a for the full writeup.

### Defect 2 — RES-A4 FAILS: a FAILED `start()` leaves `events()` permanently hanging

**File:** same module, `CodexAppServerConnector._spawn_and_initialize` (mismatch note 12's own fix)
interacting with `events()`.

This is the SAME defect class Pi was remediated for (EV-REV-003 "C3 - failed start() loops
forever: CLOSED", fixed by setting `_closed_event` in `start()`'s `except` branch). Reading the
codex code: `_spawn_and_initialize`'s failure path calls `transport.close()` on a failed handshake
— but that only sets `_CodexTransport._closed` (the TRANSPORT's own PRIVATE internal flag, used
solely to suppress `_on_child_exit` firing when the reader thread naturally hits EOF after a
deliberate close). It never touches `CodexAppServerConnector._closed_event` — the ONE flag
`events()` actually checks on every `queue.Empty`. These are two DIFFERENT `threading.Event`
objects on two different classes; setting one does not set the other. A caller of `events()` after
a failed `start()` (with no separate, explicit `close()` call — a legitimate sequence: a
supervisor that tries `start()`, gets an exception, and does not bother closing a connector that
never successfully started) never receives a shutdown signal at all.

New test `test_failed_start_leaves_events_terminable`: a child that consumes the `initialize` write
but never answers it (so the handshake's own bounded `request()` times out cleanly, matching the
EXISTING `test_failed_handshake_does_not_permanently_wedge_the_connector`'s own trigger shape —
that existing test only checks `_transport is None`, a different failure surface; it happens to
mask this exact bug because IT always calls `conn.close()` in its own `finally`).

    $ timeout 30 uv run python -m pytest -q tests/test_harness_codex_connector.py::test_failed_start_leaves_events_terminable
    FAILED ... AssertionError: events() after a FAILED start() (no close() call) did not terminate
    within 5s. REAL DEFECT: _spawn_and_initialize's failure path never sets
    CodexAppServerConnector._closed_event (it sets the TRANSPORT's own separate internal _closed
    flag instead).
    1 failed in 5.36s

Re-run 3× in isolation: **FAILED all 3 times**, identically (`5.3xs`, always fails - this is a
deterministic bug, not a race).

    run 1: FAILED (5.36s)   run 2: FAILED (5.37s)   run 3: FAILED (5.38s)

**Why it matters:** exactly the "looks alive, delivers nothing" signature the project's whole RES
suite exists to catch (D8's own framing: "a connector that has silently stopped pushing is
indistinguishable from a harness with nothing to say"). A boot-time (D8) harness declaration whose
`start()` fails wedges any code path that unconditionally drains `events()` after `start()`
regardless of its outcome — the exact "boot must assume a connector can fail in exactly that way"
scenario ADR 0004 D8 calls out.

**FIXED, Phase-4 follow-up pass.** `_spawn_and_initialize`'s `except` clause now also sets
`self._closed_event` (not just `transport.close()`), and the guarded region was widened to cover
`transport.start()` itself, catching `BaseException` rather than `Exception` — mirroring how
widely `pi.py`'s own C3 fix guards its equivalent spawn path (see codex.py's mismatch note 14b).
Re-run 3× in isolation, same test, same command:

    run 1: PASSED (1.34s)   run 2: PASSED (1.33s)   run 3: PASSED (1.34s)

**Both defects were reported here per the earlier ABSOLUTE RULE 2 (frozen file) under the ORIGINAL
task; the Phase-4 follow-up task explicitly lifted that freeze for this file and instructed the
fix.** The test file change that originally documented them
(`tests/test_harness_codex_connector.py`) was never a modification to any frozen file, and was
updated this pass to describe the now-fixed status without weakening either assertion.

---

## RES-A1 — `events()` called twice returns both times (EXISTING tests, cited)

    $ timeout 30 uv run python -m pytest -q tests/test_harness_codex_connector.py -k "events_called_twice"
    2 passed

- `test_events_called_twice_after_close_returns_both_times`
- `test_events_called_twice_after_unexpected_child_exit_returns_both_times`

Both call `events()` a SECOND time SEQUENTIALLY, after `_closed_event` is already set (by `close()`
or child death respectively) — the single-consumption-sentinel defect class codex.py's own mismatch
note 9(a) documents fixing. This passes and is genuinely different from RES-A2 above: RES-A1 is
sequential re-entry after shutdown; RES-A2 is concurrent draining of a live stream. `_closed_event`
being a simple flag (not a sentinel) is exactly why RES-A1 passes while RES-A2 fails — the flag
correctly unblocks ANY caller once set, but nothing in `events()` gives each caller its OWN
un-contended queue while the connector is still live.

## RES-A2 — see "Defect 1" above. FAILED, real defect, reported.

## RES-A3 — every blocking wait carries a timeout (structural, NEW test)

    $ timeout 30 uv run python -m pytest -q tests/test_harness_codex_connector.py::test_every_blocking_wait_in_module_carries_a_timeout
    1 passed

New test `test_every_blocking_wait_in_module_carries_a_timeout` parses the module source (comments
and docstrings excluded, to avoid false positives from prose that names these primitives) and
asserts every call site carries a visible `timeout`:

- `Queue.get(...)` — 2 real call sites (`reply_q.get(timeout=timeout_s)` in `request()`;
  `self._event_queue.get(timeout=_EVENTS_POLL_S)` in `events()`), both bounded.
- Lock `.acquire(...)` — 1 real call site (`self._write_lock.acquire(timeout=
  _STDIN_WRITE_LOCK_TIMEOUT_S)`), bounded.
- `proc.wait(...)` — 4 real call sites (the reader thread's own exit-time wait ×2 for the
  kill-then-rewait fallback, `close()`'s terminate-then-wait ×2), all bounded by
  `_PROC_WAIT_TIMEOUT_S`/`grace_s`.
- Thread/lock `.join(...)` — **zero** call sites (the module never joins its daemon reader
  threads at all — confirmed, not assumed; the only `.join(` matches in the raw source are
  `"\n".join(...)` string joins, explicitly excluded by the check).
- Socket `recv(`/`connect(`/`select(` — **zero** occurrences (this module is stdio-only, no
  sockets anywhere — confirmed by substring absence over the full source).

A structural check, not a timing check, per the case's own wording.

## RES-A4 — see "Defect 2" above. FAILED, real defect, reported.

## RES-B1 — a domain-invalid (not merely undecodable) message is surfaced, reader continues (EXISTING tests, cited)

    $ timeout 30 uv run python -m pytest -q tests/test_harness_codex_connector.py -k "empty_method or array_params"
    2 passed

- `test_empty_method_notification_does_not_wedge_the_reader_thread` — `{"method": "", "params":
  {}}`: JSON-RPC-legal, but `HarnessEvent.__post_init__` rejects an empty `native_event`. Reader
  survives, turn still completes afterward.
- `test_array_params_notification_does_not_wedge_the_reader_thread` — `{"method": "item/started",
  "params": ["not", "a", "dict"]}`: JSON-RPC 2.0 explicitly permits array params; this connector's
  `_extract_thread_id` calls `.get()` on it, raising `AttributeError`. Reader survives.

Both are exactly the two shapes the case text specifies (empty method, array params), both
surfaced as `kind="error"`/`native_event="transport/dispatch_error"`, and both are pre-existing
tests from Phase 3 remediation (module mismatch note 9(b)) — cited, not new work.

## RES-B2 — a reader thread exiting for ANY reason signals shutdown to EVERY consumer (NEW test)

    $ timeout 30 uv run python -m pytest -q tests/test_harness_codex_connector.py::test_two_concurrent_events_consumers_are_both_signalled_on_child_death
    1 passed

New test, TRULY concurrent (unlike the sequential RES-A1 pair): two consumer threads are parked on
`events()` BEFORE `TRIGGER_CRASH` kills the fake child; both threads are asserted to terminate
within 15s. This PASSES even though RES-A2 (above) FAILS — `_closed_event` is a single shared flag
set unconditionally by `_on_child_exit` regardless of how the (split) stream was delivered, so
shutdown propagation and stream fan-out are genuinely independent properties here; do not conflate
a pass on one with a pass on the other.

## RES-B3 — no cleanup path contains an unbounded wait (structural, same NEW test as RES-A3)

Covered by `test_every_blocking_wait_in_module_carries_a_timeout` above: the `proc.wait(...)` sites
it checks include BOTH cleanup paths — the reader thread's own exit-time wait in `_read_stdout`'s
`finally`, and `close()`'s terminate-then-wait — and both are bounded (`_PROC_WAIT_TIMEOUT_S`,
`grace_s`). No separate test was written since the case is structurally identical to RES-A3 for
this module (same primitives, same cleanup-path call sites already enumerated above); named
separately here per the task's "say plainly which is which" instruction rather than silently
merged.

## RES-C1 — the fake's wire behaviour is justified against captured bytes

The fake server in `tests/test_harness_codex_connector.py` (`_FAKE_SERVER_SOURCE`) is justified
against the raw captures in `EV-CX-001-int-cases.md` / the three `EV-CX-001-raw_capture_*.jsonl`
files, section by section:

- **Envelope shape** — `{"jsonrpc": "2.0", "id", "method", "params"}` requests,
  `{"jsonrpc":"2.0","id","result"|"error"}` responses, `{"method","params"}` (no `id`)
  notifications: matches every line of all three raw captures.
- **`thread/start` result shape** `{"thread": {"id": ...}}`, no top-level `threadId` on
  `thread/started`'s own params (nested at `params.thread.id`) — matches
  `EV-CX-001-raw_capture_turn.jsonl` lines for `id:2`'s result and the following
  `thread/started` notification, and is the exact shape codex.py's own mismatch note 8 documents
  fixing against.
- **`turn/start` ack-then-notify** (`{"id":3,"result":{...}}` immediately followed by
  `turn/started`) — matches `EV-CX-001-raw_capture_turn.jsonl` (`t=1.1224` result, `t=1.1251`
  `turn/started`) and `EV-CX-001-raw_capture_interrupt.jsonl` identically.
- **`turn/interrupt` real ordering**: the real capture shows the RPC result and `turn/completed`
  (`status: "interrupted"`) at the SAME wire timestamp, no separate settle notification — see
  RES-C2 below for how the fake diverges here.
- **`item/commandExecution/requestApproval` as the real ServerRequest method name** — the fake's
  own source comment documents this was corrected from a made-up `item/tool/call` after a live
  probe against 0.144.6 + `codex app-server generate-json-schema` (pre-existing work, re-verified
  present in the current fake source, not re-derived here).
- **`thread/unsubscribe` result shape** `{"status": "unsubscribed"}` (not `{"status": "ok"}`) — the
  fake's own source comment documents this was corrected after the same live probe; not
  independently re-verified against a fresh capture in this pass (no `thread/unsubscribe` appears
  in any of the three new raw captures — `end()`/`thread/unsubscribe` was outside this pass's
  capture scope), so this citation carries forward Phase 3's verification, not a new one.

## RES-C2 — for interrupt/abort, the fake emits the REAL ordering

**Real ordering** (`EV-CX-001-raw_capture_interrupt.jsonl`, INT-06 above): `turn/interrupt`'s RPC
result and `turn/completed(status="interrupted")` arrive together, no separate settle event, no
delay.

**The fake's ordering, checked against this:** the fake's `turn/interrupt` handler (lines 186–188
of `_FAKE_SERVER_SOURCE`) replies `{"result": {}}` immediately and then emits **nothing further**
— it never sends a subsequent `turn/completed` for the interrupted turn at all. `test_steer_and_
interrupt_use_the_tracked_turn_id` (the only existing test that exercises `turn/interrupt`) only
asserts the LOG entry recording that `turn/interrupt` was sent with the right `turnId`; it never
waits for or asserts a resulting `turn/completed`.

**This was a genuine RES-C2 divergence, disclosed per the case's own "Procedure when a fake is
found to diverge" instruction**, narrower in consequence than Pi's C1 (Pi's divergence inverted an
ORDERING claim a test actively asserted and got backwards; codex's fake divergence was an
OMISSION — it just never completed the turn, so no test could observe interrupt-then-complete
ordering at all, correct OR wrong).

**FIXED, Phase-4 follow-up pass.** The fake's `turn/interrupt` handler now emits
`{"method": "turn/completed", "params": {"threadId": ..., "turn": {"id": <turnId>,
"status": "interrupted"}}}` immediately after the RPC ack, matching the real capture's ordering
(same wire timestamp, no separate settle event). `test_steer_and_interrupt_use_the_tracked_turn_id`
was extended to assert this: after issuing `interrupt`, it drains `events()` for the next
`turn_completed` and asserts `payload["turn"]["id"] == turn_id` and
`payload["turn"]["status"] == "interrupted"`. A second new test,
`test_interrupt_clears_active_turn_id_so_a_second_interrupt_is_rejected`, proves the connector's
own bookkeeping actually observes that completion (not just that the wire bytes went by): a second
`interrupt()` issued after the first turn's `turn/completed(interrupted)` was delivered correctly
raises `VALIDATION_ERROR` (no active turn), exercising `_on_notification`'s
`state.active_turn_id = None` clear on the SAME code path any other `turn/completed` gets.

    $ timeout 30 uv run python -m pytest -q tests/test_harness_codex_connector.py -k "interrupt or tracked_turn_id"
    3 passed in 0.33s

## RES-C3 — the fake can FAIL, not only succeed

Existing fake triggers that make it fail (cited, not new):

- `TRIGGER_ERROR` — `turn/start` rejected with a JSON-RPC error (`-32000 "boom"`); exercised by
  `test_turn_start_error_response_becomes_error_event`.
- `TRIGGER_CRASH` — the fake process calls `os._exit(7)` mid-turn; exercised by
  `test_child_death_surfaces_process_exited_and_stops_cleanly` and the new
  `test_two_concurrent_events_consumers_are_both_signalled_on_child_death`.
- `TRIGGER_MALFORMED` — the fake writes a non-JSON line to stdout; exercised by
  `test_malformed_line_is_surfaced_and_stream_continues`.

**Gap closed with a NEW test:** none of the above rejects the HANDSHAKE itself (an
auth/protocol-level `initialize` rejection, as opposed to the already-covered "never answers at
all" timeout shape). New test `test_rejected_initialize_surfaces_as_oktonexuserror` adds a small
standalone fake that answers `initialize` with `{"error": {"code": -32600, "message": "auth
rejected"}}` and asserts the connector surfaces it as `OktoNexusError` (not a raw exception) and
leaves `_transport is None` (the same wedge-guard the timeout-shaped failure already gets).

    $ timeout 30 uv run python -m pytest -q tests/test_harness_codex_connector.py::test_rejected_initialize_surfaces_as_oktonexuserror
    1 passed

---

## Full file run + ruff

Pre-fix (original pass, cited for the record):

    $ timeout 300 uv run python -m pytest -q tests/test_harness_codex_connector.py
    2 failed, 26 passed, 1 skipped in 20.70s
    (the 1 skipped is test_live_against_real_codex_lan_box under the default env - see EV-CX-001
    for its OKTO_NEXUS_CODEX_LIVE=1 run, which passes)

Post-fix (Phase-4 follow-up pass, this file's tests only — the task instructed NOT running the
full repo suite here since sibling connector agents are mid-write on other files):

    $ timeout 300 uv run python -m pytest -q tests/test_harness_codex_connector.py
    29 passed, 1 skipped in 8.86s

    $ uv run ruff check .
    All checks passed!

## Full repo suite (REG-01 context)

Cited from the original pass, NOT re-run in this follow-up (task instruction: "Do not run the full
suite; siblings are mid-write" — the number below is stale by construction the moment any sibling
agent commits, and reconciling it is REG-01/the orchestrator's job, not this file's):

    $ timeout 900 uv run python -m pytest -q
    2 failed, 1822 passed, 4 skipped, 2 warnings in 158.42s

The 2 failures were the two defects reported above, now fixed (see each defect's own "FIXED"
block); a fresh full-suite count reflecting that fix was not taken here per the instruction above.

## Case summary

| Case | Status | Notes |
|---|---|---|
| RES-A1 | PASSED | existing tests, cited |
| RES-A2 | **PASSED (fixed this pass)** | was a real defect (split stream); fan-out fix mirrors pi.py's C2, re-run 3x |
| RES-A3 | PASSED | new structural test |
| RES-A4 | **PASSED (fixed this pass)** | was a real defect (events() never terminates); _closed_event fix mirrors pi.py's C3, re-run 3x |
| RES-B1 | PASSED | existing tests, cited |
| RES-B2 | PASSED | new test, truly concurrent |
| RES-B3 | PASSED | structural, same test as RES-A3 |
| RES-C1 | PASSED | fake audited against 3 new raw captures |
| RES-C2 | **PASSED (fixed this pass)** | fake now emits post-interrupt turn/completed(interrupted), matching the real capture; ordering asserted by 2 tests |
| RES-C3 | PASSED | 3 existing fail-modes cited + 1 new (rejected initialize) |
