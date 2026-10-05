# EV-UAT-01/02/03 — an operator attaches Pi / Codex / Claude Code and holds a real two-turn conversation

Captured: 2026-09-20, 18:17–18:24 -03. One real `okto-nexus serve` subprocess, own ephemeral
port (`56338`), own home dir, driven ONLY through the PUBLIC HTTP surface
(`POST /api/v1/harness/sessions`, `POST .../send`, `GET .../events`, `GET .../{id}`,
`POST .../close`) — never the `HarnessSupervisor` or connector modules directly. No
TestClient, no mocks, no fakes. Real `pi` 0.85.1, real `codex` 0.144.6 (LAN box
`192.168.31.152:8123`), real `claude` 2.1.278 binaries.

Driver: `uat_01_02_03.py` (scratchpad-only, not committed, same convention as
EV-SYS-003/EV-CX-001 — the real captured output is the artifact, inlined below and in
`EV-UAT-0{1,2,3}-*-results.json` / `EV-UAT-0{1,2,3}-*-wire-trace.log`, both committed).

## Why "two-turn conversation" needed a specific proof shape

`harness_send` never blocks for a reply (D1 — push, not poll, is the whole point of this
feature). So an OPERATOR holding a conversation is, structurally: `send` → wait for
`turn_completed` to show up (via `GET .../events`, a **durable replay read**, not part of the
delivery path — SYS-05 already proved delivery itself is push) → `send` again. Turn 2's prompt
word deliberately differs from turn 1's (`ok` then `two`) so the transcript proves turn 2 is a
fresh reply, not turn 1 replayed. Both turns landed inside the SAME session/thread — proving one
open session really holds a multi-turn conversation, not two independent one-shots.

Note on the poll loop in the driver: this is test/operator-side **observation** of a durable log,
explicitly not the system's own delivery mechanism (delivery push semantics are SYS-05's claim,
not this case's). Calling that out here so this file is never misread as contradicting SYS-05.

## Safety scaffold (verified BEFORE any binary spawn)

Per the composition-root gap already reported in `EV-SYS-002-boot-and-registration.md`
(`harness_open` has no backend-selection param, so an unshimmed `kind="pi"` session inherits
`~/.pi/agent/settings.json`'s `defaultProvider: "local-mac"` → `192.168.31.222`, off-limits),
this run rebuilt the same external-only workaround, independently, scoped to its own server
subprocess's env — not touching any source file, not touching `~/.pi/agent/settings.json`,
`~/.codex/config.toml`, or the operator's shell PATH:

- A PATH shim directory (`uat/bin/{pi,codex,claude}`) prepended to `PATH` in the
  `okto-nexus serve` subprocess's env only. `bin/pi` injects `--provider zai --model glm-5.3`
  ahead of the connector's own argv and relays both directions to a per-run trace log; `bin/codex`
  and `bin/claude` are pure tee (no argv injection needed — see below).
- `CODEX_HOME=uat/codex_home` (a scratch `config.toml` pointing at the LAN box,
  `model_provider="lanqwen"`, `base_url="http://192.168.31.152:8123/v1"`, `wire_api="responses"`)
  + `LANQWEN_API_KEY=unused`, inherited automatically by the codex connector's transport
  (confirmed by reading `adapters/outbound/harness/codex.py`: `full_env = os.environ.copy()`
  when no explicit `env=` override is passed).

**Re-verified per spawn, not assumed once, machine-checked across the WHOLE run** — `bin/pi` opens
its trace log in append mode, so `EV-UAT-01-pi-wire-trace.log` accumulates every real `pi` spawn
across this entire evidence run (UAT-01's session here, plus the three later `pi` sessions opened
for UAT-05's part A/B probe — see `EV-UAT-05-target-grammar-asymmetry.md`), not just this file's
own case:

```
$ grep -c "SHIM_ARGV" EV-UAT-01-pi-wire-trace.log
4
$ grep "SHIM_ARGV" EV-UAT-01-pi-wire-trace.log | grep -c "'--provider', 'zai'"
4
```

All 4 real `pi` spawns in this run carried `--provider zai` — zero unshimmed spawns, checked by
count, not by eyeballing one line. `.222` never received any inference from this evidence run.

## UAT-01 — Pi, two-turn conversation

```
POST /api/v1/harness/sessions {"agent_id":"uat_pi_agent","kind":"pi","project_root":"..."}
-> 200 hsess_b6d14a766ee84d7785ebe0770f0b072f

turn 1: POST .../send {"payload":{"text":"reply with the single word: ok"}}   -> 200
        turn_completed observed after 5.378s (49 polls of the durable event log)
turn 2: POST .../send {"payload":{"text":"reply with the single word: two"}}  -> 200
        turn_completed observed after 7.640s (68 polls)

POST .../close -> 200, status ENDED
```

Actual model replies, read straight from the persisted `turn_completed` event payload
(`EV-UAT-01-pi-two-turn-results.json`):

- Turn 1 (`native_event: turn_end`): `{"role":"assistant","content":[{"type":"text","text":"ok"}],"provider":"zai","model":"glm-5.3",...}`
- Turn 2 (`native_event: turn_end`): `{"role":"assistant","content":[{"type":"text","text":"two"}],"provider":"zai","model":"glm-5.3",...}`

Same session, two distinct real replies from the real zai/glm-5.3 backend. **Verdict: PASS.**

## UAT-02 — Codex, two-turn conversation

First attempt (not reported as a defect — see below) returned `500 INTERNAL_ERROR "codex
app-server did not answer 'initialize' within 30.0s"` after exactly the argv
`['/opt/homebrew/bin/codex', 'app-server']` was sent and the shim observed `codex` itself exit
with code 1 in 0.053s — an instant config-load failure, not a hang or a network-reachability
problem (`curl http://192.168.31.152:8123/v1/models` answered `200` throughout). Root cause: this
run's own `CODEX_HOME` scratch directory had the `LANQWEN_API_KEY`/`PATH` env vars wired but no
`config.toml` written into it yet — a scaffolding gap in this evidence run's own setup script, not
a codex/connector defect. Fixed by writing the same `config.toml` shape EV-SYS-002/the codex INT
agent already validated (`model_provider="lanqwen"`, `base_url="http://192.168.31.152:8123/v1"`,
`wire_api="responses"`) into that directory; the running server subprocess picked it up on the
NEXT spawn with no restart needed (codex reads its own config per-invocation).

Re-run, real result:

```
POST /api/v1/harness/sessions {"agent_id":"uat_codex_agent","kind":"codex","project_root":"..."}
-> 200 (open ok)

turn 1: send {"payload":{"text":"reply with the single word: ok"}}  -> 200
        turn_completed observed after 10.327s (93 polls)
turn 2: send {"payload":{"text":"reply with the single word: two"}} -> 200
        turn_completed observed after 10.907s (97 polls)

POST .../close -> 200, status ENDED
```

Actual model replies, from the real `item/completed` (`agentMessage`) events, SAME `threadId`
(`01a0c00b-e473-7ff0-b7ed-63c3c968da7e`) both turns:

- Turn 1: `{"type":"agentMessage","text":"ok",...}` then `turn/completed`
- Turn 2: `{"type":"agentMessage","text":"two",...}` then `turn/completed`

One JSON-RPC 2.0 `app-server` connection, one thread, two real turns, two distinct real replies
from the LAN box's `qwen3.8-flash`. **Verdict: PASS** (with the honest scaffolding-bug note
above — re-run once, in isolation, root-caused before re-running, per the task's "3x before
calling it a defect" rule; this was diagnosed as this run's own setup error on the first try, so
no further reruns were needed to distinguish contention from a real defect).

## UAT-03 — Claude Code (stream-json, D7a), two-turn conversation

```
POST /api/v1/harness/sessions
  {"agent_id":"uat_cc_stream_agent","kind":"claude_code","substrate":"stream","project_root":"..."}
-> 200 (open ok)

turn 1: send {"payload":{"content":"reply with the single word: ok"}}  -> 200
        turn_completed observed after 2.830s (27 polls)
turn 2: send {"payload":{"content":"reply with the single word: two"}} -> 200
        turn_completed observed after 1.594s (15 polls)

POST .../close -> 200, status ENDED
```

Both turns landed on the SAME stable `session_id` (`c98e0960-4d9c-4f62-9f0f-82d026ae01a3`,
read from the `result:success` event payload each time). Real replies, from the persisted
`output_delta`/`assistant` events: turn 1 `"text":"ok"`, turn 2 `"text":"two"`. Model used:
`claude-opus-5` (the substrate's own auth, per D7a — no backend override needed).

One process held across two turns, stable session id, both answered — reproducing the exact D7a
claim from ADR 0004 as a real operator action through the public surface rather than a
unit/spike test. **Verdict: PASS.**

## Cleanup

All three sessions closed (`status: ENDED`) via `POST .../close` before the server was torn down.
Server subprocess was SIGTERM'd cleanly at the end of the whole UAT run (this same server instance
served UAT-01 through UAT-05 — see those files):

```
$ python3 -c "os.killpg(80070, SIGTERM); ..."   # server pid 80070
exited cleanly

$ ps aux | grep -E "pi-coding-agent|codex-cli|bundle/cli.js" | grep -v grep
(zero matches — no orphaned harness children)

$ ps -p 3523,87357,92180 -o pid,etime,command
 3523  03-06:23:12  claude --dangerously-skip-permissions
87357     07:02:26  claude --dangerously-skip-permissions
92180     06:55:12  claude --dangerously-skip-permissions
```

The three genuine pre-existing interactive sessions ran continuously (monotonically increasing
elapsed time) across this whole evidence run and were never touched by it.

## Files

- `EV-UAT-01-pi-two-turn-results.json`, `EV-UAT-01-pi-wire-trace.log`
- `EV-UAT-02-codex-two-turn-results.json`, `EV-UAT-02-codex-wire-trace.log`
- `EV-UAT-03-claude-stream-two-turn-results.json`, `EV-UAT-03-claude-stream-wire-trace.log`
