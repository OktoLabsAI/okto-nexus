# Capture/projection test reconciliation — October 2, 2026

Historical Windows/Python 3.11 and 3.13 CI reported only 199/203 journal records
before an eight-second test deadline. The assertion labeled this as blocked
SQLite projection, but it did not observe either a stall or queue overflow.

Controlled investigation retained real journal writes and fsyncs and added a
40 ms delay before each append. The initial test failed at watermark 139.
A progress-aware observer then showed that this case actually stopped there:
the technical native fixture has a 128-event queue and sends 256 deltas faster
than the deliberately slow consumer. Separately, the ordinary case captured the
whole burst but exceeded the five-second result-projection wait. These findings
show that the fixture mixed capture isolation, throughput and overflow behavior.
They do not establish the exact cause of each historical CI occurrence.

## Corrected scope

The positive fixture still sends all 256 deltas, now in eight 32-event batches.
The peer waits for an acknowledgement emitted only after the batch's last real
journal append/fsync. It never waits for SQLite projection. This keeps the
positive isolation case within the bounded native queue even with slow storage.

Capture must reach at least the original 260-record increment and observe the
durable terminal event while the projection lock remains held. The native child
must remain alive and the canonical result must remain absent. After releasing
projection, the public operation must expose the exact complete output.

Each stage now distinguishes stalled progress from elapsed backlog processing:
capture still fails after eight seconds without journal advancement; projection
fails after five seconds without checkpoint advancement. Both also have a
30-second campaign guard. The positive case is not a throughput SLA.

The existing deliberate-overflow test is unchanged and was run alongside it.
That negative case requires child termination, a queue of at most 128 events,
explicit `NativeEventOverflow`, `outcome_unknown`, binding quarantine, removal
of subscribers and no fabricated completed turn. No application code, queue
capacity or product timeout changed.

## Evidence

Three source checks passed in 42.19 s. Three installed checks passed in 41.13 s
on Windows/Python 3.13.1 with unchanged campaign inputs and verified bytes for all
three pinned packages. Installed measurements:

| Case | Capture | Projection | Final watermark |
|---|---:|---:|---:|
| Normal storage | 0.518 s | 5.262 s | 261 |
| Added 40 ms per append | 10.995 s | 4.912 s | 261 |

[Campaign](evidence/ci-capture-progress/campaign.json),
[installed hashes](evidence/ci-capture-progress/installed.json),
[JUnit/measurements](evidence/ci-capture-progress/tests.xml).
Failed investigative runs are retained as `before.xml` and `after.xml`; they are
not passing acceptance. The corrected source run is `bounded.xml`.

This tests retained Server journal/supervisor behavior with a test-only legacy
transport fixture and a disposable Python child. It does not restore or qualify
a retired native adapter, validate Core provider throughput, or establish remote
physical-host acceptance. The existing Nexus development wheel remains unchanged.
Current hosted confirmation, NS14 SQLite contention, Connector hosted timeouts,
UI completion, final artifacts and G0–G3 remain open.
