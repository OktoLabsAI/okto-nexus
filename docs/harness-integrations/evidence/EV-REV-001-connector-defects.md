# EV-REV-001 — Adversarial review defect register (Phase 3)

Captured: 2026-09-20 10:31 -03
Source: Phase 3 workflow `wf_de1d2ad9-17f`, Verify stage
Status: OPEN — remediation required before these connectors are committed

## Why this file exists

Both connectors' own test suites PASSED (Codex 14/14, cc-socks 20/20) and `ruff` was clean.
An adversarial reviewer prompted to REFUTE correctness then reproduced seven real defects,
**none of which any passing test covered**. This is the concrete case for the project's DoD
rule that a green suite is not evidence of working software.

Both hard architectural gates HELD on both connectors:
- `polling_violation: false` — no polling, sleep-loop or status-request loop in either event path.
- `port_violation: false` — `git diff --stat` on `domain/harness.py` and `application/ports.py`
  is empty. The Phase 2 freeze survived four concurrent agents.

## D-01 CRITICAL — Codex: `end()` mid-turn strands events and leaks memory

`harness_codex.py` `_end()` pops `thread_id` from `_sessions_by_thread` synchronously, but the
in-flight turn keeps emitting `turn/started`, `item/*` and `turn/completed` for that thread.
`_emit_for_thread` treats any unmapped thread_id as the "thread/started raced the response" case
and buffers into `_unmapped_thread_events`, a dict drained ONLY when that exact thread_id is
re-registered — which never happens, because thread ids are never reused.

Reproduced 3/3 runs: `send_turn` then `end()` leaves 5 events permanently stranded
(`turn/started`, `item/started`, `item/agentMessage/delta`, `item/completed`, `turn/completed`).

Impact: a supervisor calling `end()` when it no longer needs a session — an ordinary sequence —
never observes that turn's completion, and every such session leaks one dict entry for the life
of the process. Unbounded growth in a long-lived multiplexing connector.

## D-02 CRITICAL — cc-socks: `probe()` raises where it documents that it cannot

`claude_code_attach.py` `_resolve_socket_path` builds `Path(registry['messagingSocketPath'])`
straight from the registry JSON. An embedded NUL makes `os.stat()` and `sock.connect()` raise
`ValueError`, which is NOT a subclass of `OSError` and so escapes the surrounding
`except OSError` blocks.

Reproduced against the live code with `"messagingSocketPath": "/tmp/cc-socks/evil\x00.sock"`:
`probe()` raises `ValueError: stat: embedded null character in path`, and `start()` raises the
same bare exception instead of `OktoNexusError`.

Impact: directly violates this module's own contracts — `probe()` promises "Never raises: every
failure mode becomes a structured, negative ProbeResult so a supervisor can poll this on a
schedule without a try/except", and the module promises every public entry point fails with an
actionable `OktoNexusError`, "never a bare exception". A supervisor trusting either contract
crashes. This is squarely the malformed-data failure mode the review was asked to probe.

## D-03 MAJOR — Codex: failed handshake permanently bricks the connector

`_spawn_and_initialize` sets `self._transport = transport` BEFORE calling
`transport.request(initialize)`. If that raises, `_transport` stays non-None while `_initialized`
stays False — and `_initialized` is write-only dead state, never read anywhere. `start()`'s guard
is `if self._transport is None`, so it never retries the handshake.

Reproduced: one timed-out `initialize` leaves every subsequent `start()` on that connector timing
out against a still-uninitialized connection, forever. The child process from the failed attempt
is also left running; only `close()` reaps it, and `close()` is not part of the
`HarnessConnector` Protocol, so a supervisor written against the port has no reason to call it.

## D-04 MAJOR — Codex: second `events()` call after shutdown hangs forever

`close()` and `_on_child_exit()` each push exactly ONE `_SHUTDOWN` sentinel. `events()` returns
when it consumes it — so the first generator consumes the sentinel and any second consumer blocks
on `get()` indefinitely.

Reproduced: after `close()`, the first `list(conn.events())` returns cleanly; a second `events()`
from another thread never joins. Nothing in the Protocol or the docstrings says `events()` is
single-shot. A supervisor that re-subscribes after detecting a stall hangs with no exception and
no log line.

## D-05 MINOR — cc-socks: `probe()` and `start()` validate in different orders

`probe()` checks `peerProtocol` before `_find_key_file()`; `start()` reads the key file first.
For a session with BOTH a protocol mismatch and a missing key file, `probe()` reports
`protocol_mismatch` while `start()` would raise NOT_FOUND / CONFIG_ERROR. A diagnosis that does
not match what the real call does undermines probe's stated purpose of detecting breakage before
the next real send.

## D-06 MINOR — cc-socks: the riskiest path is the untested one

`_computed_socket_path` is a pure function of `(pid, env)` — trivially testable. Only the
"XDG_RUNTIME_DIR set, short path" branch has coverage. Neither the unset branch (the exact shape
EV-CC-001's live capture shows) nor the >103-byte fallback is tested. The implementer's own
report flagged this function as its riskiest interpretation choice, and it shipped with zero
direct verification of the two branches in question.

## D-07 MINOR — cc-socks: pid-reuse guard's realistic case is untested

`_check_no_pid_reuse` re-reads `self._key_path`. In the realistic recycling shape — the original
key file is simply gone — that raises NOT_FOUND, is swallowed by `except OktoNexusError: return`,
and the guard silently no-ops. It currently still fails safe only because `_current_token()`
independently re-reads the same absent path immediately after, but nothing tests or asserts that
coincidence.

## D-08 CRITICAL (FIXED 2026-09-20) — Pi: second `events()` call deadlocks forever

Caught in the act: the Pi connector's own test suite HUNG for 17 minutes. Diagnosed from outside
the agent's process — PIDs 11321/11323/11325 sat with zero output and, decisively, NO
`pi --mode rpc` child was alive, proving the wait was internal rather than a slow subprocess.

Root cause: `PiRpcConnector.events()` used an UNBOUNDED `queue.Queue.get()` terminated by a
single-consumption `_SHUTDOWN` sentinel pushed once by `close()`. A test called `events()` twice
(a pump thread plus a direct `list(...)`). The first generator consumed the only sentinel; the
second blocked forever with nothing left to wake it.

Fix: replaced the sentinel with a `threading.Event` (`_closed_event`), checked on every
`queue.Empty` from a BOUNDED `Queue.get(timeout=1.0)`. Any number of callers, any number of
calls, from any thread now observe shutdown within one poll period. Also changed
`_PiTransport.request()`'s lock acquisition from a bare `with` to `acquire(timeout=timeout_s)`
raising INTERNAL_ERROR on expiry, so it is no longer merely transitively bounded by another
caller's timeout.

Verified: `timeout 120 uv run python -m pytest -q tests/test_harness_pi_connector.py`
-> 17 passed, 1 skipped, stable across 5 repeated runs (1.4-1.5s each). `ruff` clean.

**NOT a polling violation.** The 1s timeout is a bounded liveness recheck of the shutdown flag,
not event polling — events are still delivered by push the instant they are queued. This
distinction is recorded here so a later reviewer does not misread it as a DoD breach.

## CROSS-CUTTING FINDING — the single-consume sentinel is a recurring defect class

**D-04 (Codex) and D-08 (Pi) are the SAME BUG, written independently by two different agents.**
Both used a one-shot sentinel object to signal shutdown through a queue, and both therefore hang
forever on a second consumer. cc-socks avoids it only incidentally, by draining a bounded deque
rather than blocking on a queue.

This is a defect CLASS, not two incidents. Remediation must:
1. Audit EVERY connector (including `claude_code` stream-json, not yet reviewed) for one-shot
   shutdown signalling and for ANY unbounded blocking wait.
2. Standardise on Pi's pattern: a `threading.Event` for shutdown plus bounded waits everywhere.
3. Add, per connector, a test that calls `events()` twice and asserts the second call returns
   rather than hangs — with an explicit test timeout so a regression fails in seconds instead of
   wedging CI.

Standing requirement for all four connectors: **every blocking wait has a timeout and raises a
clear error on expiry.** A wedged supervisor is worse than a crashed one — a crash is observable
and recoverable, a hang silently consumes a slot forever.

## Related limitation (not a defect — protocol reality)

cc-socks `send()` treats a clean socket write as delivery success and transitions to RUNNING.
Because the transport is genuinely ack-less (EV-CC-001), a stale token or a peer that accepts then
closes on a bad auth line is indistinguishable from success. The test suite's fake server
unconditionally accepts every connection, so no test could fail if `send()`'s success were
meaningless. This cannot be fully fixed at the connector — but it MUST be tested for, and
"send() did not raise" must never be documented as proof of delivery.

## Remediation requirement

Every defect above is fixed AND covered by a test that fails against the current code before the
connector is committed. A fix without a regression test does not close a finding here.
