# Writer deadline after notification — October 2, 2026

Review of `0994c6b` found an admission race: a queued writer notified after its
deadline could observe a free slot and bypass the timeout check inside the wait
loop. It could then start a transaction with SQLite's zero busy timeout despite
having exhausted its queue budget.

The gate now checks the remaining positive wait budget again before taking the
slot. Expiry removes the waiter and raises the existing retryable DB_ERROR;
the unit of work closes its connection without issuing BEGIN. An explicitly
zero budget still permits an immediately available slot and refuses contention.
No automatic transaction replay, configured timeout or wire contract changed.

Two controlled-clock cases reproduced the defect at the deadline and just after
it before the fix. They verify no SQL executes, the expired connection closes,
the queue is empty and a later transaction can proceed. They replace only the
gate's clock reference and model notification without sleeps or global time
changes. The existing FIFO, external SQLite lock, reader, cleanup and shared
budget cases remain unchanged.

- [Before: two expected failures](evidence/writer-deadline-before.xml).
- [Source: 22 passed](evidence/writer-deadline-source.xml).
- [Installed Windows/Python 3.13.1: 29 passed, 18.73 s](evidence/writer-deadline-windows/tests.xml).
- [Installed WSL Linux/Python 3.12.13: 29 passed, 26.26 s](evidence/writer-deadline-linux/tests.xml).

Installed campaigns additionally cover heartbeat storage closure and dispatch
ownership/cancellation. Both runners checked Nexus/Core/Connector package bytes
against pinned wheels, ran with isolated Python outside the checkout and
reported unchanged inputs. These are the same 29 cases on two environments,
not 58 unique cases or two physical hosts. Earlier load evidence in
[M13_WRITER_FAIRNESS.md](M13_WRITER_FAIRNESS.md) remains tied to its earlier wheel;
load and the full hosted matrix have not been requalified on this artifact.

Development wheel SHA-256:
`664889e396fc763837ab7234ccc6f9ef0952577a19f62e3868e5be2e97b33a8c`.
Development sdist SHA-256:
`87066050e3c43d3d487dac6a290696c907c031437acf2d2c3ac9306c192d9262`.
The [build manifest](evidence/writer-deadline-build.json) records exact source
hashes against parent `0994c6b`. Core and Connector artifacts are unchanged.

This does not freeze M13 or close NS15.05/G0–G3. Full CI, remaining UI/CLI work,
Connector timeout diagnosis and independent-host/platform/provider/fault
acceptance remain required.
