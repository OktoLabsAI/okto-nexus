# EV-PI-001 — Pi RPC protocol verified live

Captured: 2026-09-20 10:10 -03
Binary: `pi` 0.85.1 at `/opt/homebrew/bin/pi`
Backend: `zai/glm-5.3`

Provider note: `~/.pi/agent/settings.json` maps the default `local-mac` provider to the
**192.168.31.222** box, which is reserved for a multi-day benchmark. The spike checked this
BEFORE running and overrode to `zai/glm-5.3`. No inference was sent to `.222`.

Full protocol reference: [`../research/pi-rpc-protocol-reference.md`](../research/pi-rpc-protocol-reference.md)
Raw captures: `EV-PI-001-raw_capture.log`, `EV-PI-001-raw_capture2.log`, `EV-PI-001-raw_capture3.log`

## Findings (all 7 items verified with raw bytes)

1. **Handshake.** There is NO "ready" event. On spawn, pi emits 7 unsolicited
   `extension_ui_request` lines — UI noise from loaded pi extensions. Readiness is the first
   `response` envelope. A connector that waits for a hello will hang forever.

2. **PUSH CONFIRMED (satisfies INT-04 for Pi).** A single `prompt`/`steer` write was followed by
   13 to 300+ push events with ZERO client writes in between, with timestamps. Pi is genuinely
   event-driven; the polling in `pi-delegate` exists only because MCP tools cannot push.

3. **Event vocabulary.** Enumerated in order for both plain and tool-using turns:
   `agent_start` -> ... -> `agent_settled`. Confirmed present: `agent_start`, `turn_start`,
   `turn_end`, `agent_end`, `agent_settled`, `extension_ui_request`, and streaming deltas.

4. **Steer timing.** Confirms the plugin's `docs/architecture.md` claim exactly: `queue_update`
   fires IMMEDIATELY, but delivery is deferred to the turn boundary after the in-flight tool call
   finishes. This is why the port declares `steer_timing=NEXT_TURN_BOUNDARY` for Pi.

5. **Abort / settle ordering.** `agent_settled` for the ABORTED turn is the correct
   safe-to-reprompt signal. Confirmed by successful immediate reprompts. Getting this wrong is
   the classic hang.

6. **Session persistence.** Proven by full process kill + respawn with the same `--session-id`:
   a remembered phrase (`PURPLE_ELEPHANT_42`) was correctly recalled by the FRESH process.
   Path confirmed: `~/.pi/agent/sessions/<cwd-slug>/<ts>_<session-id>.jsonl`.

7. **Error edges.** Malformed JSON and unknown verbs BOTH return clean
   `{"success":false,"error":"..."}` and the process stays alive in both cases.

## Discrepancies found — the binary wins

- **Abort latency is ~17ms measured**, not the plugin's documented "~150ms". Connector abort
  timeouts sized around 150ms are overly conservative rather than wrong, but the real figure is
  an order of magnitude tighter.
- The plugin's architecture doc claims a malformed / wrong-field envelope yields "an unhelpful
  internal TypeError". **Not reproduced** in 0.85.1 for malformed JSON or an unknown verb — both
  returned clean structured errors. The specific wrong-field-name-on-`prompt` case was not
  independently retested and is flagged UNVERIFIED rather than confirmed either way.

## Cleanup

All spawned pi RPC processes killed (`pgrep` clean). All 5 throwaway session jsonl files and the
now-empty session directory deleted. Nothing under `okto-nexus` or the pi-delegate plugin touched.
