# EV-PI-RES-001 — Pi connector, RES-A/B/C resilience cases

Captured: 2026-09-20 -03
Module under test: `src/okto_nexus/adapters/outbound/harness/pi.py` (FROZEN — task rule 2; no
line of it was modified to produce this evidence)
Test file: `tests/test_harness_pi_connector.py` (not frozen — 3 new tests added this session, all
others pre-existing from Phase 3/3.5 remediation)

Convention below: **RUN AND CITE** = a pre-existing test already proves this case;
**NEW** = a test added this session because no prior test covered it.

---

## RES-A1 — `events()` called TWICE, both return (NEW)

`test_res_a1_events_called_twice_sequentially_both_return` — distinct from the pre-existing
concurrent-consumers test (RES-A2): calls `list(connector.events())` to completion, then calls it
a SECOND time on the same connector, sequentially (not concurrently), and asserts the second call
also terminates and returns the identical backlog. This is the case the module's own C2 fan-out
fix (`_event_history` + per-call subscriber queue, seeded from a history snapshot) makes possible;
before that fix a second call after the first was never proven not to hang.

```
$ timeout 300 uv run python -m pytest -q tests/test_harness_pi_connector.py -k test_res_a1
1 passed
```

**Verdict: PASS.**

## RES-A2 — two CONCURRENT `events()` consumers, full stream (RUN AND CITE)

`test_events_fan_out_to_two_independent_concurrent_consumers` (pre-existing, Phase 3.5
remediation for the C2 defect: "thread A got all 17 events, thread B got zero"). Two threads each
call `connector.events()` independently and each must see the identical, complete native-event
sequence through `agent_settled`.

```
$ timeout 300 uv run python -m pytest -q tests/test_harness_pi_connector.py -k test_events_fan_out
1 passed
```

**Verdict: PASS** (pre-existing coverage, re-run and confirmed, not duplicated).

## RES-A3 — every blocking wait carries a timeout (structural grep, NOT timing)

Enumerated every candidate site in `pi.py` via:

```
$ grep -n "\.get(timeout\|\.acquire(timeout\|\.join(timeout\|proc\.wait(\|\.wait(timeout\|\.recv(\|\.connect(\|select\.\|Queue\.get\|readline\|for raw_line\|for raw in" \
    src/okto_nexus/adapters/outbound/harness/pi.py
```

| Line | Call | Bounded? |
|---|---|---|
| 314 | `self._request_lock.acquire(timeout=timeout_s)` | YES |
| 328 | `reply_q.get(timeout=timeout_s)` | YES |
| 358 | `for raw_line in self._proc.stdout:` (blocking readline loop) | Design-intentional unbounded block-on-I/O (the push-protocol read pump itself — this IS the "block on real work, never poll" shape D1 asks for; it resolves the instant the child writes or exits) |
| **371** | **`self._proc.wait()` — NO timeout** | **NO — see below** |
| 382 | `for raw_line in self._proc.stderr:` (same shape as 358) | Same as 358 |
| 414, 418 | `self._proc.wait(timeout=grace_s)` (in `close()`) | YES |
| 687 | `my_queue.get(timeout=_EVENTS_POLL_S)` (in `events()`) | YES |

All lock acquisitions elsewhere (`_pending_lock`, `_write_lock`, `_start_lock`, `_session_lock`,
`_history_lock`) are bare `with self._lock:` with no explicit timeout, but every one guards only
brief in-process dict/list bookkeeping — never held across an I/O call or another actor's
response — so they are not a hang risk in the sense this case is checking (the module's own docs,
around `_request_lock`, single out exactly the ONE lock acquisition that IS held across I/O for
the explicit-timeout treatment, and it has one). One secondary, narrower structural note:
`_write()`'s `stdin.write()`/`.flush()` (line ~289) runs inside `with self._write_lock:` with no
timeout of its own; a pipe-full/non-reading child could in principle block it. Not exercised
further here — flagged for completeness, not elevated to a finding, since no reachable path in
this task's testing produced it and it mirrors mismatch note 8's already-disclosed
worst-case-latency discussion for `send()`.

**Line 371 is a CONFIRMED, EMPIRICALLY REPRODUCED unbounded wait — not a theoretical one.** See
RES-B1 below for the reproduction. This corrects `EV-REV-003`'s earlier characterization
("`self._proc.wait()` in `_read_stdout`'s `finally` carries no timeout, but only runs after
stdout hit EOF (child already exiting), so it is not a genuine hang risk") — that assumption holds
ONLY if the `for raw_line in self._proc.stdout:` loop can exit solely via normal `StopIteration`.
It cannot: an uncaught exception raised while iterating (see RES-B1) exits the SAME loop, via the
SAME `finally`, while the child is provably still alive and healthy, landing on the identical
unbounded `self._proc.wait()`. The earlier evidence file's downgrade is superseded by this finding.

**Verdict: DEFECT CONFIRMED (line 371), not a clean PASS.** Reported per task rule 2 (frozen
module — not fixed here). Every OTHER blocking wait in the module is correctly bounded.

## RES-A4 — a FAILED `start()` still leaves `events()` terminable (RUN AND CITE)

`test_failed_start_still_terminates_events` (pre-existing, C3 remediation: a fake `pi` that never
acks `get_state` makes `start()` raise as expected, and a prior bug left `events()` looping
forever afterward because `transport.close()` only cleared the transport's OWN `_closed` flag, not
the connector's separate `_closed_event`).

```
$ timeout 300 uv run python -m pytest -q tests/test_harness_pi_connector.py -k test_failed_start
1 passed
```

**Verdict: PASS** (pre-existing coverage, re-run and confirmed).

---

## RES-B1 — CRITICAL DEFECT: a syntactically-valid-JSON line that is NOT a `JSONDecodeError` bypasses the reader loop's only guard and wedges every consumer forever (NEW — characterization, not fixed)

The case text's literal shapes ("empty method", "params as a JSON array") are JSON-RPC 2.0
vocabulary (Codex's wire, not Pi's — Pi has no `method`/`params` fields at all, see
`docs/design/0004-harness-integrations.md` D4). Investigated the equivalent question for Pi's
actual `{"type": ...}` envelope instead, per the task's "adapt to protocol facts" framing: **can
any line make `_PiTransport._read_stdout`'s per-line dispatch fail in a way that is not a
`json.JSONDecodeError`?**

### Systematic probe of `_dispatch`/`_on_push_event` itself

Nine shapes were tried directly against the running connector (scratchpad probe, not committed):
top-level JSON array, bare scalar, bare string, `{"type": ""}`, `{"type": {"nested":"dict"}}`,
`{"type":"response","command":123}`, `{"type":"response"}` (no `command` field),
`extension_ui_request` with a dict `id`, one with a list `id`, and a line with an embedded NUL
byte in `type`. **All nine were handled cleanly** — every field access in `_dispatch`/
`_on_push_event` is guarded by an `isinstance` check or a safe `.get()` with a coercion fallback
(`native_type` -> `"unknown"` if not a non-empty string; `verb` -> `None` if not `str`), so none of
these shapes reach `HarnessEvent.__post_init__`'s validators in an invalid state, and the reader
thread survived all nine, continuing to dispatch a marker event afterward in every case. **This is
a real, positive result**: `_dispatch` itself is tightly guarded, unlike Codex's `_extract_thread_id`
(EV-REV-002), and does not reproduce the Class-B shape at that layer.

### The actual defect: one layer UP, in `json.loads` itself

`_read_stdout` wraps only the parse call:

```python
try:
    msg = json.loads(line)
except json.JSONDecodeError as exc:
    self._on_malformed_line(line, str(exc))
    continue
self._dispatch(msg)
```

A **syntactically valid, balanced JSON array nested ~20,000 levels deep** — `"[" * 20000 + "]" *
20000` — is legal JSON. `json.loads()` parsing it raises `RecursionError`, confirmed directly:

```
$ uv run python -c "
import json
depth = 20000
json.loads('[' * depth + ']' * depth)
"
RecursionError: maximum recursion depth exceeded while decoding a JSON array from a unicode string
```

`RecursionError` is **not** a subclass of `ValueError`/`json.JSONDecodeError`, so `except
json.JSONDecodeError` does not catch it. It propagates straight out of the `for raw_line in
self._proc.stdout:` loop — `self._dispatch(msg)` is never even reached — into the bare `finally`
block, which calls `self._proc.wait()` (line 371, no timeout) on a child that is, at that instant,
fully alive and healthy (simply sitting in its own read loop waiting for the next stdin line,
exactly like every other idle moment).

**Reproduced and instrumented directly (`test_res_b1_deeply_nested_json_line_is_not_a_jsondecodeerror_and_wedges_the_reader`,
new test, added to the suite — bounded to a few seconds so it cannot itself wedge the run):**

```
$ timeout 300 uv run python -m pytest -q tests/test_harness_pi_connector.py -k test_res_b1 -v
tests/test_harness_pi_connector.py::test_res_b1_deeply_nested_json_line_is_not_a_jsondecodeerror_and_wedges_the_reader PASSED
```

The test's own PytestUnhandledThreadExceptionWarning captures the exact live traceback:

```
Exception in thread pi-stdout:
Traceback (most recent call last):
  File ".../threading.py", line 1041, in _bootstrap_inner
    self.run()
  File ".../threading.py", line 992, in run
    self._target(*self._args, **self._kwargs)
  File "src/okto_nexus/adapters/outbound/harness/pi.py", line 363, in _read_stdout
    msg = json.loads(line)
          ...
RecursionError: maximum recursion depth exceeded while decoding a JSON array from a unicode string
```

A separate, longer-running manual instrumentation (not part of the committed suite, for
confirming the WORST case rather than just the bounded test's few-second window) watched
continuously for 30 real seconds after triggering this:

```
t=1s .. t=30s: reader_thread_alive=True child_proc_alive=True closed_event=False n_events=7
FINAL: done=False events=7
```

**The hang does not resolve on its own. It is unbounded in practice** (the test only bounds ITS
OWN patience, not the actual defect — the connector genuinely never recovers without external
intervention). Only calling `connector.close()` (which SIGTERMs the child directly, unblocking the
wedged `proc.wait()` from the outside) ends it — exactly the "looks alive, delivers nothing"
signature this entire RES suite exists to catch: no exception reaches any caller, no error event
is ever pushed, `_closed_event` is never set, and `conn._transport.is_alive()` keeps reporting
`True` throughout, actively misleading anyone who checks.

### Why this is real, not academic

Pi does not need to be malicious to hit this in principle — the same failure class (an uncaught,
non-`JSONDecodeError` exception escaping the reader loop before `_dispatch` even runs) would be
triggered by ANY future pi release that emits a structurally-unusual-but-technically-valid line
this parser can't handle, not only a deliberately pathological one. The fix, were this module not
frozen, is the same one already applied to sibling connectors' Class-B gap in spirit: wrap the
per-line processing (parse AND dispatch) in a broad `except Exception`, surface it as an `error`
`HarnessEvent`, and continue the loop — exactly the pattern `_on_malformed_line` already
establishes for the narrower `JSONDecodeError` case, just not wide enough.

**Verdict: CRITICAL DEFECT, CONFIRMED, NOT FIXED (frozen module — task rule 2).** RES-B1 as
originally scoped (JSON-RPC shapes) does not directly apply to Pi's wire vocabulary and, adapted
to Pi's actual envelope, the DISPATCH layer itself is clean; but the equivalent-severity Class-B
failure exists one layer up, in unguarded per-line JSON parsing, and is fully reproduced.

## RES-B2 — a reader thread that exits for ANY reason signals shutdown to EVERY consumer (NEW)

`test_res_b2_reader_thread_exit_signals_shutdown_to_every_concurrent_consumer` — two independent
concurrent `events()` consumers (bypassing the shared single-pump test helper, same pattern as the
RES-A2 fan-out test), triggered by `TRIGGER_CRASH` (the reader thread exits via the NORMAL,
already-guarded child-death path — `_on_child_exit` -> `_closed_event.set()` — not the RES-B1
defect path). Both consumers must observe shutdown and return.

```
$ timeout 300 uv run python -m pytest -q tests/test_harness_pi_connector.py -k test_res_b2
1 passed
```

**Verdict: PASS** for the guarded exit path (child death via `os._exit`, already covered by M2's
fix). **NOT proven** for the RES-B1 exit path (uncaught-exception-mid-loop) — by construction, that
path never reaches the shutdown signal at all (see RES-B1); a second consumer added to that
scenario would hang identically to the first, since neither `_fail_all_pending` nor
`_on_child_exit` ever runs. Recorded as a corollary of RES-B1, not a second independent defect.

## RES-B3 — no cleanup path contains an unbounded wait (same structural enumeration as RES-A3)

Same table as RES-A3. The one cleanup-path entry, `self._proc.wait()` at line 371 inside
`_read_stdout`'s `finally`, is the SAME confirmed unbounded wait RES-A3/RES-B1 document. No
DIFFERENT cleanup path (`close()`, `_terminate_group()`, `_kill_group()`) was found unbounded —
`close()`'s two `proc.wait(timeout=grace_s)` calls are correctly bounded with a fallback SIGKILL.

**Verdict: DEFECT CONFIRMED (same line 371 as RES-A3), not a clean PASS.**

---

## RES-C1 — every fake's wire behaviour justified against captured bytes (RUN AND CITE)

Already the subject of a dedicated prior evidence file, `EV-REV-003-pi-recheck.md`: the fake
server's abort/settle ordering was found to CONTRADICT the real captured wire order (ack-before-
settle in the fake vs settle-before-ack in reality, per
`docs/harness-integrations/research/pi-rpc-protocol-reference.md` §6b and
`EV-PI-001-raw_capture2.log`/`raw_capture3.log`), the fake was corrected FIRST, and the two tests
that had been passing against the wrong order were shown to fail against the corrected fake, then
rewritten against the true order. This session's own live run against the real binary
(`EV-PI-INT-001`, INT-06) INDEPENDENTLY reconfirms the same ordering
(`agent_settled` at `t=6.979398` before `response(abort,...)` at `t=6.979440`) — the fake's
corrected behaviour and the real binary's live behaviour now agree, checked twice by two different
methods.

`EV-REV-003`'s "Fake server audit beyond C1" section additionally checked and confirmed: the
7-line `extension_ui_request` startup burst, the absence of a ready/hello event, and the steer
immediate-queue/deferred-delivery ordering — all cross-checked against the protocol reference, no
further divergence found.

**Verdict: PASS** (existing evidence, independently reconfirmed live this session, not duplicated).

## RES-C2 — interrupt/abort path: fake emits the REAL ordering (RUN AND CITE)

Same citation as RES-C1 — this IS the C1 finding (the fake's interrupt/abort ordering was the
divergent behaviour found and fixed). See `test_interrupt_blocks_further_sends_until_agent_settled`
and `test_interrupt_gate_holds_during_real_race_window`, both built against and passing with the
corrected real-order fake, re-run below.

```
$ timeout 300 uv run python -m pytest -q tests/test_harness_pi_connector.py -k "interrupt"
5 passed
```

**Verdict: PASS.**

## RES-C3 — fakes can FAIL, not only succeed (RUN AND CITE)

The fake server in `tests/test_harness_pi_connector.py` fails five distinct ways, each with its
own consuming test:

| Fake failure mode | Trigger | Consuming test |
|---|---|---|
| Never acks handshake | `NO_ACK_GET_STATE` argv flag | `test_failed_start_still_terminates_events` |
| `prompt` rejected | `TRIGGER_ERROR` | `test_prompt_rejected_by_pi_surfaces_error_event_without_raising` |
| Child crashes mid-turn | `TRIGGER_CRASH` (`os._exit(7)`) | `test_child_crash_surfaces_process_exited_and_stops_cleanly`, `test_res_b2_...` (new, this session) |
| Child dies mid-abort, never acks | `TRIGGER_DIE_ON_ABORT` (`os._exit(9)`) | `test_child_death_fails_pending_request_immediately` |
| Sends garbage (non-JSON) line | `TRIGGER_MALFORMED` | `test_malformed_line_from_child_is_surfaced_and_stream_continues` |

Plus this session's addition, `TRIGGER_DEEPNEST` (RES-B1) — a sixth failure mode, added
specifically to characterize the newly found defect, not merely to succeed.

```
$ timeout 300 uv run python -m pytest -q tests/test_harness_pi_connector.py
24 passed, 1 skipped in 8.14s
```

**Verdict: PASS** (existing + this session's extension).

---

## Summary

| Case | Verdict | Source |
|---|---|---|
| RES-A1 | PASS | NEW |
| RES-A2 | PASS | RUN AND CITE |
| RES-A3 | **DEFECT CONFIRMED** (line 371) | structural + NEW repro |
| RES-A4 | PASS | RUN AND CITE |
| RES-B1 | **CRITICAL DEFECT CONFIRMED** (RecursionError bypasses the only guard) | NEW |
| RES-B2 | PASS for the guarded exit path; **inherits RES-B1's gap** for the unguarded one | NEW |
| RES-B3 | **DEFECT CONFIRMED** (same line 371) | structural |
| RES-C1 | PASS | RUN AND CITE (EV-REV-003) + live reconfirmation |
| RES-C2 | PASS | RUN AND CITE (EV-REV-003) |
| RES-C3 | PASS | RUN AND CITE + NEW extension |

**One real, reachable, unfixed defect** (RES-A3/B1/B3 are three views of the same root cause):
`_PiTransport._read_stdout` catches only `json.JSONDecodeError`, not the broader class of
exceptions a pathological-but-syntactically-valid line (or any other unforeseen per-line
processing failure) can raise; when one occurs, the reader thread dies silently, the cleanup path
it would have triggered is itself blocked on an unbounded `self._proc.wait()` against a healthy
child, and every current and future consumer of `events()` hangs forever with no error surfaced
anywhere. `pi.py` is FROZEN for this task (rule 2) — this is reported, not fixed, per instructions.

## Closing commands

```
$ timeout 300 uv run python -m pytest -q tests/test_harness_pi_connector.py
24 passed, 1 skipped in 8.14s

$ uv run ruff check .
All checks passed!
```
