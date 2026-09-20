# EV-SYS-008 — SYS-08: one harness child dying does not take down the hub or the other harnesses

Real `SIGKILL` sent to the REAL immediate child process the pi connector owns pipes to (the
`bin/pi` PATH shim — see EV-SYS-002 for why the connector's `Popen` target IS the shim process;
killing it breaks the connector's stdin/stdout pipe exactly as a real `pi` binary crash would
present, since the shim's own further child, the real `/opt/homebrew/bin/pi`, is invisible to
Nexus either way).

`sys08_isolation.py` is scratchpad-only (never committed, same convention as the other SYS
evidence files) — its real captured output is inlined below.

```
$ timeout 120 uv run python sys08_isolation.py
pi shim (real connector child) pid = 61688
GET /api/v1/info before kill: 200
SIGKILL sent to 61688 at wall=1789927547.924971
pi shim still alive 1s after SIGKILL: False (expected False)
GET /api/v1/info after kill: 200
pi session status after its child died: ENDED
sibling codex send after pi died: status=200
sibling cc_stream send after pi died: status=200
siblings completed their post-kill turn: {'codex': True, 'cc_stream': True}

Written sys08_result.json

SYS-08 PASS
```

- The hub (`GET /api/v1/info`) answered 200 both before AND after the kill — never went down.
- BOTH surviving harnesses (codex, claude_code/stream) were sent a **fresh, real trivial turn**
  AFTER pi's child died, and both completed normally (verified via durable `turn_completed`
  events, not just a 200 on the send call) — genuine proof of isolation, not merely "the process
  didn't crash."
- The pi session itself transitioned out of `RUNNING` once its child died, as expected.

## One disclosed observation (not a SYS-08 failure — the case only asks that siblings/hub
survive, which they did)

The pi session's final status came back `ENDED`, not `ERRORED`. Reading
`HarnessSupervisor._pump`/`_reap`: the reader thread's `for event in connector.events(): ...`
loop, on a `SIGKILL`'d child, sees a clean EOF on the pipe rather than a raised exception, so the
generator simply returns and `_reap(session_id, error=None)` runs — the same code path an
intentional, graceful session end takes. A child that dies unexpectedly and a child that is asked
to end therefore currently produce the SAME terminal status from the supervisor's point of view,
which could make an unexpected pi crash harder to distinguish from a normal close by a caller
reading only `harness_get`'s `status` field. Reported as a disclosed nuance in the same spirit as
EV-SYS-001's F-01/F-02, not asserted as a SYS-08 defect — the case's actual requirement
(hub + siblings survive) held.

Full raw result (including the exact final session record and sibling send/completion evidence):
`EV-SYS-008-isolation_result.json`, `EV-SYS-008-pi_final_session.json`.

**Verdict: SYS-08 PASS**, with the `ENDED`-vs-`ERRORED` nuance disclosed above.
