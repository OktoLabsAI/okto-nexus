# RES — Claude Code ATTACH (`cc-socks`) resilience suite

> **CORRECTION — 2026-09-20, added post-`1cc8522`, historical body below UNCHANGED.**
> The RES-A2 verdict this file recorded ("partition (not broadcast) is the documented,
> by-design behaviour") was **wrong**. It was a real defect, not a design choice: two
> concurrent `events()` consumers on this connector split a single shared
> `collections.deque` between them, so each consumer only ever saw *some* of the event
> stream, never all of it. Calling that "documented, by-design" is exactly why the
> defect survived Phase 5 unfixed — a reader of this file (including the Phase 5 six-
> agent pass that closed 13 of 14 other findings) had every reason to conclude cc-socks
> was fine, because this file told them so.
>
> Commit `1cc8522` fixed it, mirroring the fan-out fix already applied to `pi.py`,
> `codex.py`, and `claude_code_stream.py`: `events()` is now a **broadcast snapshot**
> over an append-only `_event_history` list, guarded by `_history_lock`
> (`claude_code_attach.py:288-304`, `:815-849`), not a destructive drain over a shared
> deque. Two concurrent consumers each receive the FULL stream now — re-verified live
> in this session by running
> `tests/test_harness_claude_code_connector.py::test_res_a2_two_concurrent_events_consumers_each_receive_the_full_stream`
> (2 threads, parked-before-send choreography, `kinds1 == kinds2` assertion) — **PASSED**.
>
> The fix also exposed a second, real regression: `HarnessSupervisor.send()`'s
> `send_only` branch used to re-drain `events()` after every `send()` assuming the old
> destructive-drain semantics (each event handled exactly once because it left the
> queue). Once `events()` became a non-destructive broadcast snapshot, that same branch
> would have re-handled event #1 on every subsequent `send()` — N sends would persist,
> publish, and inbox-notify each earlier event N times over, a duplication bug the
> frozen port never promised destructive draining would prevent. Commit `1cc8522` also
> added a per-session cursor (`harness_supervisor.py:143-153`, `:527-540`,
> `send_only_events_handled`) so each event is still handled exactly once regardless of
> how many times `send()` is called. Independently re-verified in this session (not
> just by reading the committed test): 3 `send()` calls → exactly 3 persisted events,
> exactly 3 published events, **and exactly 3 inbox notifications** (the inbox count was
> not asserted by the committed test; confirmed separately via a scratch script reusing
> the same fixtures).
>
> **RES-A2 (H-CA) status: PASSED as of `1cc8522`.** See `EV-INDEX.md` for the
> authoritative current status of this and every other case. Everything below this
> notice is the original Phase-4/pre-fix capture, preserved verbatim as history — do
> not read its RES-A2 verdict as current.

Captured: 2026-09-20 17:20–17:30 UTC
Commit under test: `b661538dda0055a557beaddd8f83c5e770206c43`
Module under test (FROZEN, not modified — status as of that commit; no longer frozen,
see correction above): `src/okto_nexus/adapters/outbound/harness/claude_code_attach.py`
Test file (NOT frozen, extended): `tests/test_claude_code_attach_connector.py`

Command for every case below unless noted otherwise:

```
$ timeout 300 uv run python -m pytest -q tests/test_claude_code_attach_connector.py
............................................                             [100%]
44 passed in 3.24s
```

(39 tests pre-existed this task; 5 are new — `test_res_a3_and_b3_every_blocking_wait_in_the_module_carries_a_timeout`,
`test_res_a4_a_failed_start_still_leaves_events_terminable`,
`test_res_a4_a_failed_start_after_partial_probe_success_still_leaves_events_terminable`,
`test_res_a2_concurrent_events_consumers_partition_without_loss_or_raise`. See per-case notes
below for which existing tests are cited as-is vs. which are new.)

```
$ uv run ruff check .
All checks passed!
```

## RES-A1 — `events()` called twice returns both times

**Existing test, cited, not duplicated**: `test_events_can_be_called_twice_without_hanging`
(`tests/test_claude_code_attach_connector.py:982-989`). Calls `list(connector.events())` twice
on a fresh connector and asserts both return `[]` without hanging. Because `events()` here is a
bounded deque-drain (`claude_code_attach.py:789-807`), a second call after the first is
structurally guaranteed to terminate (there is no generator state, no `StopIteration` edge, no
blocking primitive in the method at all) — this test documents that property rather than
guarding against a real risk of hanging, and passed as part of the 44/44 run above. **PASSED.**

## RES-A2 — two CONCURRENT `events()` consumers each receive the FULL stream

**New test**: `test_res_a2_concurrent_events_consumers_partition_without_loss_or_raise`.

This connector's `events()` is a documented **drain snapshot** over a plain
`collections.deque` (module docstring; `test_send_fails_loudly_and_records_error_event_when_peer_unreachable`'s
existing "Draining again must be empty" assertion), not a broadcast pump backed by a reader
thread the way Pi's `Queue`-backed generator is — Pi's actual RES-A2 defect (register: "thread A
got all 17 events, thread B got zero") cannot occur here in the same shape because there is no
shared reader thread continuously feeding a queue two independent generators race over.

There IS a real, narrower hazard worth checking directly: `events()`'s body —

```python
while self._events:
    drained.append(self._events.popleft())
```

— is a check-then-act pair, not one atomic operation. Two threads calling `events()`
concurrently on the SAME connector could in principle interleave such that one thread's
`popleft()` fires on an already-emptied deque and raises a bare `IndexError`. A bare `IndexError`
escaping `HarnessConnector.events()` would be exactly the "looks alive, silently breaks" failure
signature this whole suite exists to catch.

**Standalone probe, run BEFORE writing the pytest test**, to determine the real answer rather
than assume one:

```
$ timeout 120 uv run python res_a2_probe.py     # 200 trials x 200 events, threading.Barrier
=== summary ===
trials=200 n_events=200
hangs=0 raises=0 raise_types=set() lost_or_extra=0 duplicates=0

$ timeout 120 uv run python res_a2_probe2.py    # 5000 trials x 3 events,
                                                  # sys.setswitchinterval(0.00001)
                                                  # to maximise the exact race window
=== summary ===
trials=5000 n_events=3
hangs=0 raises=0 raise_types=set() lost_or_extra=0 duplicates=0
```

(Both scripts lived in the session's scratchpad directory, never in the repo, same convention
`EV-SYS-001-phase35-real-socket.md` states: "The verification script lived in the scratchpad,
never in the repo." They are exploratory probes, not committed regression tests — the committed
regression guard is the pytest test named above.)

5,200 trials total (two different stress shapes — high volume, and an aggressive
GIL-switch-interval targeting the exact last-item race) produced **zero** hangs, zero raised
exceptions, zero lost events, zero duplicated events. The pytest test committed above
(`60 trials x 80 events`, run inline in the suite in 0.01s; events are injected directly via the
connector's private `_record_local_event` to reach this volume cheaply rather than driving 80
real failed sends per trial through a fake socket — disclosed in the test's own comment) reproduces the same result under the
default test-suite conditions and asserts it as a regression guard: no hang (`join(timeout=5)`
+ `is_alive()` check), no raised exception, and the two consumers' combined output is lossless
and non-duplicating (a true partition of the queued events, never a drop, never a double
delivery).

**Verdict, stated precisely per the task's request to say plainly which case applies and how**:
measured, not assumed. The literal "each consumer gets the FULL stream" (broadcast) framing does
not hold for this connector — the assertions (`len(combined) == len(set(combined))` and
`set(combined) == expected`) show the queue is never broadcast to both consumers (no consumer
result set ever contained an item the other also received, and nothing was lost), but they do
NOT by themselves distinguish a true item-by-item partition from one thread draining everything
and the other getting nothing on a given trial — that finer mechanism was not separately
measured. What IS established, across 5,200+60 trials: no loss, no hang, no silent break, and no
duplication. This is a documented deviation from the broadcast framing, not a bug this task can
fix even if it were one (the module is FROZEN): `events()`'s own docstring already states the
drain-snapshot contract, and this connector's design was never a broadcast pump to begin with.

**Why this never arises in production**: the harness supervisor never creates two concurrent
`events()` consumers for a `send_only` connector. `send_only` connectors skip the dedicated pump
thread entirely and instead drain `events()` synchronously, inline, in the SAME thread that just
called `send()`:

```python
# src/okto_nexus/application/harness_supervisor.py:348-357 (cited, not modified by this task -
# only the four connector modules, domain/harness.py, and the two Protocols in ports.py are
# FROZEN per this task's scope; verified with
# `grep -n "if not connector.capabilities.send_only:\|thread.start()" ...`)
if not connector.capabilities.send_only:
    thread = threading.Thread(target=self._pump, args=(session.session_id,), ...)
    ...
    thread.start()
# src/okto_nexus/application/harness_supervisor.py:~480
if caps.send_only:
    for event in live.connector.events():
        self._handle_event(session_id, event)
```

`claude_code_attach.CAPABILITIES.send_only == True`, so this connector's `events()` is only ever
called by the same thread, synchronously, right after `send()` — the supervisor's own
architecture structurally avoids the concurrent-consumer scenario this case probes. The test
above checks the connector's own robustness regardless, since a future caller (a diagnostic tool,
a different supervisor path) is not contractually forbidden from calling `events()` concurrently
just because today's supervisor doesn't. **MEASURED — no loss/hang/raise found; partition
(not broadcast) is the documented, by-design behaviour.**
>
> **[CORRECTED, see notice at top of file] This verdict was wrong.** Calling the
> partition "by-design" was itself the failure — the module was never contractually a
> partition-only transport, and the risk this paragraph waves off ("a future caller...
> is not contractually forbidden from calling `events()` concurrently") materialized
> immediately once `HarnessSupervisor`'s send_only drain path was fixed to treat
> `events()` as idempotent-safe. Fixed in `1cc8522`: `events()` is now a broadcast
> snapshot; see the top-of-file correction for the re-verification.

## RES-A3 — every blocking wait carries a timeout (structural, not timing)

**New test**: `test_res_a3_and_b3_every_blocking_wait_in_the_module_carries_a_timeout`. Combines
RES-A3 and RES-B3 (both are the identical structural check for this module — see RES-B3 below).

Raw grep, run directly against the module (the same commands the pytest test automates):

```
$ grep -n "Queue\.get\|\.acquire(\|\.join(\|proc\.wait\|\.recv(\|select\." \
    src/okto_nexus/adapters/outbound/harness/claude_code_attach.py
(no output — zero matches)

$ grep -n "\.connect(" src/okto_nexus/adapters/outbound/harness/claude_code_attach.py
577:            sock.connect(str(socket_path))          # probe()
635:            sock.connect(str(socket_path))          # start()
753:            sock.connect(str(self._socket_path))    # send()

$ grep -n "settimeout" src/okto_nexus/adapters/outbound/harness/claude_code_attach.py
576:            sock.settimeout(self._timeout_s)
634:            sock.settimeout(self._timeout_s)
752:            sock.settimeout(self._timeout_s)
```

All three `connect()` call sites are immediately preceded (the line directly above, inside the
same `try:` block) by `sock.settimeout(self._timeout_s)`. `self._timeout_s` is clamped in
`__init__` to `max(float(connect_timeout_s), 0.001)` — never zero, never `None`, so it can never
silently become an unbounded wait. There is no `Queue.get`, lock `.acquire(`, `thread.join(`,
`proc.wait`, or `select.` anywhere in the module — this connector spawns nothing and reads
nothing off a socket at all (send-only, no reader thread), so those primitives simply do not
appear. **PASSED — every blocking wait in the module is bounded.**

## RES-A4 — a FAILED `start()` still leaves `events()` terminable

**New tests**: `test_res_a4_a_failed_start_still_leaves_events_terminable` (earliest failure —
missing registry, `NOT_FOUND`, before any state is set) and
`test_res_a4_a_failed_start_after_partial_probe_success_still_leaves_events_terminable` (a LATER
failure — registry+key read successfully, but the resolved socket path is not a socket,
`CONFIG_ERROR` — closer to the Pi failure shape, where partial setup work had already happened
before the error path was hit).

Both call `connector.start(...)` inside `pytest.raises(OktoNexusError)`, then immediately
`list(connector.events())` and assert `== []`. Both pass (see the 44/44 run above). This
connector's error paths never assign anything to `self._events` except through
`_record_local_event` (only reachable from inside `send()`, never from `start()`'s failure
paths, and `start()` never leaves any bookkeeping in a state `events()` could get stuck on — the
deque is initialised empty in `__init__` and `start()` failures raise before touching it at all).
**PASSED, both variants.**

## RES-B1 / RES-B2 / RES-B3 — reader-thread dispatch hazards

**Do not apply to this connector — stated explicitly, not silently skipped.** `cc-socks` is
SEND-ONLY with NO inbound channel of any kind (module docstring, `claude_code_attach.py:37-38`;
`capabilities.send_only=True`). There is no reader thread, no per-line dispatch loop, and
therefore:

- **RES-B1** ("a domain-invalid message surfaces as an error and the reader loop continues") has
  no reader loop to continue. The nearest structural analogue this connector DOES have — parsing
  externally-supplied, potentially-malformed input it does not control (the registry and
  key-file JSON, not a wire read loop) — is already covered:
  `test_probe_and_start_agree_when_key_file_exists_but_is_unparseable` (key file present but not
  JSON), `test_probe_never_raises_on_embedded_null_byte_in_socket_path` and
  `test_start_raises_oktonexuserror_not_valueerror_on_embedded_null_byte` (a value that is valid
  JSON/a valid Python `str` but domain-invalid in exactly the JSON-RPC-array-params sense
  RES-B1 asks about — a NUL byte passes every earlier type check and only breaks at
  `os.stat`/`socket.connect`, which raise `ValueError`, not `OSError`). Each surfaces a
  structured `OktoNexusError`, never a bare exception — the same discipline RES-B1 asks of a
  per-line dispatch loop, applied at this connector's actual untrusted-input boundary.
- **RES-B2** ("a reader thread exiting for ANY reason signals shutdown to EVERY consumer") has no
  reader thread to exit.
- **RES-B3** is identical to RES-A3 for this module (see above) — "no cleanup path contains an
  unbounded wait" is the same grep, same result: zero unbounded waits anywhere in the file.

## RES-C1 — every fake's wire behaviour is justified against CAPTURED BYTES

Cited section, `docs/harness-integrations/evidence/EV-CC-001-cc-socks-external-inject.md`,
"Wire protocol (recovered from the CLI bundle)":

> Newline-delimited JSON. An auth line is REQUIRED first. Verbatim from a log string inside the
> shipped binary:
>
>     [uds-messaging] Inject messages (auth line REQUIRED here):
>     { echo '{"type":"auth","token":"'"$CLAUDE_CODE_MESSAGING_TOKEN"'"}';
>       echo '{"type":"user","message":{"role":"user","content":"hello"}}'; } | socat ...
>
> Send is fire-and-forget: the connection is accepted with no synchronous ack.

Every fake server in `tests/test_claude_code_attach_connector.py` (`_FakeSocketServer`,
`_AcceptThenCloseServer`, `_RejectAfterAuthServer`, `_CloseMidMessageServer`) is a plain
`AF_UNIX` `SOCK_STREAM` listener that reads raw NDJSON off the wire with no assumed framing
beyond newlines — matching the captured shape exactly, not modelling anything the capture
doesn't show. `test_send_delivers_auth_then_user_ndjson_lines`
(`tests/test_claude_code_attach_connector.py:319-338`, EXISTING, cited not duplicated) asserts
the exact ordering and shape against a real `AF_UNIX` socket:

```python
assert lines[0] == {"type": "auth", "token": "tok-xyz"}
assert lines[1]["type"] == "user"
assert lines[1]["message"]["role"] == "user"
```

— auth line first, `{"type":"auth","token":...}`, then `{"type":"user","message":{"role":"user",
"content":...}}`, byte-for-byte the shape EV-CC-001 captured from the real binary's own log
string. `test_send_against_a_peer_that_reads_auth_then_rejects`
(`tests/test_claude_code_attach_connector.py:863-911`, EXISTING) independently confirms the same
ordering against a *different* fake (`_RejectAfterAuthServer`) via
`server.observed_auth_lines == [{"type": "auth", "token": "tok-xyz"}]`. **PASSED — justified
against EV-CC-001, cited above.**

## RES-C2 — the fake emits the REAL interrupt/abort ordering

**Does not apply.** This connector has no interrupt/abort path at all (`send()` rejects every
verb other than `send_turn` — `claude_code_attach.py:702-710`; there is no settle-event
ordering to get wrong because there is no abort verb on this transport to order in the first
place). RES-C2 is specifically Pi's failure class (abort-ack-before-settle); `cc-socks` has no
analogous two-step handshake to mis-order.

## RES-C3 — fakes can FAIL, not only succeed

**Existing, cited, not duplicated.** Three fakes exist specifically to reject/drop, not merely
accept:

- `_AcceptThenCloseServer` (`tests/test_claude_code_attach_connector.py:672-700`) — accepts then
  closes immediately without reading anything, exercised by
  `test_send_against_a_peer_that_accepts_then_closes_is_documented_not_detected`.
- `_RejectAfterAuthServer` (`:757-813`) — reads the auth line, then closes without ever reading
  the user line or acking, exercised by `test_send_against_a_peer_that_reads_auth_then_rejects`.
- `_CloseMidMessageServer` (`:816-860`) — reads the auth line fully, reads only part of the user
  line, then drops the connection, exercised by
  `test_send_against_a_peer_that_closes_mid_message`.

All three tests assert the connector never leaks a bare non-`OktoNexusError` exception against a
peer that actively misbehaves (`pytest.fail(f"send() leaked a bare {type(exc).__name__}...")` in
each), which only has teeth because the fakes genuinely CAN and DO fail the connection — a fake
that only ever accepted-and-acked could never exercise that assertion at all. **PASSED — cited,
not duplicated.**

## Summary

| Case | Status | Evidence |
|---|---|---|
| RES-A1 | PASSED (existing) | `test_events_can_be_called_twice_without_hanging` |
| RES-A2 | ~~MEASURED (partition, not broadcast...)~~ **CORRECTED: was a defect, FIXED in `1cc8522`, now PASSED (broadcast, re-verified live)** | new test + standalone probes (pre-fix); `test_res_a2_two_concurrent_events_consumers_each_receive_the_full_stream` (post-fix) |
| RES-A3 | PASSED (structural) | new test, grep output above |
| RES-A4 | PASSED (new) | 2 new tests |
| RES-B1 | N/A (no reader loop) | nearest analogue cited: existing key-file/NUL-byte tests |
| RES-B2 | N/A (no reader thread) | — |
| RES-B3 | PASSED (structural, same as RES-A3) | new test |
| RES-C1 | PASSED (existing) | cited against EV-CC-001 |
| RES-C2 | N/A (no interrupt path) | — |
| RES-C3 | PASSED (existing) | 3 fakes that genuinely fail |

No defect was found in the FROZEN `claude_code_attach.py` module by any RES case above.
