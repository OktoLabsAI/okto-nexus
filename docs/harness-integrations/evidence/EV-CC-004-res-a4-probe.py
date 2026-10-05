"""RES-A4 repro: a FAILED start() (real subprocess.Popen OSError, nonexistent
binary path) must still leave events() terminable. Run from the repo root
with ``src`` importable (pytest's ``pythonpath = src`` convention)."""

import threading
import time

from okto_nexus.adapters.outbound.harness.claude_code_stream import ClaudeCodeStreamConnector
from okto_nexus.errors import OktoNexusError

connector = ClaudeCodeStreamConnector(binary="/nonexistent/binary/definitely-not-here-xyz")
try:
    connector.start(owning_agent_id="agent_test")
    print("start() did NOT raise - unexpected")
except OktoNexusError as exc:
    print(f"start() raised as expected: {exc.code}")

result = {}
def _drain():
    result["events"] = list(connector.events())

t = threading.Thread(target=_drain, daemon=True)
t0 = time.monotonic()
t.start()
t.join(timeout=5.0)
elapsed = time.monotonic() - t0
print(f"events() thread alive after 5s join: {t.is_alive()} (elapsed {elapsed:.2f}s)")
print(f"_closed_event.is_set(): {connector._closed_event.is_set()}")
if "events" in result:
    print(f"events collected: {result['events']}")
else:
    print("events() NEVER RETURNED within 5s - CONFIRMED HANG")
