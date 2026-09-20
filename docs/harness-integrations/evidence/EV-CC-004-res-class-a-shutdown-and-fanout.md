# EV-CC-004 — RES-A1..A4, Claude Code stream-json connector

Captured: 2026-09-20, this session. Module under test:
`src/okto_nexus/adapters/outbound/harness/claude_code_stream.py` (FROZEN — read-only; **two real
defects found below, reported per rule 2, NOT fixed**).

Per the task brief, unit-level RES cases against the connector use the fake-binary infrastructure
already established in `tests/test_harness_claude_code_connector.py` (the `_FAKE_CLAUDE_SCRIPT`),
which is itself REAL subprocess/thread/queue machinery — only the child binary is a stand-in.
RES-A2 and RES-A4 below reproduce with the REAL `claude` binary too where noted.

**No new tests were added to the pytest suite for RES-A2 or RES-A4.** Both are confirmed,
reproducible defects in FROZEN code; per rule 3 ("do not weaken, skip or xfail") and the general
instruction not to fix frozen code inside a test-writing task, adding a permanently-failing
assertion to the suite would misrepresent `REG-01`'s "zero pre-existing failures" baseline for a
defect this task is not authorized to fix. The repro scripts below (committed alongside this file)
and their real, captured output ARE the evidence for these two cases, exactly as EV-SYS-001 and
other prior evidence files in this project use scratchpad-authored repro scripts rather than
suite-resident tests for a defect-confirmation case.

## RES-A1 — `events()` called twice returns both times (PASS, existing)

`test_events_called_twice_both_return_after_close_not_just_one` (existing test, unchanged) —
opens two generators via `connector.events()` before the child exits, drains the first to
exhaustion, then proves the SECOND also returns (not hangs) via a bounded
`thread.join(timeout=10.0)`. PASSED as part of the full-file run below.

## RES-A2 — two CONCURRENT `events()` consumers each receive the FULL stream — **DEFECT, CONFIRMED**

**This connector does NOT satisfy RES-A2.** It shares exactly ONE `queue.Queue` across every
`events()` call (`self._events: queue.Queue[HarnessEvent] = queue.Queue()`, `__init__`,
`claude_code_stream.py:275`); every `events()` generator does `self._events.get(...)` against that
SAME queue (line 443). Two concurrent consumers therefore race for each item — the stream SPLITS
between them, exactly the Pi failure the test plan cites ("thread A got all 17 events, thread B
got zero") — it does not duplicate to both.

**This is a regression against the project's own established, working reference pattern.** The
sibling `pi.py` connector had and fixed the IDENTICAL defect ("C2 fix", its own `events()`
docstring, `pi.py:651-654`): *"calling this a second time, or from a second thread, no longer
SPLITS the stream with the first caller (the pre-fix defect: one shared `queue.Queue` meant two
concurrent consumers each got roughly half the events, unpredictably, with no way to tell which
half)."* Pi's fix: `events()` registers a fresh per-consumer `queue.Queue`, backed by an
append-only `_event_history` + a `_subscribers` list `publish()` fans out to under a shared lock
(`pi.py:543, 678-703, 894-905`). `claude_code_stream.py` has no `_subscribers` list, no
`_event_history`, and no fan-out in `_emit()` (`claude_code_stream.py:884-895` — a single
`self._events.put(...)`, nothing else). The standard fix EV-REV-002 documents
("Class A ... reference implementation: `pi.py`") only actually addresses the ONE-SHOT SHUTDOWN
half of Class A (the `threading.Event` for RES-A1/A4 termination); it does not, by itself, give a
connector fan-out — `pi.py` needed a SEPARATE mechanism (the subscriber list) for that, and
`claude_code_stream.py` never received it.

Reproduced 3/3 runs, both consumer threads confirmed PARKED in `queue.Queue.get()` (via a
`threading.Event` each sets right before entering the generator, both waited-on before the turn is
even sent) — ruling out a thread-start race as the explanation:

    $ timeout 30 uv run python EV-CC-004-res-a2-probe.py     # run 1
    t1 alive: True t2 alive: False
    consumer1 got 3 events, kinds=['turn_started', 'tool_activity', 'tool_activity']
    consumer2 got 4 events, kinds=['output_delta', 'output_delta', 'tool_activity', 'turn_completed']
    combined total across both consumers: 7
    consumer1 saw turn_completed: False
    consumer2 saw turn_completed: True

    $ timeout 30 uv run python EV-CC-004-res-a2-probe.py     # run 2
    consumer1 got 2 events, kinds=['turn_started', 'tool_activity']
    consumer2 got 5 events, kinds=['tool_activity', 'output_delta', 'output_delta', 'tool_activity', 'turn_completed']
    combined total across both consumers: 7

    $ timeout 30 uv run python EV-CC-004-res-a2-probe.py     # run 3
    consumer1 got 3 events, kinds=['turn_started', 'tool_activity', 'tool_activity']
    consumer2 got 4 events, kinds=['output_delta', 'output_delta', 'tool_activity', 'turn_completed']
    combined total across both consumers: 7

Every run: the full 7-event stream is non-deterministically partitioned across the two consumers
(combined total always 7, individual counts vary run to run), and `t1` (whichever consumer did not
get the `turn_completed` sentinel event) is left parked indefinitely in its generator, still
technically alive at the 10s join bound (only exits once the connector later closes and
`_closed_event` fires — a SEPARATE mechanism, RES-A1's fix, which is why RES-A1 itself still
passes even though RES-A2 does not: shutdown reaches both consumers eventually, but the actual
event PAYLOADS were already lost to whichever consumer's `get()` won each race).

**Severity, and reachability audited (not left open)**: this is a real defect in the connector's
own multi-consumer contract (the frozen `HarnessConnector.events()` port makes no "single
consumer" promise — see `application/ports.py:1687-1697`, typed `Any` specifically so different
transports can shape this differently, but nothing there licenses silently losing events to a
second caller). Checked the actual call graph rather than leaving this open:

    $ grep -rn "\.events()" src/okto_nexus/
    src/okto_nexus/application/harness_supervisor.py:480:            for event in live.connector.events():
    src/okto_nexus/application/harness_supervisor.py:676:            for event in live.connector.events():

Both hits are the SAME logical call site read twice (module docstring at 480, `_pump`'s real body
at 676) — `open()` (`harness_supervisor.py:343-353`) starts exactly **ONE** dedicated daemon pump
thread per full-duplex connector instance ("Full-duplex connectors (send_only=False) get ONE
dedicated daemon pump thread that blocks on connector.events() for the session's whole life"),
and external consumers never call the connector's `events()` directly at all — they subscribe to
`HarnessSubscriberRegistry`, which `_pump`'s single internal loop fans out to via
`_handle_event`/`self._subscribers.publish(event)` (`harness_supervisor.py:679-691`), a completely
separate mechanism from the connector's own `events()`. **Verdict: LATENT, not currently reachable**
through this project's own supervisor wiring — `connector.events()` is called exactly once per
connector instance in the whole codebase, so the split-stream failure mode cannot occur through
`harness_supervisor.py` as written today. It remains a genuine violation of the general
`HarnessConnector` port contract (nothing gates a future caller, a different supervisor, or a test
from calling `events()` twice, and the sibling `pi.py` connector treats "must not split across
concurrent consumers" as a real requirement worth its own fix) — reported prominently per rule 2 as
a real, reproducible connector-level defect, with its production reachability stated honestly as
latent rather than overclaimed as live.

Repro script committed: `EV-CC-004-res-a2-probe.py`.

## RES-A3 — every blocking wait carries a timeout (PASS, structural)

    $ grep -n "\.get(\|\.acquire(\|\.join(\|\.wait(\|\.recv(\|\.connect(\|select\.\|Queue\.get\|proc\.wait" \
        src/okto_nexus/adapters/outbound/harness/claude_code_stream.py
    443:                item = self._events.get(timeout=_EVENTS_POLL_S)
    604:        content = command.payload.get("content")                    # dict.get, not blocking
    657:        acquired = self._write_lock.acquire(timeout=_WRITE_LOCK_TIMEOUT_S)
    739:            self._stderr_thread.join(timeout=_EXIT_WAIT_TIMEOUT_S)
    745:                exit_code = proc.wait(timeout=_EXIT_WAIT_TIMEOUT_S)
    763:                    proc.wait(timeout=_EXIT_WAIT_TIMEOUT_S)
    (+ several more dict.get(...) calls on JSON payloads — not blocking waits, excluded)

Every genuine blocking primitive in the module carries an explicit timeout: the events queue
(`_EVENTS_POLL_S=1.0`), the write lock (`_WRITE_LOCK_TIMEOUT_S=10.0`), the stderr-thread join and
both `proc.wait()` calls (`_EXIT_WAIT_TIMEOUT_S=10.0`). No `select.`, `socket.recv`/`.connect` in
this module (subprocess-pipe based, not socket based — no such calls exist here at all). No bare
`.acquire()`, `.join()`, `.wait()` or `Queue.get()` (unbounded) found anywhere.

**Two reads that are structurally unbounded but are the reader thread's own designed job, not a
hazard** — narrower claim than "every blocking wait is bounded," disclosed rather than glossed:

* `for raw_line in self._proc.stdout:` (`claude_code_stream.py:694`) — an unbounded pipe read.
  Justified: this line IS the entire job of the dedicated stdout reader thread; it terminates on
  the child's own EOF, and the surrounding `try/finally: self._finish()` guarantees shutdown
  signalling fires regardless of how/when the loop ends (see RES-B2/EV-CC-005). Not equivalent to
  a caller-facing hang — nothing else in the connector blocks waiting on this thread without its
  own timeout (the joins/waits above ARE bounded).
* `proc.stdin.write(...)` / `.flush()` inside `_write_json` (`claude_code_stream.py:638-639`) — the
  module's OWN docstring discloses this as a deliberate residual, not an oversight
  (`claude_code_stream.py:616-626`): a single JSON line is always far under the OS pipe buffer's
  atomic-write threshold (`PIPE_BUF`), so the syscall itself either completes immediately or the
  pipe is already broken (`BrokenPipeError`/`OSError`, handled). What IS bounded is the LOCK
  ACQUIRE guarding it (`_write_lock.acquire(timeout=...)`, line 657) — see RES-A3's grep hit above
  and `test_write_lock_contention_raises_instead_of_blocking_forever` (existing, PASS).

RES-A3 **PASSES** with these two disclosed, justified exceptions — narrower than a flat "every wait
is bounded," matching the module's own honesty.

**RES-A3 stale-evidence note (added with the RES-A2/A4 fix, same session)**: the RES-A2 fix below
adds two new `with self._history_lock:` critical sections (in `_emit()` and `events()`), which the
grep pattern above (`\.get(|\.acquire(|\.join(|\.wait(|...`) does not textually match — `with lock:`
is sugar over `lock.acquire()`/`lock.release()`, not the literal `.acquire(` the grep looks for.
Re-checked directly rather than left implicit: both critical sections do only an in-memory list
append/copy under the lock (no I/O, no nested wait, no call into anything that itself blocks) —
identical in shape and duration to `pi.py`'s `_history_lock` critical sections, which this design
mirrors exactly. RES-A3 still **PASSES**; nothing here is a new unbounded wait.

## RES-A4 — a FAILED `start()` still leaves `events()` terminable — **DEFECT, CONFIRMED**

**This connector does NOT satisfy RES-A4.** `start()`'s failure path
(`claude_code_stream.py:347-365`) is:

```python
try:
    proc = subprocess.Popen(...)
except OSError as exc:
    raise OktoNexusError(ErrorCode.CONFIG_ERROR, f"failed to spawn Claude Code binary ...", ...) from exc
```

`self._closed_event` (the flag `events()` checks on every `queue.Empty`, line 445) is **never set**
on this path. `self._proc` stays `None` (the assignment on the next line is never reached). No
reader thread is ever started (nothing pushed the sentinel that would set it either). A subsequent
`events()` call therefore loops forever: `get(timeout=1.0)` → `queue.Empty` → `_closed_event.is_set()`
is `False` → `continue` → repeat, indefinitely.

This is the EXACT defect class the test plan's own parenthetical describes — *"Pi failed this: the
error path closed the transport but not the connector, so `events()` looped forever"* — reproduced
here in the SIBLING connector this project's own defect register calls a "reference
implementation." `pi.py`'s `start()` fixes this explicitly, with a comment that names the failure
mode by number (`pi.py:589-605`, "C3 fix"):

```python
except BaseException:
    transport.close()
    ...
    # C3 fix: transport.close() only sets the TRANSPORT's own `_closed` Event ... it has no way
    # to reach the CONNECTOR's separate `_closed_event`, which is what events() actually checks
    # on every queue.Empty. Without this, a failed start() leaves events() looping forever...
    self._closed_event.set()
    raise
```

`claude_code_stream.py`'s `start()` has no equivalent `except`-path `_closed_event.set()` call —
confirmed by reading the full method (`claude_code_stream.py:335-386`) — this fix was never
applied here.

Reproduced 3/3 runs against the connector with a nonexistent binary path (forcing the real
`subprocess.Popen` `OSError` path — no mock of `Popen` itself, the real syscall genuinely fails):

    $ timeout 30 uv run python EV-CC-004-res-a4-probe.py     # run 1
    start() raised as expected: CONFIG_ERROR
    events() thread alive after 5s join: True (elapsed 5.01s)
    _closed_event.is_set(): False
    events() NEVER RETURNED within 5s - CONFIRMED HANG

    $ timeout 30 uv run python EV-CC-004-res-a4-probe.py     # run 2
    start() raised as expected: CONFIG_ERROR
    events() thread alive after 5s join: True (elapsed 5.01s)
    _closed_event.is_set(): False
    events() NEVER RETURNED within 5s - CONFIRMED HANG

    $ timeout 30 uv run python EV-CC-004-res-a4-probe.py     # run 3
    start() raised as expected: CONFIG_ERROR
    events() thread alive after 5s join: True (elapsed 5.01s)
    _closed_event.is_set(): False
    events() NEVER RETURNED within 5s - CONFIRMED HANG

The probe used a 5s bound only to keep the repro fast; nothing in the code would ever cause it to
return on its own — the loop is unconditional given `_closed_event` can never become set on this
path. This is a genuine, structural, 100%-reproducible hang (not timing/contention — see the
matching code citation above), not a flake requiring the "re-run 3x" leniency for load-related
failures, though it was re-run 3x regardless per the machine-loaded rule.

**Severity, and reachability audited (not left open)**: checked whether `harness_supervisor.py`
actually has a code path that calls `connector.events()` after a `start()` failure. It does not,
by construction: `open()` calls `self._bounded_start(...)` (`harness_supervisor.py:286`) FIRST,
and only after it returns successfully does `open()` ever add the session to the live registry or
start the pump thread that calls `.events()` (`harness_supervisor.py:343-353`, `_pump` at 676). If
`_bounded_start` re-raises (which it does whenever `connector.start()` itself raises —
`harness_supervisor.py:409-413`, `outcome["error"]` re-raised on the caller's thread), `open()`
propagates immediately; the live registry and pump thread are never touched. The other place that
tears a connector down, `_best_effort_teardown` (`harness_supervisor.py:545-573`, used by `close()`
and by `open()`'s own post-start failure branch), calls `connector.send(verb="end")` and an
optional `connector.close()` — it never calls `.events()` either. **Verdict: LATENT, not currently
reachable** through `harness_supervisor.py` as written — this project's own supervisor never calls
`events()` on a connector whose `start()` failed. It remains a genuine, structural, 100%-reproducible
defect at the connector's own API boundary (this test plan's own framing: *"the transport stops
delivering events while appearing alive ... a connector that has silently stopped pushing is
indistinguishable from a harness with nothing to say"* — here even sharper, since the caller DOES
get a clear `start()` failure signal, but ANY future or different caller that follows the natural
`try: start(); ... finally: for e in connector.events(): ...` cleanup idiom — exactly what the
sibling `pi.py` connector's own "C3 fix" comment names as the failure mode it was written to
prevent — hangs forever with no further diagnostic). Reported prominently per rule 2 as a real,
reproducible connector-level defect, with its production reachability stated honestly as latent.

Repro script committed: `EV-CC-004-res-a4-probe.py`.

## Commands run this session

    timeout 300 uv run python -m pytest -q tests/test_harness_claude_code_connector.py
    -> 33 passed in 83.59s   (includes RES-A1's existing test)

    timeout 30 uv run python EV-CC-004-res-a2-probe.py    (x3)
    timeout 30 uv run python EV-CC-004-res-a4-probe.py    (x3)
    grep -n "..." src/okto_nexus/adapters/outbound/harness/claude_code_stream.py   (RES-A3)

## Addendum, same day — RES-A2 and RES-A4 FIXED (`claude_code_stream.py` back in scope)

The FROZEN designation above described the *previous* task's scope, not a permanent constraint —
this connector was explicitly back in scope for a fix this session (module docstring's own
framing, "this is the STABLE FLOOR"). Both defects are now fixed, mirroring `harness/pi.py`'s
reference shapes (C2 fan-out, C3 shutdown-on-failed-start) exactly as this file's analysis above
called for.

### Failing-first: two new tests added to the suite, confirmed FAILING against the pre-fix code

`test_res_a2_two_concurrent_events_consumers_each_receive_the_full_stream` (pytest port of
`EV-CC-004-res-a2-probe.py`'s choreography: both consumers confirmed PARKED via a
`threading.Event` each before the turn is sent) and
`test_res_a4_failed_start_leaves_events_terminable_not_hung` (pytest port of
`EV-CC-004-res-a4-probe.py`), run in isolation against the connector as committed above:

    $ timeout 120 uv run python -m pytest -q tests/test_harness_claude_code_connector.py \
        -k "test_res_a2_two_concurrent_events_consumers_each_receive_the_full_stream or test_res_a4_failed_start_leaves_events_terminable_not_hung"
    FAILED ...::test_res_a2_two_concurrent_events_consumers_each_receive_the_full_stream
    AssertionError: a consumer hung waiting for turn_completed - it never saw the full stream (RES-A2 split-stream regression)
    FAILED ...::test_res_a4_failed_start_leaves_events_terminable_not_hung
    AssertionError: events() hung after a failed start() - _closed_event was never set (RES-A4 regression; see harness/pi.py's C3 fix for the reference shape)
    2 failed, 33 deselected in 15.22s

Both fail exactly on the assertion that encodes the case's literal requirement, not on an
unrelated error — failing-first confirmed.

### The fix

`__init__`: `self._events: queue.Queue[...]` replaced with `self._event_history: list[HarnessEvent]`
+ `self._history_lock: threading.Lock` + `self._subscribers: list[queue.Queue[HarnessEvent]]` —
identical shape to `pi.py:541-543`'s C2 fix.

`_emit()`: now builds the `HarnessEvent` once, appends it to `_event_history` and snapshots
`_subscribers` under `_history_lock`, then `put()`s to each subscriber queue OUTSIDE the lock —
identical ordering to `pi.py`'s `_push_event` (`pi.py:882-905`), which is what makes
subscribe-vs-emit race-free (see that method's docstring, carried into this module's version).

`events()`: now registers a fresh per-consumer `queue.Queue`, snapshots `_event_history` as its
backlog under the SAME lock, yields the backlog, then drains its own queue with the existing
bounded `get(timeout=_EVENTS_POLL_S)` / `_closed_event` loop, and removes itself from
`_subscribers` in a `finally` — identical shape to `pi.py:679-699`'s `events()`.

`start()`: the `subprocess.Popen` → session/registration → `self._stdout_thread.start()` /
`self._stderr_thread.start()` sequence is now one `try` block with two `except` clauses:
`except OSError` (the existing CONFIG_ERROR translation, now also setting `_closed_event` before
raising) and `except BaseException` (a backstop for any OTHER failure in that sequence, e.g. a
thread-start `RuntimeError` — not just the one `OSError` path this connector itself anticipates),
mirroring `pi.py:594-613`'s C3 fix and its "caught as BaseException, not just the one exception
this module raises" framing exactly. The already-started CONFLICT guard stays OUTSIDE the `try` —
wrapping it would set `_closed_event` on every rejected `start()` of an already-healthy session,
killing that live session's `events()` within one poll period; verified this does NOT happen (see
`test_start_twice_raises_conflict`, still green below).

One consequence of this fix, decided explicitly rather than silently inherited: after a failed
`start()` sets `_closed_event`, `self._proc` is still `None` (never assigned on that path), so a
retry `start()` on the SAME instance is permitted and will succeed — but `_closed_event` would
otherwise still read `True` from the earlier failure, making the retried, healthy session's
`events()` return prematurely the next time its queue happens to run momentarily dry, even with
real events still to come. Fixed with one line: `start()` now calls `self._closed_event.clear()`
immediately after the CONFLICT guard, before the `try` — so a fresh `start()` attempt always
begins from a clean shutdown-signal state. Verified with a standalone probe: `start()` with a
nonexistent binary (fails, `_closed_event` set), then the SAME connector's `_binary`/`_argv`
corrected to a working fake script and `start()` called again (`_proc` was `None`, so this is
accepted) — `_closed_event.is_set()` reads `False` immediately after the successful retry, and the
retried session's `events()` correctly delivers its real event instead of returning empty.
`harness/pi.py` has the same latent hole (not fixed here — out of scope, not this task's file).

### Regression this fix surfaced, and why it is expected (not a new defect)

Three pre-existing tests called `connector.events()` a SECOND time mid-session, expecting the new
call to see only events NOT yet consumed by the first call — the old single shared-queue design's
(buggy) behaviour. Under the correct fan-out design, every `events()` call is an independent
subscriber that replays the FULL history from the start (this is the explicit design point of
`pi.py`'s C2 fix: "a LATE subscriber ... still gets everything from the start, not just what
happens to be pushed after it subscribes" — required so a real supervisor reconnecting mid-session
never silently misses earlier events). Re-subscribing mid-session to only see "what's new" was
never a promise this fix (or `pi.py`'s reference shape) makes; production code itself never does
this either — `harness_supervisor.py` opens exactly ONE pump thread that calls `events()` once and
iterates it for the connector's whole life (cited in this file's RES-A2 section above). The three
tests (`test_second_turn_reuses_same_nexus_session_id`,
`test_steer_in_unsafe_window_is_deferred_and_degrades_to_a_queued_turn`,
`test_real_claude_two_turns_share_session_and_process_survives`) were updated to hold ONE
`events()` iterator across all turns, matching the real usage pattern, with an inline comment at
each site explaining why. No assertion in any of the three was weakened, loosened or removed —
each still checks exactly what it checked before, against the same iterator's continued output.

### Passing, post-fix

    $ timeout 120 uv run python -m pytest -q tests/test_harness_claude_code_connector.py \
        -k "test_res_a2_two_concurrent_events_consumers_each_receive_the_full_stream or test_res_a4_failed_start_leaves_events_terminable_not_hung"
    2 passed in 4.73s

    $ timeout 300 uv run python -m pytest -q tests/test_harness_claude_code_connector.py
    35 passed in 92.44s   (33 pre-existing + 2 new; includes the 3 updated multi-turn tests, all green)

    $ uv run ruff check .
    All checks passed!

Both committed repro scripts re-run post-fix, 3/3 each, now demonstrating the FIX using the exact
scripts that demonstrated the defect (nothing in them was touched):

    $ timeout 30 uv run python EV-CC-004-res-a2-probe.py     (x3)
    t1 alive: False t2 alive: False
    consumer1 got 7 events, kinds=['turn_started', 'tool_activity', 'tool_activity', 'output_delta', 'output_delta', 'tool_activity', 'turn_completed']
    consumer2 got 7 events, kinds=['turn_started', 'tool_activity', 'tool_activity', 'output_delta', 'output_delta', 'tool_activity', 'turn_completed']
    combined total across both consumers: 14
    consumer1 saw turn_completed: True
    consumer2 saw turn_completed: True
    (identical on all 3 runs - both consumers now get the FULL stream, not a split of it)

    $ timeout 30 uv run python EV-CC-004-res-a4-probe.py     (x3)
    start() raised as expected: CONFIG_ERROR
    events() thread alive after 5s join: False (elapsed 1.00s)
    _closed_event.is_set(): True
    events collected: []
    (identical on all 3 runs - events() now terminates within one poll period instead of hanging)

### Verdict update

RES-A2 (H-CC): **FAILED — real defect** → **PASSED (fixed this session)**.
RES-A4 (H-CC): **FAILED — real defect** → **PASSED (fixed this session)**.

`EV-INDEX.md` is a cross-agent consolidation file owned by the orchestrator and is intentionally
NOT edited here; the orchestrator should flip these two rows (RES-A2 H-CC, RES-A4 H-CC) from
FAILED to PASSED, pointing at this addendum. Not stating a new RES-suite total here deliberately:
the codex connector agent is concurrently fixing its own RES-A2/A4 rows in the same tree (see
`git status` — `codex.py`/`EV-CX-002-res-cases.md` mid-write this session), so the orchestrator
should recompute the RES suite's FAILED total once across ALL connectors' evidence, not have two
agents each independently subtract from the same starting number.
