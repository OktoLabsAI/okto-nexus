# pi 0.85.1 `--mode rpc` protocol reference (verified live, 2026-09-20)

Model used: **zai/glm-5.3** (`--provider zai --model glm-5.3`), sourced via
`ZAI_API_KEY`/`ZAI_BASE_URL` from okto-nexus `.secrets/harness.env`. `local-mac` in
`~/.pi/agent/settings.json` was NOT used — checked first, `local-mac` maps to the
`.222` box, which is off-limits (multi-day benchmark). No inference was sent to
`.222`. `.152:8123` was not needed since glm-5.3 worked cleanly.

All claims below are backed by raw captured JSONL in this directory:
`raw_capture.log`, `raw_capture2.log`, `raw_capture3.log`.

## 1. Spawn / handshake

`pi --mode rpc --session-id <name> --provider zai --model glm-5.3`, stdio all piped.

**pi emits 7 unprompted lines before any command is sent** (t≈0.9–1.4s after spawn),
all `extension_ui_request` events from loaded pi packages (statusline, goal tracker,
MCP count, thinking-saver notice, delegate status, model-discovery, Slack tool
count). None of them is a "ready"/"hello" event in the sense of a protocol
handshake — they are UI/extension noise. A connector must NOT treat "some bytes
arrived" as readiness; it should treat "stdin accepted a write + a `response`
envelope came back for the first real command" as readiness. There is no explicit
ready signal.

Example line:
```json
{"type":"extension_ui_request","id":"3293a56c-...","method":"setStatus","statusKey":"statusline"}
```
A connector must reply to each with `{"type":"extension_ui_response","id":<id>,"cancelled":true}` or they queue up as noise (confirmed: the plugin does this defensively; not required for basic function but recommended).

## 2. Command / response envelope (confirmed exact match to plugin's documented contract)

Command: `{"type": "<verb>", ...fields}` — no `id` required; verbs correlate by `command` field in the response.

Response: `{"type":"response","command":"<verb>","success":bool,"data"?,"error"?}`

Framing: strict LF-delimited JSON, one object per line. No length-prefixing, no other framing.

Verbs confirmed live: `prompt` (`{message}`), `steer` (`{message}`), `abort` (no fields), `get_last_assistant_text`, `get_state`, `get_session_stats`, `extension_ui_response` (`{id, cancelled}`).

## 3. Full turn — complete event vocabulary, in order

For prompt `"Reply with the single word: ok"` (glm-5.3, non-tool-using turn):

```
response(prompt, success:true)
agent_start
turn_start
message_start   (role:user, echoes the prompt)
message_end     (role:user)
  ... model latency (network round trip to zai) ...
message_start   (role:assistant, stopReason:"pending")
message_update  (assistantMessageEvent.type:"text_start", contentIndex:0)
message_update  (assistantMessageEvent.type:"text_delta", delta:"ok")
message_update  (assistantMessageEvent.type:"text_end", content:"ok")
message_end     (role:assistant, stopReason:"stop", full usage/cost block)
turn_end        (duplicate of the final assistant message + toolResults:[])
agent_end       (messages:[...full turn transcript...], willRetry:false)
agent_settled
```

For a tool-using turn (bash), additional event types appear between `message_start`
(assistant) and `turn_end`:
```
message_update (assistantMessageEvent.type:"toolcall_delta" ...)   -- streamed tool-call JSON args
message_end     (role:assistant, content:[toolCall{...}])
tool_execution_start  {toolCallId, toolName, args}
tool_execution_update {toolCallId, toolName, args, partialResult}   -- 0+ times, streams stdout
tool_execution_end    {toolCallId, toolName, result, isError}
message_start   (role:toolResult, content:[...])
message_end     (role:toolResult)
turn_end
turn_start       -- a NEW turn_start fires immediately, because the agent loop continues after a tool result
queue_update     {steering:[...], followUp:[...]}   -- fires here if a steer message is queued (see §4)
message_start/message_end (role:user)   -- if a steer message was queued, it's injected as a user turn here
... model responds, possibly with "thinking" content (type:"thinking", thinking_start/thinking_delta/thinking_end) ...
turn_end
agent_end
agent_settled
```

Confirmed present: `agent_start`, `turn_start`, `turn_end`, `agent_end`, `agent_settled`, `extension_ui_request` (pre-turn only in this run), streaming/delta events (`message_update` carrying `text_delta`/`thinking_delta`/`toolcall_delta`, plus `tool_execution_update` for tool-output streaming).

**Full observed type set** (`grep -o '"type":"[a-z_]*"' | sort -u` across all captures): `agent_end, agent_settled, agent_start, extension_ui_request, message_end, message_start, message_update, queue_update, response, thinking (content item), thinking_delta, thinking_end, thinking_start, text (content item), text_delta, text_end, text_start, tool_execution_end, tool_execution_start, tool_execution_update, toolcall_delta, toolcall_end, toolcall_start, turn_end, turn_start`.

`extension_ui_request` did NOT reappear mid-turn in these runs (only at startup) — contrary to the plugin comment "fire continuously as UI noise." In this pi version/config they were a one-time startup burst, not continuous. Still safe/correct to auto-cancel any that do appear.

## 4. PUSH vs PULL — proven

Raw evidence (`raw_capture.log`, Part 2/3): after a single `send` of the prompt command at `t=3.012`, **13 lines** of push events arrived over the following ~7.4s (`agent_start` through `agent_settled` at `t=10.411`) with **zero writes from the client** in between. The client's next write (`get_last_assistant_text`) only happened at `t=28.031`, long after the turn had already settled — i.e. the client did not need to poll or write anything to receive the full event stream.

The steer test (`raw_capture2.log`, Part 4) shows the same thing even more starkly: one `steer` write at `t=4.544`, then a stream of 300+ push events (tool execution, thinking, text deltas) arriving unprompted over the next ~19 seconds with no further client writes, up to `agent_settled` at `t=23.651`.

**Verdict: confirmed push.** Events stream on stdout as they happen; the client only writes when it has something new to say (prompt/steer/abort), never to request the next event.

## 5. Turn-boundary steering — confirmed exactly as documented

Sequence observed (`raw_capture2.log`, Part 4), timestamps relative to spawn:
- `t=2.543` prompt sent: "Run the bash tool: sleep 6 && echo TOOLDONE..."
- `t=4.544` steer sent mid-tool-call (tool was still running — `tool_execution_start` had not even fired yet, the model was still deciding). Response: `queue_update {"steering":["STEERMARKER..."],"followUp":[]}` — this confirms the "internal queue update fires immediately" half of the claim.
- `t=10.149`–`t=16.362` the bash tool call streams and finishes (`tool_execution_end` at t=16.362).
- **Only at `t=16.362`**, right after `turn_end`/new `turn_start`, does `queue_update {"steering":[],"followUp":[]}` fire (queue drained) followed immediately by the steer message being injected as a `message_start/message_end` (role:user) turn.
- The model then responds (visibly incorporating the steer: final assistant thinking says "report TOOLDONE and print BANANA") and `agent_settled` fires at `t=23.651`.

**Confirmed**: queue update is immediate; delivery to the model is deferred until the in-flight tool call finishes, at the turn boundary. Matches `docs/architecture.md:194-196` exactly.

## 6. Interrupt / abort — settle signal and ordering

Two abort scenarios tested:

**(a) Abort with no tool in flight yet** (`raw_capture2.log`, Part 5): prompt sent at `t=2.556`, abort sent at `t=4.562` while the model was still generating (no tool call started). Sequence: `message_start`→`message_end` (empty assistant message)→`turn_end`→`agent_end`→`agent_settled`→`response(abort,success:true)`, all within 2ms (`t=4.563`–`4.564`). A reprompt sent at `t=12.581` (well after settle) completed cleanly.

**(b) Abort mid-tool-call** (`raw_capture3.log`, Part 5b) — the case the plugin's ~150ms claim is about: prompt `sleep 30`, waited for `tool_execution_start` (observed at `t=12.701`), sent `abort` at the same instant. Result:
```
t=12.701  abort sent
t=12.718  tool_execution_end  {result: "Operation aborted", isError:true}   (+17ms)
t=12.719  turn_end
t=12.730  message_start/message_end (assistant, stopReason:"error", errorMessage:"This operation was aborted")
t=12.730  turn_end
t=12.731  agent_end
t=12.731  agent_settled
t=12.731  response(abort, success:true)
```

**Discrepancy found**: the plugin's architecture doc claims abort cuts a running tool call in "~150ms." Measured here: **~17ms** from abort-write to `tool_execution_end`, and ~30ms total to `agent_settled`. The binary is faster than documented — not a correctness bug, but the 150ms figure is stale/wrong and should not be used to size a connector's abort timeout. (The earlier "no tool in flight" case settled in ~2ms, consistent with there being nothing to interrupt.)

**Safe-to-send-next-prompt signal**: `agent_settled` for the ABORTED turn is the correct and sufficient signal — confirmed by successfully sending a fresh `prompt` immediately after observing it (both in the mid-tool and pre-tool cases) and getting a clean full turn back with no interleaving/corruption. The `response(abort,success:true)` — which the plugin also waits for as a secondary confirmation — actually arrives in the SAME event batch as (immediately after) `agent_settled` in both observed cases, so either can be used as the gate in practice, but `agent_settled` is the semantically correct one per the plugin's own `turnGeneration` design (§ pi-companion.mjs:814-832) and is what should be documented as canonical.

## 7. Session persistence — confirmed

`raw_capture3.log`, Part 6: spawned session `spike-persist-9f2a`, sent "Remember this exact phrase: PURPLE_ELEPHANT_42", got "stored"-equivalent ack, then **SIGTERM'd the whole process** (not `--session-id` end, not abort — a hard kill of the pi binary). Waited 1s, respawned `pi --mode rpc --session-id spike-persist-9f2a` (same session id) as a brand-new process. Asked "What exact phrase did I ask you to remember earlier?" — **response: `"PURPLE_ELEPHANT_42"`**, ie. full conversation history survived the kill and was correctly loaded by the fresh process.

On-disk location confirmed: `~/.pi/agent/sessions/<cwd-slug>/<timestamp>_<session-id>.jsonl`, exactly matching the expected pattern, e.g.:
```
~/.pi/agent/sessions/--private-tmp-claude-501--...-scratchpad--/2026-09-20T12-41-27-881Z_spike-persist-9f2a.jsonl
```
The cwd-slug encodes the physical (realpath-resolved) cwd, `/` and `:` → `-`, wrapped in `--...--`, matching pi-companion.mjs's `sessionSlugForCwd`.

`get_state` on a fresh process against an existing session-id correctly reports the same `sessionId` and the prior `messageCount`.

## 8. Error edges — confirmed, and a discrepancy found

- **Malformed JSON** (`{not valid json!!!`): pi returns a clean structured error response and **stays alive**:
  ```json
  {"type":"response","command":"parse","success":false,"error":"Failed to parse command: Expected property name or '}' in JSON at position 1 (line 1 column 2)"}
  ```
- **Unknown verb** (`{"type":"totally_unknown_verb_xyz"}`): also a clean structured error, process stays alive:
  ```json
  {"type":"response","command":"totally_unknown_verb_xyz","success":false,"error":"Unknown command: totally_unknown_verb_xyz"}
  ```
- Process remained fully functional afterward — a subsequent `get_state` succeeded normally.

**Discrepancy found**: the plugin's architecture doc (§5/§6 probe notes) claims a wrong field name in a `prompt`/`steer` envelope "produces an unhelpful internal `TypeError` rather than a validation error." That was NOT reproduced here for malformed JSON or an unknown verb type — pi 0.85.1 returns a clean, well-formed `success:false` error response in both cases tested. (Not tested: a well-formed-JSON-but-wrong-field-name payload for `prompt` specifically, e.g. `{"type":"prompt","text":"..."}` instead of `"message"` — that specific case from the doc was not re-verified live; flagging as unverified rather than confirmed-fixed.) A connector can safely treat `success:false` responses as the general error-handling path for malformed input and unknown verbs; the process does not need to be respawned on either error.

## Summary for a connector author

1. Spawn `pi --mode rpc --session-id <id> [--provider P --model M]` with `stdio: pipe/pipe/pipe`. Expect 0+ unsolicited `extension_ui_request` lines before your first command's response; auto-reply `{"type":"extension_ui_response","id":<id>,"cancelled":true}` to each.
2. Write one JSON object + `\n` per command. No id/correlation needed beyond matching `response.command`.
3. It's a genuine push protocol — after `prompt`/`steer`, read stdout continuously; do not write again until you need to (steer/abort) or the turn settles.
4. `agent_settled` is the canonical turn-complete / safe-to-send-next-command signal. For abort specifically, wait for `agent_settled` belonging to the ABORTED turn (which arrives ~2-30ms after the abort write) before sending a reprompt.
5. Steer messages are queued immediately (`queue_update`) but only delivered to the model at the next turn boundary (after any in-flight tool call finishes).
6. Sessions are pure jsonl files under `~/.pi/agent/sessions/<cwd-slug>/<ts>_<session-id>.jsonl`; killing the process and respawning with the same `--session-id` fully restores history. Deleting that file is the correct "end conversation" cleanup.
7. Malformed JSON and unknown verbs both produce `{"type":"response","success":false,"error":"..."}` and do not crash the process — treat `success:false` as the uniform error path.
