# EV-REV-002: Adversarial Code Review Defect Register

Captured 2026-09-20. Source workflow: `wf_de1d2ad9-17f`. These are adversarial review findings against three connectors (codex, claude-code-ccsocks, claude-code-streamjson) whose own test suites all passed. Each finding documents a concrete defect with file/line references and requires a failing-first regression test before closure.

## Summary

| Connector | Verdict | polling_violation | port_violation | critical | major | minor |
|-----------|---------|-------------------|----------------|----------|-------|-------|
| claude-code-ccsocks | DEFECTS_FOUND | false | false | 0 | 2 | 2 |
| claude-code-streamjson | DEFECTS_FOUND | false | false | 2 | 2 | 1 |
| codex | DEFECTS_FOUND | false | false | 1 | 3 | 2 |

## claude-code-ccsocks

### MAJOR — The 'anti-pid-reuse guard' (_check_no_pid_reuse, ~lines 730-764) re-reads only t...
**File:** `src/okto_nexus/adapters/outbound/harness/claude_code_attach.py`

The 'anti-pid-reuse guard' (_check_no_pid_reuse, ~lines 730-764) re-reads only the exact key-file path pinned at start() (self._key_path, set at line 590), never re-globbing `{pid}.*.key` the way _find_key_file (lines 347-375) does. A genuine OS pid recycling event produces a NEW Claude Code session that writes a NEW `<pid>.<newhash>.key` file, leaving the OLD file (if not cleaned up by Claude Code) untouched with its original procStart. In that scenario the guard compares the stale file to itself, finds no mismatch, and send() proceeds to deliver a stale peerToken to the socket path (also pid-keyed, so likely now owned by the new session) with no ack read to detect the auth rejection. The test that exercises this guard (test_send_trips_pid_reuse_guard_on_proc_start_mismatch) only simulates an in-place rewrite of the SAME file path -- exactly the narrow case that works -- not the realistic new-session-new-hash-file case the guard is meant to catch.

**Why it matters:** The module and report both frame this as protection against a recycled pid; as implemented it only catches a scenario (in-place content mutation of one fixed file) that real Claude Code pid reuse is unlikely to produce, so the guard gives a false sense of safety and a failed send silently returns success (status transitions to RUNNING) while the message was actually delivered to, or rejected by, an unrelated process.

### MAJOR — Neither start() (socket stat at lines 538-556) nor send() (socket connect at lin...
**File:** `src/okto_nexus/adapters/outbound/harness/claude_code_attach.py`

Neither start() (socket stat at lines 538-556) nor send() (socket connect at lines 667-698) verifies the target socket's owning uid (st_uid) before connecting and writing the bearer token. EV-CC-001 documents that the Claude Code SERVER verifies the connecting client via SO_PEERCRED/ownerUids, but this connector, as the CLIENT, performs no equivalent check that the socket it is about to authenticate against actually belongs to the expected same-user Claude Code process.

**Why it matters:** The computed-fallback path (_computed_socket_path, used whenever the registry omits messagingSocketPath) targets /tmp/cc-socks/<pid>.sock, a path under the world-writable /tmp. If a socket already exists there under another (malicious, local) uid's control -- e.g. the real /tmp/cc-socks directory has not yet been created with 0700 permissions -- this connector would happily connect and write the 0600-protected peerToken read from the key file straight to it, disclosing the token to a process that could not otherwise have read it.

### MINOR — Several behaviors the module docstring and the implementer's report explicitly c...
**File:** `tests/test_claude_code_attach_connector.py`

Several behaviors the module docstring and the implementer's report explicitly call out are asserted nowhere in the 20 tests: (1) the /tmp/cc-socks-<uid>/<pid>.sock overflow branch of _computed_socket_path (only the XDG_RUNTIME_DIR-set, non-overflow branch is covered by test_start_falls_back_to_computed_socket_path_when_registry_omits_field); (2) that send() genuinely re-reads the token file each call -- the pid-reuse-guard test rewrites the key file but keeps the same token value, so no test proves a ROTATED token actually appears on the wire on a subsequent send; (3) probe()'s 'not_a_socket' outcome; (4) start()'s CONFIG_ERROR path for a non-socket file at the resolved path.

**Why it matters:** These are exactly the areas the report itself flags as least certain (gap #8, the token re-read claim); an untested branch in reverse-engineered, undocumented-protocol code is where a real regression is most likely to hide, and CI would not catch it. Confirmed by direct execution: the overflow branch's logic is correct (verified with `_computed_socket_path(12345, {'XDG_RUNTIME_DIR': 'a'*90-char string})` -> falls back to /tmp/cc-socks-<uid>/), but nothing in the suite exercises it.

### MINOR — probe() is documented to 'never raise' (module docstring, method docstring at li...
**File:** `src/okto_nexus/adapters/outbound/harness/claude_code_attach.py`

probe() is documented to 'never raise' (module docstring, method docstring at line 409), but its filesystem calls (os.stat at line 475, socket.connect at line 500) are guarded only against OSError. A pathological pid value or a path containing a null byte raises ValueError, not OSError, and would escape probe()'s try/except and propagate to the caller.

**Why it matters:** A supervisor polling probe() on a schedule specifically to avoid try/except around this connector (per the method's own stated purpose) could still crash on this input, though the trigger requires an unusual/corrupted registry value.

## claude-code-streamjson

### CRITICAL — _pump_stdout has no exception guard around per-line dispatch; a syntactically-va...
**File:** `src/okto_nexus/adapters/outbound/harness_claude_code.py`

_pump_stdout has no exception guard around per-line dispatch; a syntactically-valid but shape-drifted native event (e.g. {"type":"stream_event","event":"oops"}) raises AttributeError inside _handle_stream_event/_handle_assistant/_handle_result's unchecked `.get()` calls, silently killing the reader thread (Python swallows the exception; no HarnessEvent, no propagated error).

**Why it matters:** Verified end-to-end with a real child process (fake 'claude' emitting message_start, then the drifted line, then sleeping mid-turn with stdin still open): the reader thread dies immediately, _finish() then blocks 10s joining the never-closing stderr thread plus 10s on proc.wait() (both time out since the child is genuinely still alive and its stdin is open), and only after ~20s does the connector emit a process_exit error event and the terminal sentinel -- while proc.poll() proves the child is STILL RUNNING at that exact moment. The connector fabricates a session-end signal it never observed, directly contradicting its own declared observes_session_end=True capability, drops the turn's real eventual result forever (nothing reads stdout again), and leaks the child process. This is exactly the 'malformed JSON arrives' / 'does it hang' failure mode the task asks about, and the module's own docstring says robustness here is the entire point of this connector.

### CRITICAL — _request_interrupt() marks self._pending_turns[-1] (the most-recently-queued, st...
**File:** `src/okto_nexus/adapters/outbound/harness_claude_code.py`

_request_interrupt() marks self._pending_turns[-1] (the most-recently-queued, still-unresolved turn) as interrupted, but _handle_result() always resolves via popleft() (oldest-first) -- these two ends disagree about which pending entry an interrupt belongs to whenever more than one turn is outstanding.

**Why it matters:** This inverts exactly the classification bug the implementer's report presents as its headline fix ('a genuine correctness bug found and fixed... interrupted turn's belated result got misclassified'). The FIFO-resolution half of the fix (popleft matching arrival order) is correct, but the marking half (which index gets flagged) was never updated to match -- it still marks the tail instead of the head. Any downstream consumer treating turn_completed as authoritative (this is literally the harness event stream Nexus persists for durability) will silently miss a real failure and believe an interrupt succeeded on the wrong turn.

### MAJOR — No test -- fake or @requires_real_claude -- exercises the steer verb against the...
**File:** `tests/test_harness_claude_code_connector.py`

No test -- fake or @requires_real_claude -- exercises the steer verb against the real claude binary; every steer/FIFO-ordering test only runs against the fake script's modeled behavior.

**Why it matters:** A test suite that validates the hardest, most-recently-fixed logic path only against a hand-written fake (which necessarily encodes the author's own assumptions) cannot catch a real-CLI behavior mismatch or, as shown above, a logic bug the fake itself doesn't happen to exercise (neither steer test ever queues a second turn before the first resolves).

### MAJOR — The only signal that a steer()/interrupt() degraded away from the declared steer...
**File:** `src/okto_nexus/adapters/outbound/harness_claude_code.py`

The only signal that a steer()/interrupt() degraded away from the declared steer_timing=IMMEDIATE behavior is a specific native_event string ('steer_interrupt_deferred_unsafe_window' / 'interrupt_deferred_unsafe_window') inside a generic tool_activity HarnessEvent.

**Why it matters:** This is disclosed in the module docstring (not hidden), and the window is real and narrow, so it stops short of being a bare capability lie -- but it does mean the declared steer_timing=IMMEDIATE capability has no port-legal, closed-vocabulary way for a supervisor to learn about its own documented exception, which the port's own capability-fields rationale says should change supervisor control flow.

### MINOR — test_events_iterator_wakes_promptly_not_on_a_poll_interval does not actually tes...
**File:** `tests/test_harness_claude_code_connector.py`

test_events_iterator_wakes_promptly_not_on_a_poll_interval does not actually test what its name and docstring claim.

**Why it matters:** This test provides no actual evidence against polling -- the real evidence is the straightforward code inspection (events() is `while True: item = self._events.get()`, a genuine blocking wait, confirmed by grep: no sleep/poll/time. anywhere in the module outside comments/docstrings). Reporting a test as proof of a property it can't actually distinguish is a test-honesty gap, even though the underlying code claim happens to be true.

## codex

### CRITICAL — A single JSON-RPC-legal but domain-invalid inbound notification permanently wedg...
**File:** `src/okto_nexus/adapters/outbound/harness_codex.py` line 328

A single JSON-RPC-legal but domain-invalid inbound notification permanently wedges the reader thread and hangs events() forever, with no process/exited event and no _SHUTDOWN sentinel.

**Why it matters:** _read_stdout's for-loop calls self._dispatch(msg) with no exception guard (line 340); _dispatch -> _on_notification -> _push_event can raise (e.g. HarnessEvent.__post_init__ rejects native_event="" per domain/harness.py:323-328, or _extract_thread_id's params.get() raises AttributeError if params is a JSON array, which JSON-RPC 2.0 permits). When that happens, the exception unwinds into the unguarded finally block (lines 341-345), which calls self._proc.wait() with NO TIMEOUT while the child is still alive and running normally - so the thread blocks there forever, _on_child_exit is never reached, _SHUTDOWN is never pushed, and stdout is no longer drained (the exact pipe-fill deadlock shape task item 3 warns about). I verified this empirically: built a scripted fake server that emits {"method": "", "params": {}} mid-turn, ran it against the real CodexAppServerConnector, and after 8 seconds the 'codex-stdout' thread was still alive (not exited, not finished), zero events had been delivered, and the events() consumer thread never returned. The only malformed-input test in the suite (test_malformed_line_is_surfaced_and_stream_continues) covers a JSONDecodeError, which IS caught (line 336-339) - it never exercises a structurally-valid-but-domain-invalid message, so this entire failure class is untested and undisclosed.

### MAJOR — "process/exited" (and "transport/malformed_line") fall through to kind="tool_act...
**File:** `src/okto_nexus/adapters/outbound/harness_codex.py` line 109

"process/exited" (and "transport/malformed_line") fall through to kind="tool_activity" instead of kind="error", so a supervisor branching on the normalized kind cannot distinguish the child dying from routine noise.

**Why it matters:** _EVENT_KIND_BY_METHOD (lines 109-121) has no entry for the synthetic native_event strings this connector itself mints on child death (_on_child_exit, line 728-742: native_event="process/exited") or on a malformed line (_on_malformed_line, line 744-754: native_event="transport/malformed_line"), so both fall to _DEFAULT_EVENT_KIND="tool_activity" (line 125) - the same bucket as a routine token-usage update. EVENT_KINDS already has an "error" slot built for exactly this, and the domain's STARTING->ERRORED / RUNNING->ERRORED transitions exist for the child-died case. Since observes_session_end=True is the capability this whole path is supposed to deliver on, classifying its one real signal as indistinguishable-from-noise materially undercuts that claim. It's also a test-honesty gap: test_child_death_surfaces_process_exited_and_stops_cleanly (tests/test_harness_codex_connector.py:436-461) asserts only `any(ev.native_event == "process/exited" for ev in collected)` and never checks `ev.kind`, so it passes even though the kind is wrong.

### MAJOR — subprocess.Popen() in _CodexTransport.start() is not wrapped, so a missing or un...
**File:** `src/okto_nexus/adapters/outbound/harness_codex.py` line 216

subprocess.Popen() in _CodexTransport.start() is not wrapped, so a missing or unreadable codex binary raises a raw, unclassified FileNotFoundError/OSError instead of an OktoNexusError.

**Why it matters:** Every other I/O failure path in this same file (stdin write at line 257, request timeout at line 281, etc.) is deliberately wrapped into OktoNexusError with a catalog ErrorCode. This one isn't. I verified it directly: `CodexAppServerConnector(command=['this-binary-does-not-exist-xyz']).start(...)` raises a bare `FileNotFoundError`, not `OktoNexusError`. The sibling connector for the same port, harness_claude_code.py:262-281, wraps the identical subprocess.Popen() call in `except OSError as exc: raise OktoNexusError(ErrorCode.CONFIG_ERROR, f"failed to spawn ... {exc}", {...}) from exc` - the house pattern this file otherwise follows everywhere else. A generic top-level handler (errors.py:221-234) will eventually catch anything and map it to a generic INTERNAL_ERROR, so this doesn't crash the whole process, but it silently drops the specific, actionable CONFIG_ERROR classification and the {"binary":..., "argv":...} details the sibling connector provides for this exact scenario - the task's failure-mode checklist item ('the binary is missing... does it fail cleanly?') is not met to the standard already established in this codebase, and no test in the connector's suite exercises this path.

### MAJOR — self._transport is assigned before the initialize handshake is confirmed to succ...
**File:** `src/okto_nexus/adapters/outbound/harness_codex.py` line 637

self._transport is assigned before the initialize handshake is confirmed to succeed, so a handshake timeout/rejection permanently wedges the connector with no way to recover except constructing a brand-new instance.

**Why it matters:** _spawn_and_initialize (lines 626-641) does `self._transport = transport` (line 637) BEFORE calling `transport.request(_METHOD_INITIALIZE, ...)` (line 638-640). If that request raises (handshake timeout or an error response), the exception propagates out of start(), but self._transport is already non-None. start()'s own guard (`if self._transport is None: self._spawn_and_initialize()`, line 481-482) means every subsequent call to start() will skip respawning entirely and instead fire thread/start straight at a transport whose handshake never completed. self._initialized (set at line 459 and 641) is written but never read anywhere in the class (confirmed by grep) - there is no gating logic that would have caught or recovered from this state. This is a genuine, if less common, second way to wedge the connector permanently (distinct from finding #1), and it is not covered by any test in the suite (no test exercises a failed/timed-out initialize).

### MINOR — The early-notification buffer/replay mechanism has an unguarded TOCTOU race that...
**File:** `src/okto_nexus/adapters/outbound/harness_codex.py` line 674

The early-notification buffer/replay mechanism has an unguarded TOCTOU race that can drop a buffered event permanently.

**Why it matters:** _emit_for_thread (lines 674-688) acquires self._sessions_lock only for the `_sessions_by_thread.get(thread_id)` lookup, releases it, then appends to the completely unlocked `_unmapped_thread_events` dict. start() (lines 496-501) registers the mapping AND pops `_unmapped_thread_events.pop(thread_id, [])` inside the same lock acquisition. If the reader thread's lookup (sees state=None) is followed by a context switch into start() registering the mapping and popping an as-yet-empty buffer, and only then does the reader thread's append run, that event is buffered forever and never replayed - the exact scenario the buffer/replay mechanism (documented as mismatch note 8's fix) exists to prevent. I did not reproduce this empirically (the window is a few instructions wide on a local pipe), but it is structurally real, and test_early_thread_started_notification_is_buffered_and_replayed cannot detect it: the fake server always emits the early thread/started notification well before writing the thread/start response, so the reader is never actually racing start()'s pop - the one interleaving that matters is never produced by that test.

### MINOR — A late JSON-RPC error surfaced for a fire-and-forget command carries no record o...
**File:** `src/okto_nexus/adapters/outbound/harness_codex.py` line 712

A late JSON-RPC error surfaced for a fire-and-forget command carries no record of which command (send_turn/steer/interrupt/end) produced it, and thread_id is hardcoded to None even though the connector already knows it.

**Why it matters:** _on_unmatched_response (lines 712-726) pushes `HarnessEvent(kind="error", native_event="jsonrpc/error_response", thread_id=None, turn_id=None, payload=<raw wire error>)` for any rejected fire-and-forget request. The payload is just the raw `{code, message}` from codex - it never includes the original method (turn/start vs turn/steer vs turn/interrupt vs thread/unsubscribe) or the thread_id, despite both being readily available (the method was passed to send_fire_and_forget by the caller, and thread_id is on the same _ThreadState the session_id already resolves to in self._sessions_by_id). A supervisor with more than one fire-and-forget command in flight for a session (e.g. steer followed quickly by interrupt) has no way to tell from the surfaced event which command actually failed.

## Verbatim Reviewer Summaries

### claude-code-ccsocks

Reviewed the actual code, not just the report. No polling/sleep-loop/busy-wait anywhere in the event path (events() is a bounded deque drain; the only time.sleep is in the test harness's own connection-wait helper, which is test scaffolding, not the connector's delivery path). No modification to the frozen port files (git diff --stat on domain/harness.py and application/ports.py is empty). Declared HarnessCapabilities (send_only=True, steer_timing=None, multiplexes_sessions=False, observes_session_end=False) are honestly enforced by the code (send() structurally rejects every verb but send_turn; the connector never drives a session to ENDED). The deadlock/pipe-draining check is not applicable: this connector spawns no child process and holds no stdout/stderr pipes at all, it is a pure socket client -- confirmed by reading the full file. Import-boundary test passes, though it only scans domain/ and application/ for sqlite3/mcp imports and does not itself check native-vocabulary leakage into domain types; manual inspection confirms HarnessEvent.kind stays within the closed EVENT_KINDS set and native protocol details are confined to native_event strings and session.metadata, as the port intends. Ran the connector's own 20 tests directly (uv run python -m pytest tests/test_claude_code_attach_connector.py) -- all pass, and they exercise real AF_UNIX sockets, real threads and real JSON parsing rather than mocks that would pass regardless, so they are honest tests, just incomplete on a few branches (see findings). Two genuine, verified defects found beyond what the report disclosed: the 'anti-pid-reuse guard' only detects an in-place rewrite of the exact key-file path captured at start(), not the realistic case of a recycled pid producing a new hash-named key file, so it likely never fires against a real pid-reuse event; and neither start() nor send() verifies the target socket's owning uid before writing the bearer token to it, which is a latent token-disclosure risk on the world-writable /tmp fallback path if /tmp/cc-socks does not yet exist with correct permissions. A minor test-coverage gap and a minor probe()-can-still-raise edge case round out the findings. Verdict: DEFECTS_FOUND (not fabricated for volume -- these are concrete, code-verified, with file/line references), no polling violation, no port violation.

### claude-code-streamjson

No polling and no frozen-port modification (git diff --stat on domain/harness.py and application/ports.py is empty; both connector files are untracked-new). Stdout and stderr are both drained on dedicated threads, and events() is a genuine blocking Queue.get(). However, two CRITICAL, empirically-reproduced defects survive: (1) a single type-confused-but-valid native JSON line silently kills the stdout reader thread, leaks the live child process for up to 20s, and then falsely reports process_exit/session-end while the child is still alive (verified end-to-end with a real subprocess); (2) _request_interrupt() marks the newest pending turn while _handle_result() resolves oldest-first, so interrupt()/steer() attach 'interrupted_by_connector' to the wrong turn whenever more than one turn is queued (trivially reachable via two ordinary send_turn calls) -- deterministically reproduced with no threading, and it inverts exactly the classification the implementer's report claims to have fixed. All 21 tests in tests/test_harness_claude_code_connector.py pass (including the 4 @requires_real_claude ones, since claude is on PATH), and tests/test_import_boundary.py passes, but that test only checks sqlite3/mcp import bans -- it says nothing about native-vocabulary leakage into domain decision logic, which does exist for steer degradation (see finding 4).

### codex

Ran the connector's own 15 tests (14 passed, 1 skipped) and confirmed the report's headline claims empirically: no polling (readline()/Queue.get() block, the only time.sleep() is in a test helper off the event path), no diff on the two frozen port files (git diff --stat is empty, both are absent from git status), and the 'sandbox must be a bare string, not the tagged object the JSON Schema shows' + 'thread/started has no top-level threadId' findings both reproduce against the real installed codex 0.144.6 binary (probed live against http://192.168.31.152:8123, never .222, writing only to a scratch CODEX_HOME). However the connector has a genuine, reproducible deadlock in the event path that the report does not disclose or test, plus three more verified defects: a normalized-kind misclassification that quietly breaks the observes_session_end capability, an unguarded subprocess.Popen() that leaks a raw exception instead of following the codebase's own OktoNexusError pattern (visible by diffing against the sibling harness_claude_code.py connector written for the same port), and a handshake-ordering bug that can permanently wedge the connector after one failed initialize. Two of these (the reader-thread wedge, the missing-binary leak) are exactly the failure-mode classes the task asked me to check and are absent from the implementer's test list.

---

## Cross-cutting analysis (added by the orchestrator, 2026-09-20)

Two defect CLASSES recurred across connectors written independently by different agents that
never saw each other's code. These are not isolated incidents and must be audited for in every
connector, including any added later.

### Class A — one-shot shutdown signalling / unbounded blocking waits

Occurrences: Codex (`events()` second consumer hangs), Pi (same, caught live as a 17-minute test
hang — see EV-REV-001 D-08).

A single `_SHUTDOWN` sentinel pushed once into a queue is consumed by whichever consumer calls
`get()` first; every later consumer blocks forever on an unbounded `Queue.get()`.

Standard fix (reference implementation: `adapters/outbound/harness/pi.py`): a `threading.Event`
for shutdown, checked on every `queue.Empty` from a BOUNDED `get(timeout=1.0)`. Any number of
callers, from any thread, observe shutdown within one poll period. The bounded timeout is NOT
event polling — events still arrive by push the instant they are queued; the bounded wait exists
only to recheck the shutdown flag.

### Class B — unguarded per-line dispatch in the reader thread

Occurrences: Codex (`_read_stdout` ~line 328), Claude Code stream-json (`_pump_stdout`).

The reader loop calls dispatch with no exception guard. A syntactically valid but
domain-invalid message raises, the exception unwinds the reader thread, and in the Codex case it
lands in an unguarded `finally` that calls `self._proc.wait()` with NO timeout while the child is
still healthy — so the thread blocks there forever, the shutdown sentinel is never pushed, and
stdout stops being drained, producing a pipe-fill deadlock.

Both connectors' existing malformed-input tests covered only `JSONDecodeError`, which IS caught.
The structurally-valid-but-domain-invalid class was untested in both.

Required in every connector: the per-message dispatch inside a reader loop is individually
guarded; a bad message is surfaced as an error event and the loop CONTINUES; the reader thread
can never exit without signalling shutdown; and no cleanup path contains an unbounded wait.

### Why this matters beyond these two bugs

Both classes share a failure signature: **the transport stops delivering events while appearing
alive.** No exception reaches the supervisor, no process dies, nothing is logged. The session
simply goes quiet forever.

That is the worst possible failure mode for this feature, because the entire Definition of Done
rests on push delivery. A connector that silently stops pushing is indistinguishable, from the
hub's perspective, from a harness that has nothing to say.

STANDING REQUIREMENT for all connectors: every blocking wait has a timeout and raises a clear
error on expiry; every reader loop guards per-message dispatch and continues; a reader thread
that exits for any reason MUST signal shutdown to every consumer. A wedged supervisor is worse
than a crashed one — a crash is observable and recoverable, a hang silently consumes a slot.

### Note on severity grading

The cc-socks `probe()` bare-`ValueError` finding (embedded NUL in `messagingSocketPath`) was
graded CRITICAL by the first review pass and MINOR by the re-run. This register reflects the
LATER grading. The remediation brief used the earlier, harsher framing, so the defect is being
fixed regardless; the discrepancy is recorded here rather than silently reconciled.
