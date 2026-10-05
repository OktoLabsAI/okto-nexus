"""RES-A2 repro: two CONCURRENT events() consumers, both confirmed parked in
queue.Queue.get() (via a threading.Event each sets on generator entry)
BEFORE the turn is sent, so the split below cannot be a thread-start race.
Run from the repo root with ``src`` importable (pytest's ``pythonpath =
src`` convention)."""

import importlib.util
import threading
import time

from okto_nexus.domain.harness import HarnessCommand

spec = importlib.util.spec_from_file_location(
    "t", "tests/test_harness_claude_code_connector.py"
)
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)

connector = t._connector("slow_start")  # 0.5s gap before first event - gives us time to confirm both parked in get()
session = connector.start(owning_agent_id="agent_test")

it1 = connector.events()
it2 = connector.events()

out1, out2 = [], []
started1 = threading.Event()
started2 = threading.Event()

def drain(it, out, started, stop_kind="turn_completed"):
    started.set()
    for ev in it:
        out.append(ev)
        if ev.kind == stop_kind:
            return

t1 = threading.Thread(target=drain, args=(it1, out1, started1))
t2 = threading.Thread(target=drain, args=(it2, out2, started2))
t1.start()
t2.start()
started1.wait(timeout=5)
started2.wait(timeout=5)
# both threads have entered the generator and are now blocked in queue.get()
# (connector._events is empty at this point - nothing sent yet).
time.sleep(0.1)
connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "hello"}))

t1.join(timeout=10.0)
t2.join(timeout=10.0)
print("t1 alive:", t1.is_alive(), "t2 alive:", t2.is_alive())
print(f"consumer1 got {len(out1)} events, kinds={[e.kind for e in out1]}")
print(f"consumer2 got {len(out2)} events, kinds={[e.kind for e in out2]}")
total_seen = len(out1) + len(out2)
print(f"combined total across both consumers: {total_seen}")
print(f"consumer1 saw turn_completed: {any(e.kind=='turn_completed' for e in out1)}")
print(f"consumer2 saw turn_completed: {any(e.kind=='turn_completed' for e in out2)}")

connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
for _ in connector.events():
    pass
