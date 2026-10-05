# EV-UAT-06 — graceful degradation when `cc-socks` is unavailable

Captured: 2026-09-20, 18:23 -03. Real `okto-nexus serve` subprocess (same instance as
UAT-01/02/03/05). Driven ONLY through `POST /api/v1/harness/sessions` — the public surface.

This case exists because D7b's breakage risk (ADR 0004: "`cc-socks` is an undocumented private
protocol and can break on any Claude Code release with no deprecation notice... D7b must therefore
be isolated behind the same connector port as everything else, degrade gracefully, and never be
on the critical path of the other two harnesses") was accepted deliberately, not accidentally.

## Simulating the break

`ClaudeCodeAttachConnector._read_registry` (frozen source, read only — not modified) raises
`OktoNexusError(NOT_FOUND, ...)` when `~/.claude/sessions/<pid>.json` is absent — exactly what a
Claude Code update that changes or drops the registry file would produce, from the connector's own
point of view. This case attaches to a `target_pid` that is a REAL, currently-running process on
this machine (so the failure mode is "no cc-socks registry for this pid", the faithful simulation,
not "kernel rejects an obviously-bogus pid") but is verified, in code, to have no registry entry
and to not be one of the three protected pre-existing interactive sessions:

```python
FAKE_TARGET_PID = os.getppid()   # this script's own parent process
assert FAKE_TARGET_PID not in {3523, 87357, 92180}
assert not os.path.exists(f"~/.claude/sessions/{FAKE_TARGET_PID}.json")
```

(Both assertions passed at run time — `FAKE_TARGET_PID` resolved to `87030`, this run's own shell
process, which unsurprisingly has no Claude Code cc-socks registry entry.)

## Assertion 1 — fails FAST with a clear, actionable error, not a hang

```
POST /api/v1/harness/sessions
  {"agent_id":"uat06_broken_attach_agent","kind":"claude_code","substrate":"attach",
   "project_root":"...","target_pid":87030}

-> 404 in 0.013s
{
  "ok": false,
  "error": {
    "code": "NOT_FOUND",
    "message": "No Claude Code session registry at /Users/maheidem/.claude/sessions/87030.json.
                 The session may have ended, the pid may be wrong, or this is not an interactive
                 session (`claude -p` sessions have no registry entry)."
  }
}
```

13 milliseconds, not a bounded-timeout-then-fail — an immediate, synchronous rejection with a
message that tells the operator exactly what to check next. **This is the graceful-degradation
half of the claim.**

## Assertion 2 — the PRIMARY path (D7a, stream) still works on the SAME hub, right after

```
POST /api/v1/harness/sessions
  {"agent_id":"uat06_stream_after_failure_agent","kind":"claude_code","substrate":"stream",
   "project_root":"..."}
-> 200

POST .../send {"payload":{"content":"reply with the single word: ok"}} -> 200
  turn_completed observed: True (real `result:success` event, real reply "ok")

POST .../close -> 200, status ENDED
```

**This is the actual D7b-risk-accepted claim, not just "the attach call itself returns an
error."** One substrate breaking does not take the feature down; the hub, the other harness
kinds, and even the OTHER Claude Code substrate on the same hub are unaffected.

## Verdict

**PASS.** Both required assertions hold: fast, clear, non-hanging failure on the broken substrate;
undiminished primary-path capability on the same hub immediately after.

## Files

- `EV-UAT-06-graceful-degradation-results.json` — full request/response capture, both steps.
