# EV-SYS-007 — SYS-07: the SQLite write is a side effect of delivery, never its trigger

## Code-level ordering (the structural claim both halves rest on)

`HarnessSupervisor._handle_event` (`application/harness_supervisor.py`):

```python
def _handle_event(self, session_id, event):
    try:
        self._subscribers.publish(event)          # 1. in-memory push, UNCONDITIONAL, first
    except Exception:
        self._log_best_effort_failure(...)
    self._persist_event(event)                     # 2. durable write, best-effort, AFTER
    if event.kind in NOTABLE_EVENT_KINDS:
        self._deliver_notable_message(session_id, event)
```

`_persist_event` wraps its own SQLite write in a bare `except Exception:` (best-effort) — a
failed or slow write can never un-publish an event that already went out in step 1, and can never
raise past this method. This ordering is what both halves of SYS-07 are checked against below;
neither check trusts the docstring's claim without exercising it.

`sys07_subscriber_kill.py` and `sys07_db_lock_experiment.py` are both scratchpad-only (never
committed, same convention as the other SYS evidence files) — their real captured output is
inlined below and their structured results are committed as
`EV-SYS-007-db_lock_experiment_result.json`.

## Half 1 — killing/breaking a subscriber does not lose the record

The subscriber registry (`InMemoryHarnessSubscriberRegistry`) has **no external HTTP surface at
all** in this phase (its own module docstring: a future SSE reader "subscribes here directly" —
none exists yet), so there is no black-box way to attach an external subscriber through the real
running server and then kill it externally. This is exercised the same way SYS-06 is: against the
REAL, frozen class, in-process, not a mock or reimplementation:

```
$ timeout 20 uv run python sys07_subscriber_kill.py
PASS: a subscriber callback that raises does not stop publish() from reaching the other
subscriber, and does not raise out of publish() itself - a broken/killed consumer cannot lose
the in-memory push to anyone else, matching the class's own docstring guarantee.
```

Concretely: two subscribers registered on one session_id, one raises `RuntimeError` on every
call (simulating a subscriber that died mid-stream), the other records what it received.
`registry.publish(event)` is called twice — the surviving subscriber received the event BOTH
times (2/2), `publish()` itself never raised despite the other callback blowing up every time,
and `unsubscribe()`-ing the dead one twice (double-kill) was a harmless no-op, matching the
class's own idempotency docstring.

Separately, the multi-harness run in EV-SYS-004-005-009 already demonstrates the DEGENERATE case
of this same claim against the real server: **zero subscribers were ever registered** for any of
the three sessions sent real turns, and every one of those turns' durable events still landed
correctly (`GET .../events` returned them all, content matching). Durability does not depend on a
live subscriber being present at all, let alone a surviving one.

## Half 2 — a slow/failing DB write does not block or drop the push

No clean external fault-injection point exists inside the process (frozen/non-frozen source was
not modified). Instead, this holds a REAL `BEGIN EXCLUSIVE` lock on the SAME `nexus.db` file the
real running `serve` process uses, from a SEPARATE `sqlite3` connection, spanning a real pi turn
sent through the hub — `config.py`'s `busy_timeout_ms` default is 5000ms, so the lock is held for
8s, longer than any single write's own busy-timeout retry window:

```
$ timeout 60 uv run python sys07_db_lock_experiment.py
EXCLUSIVE lock acquired on .../home/nexus.db at wall=1789927458.788107
POST /send status=200 call_seconds=0.022 (while DB EXCLUSIVE-locked)
wire trace lines: before_send=31 while_still_locked_or_done=45
turn's agent_settled observed at wall=1789927464.244, lock still held at that moment: True
lock released. lock_error: {}
durable events for this session after unlock: 30 total, 9 mention 'delta' (this turn's own text)
```

Three findings, reported exactly as observed:

1. **The send call itself is never gated by DB availability**: `POST /send` returned in 22ms
   while an external process held an EXCLUSIVE lock on the database file. This matches the code
   path directly — `HarnessSupervisor.send()`'s outbound half never touches SQLite at all.
2. **The harness's own turn completed normally WHILE the external lock was still held**
   (`agent_settled` observed on the wire at t+5.45s into an 8s lock window) — the real pi child
   process is naturally unaware of Nexus's DB state, so this on its own only proves the harness
   side kept working; it does NOT by itself prove Nexus's in-memory publish kept pace, since this
   evidence run had no live subscriber to time that against directly (see Half 1's honesty note).
   What it DOES prove, combined with the code-level ordering above, is that nothing in this path
   made the DB lock visible to the harness or the caller — no hang, no dropped connection, no
   error surfaced anywhere in the send/receive path.
3. **No row was actually dropped in this run**: after the lock released, all 9 of this turn's
   `delta`-bearing events were present in the durable replay. This is explained by SQLite's own
   `busy_timeout`: each individual `_persist_event()` write, if it started while the external lock
   was held, blocked (retried internally) rather than failing outright, and the external lock
   happened to release (at t=8s) before any single write's own 5s busy-timeout window elapsed — so
   every write eventually succeeded once the lock cleared. **This experiment did not force the
   `except Exception` drop branch to actually fire** (it would need the external lock held longer
   than any individual write's busy-timeout window, measured from THAT write's own start, which
   this 8s/5s combination didn't quite achieve for a fast pi turn) — reported honestly rather than
   overclaimed. The branch that WOULD handle a genuine failure is proven to exist and to be
   correctly scoped by code reading (`_persist_event`'s bare `except Exception:`, wrapped strictly
   AFTER the unconditional `publish()` call), just not forced to fire by this particular real-world
   contention experiment.

**Verdict: SYS-07 PASS** on the structural claim (code ordering, confirmed by reading) and on
both empirically-checkable halves (subscriber survival: exercised directly against the real
class; DB contention: real lock, real server, send never blocked, harness never wedged, no row
lost in this run). The stronger "a write that ACTUALLY fails past its busy-timeout still doesn't
drop the push, only the row" claim rests on code inspection alone, disclosed as such rather than
dressed up as forced-and-observed.

Full raw result: `EV-SYS-007-db_lock_experiment_result.json`.
