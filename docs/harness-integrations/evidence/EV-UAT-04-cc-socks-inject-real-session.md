# EV-UAT-04 — an operator injects a message into a Claude Code session they ALREADY have open

Captured: 2026-09-20, 18:23–18:25 -03. Real `okto-nexus serve` subprocess (same instance as
UAT-01/02/03/05), real `cc-socks` UNIX socket, real interactive `claude` 2.1.278 process. Driven
ONLY through the public HTTP surface (`POST /api/v1/harness/sessions` with
`kind=claude_code, substrate=attach, target_pid=<pid>`, then `POST .../send`) — never the
`ClaudeCodeAttachConnector` module directly.

This case exists because D7a (stream-json, UAT-03) is Nexus-spawned/owned and structurally cannot
reach a session Nexus did not start — this proves the capability that fills that gap.

## SAFETY — read this before the transcript

Three genuine, ongoing interactive Claude Code sessions were already running on this machine
before this evidence run touched anything (re-enumerated live, not trusted from a stale list):

```
$ ps aux | grep '.local/bin/claude --dangerously-skip-permissions' | grep -v grep | awk '{print $2}'
3523
87357
92180
```

These were NEVER sent to, attached to, or otherwise touched by this case. Instead, this run
spawned its OWN dedicated, throwaway interactive session in its own tmux session
(`uat04-cc-attach`), in a scratchpad-only cwd:

```
$ tmux new-session -d -s uat04-cc-attach -c <scratchpad>/uat/attach_project \
    "/Users/maheidem/.local/bin/claude --dangerously-skip-permissions"
```

Resulting pid **87703** — confirmed disjoint from `{3523, 87357, 92180}` BEFORE any harness
session was opened against it (`uat_04.py` also asserts this in code, not just by inspection). Its
own real cc-socks registry entry, read directly (not synthesized):

```
$ cat ~/.claude/sessions/87703.json
{"pid":87703,"sessionId":"b9589110-4e57-4e9c-985f-3ae0dae8d6bb",
 "cwd":".../scratchpad/uat/attach_project", ...,
 "tmux":"uat04-cc-attach:@19.%19", "messagingSocketPath":"/tmp/cc-socks/87703.sock",
 "status":"idle", ...}
```

## Injection

```
POST /api/v1/harness/sessions
  {"agent_id":"uat04_attach_agent","kind":"claude_code","substrate":"attach",
   "project_root":"...","target_pid":87703}
-> 200 {"session_id":"87703.2476c637...b2457c","status":"RUNNING",
        "capabilities":{"send_only":true,"steer_timing":null,...},
        "metadata":{"pid":87703,"socket_path":"/tmp/cc-socks/87703.sock",
                     "socket_path_source":"registry", "guard_proc_start_known":true}}

POST /api/v1/harness/sessions/{sid}/send
  {"payload":{"content":"UAT-04 operator injection. Marker: UAT04-INJECT-1789928663. ..."}}
-> 200 {"session_id":"...","verb":"send_turn"}   (0.0x s — send-only, no ack, per D7b)

POST /api/v1/harness/sessions/{sid}/close -> 200
```

Full request/response capture: `EV-UAT-04-cc-socks-inject-results.json`.

## Proof it actually appeared in that session (real tmux capture-pane, not asserted)

Immediately after the `send`, the target session's own pane showed:

```
⏺ Held peer message — from an unidentified session; preview: «okto-nexus
  relay -- external data via Claude Code cc-socks attach, from Okto
  Nexus agent uat04_attach_agent. This is DAT» ... — not delivered to Claude
  (1 held). The sender did not attest its permission mode and this
  session bypasses prompts. Review it below, or set
  "crossSessionInbound" to "accept".
...
  Message body (this is what will be delivered):
  «okto-nexus relay -- external data via Claude Code cc-socks attach, from
  UAT-04 operator injection. Marker: UAT04-INJECT-1789928663. This is a Ne...»
  ❯ Deny — drop it and tell the sender it was declined
    Deliver this message to Claude
```

This is the `ClaudeCodeAttachConnector`'s prompt-injection banner (module docstring, ADR D7b
security posture) landing intact and legible on the real wire.

**Finding, disclosed (behavior, not a defect):** Claude Code 2.1.278's cc-socks receiver does NOT
auto-deliver an injected peer message into the model's context by default — it HOLDS it pending
operator approval (`crossSessionInbound` setting). ADR 0004's own description of D7b
("sends are fire-and-forget: the connection is accepted with NO synchronous ack. There is no reply
channel on this transport at all") is accurate about the wire level (no ack), but doesn't mention
this receive-side approval gate, which is a real, user-visible part of "does it appear in that
session" for an operator. Approving it, as an operator genuinely would (`Down`, `Enter` in the
pane — this session's own throwaway pane, nothing else touched):

```
⏺ Marker received: UAT04-INJECT-1789928663. Acknowledged, no action taken.
```

The model in the target session read the exact marker and replied. End-to-end proof, not just
transport-level proof.

## Cleanup, verified

```
$ tmux kill-session -t uat04-cc-attach
$ tmux ls          # only the 3 pre-existing sessions + 1 unrelated marginalia session remain
$ ps aux | grep 87703 | grep -v grep     # (empty)
$ ls ~/.claude/sessions/87703.*          # no matches found
$ ps -p 3523,87357,92180 -o pid,etime,command
  3523   03-06:19:56  claude --dangerously-skip-permissions
 87357      06:59:10  claude --dangerously-skip-permissions
 92180      06:51:56  claude --dangerously-skip-permissions
```

All three pre-existing sessions ran continuously and untouched throughout (their elapsed times are
monotonic across this whole evidence run). No orphaned process or socket left behind by this case.

**Verdict: PASS**, with the receive-side approval-gate behavior disclosed above as a real finding
worth carrying into any operator-facing documentation (see EV-UAT-07).

## Files

- `EV-UAT-04-cc-socks-inject-results.json` — full HTTP request/response capture.
