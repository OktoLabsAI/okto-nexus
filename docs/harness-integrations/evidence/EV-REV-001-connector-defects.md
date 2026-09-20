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
