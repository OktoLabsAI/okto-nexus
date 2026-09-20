# EV-SYS-003 — SYS-03: hub → harness routing via the EXISTING target grammar

`sys03_target_grammar_check.py` is scratchpad-only (never committed), matching the EV-CX-001/
EV-PI-INT-001 convention — the driver script isn't the artifact, its real captured output is
(inlined below and in the committed raw-result files it wrote).

**Verdict: SYS-03 FAILED, as literally worded.** The plan's wording is "a message routed via the
EXISTING target grammar reaches each harness." The existing target grammar
(`direct`/`capability`/`role`/`tag`, resolved by `message_create`, ADR 0001) does **not** reach a
harness. What actually reaches a harness is a different, direct-session-id-addressed mechanism
(`harness_send`/HTTP `POST /harness/sessions/{id}/send`), demonstrated working in
`EV-SYS-004-005-009` under "what exists instead" below. This is not a softened partial pass —
the specific claim in the case text is false, and the same claim underlies UAT-05
("harnesses are first-class agents, not a bolted-on side channel... addressed... through the
target grammar"), which this finding also undercuts; flagged here for whoever runs UAT.

## Static evidence: the only callers of `HarnessSupervisor.send`

```
$ grep -rn "supervisor.send(\|\.send(session_id" src/okto_nexus --include="*.py" | grep -v test
src/okto_nexus/adapters/inbound/http/routes.py:918:  supervisor.send(session_id, "send_turn", payload)
src/okto_nexus/adapters/inbound/http/routes.py:934:  supervisor.send(session_id, "steer", payload)
src/okto_nexus/adapters/inbound/http/routes.py:950:  supervisor.send(session_id, "interrupt", payload)
```

Plus the MCP tool mirror (`tools/harness.py:565-598`, same three verbs). **All six call sites
address a session by its `session_id`, resolved from the HTTP path / tool argument directly.**
None reads an inbox, none resolves a target against the agent registry, none is reachable from
`message_create`. There is no code path, anywhere in `src/`, from the target-grammar resolver
(`domain/targets.py` + `MessageService.create_message`'s recipient resolution) into
`HarnessSupervisor.send`.

## Empirical falsification (real server, real pi child, real message_create call)

Registered a fresh probe agent (`POST /agents`) to get a real `nxs_` key, then called the REAL
`message_create` MCP tool over the running hub's actual Streamable-HTTP `/mcp` mount (not a
TestClient — the same process SYS-01/02 booted), addressed directly at the pi harness's own
registered agent:

```
$ timeout 40 uv run python sys03_target_grammar_check.py nxs_<redacted>
# key came from `POST /agents {"agent_id":"sys_grammar_probe"}` moments earlier in this same
# run - a throwaway credential in an ephemeral, since-torn-down home dir/DB, redacted here as a
# hygiene practice rather than because it carries any standing access.
message_create result:
{
  "ok": true, "data": {
    "message_id": "msg_cd75d5b7118b4cd5afec032cf1c0c55c",
    "from_agent_id": "sys_grammar_probe",
    "target": {"strategy": "direct", "agent_id": "sys_pi_agent"},
    "body": "reply with the single word: ok",
    "recipients": ["sys_pi_agent"],
    "delivered_count": 1,
    "workspace_created": true
  }
}

pi wire trace lines: before=17 after=17
NEW_WIRE_ACTIVITY: False (expected False - the target-grammar message never reaches the connector)

GET /api/v1/messages?agent=sys_pi_agent&undelivered=true -> 200
{"ok": true, "data": {"items": [], "page": 1, "page_size": 50, "total": 0}}
```

The message layer (ADR 0001) reports success — `delivered_count: 1`, `recipients:
["sys_pi_agent"]` — this is genuine, correct ordinary-inbox delivery, exactly as it would behave
for any non-harness agent. But the **pi child process's own wire trace gained zero new bytes**
(17 lines before, 17 after — same file, same count, byte-identical) in the seconds around the
call. The message was never translated into a `HarnessCommand` and never reached
`PiRpcConnector.send`. "Delivered" here means "written to the recipient's ordinary inbox row,"
not "reached the harness transport" — those are different claims and the plan's SYS-03 wording
conflates them.

## What exists instead (demonstrated working — see EV-SYS-004-005-009)

Direct session-id addressing (`POST /harness/sessions/{session_id}/send`) DOES reach every
full-duplex harness, with a real wire-level round trip, no client polling in the delivery path,
and correct per-session demultiplexing under concurrent load. That is a real, working,
well-isolated mechanism — it is simply a *different* addressing scheme than "the existing target
grammar" the case names, and a caller needs the harness's `session_id` (returned once, by
`harness_open`) rather than its `agent_id` to use it.

---

## Addendum — the gap this file documents is now CLOSED

This file's verdict (FAILED, as worded, at the commit under review) is left unchanged above: it
was a correct, evidence-backed finding at the time it was captured. A follow-up build closed the
gap in the same working tree, with its own failing-first evidence and a live re-run of this exact
check reversing the result (real wire activity this time). See
`EV-SYS-003-FOLLOWUP-target-grammar-fix.md` for the fix and its evidence; that file also carries
forward this file's finding as the reproduction baseline rather than re-deriving it.
