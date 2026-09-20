# EV-UAT-05 — addressing a harness through the EXISTING target grammar

Captured: 2026-09-20, 18:21–18:22 -03. Real `okto-nexus serve` subprocess (same instance as
UAT-01/02/03/04). Driven as an operator, over the real Streamable-HTTP `/mcp` mount (real
`message_create` MCP tool call, real `mcp.ClientSession`) plus the real HTTP surface — never the
supervisor or a connector directly.

**Verdict: FAILED, as the case is literally worded.** UAT-05 asks whether "an operator addresses a
harness through the EXISTING target grammar... rather than a harness-specific API" — that is an
INPUT-direction claim (operator → harness), and it is false: `message_create` reports success
while never reaching the connector. `EV-SYS-003-target-grammar-gap.md` already empirically
falsified this and flagged it forward to whoever ran UAT; this case reproduces that falsification
independently (own agents, own fresh session, own run — not borrowed).

This case also went one step further and tested the OUTPUT direction, because `harness_open`
accepts a `notify_target` parameter using the identical target-grammar shape, and
`harness_supervisor.py`'s own source (`_deliver_notable_message`) says notable events are
delivered through it. That half is NOT falsified — it genuinely works, on the real wire. This is
reported below as a real, useful secondary finding, but it does not change the case's verdict:
the case asks about addressing (input), not notification (output), and the plain reading fails.

**The accurate statement is asymmetric**: the target grammar reaches a harness's OUTPUT (turn
completions, errors) but not its INPUT (an operator cannot address a harness with
`message_create`/`direct`/`capability`/`role`/`tag` the way they would any other agent). D2/D3's
registration gives the harness a real identity in the agent registry (confirmed, `GET
/api/v1/agents/uat05_pi_agent` returns `metadata.harness_kind:"pi"` — not shown again here, already
proven in EV-SYS-002), but that identity is currently a *sender* addressable-by-grammar for its
own output, not a *recipient* reachable-by-grammar for input. "First-class agent" is true for one
direction and not yet true for the other.

## Setup

Fresh pi session opened specifically for this case (not reusing UAT-01's already-closed one, so a
negative result can't be blamed on "well, the session wasn't live anyway"), WITH an explicit
`notify_target` pointed at a plain, non-harness observer agent:

```
POST /api/v1/agents {"agent_id":"uat05_observer"}   -> 200 (plain, non-harness agent)
POST /api/v1/agents {"agent_id":"uat05_operator"}   -> 200, api_key: nxs_605d33bb... (for /mcp auth)

POST /api/v1/harness/sessions
  {"agent_id":"uat05_pi_agent","kind":"pi","project_root":"...",
   "notify_target":{"strategy":"direct","agent_id":"uat05_observer"}}
-> 200 hsess_0ac2a3d7afb44ac6b347af88b091e765
```

(Discovered empirically along the way: the REST surface is `trust_mode: open` and needs no
auth, but the `/mcp` Streamable-HTTP mount does — a first attempt with no `Authorization` header
got a real `401 Unauthorized`. Registering an operator agent and using its `nxs_` key as a Bearer
token, exactly as EV-SYS-003 did, fixed it.)

## Part A — INPUT direction: does `message_create` reach the harness?

```python
await session.call_tool("message_create", {
    "project_root": ..., "from_agent_id": "uat05_operator",
    "subject": "UAT-05 target-grammar INPUT probe",
    "body": "reply with the single word: ok",
    "target": {"strategy": "direct", "agent_id": "uat05_pi_agent"},
})
```

Result: `{"ok": true, "data": {..., "delivered_count": 1, "recipients": ["uat05_pi_agent"]}}` —
the message layer reports success, exactly as it would for any ordinary agent.

The pi child's own wire trace — `EV-UAT-01-pi-wire-trace.log` (the log is cumulative/append-mode
across this whole evidence run: it holds all 4 real `pi` spawns, UAT-01's plus the 3 opened for
this case's parts A/B, so the before/after line counts below are read as a delta within that one
growing file, not from a per-case-fresh file): **zero new bytes** in the seconds around the
`message_create` call (`part_a_wire_trace_before` == `part_a_wire_trace_after`,
`part_a_new_wire_activity: false`). The message never reached `PiRpcConnector.send`.

Where it actually went — `GET /api/v1/messages?agent=uat05_pi_agent&include_body=true` (run
AFTER this file's first pass revealed the `undelivered=true` filter checks a different status
field than expected — see the honesty note below): the message sits as `msg_11ae590d...`,
`status: "unread"`, `body: "reply with the single word: ok"` — an ordinary, undelivered-to-harness
inbox row, identical in kind to `EV-SYS-003`'s finding.

**Part A verdict: matches EV-SYS-003 exactly, reproduced independently. Target-grammar INPUT to a
harness does not work.**

## Part B — OUTPUT direction: does a harness's own activity reach the target grammar?

```
POST /api/v1/harness/sessions/{sid}/send {"payload":{"text":"reply with the single word: notify"}}
-> 200
```

Polled the OBSERVER's ordinary inbox (`GET /api/v1/messages?agent=uat05_observer`, no special
harness-aware call — the exact same read path any operator would use for any agent's mail):

```json
{
  "message_id": "msg_ae894fab4f8944c28803f43dd1660e01",
  "from_agent_id": "uat05_pi_agent",
  "subject": "harness pi session hsess_0ac2a3d7afb44ac6b347af88b091e765: turn_completed",
  "target": {"strategy": "direct", "agent_id": "uat05_observer"},
  "body": "{\"native_event\": \"turn_end\", \"payload\": {..., \"message\": {\"role\": \"assistant\", \"content\": [{\"type\": \"text\", \"text\": \"notify\"}], \"provider\": \"zai\", \"model\": \"glm-5.3\", ...}}, ...}"
}
```

A second message (`msg_b574b277...`, `native_event: agent_settled`) arrived the same way. Both
messages: sent BY the harness's own registered agent (`uat05_pi_agent`), addressed via
`{"strategy":"direct","agent_id":"uat05_observer"}` — the identical target-grammar shape
`message_create` uses — and readable through the plain, harness-unaware `GET /api/v1/messages`
route. The observer never called anything harness-specific.

**Part B verdict: genuine PASS.** The `notify_target` parameter on `harness_open` really does put
a harness's activity onto the existing target grammar, exactly as `harness_supervisor.py`'s
`_deliver_notable_message` docstring (D10) describes: `{"strategy":"broadcast"}` is the default
when `notify_target` is omitted; any grammar shape is honored when supplied.

## Honesty note on the driver script's own bug (not a defect, disclosed for transparency)

The driver's live-run inbox check for Part A used `GET .../messages?agent=...&undelivered=true`,
printing `total: 0` and reporting it as "message sat in pi agent's ordinary inbox: False" during
the run. That query param (`undelivered_only`, filtering on delivery `status`) is a DIFFERENT
signal than "unread" — the message actually IS present (`status: "unread"`), just not flagged
`undelivered` by that particular filter. Re-checked with `include_body=true` and no filter
immediately after (see above) — the message is genuinely there. This did not change Part A's
verdict (the wire-trace zero-new-bytes proof is the load-bearing evidence, and it never depended
on the inbox filter), but is disclosed here rather than silently corrected, per the task's
evidence-honesty rule.

## Cleanup

`POST .../close -> 200, status ENDED` before teardown.

## Files

- `EV-UAT-05-target-grammar-results.json` — full request/response capture, both parts.

## Addendum — INPUT-direction addressing now works

Part A's verdict above (operator → harness addressing via the target grammar is FAILED, as
worded) is left unchanged: it was correct at the time it was captured. A follow-up build closed
the underlying gap (same root cause as SYS-03) in the same working tree; see
`EV-SYS-003-FOLLOWUP-target-grammar-fix.md` for the fix and a live re-run reversing this result.
Part B's finding (OUTPUT-direction delivery via `notify_target` genuinely works) is unaffected
either way and stands as originally captured.
