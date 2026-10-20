# M7o: installed real-harness load distribution

The fixed [M7o protocol](m7o-load-protocol.md) ran on 2026-10-18 in the disposable Nexus 0.3.1 UI at `127.0.0.1:8204` with installed Connector 0.0.10 and Core 0.0.12. Real Pi 0.87.1, Claude Code 2.1.301 and Codex CLI 0.162.1 each used embedded one-shot, maximum 2 parallel instances, 1 warm instance, queue capacity 1 and a 300-second start deadline. The Pi deadline was changed from its earlier 5-second fault-test value through Agents > Connections and verified after saving. The global Nexus was not started.

Each harness received six bursts of three short, unique exact-marker requests from three independent Meta-harness tabs. Only one harness was under test at a time. The host had 16 logical cores and 31.7 GiB RAM; the lowest *pre-burst* free-memory reading was 5.20 GiB, above the 4 GiB abort floor. There was no continuous memory trace. The 54 browser sends created exactly 54 messages and 54 one-shot calls. All 54 finished `SUCCEEDED` with the exact requested marker, durable delivery `read`, outbox ACK `NATIVE_ACCEPTED`, and 54 distinct turn sessions. No call was missing or repeated. After every burst the tested pool returned to 1/2 available; open-to-close session intervals used by this campaign peaked at two per harness. The 50 ms nominal read-only queue poller reported no SQLite error and observed one `QUEUED` to `ADMITTED` transition per burst.

All values below are **seconds**. Each cell is `p50 / p95 / p99`; linear interpolation over the observed samples was used. The complete counts and maxima are in [m7o-results.json](m7o-results.json).

| Harness | UI send duration, n=18 | Warm enqueue→start, n=6 | Cold open→start, n=6 | Observed queue, n=6 | Queued enqueue→start, n=6 |
| --- | --- | --- | --- | --- | --- |
| Claude | 1.880 / 2.307 / 2.308 | 1.934 / 2.788 / 2.908 | 54.082 / 60.400 / 61.826 | 18.175 / 19.316 / 19.417 | 70.839 / 76.743 / 77.197 |
| Codex | 1.873 / 4.415 / 7.970 | 1.788 / 2.039 / 2.075 | 48.220 / 51.869 / 52.231 | 16.130 / 18.292 / 18.570 | 63.102 / 69.546 / 71.113 |
| Pi | 1.965 / 2.656 / 5.229 | 1.761 / 2.350 / 2.456 | 51.893 / 57.097 / 57.820 | 18.036 / 20.186 / 20.202 | 67.252 / 70.616 / 71.298 |

UI send duration is the browser click interval, not a server-only transaction time. A warm call uses a session whose `runtime.open` had a `SUBMITTED` receipt before its enqueue; a cold call uses a nonqueued session whose receipt arrived afterwards. Cold open duration runs from durable `runtime.open` creation to execution start. Queue duration runs from the poller's first observed `QUEUED` to first observed `ADMITTED`, so it has observation uncertainty; durable enqueue-to-start is also reported as the caller-visible wait. The p99 values describe these small samples and are not population guarantees or a baseline speedup claim.

The warm path stayed under 3 seconds at the observed p99 while cold openings took roughly 48–54 seconds at the median. The short warm responses completed while cold openings were still active, and the queued calls eventually returned without user repair. This meets the fixed M7 load acceptance for the installed local host and shows the remaining latency cost is concentrated in native opening, not in warm dispatch. It does not prove a remote physical host or all M8 failure modes.

After collection, the browser and scoped disposable Nexus process tree were stopped. Port 8204 has no listener, and the global Nexus instance was not started.
