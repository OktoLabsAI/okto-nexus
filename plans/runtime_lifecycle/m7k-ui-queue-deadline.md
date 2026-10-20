# M7k — Real Pi UI queue deadline and opening timeout

Date: 2026-10-18 UTC. Partial UI-B evidence from the disposable installed Nexus 0.3.1 fixture at `127.0.0.1:8204`, installed Connector 0.0.10, Core 0.0.12 and real Pi 0.87.1. The global Nexus remained stopped.

Agents > Connections set Pi one-shot to maximum 2 parallel, 1 warm, 1 queued and a 5-second wait-to-start timeout. The Agents card showed **1/2 available** before sending. Three prepared Meta-harness tabs sent private requests within about 200 ms, each asking Pi to wait 30 seconds and return a distinct `M7K_[A-C]_OK` marker. All three UI clicks were accepted and produced sent messages.

Durable one-shot records separate the outcomes. C acquired the warm slot, started 1.992 seconds after enqueue and returned exactly `M7K_C_OK` at 02:48:06.946 UTC; its turn and close had SUCCEEDED receipts. B was admitted to a cold opening but expired at the 5-second admission deadline with `ONE_SHOT_START_TIMEOUT`, `execution_started=false`, `possible_effect=false` and `retry_safe=true`. A remained queued and expired with `ONE_SHOT_QUEUE_EXPIRED` and the same no-effect/retry-safe properties. Both failures were visible as one-shot error messages in Meta-harness. The C result was also visible there. Since the three sends raced, their letter order does not imply admission order.

B's `runtime.open` produced its first SUBMITTED receipt only at 02:47:57.649 UTC, after its call had expired. It did not execute B's turn. The resulting session was retained as the configured warm slot; no completed call was incorrectly resumed. This sample demonstrates a real queue deadline, cold-opening deadline and operator-visible error delivery, not a latency distribution. A five-second budget is intentionally shorter than observed Pi cold startup and therefore expected to reject that opening.

The Connector daemon stopped via CLI. Nexus recorded `DRAINED` with empty resources/error codes at 02:48:40.752 UTC, then `lifespan_finished`; the browser closed, fixture PID exited and neither 8202 nor 8204 listened. UI-B still needs an installed embedded comparison, other harnesses, agent creation during recovery and a wider load distribution.
