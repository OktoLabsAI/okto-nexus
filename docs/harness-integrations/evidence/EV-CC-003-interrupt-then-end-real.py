"""RES-C1/INT-06 repro: interrupt() immediately followed by end() with no
further turn in between, driven through the real connector against the real
``claude`` binary. Run from the repo root (uses pytest's own ``pythonpath =
src`` convention, so ``PYTHONPATH=src`` must be set, or run via ``uv run
python`` from the repo root with ``src`` importable)."""

from okto_nexus.adapters.outbound.harness.claude_code_stream import ClaudeCodeStreamConnector
from okto_nexus.domain.harness import HarnessCommand

connector = ClaudeCodeStreamConnector()
session = connector.start(owning_agent_id="agent_test")
connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn",
                payload={"content": "Write the numbers 1 to 40, one per line, nothing else. Do not stop early."}))

it = connector.events()
for event in it:
    print("EVT", event.kind, event.native_event)
    if event.native_event in ("stream_event:message_start", "stream_event:content_block_start"):
        break

connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt"))

# Immediately end - NO further turn - the gap the existing suite never covers on the real binary.
connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))

remaining = []
for event in it:
    print("EVT", event.kind, event.native_event, event.payload if event.kind == "error" else "")
    remaining.append(event)

print("---")
print("total remaining events:", len(remaining))
print("has process_exit error:", any(e.kind == "error" and e.native_event == "process_exit" for e in remaining))
for e in remaining:
    if e.kind == "error":
        print("ERROR EVENT:", e.native_event, e.payload)
