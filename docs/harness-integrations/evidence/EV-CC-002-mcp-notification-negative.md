# EV-CC-002 — MCP server-initiated notifications do NOT reach the model

Captured: 2026-09-20 09:07 -03
Substrate under test: custom MCP `notifications/claude/channel` push
Verdict: **ELIMINATED**

## Claim under test

An arbitrary MCP server, connected to Claude Code, can push an unsolicited
`notifications/claude/channel` JSON-RPC notification that surfaces to the model — the mechanism
Anthropic's own Discord plugin appears to use.

## Why this was plausible

`~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/discord/server.ts:875-884`
does exactly this, and inbound Discord messages demonstrably reach the model as
`<channel source="discord">` tags.

## Method

A throwaway MCP server emitted `notifications/claude/channel` carrying a unique marker, on a
timer and on a tool call. Tested across the full matrix:

| Mode | Transport | Marker reached model? |
|---|---|---|
| `claude -p` (headless) | Streamable HTTP | NO |
| `claude -p` (headless) | stdio | NO |
| interactive (tmux TUI) | Streamable HTTP | NO |

## The setup fix that makes this negative trustworthy

The first spike servers declared `capabilities: { tools: {} }` only. The real Discord plugin
ALSO declares `capabilities.experimental['claude/channel']: {}` at `initialize`
(`external_plugins/discord/server.ts:~440-452`) and pushes `{ content, meta: {...} }` params.
Both spike servers were patched to match that capability declaration and payload shape, and the
tests re-run. This negative is therefore NOT a capability or payload mismatch.

## Evidence

Transport and send were confirmed healthy in every run — this is a render-path failure, not a
delivery failure:

- Client: `Successfully connected (transport: http)`; the standalone `GET /mcp` SSE stream was
  opened by the client (`Accept: text/event-stream`).
- Server: `session initialized`, then `firing notification (timer)... notification SENT
  successfully` repeatedly, both while the session was idle and during an active tool call.
- Headless: 0 occurrences of the marker in `raw-stdout.jsonl` / `raw-stdout-stdio2.jsonl`.
- Interactive: 0 occurrences in `tmux capture-pane -p -J -S -` across 12s of idle spanning 2+
  timer fires, and across a tool-triggered push window.
- The model was asked directly (the marker was never typed into the TUI, to avoid contaminating
  the test) whether it had received any out-of-band content. It answered:
  *"Zero task notifications. Zero `<system-reminder>` content beyond the style reminder.
  No push notification text."*
- `client-debug.log` registers notification handlers for other namespaces (e.g. LSP
  `publishDiagnostics`) but shows NO registration line for `notifications/claude/channel`.

## Conclusion

The notification is genuinely sent and the channel is genuinely open, but
`notifications/claude/channel` is not rendered or injected into model context in either headless
or interactive sessions, idle or mid-turn.

The Discord plugin's delivery must therefore go through a different path — most plausibly
host-side wiring for first-party/bundled plugins that is not exposed to arbitrary
`--mcp-config` servers. Determining that is out of scope; the substrate is abandoned either way.

## Consequence

ADR 0004 D7 is amended: the Claude Code substrate choice is between `cc-socks` (EV-CC-001) and
`claude -p` stream-json. The MCP-notification path is removed from consideration.
