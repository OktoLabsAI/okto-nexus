# Linux load diagnosis — October 2, 2026

Two installed NS14.04 executions on WSL Linux/Python 3.12.13 failed the existing
thread-growth assertion. Both completed all 100,000 identity resolutions in 200
write transactions. Neither reached the subsequent admission/control-lane load
checks; neither is a passing load campaign.

| Measurement | First run | Thread-instrumented run |
|---|---:|---:|
| Maximum writer acquisition | 24.7 ms | 17.2 ms |
| Maximum transaction held | 201.3 ms | 227.2 ms |
| Total transaction held | 25.93 s | 29.21 s |
| Pytest duration | 57.53 s | 56.79 s |

The second run grew from 17 to 28 live threads. All 11 additional threads were
named `asyncio_3` through `asyncio_13`; the named Nexus workers were unchanged.
Both runs logged dispatcher storage/recovery and result-publication failures.
These measurements exclude one long identity transaction as the explanation in
these two runs. They do not establish the cause of the background storage
failures, prove a thread leak, or reproduce the historical heartbeat exception.
Repeated writer competition and default-pool scheduling need further diagnosis.

The test now records bounded transaction timing and thread snapshots before its
existing assertions. No application code, timeout, admission rule, batch size,
thread limit or identity touch semantics changed.

Both runs used the Nexus development wheel from `2162908`, SHA-256
`65c9127c5ee4ac90d93627d907cdc32404db07f0fe9c254b9ba4effba3cbd5d2`.
The runner verified installed Nexus/Core/Connector package bytes and recorded
unchanged campaign inputs. Python dependencies were installed into a new Linux
virtual environment; tests ran with `-I` outside the checkout. This remains one
physical Windows machine with WSL, not independent-host acceptance.

- [First campaign](evidence/ci-load-linux-timing/campaign.json) and
  [timings/failure](evidence/ci-load-linux-timing/tests.xml).
- [Thread-instrumented campaign](evidence/ci-load-linux-threads/campaign.json),
  [thread snapshots/failure](evidence/ci-load-linux-threads/tests.xml) and
  [installed artifacts](evidence/ci-load-linux-threads/installed.json).

NS14.04 Linux acceptance, full hosted regression and G0–G3 remain open. The
second Windows computer's empty discovery still needs its installed versions,
provider command locations and doctor output before configuring its executor.
Connector issue #1 was rechecked: it remains the only open issue and describes
unsupported native macOS containment plus discovery questions. The Windows/Linux
support scope and documented Linux guest workaround remain unchanged.
