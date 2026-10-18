# M7f — UI sample of one warm turn and concurrent cold Pi openings

Date: 2026-10-18 UTC. This is partial UI-B evidence, not a latency distribution or full gate completion.

An installed Nexus 0.3.1 in the disposable `build/runtime-m6d-ui` home ran on `127.0.0.1:8204`, with installed Connector 0.0.10 wheel SHA-256 `7267f377ebcfce175c11828f2fe4febd0d1d2f75010b622e01372b7c93fd7b67`, Core 0.0.12 and real Pi 0.87.1 via the local Connector daemon. The global Nexus stayed stopped. Agents showed remote Pi Online and its one-shot pool at **1/2 available** before the test.

Two browser tabs sent private Meta-harness messages at 01:41:10 UTC. Both UI sends succeeded. The second-tab marker `M7F_COLD_OK` was actually allocated the warm session `ses_69442bf5`; the durable `turn.submit` reached SUCCEEDED in **6.413 s**. The first-tab marker `M7F_WARM_OK` was allocated a new cold session `ses_f4bdc848`; its `runtime.open` reached the first SUBMITTED receipt in **47.319 s**, then its turn reached SUCCEEDED at 01:43:10 UTC. The marker names reflect the test prompts, not the actual allocation. Both exact responses and **1/1 ACK** appeared in the UI.

After the warm session closed, the pool independently opened `ses_c308c229` as replenishment. Its first open receipt took **38.260 s**. The two cold openings overlapped; trace metadata showed three full Pi build-identity calls in each opening, down from the four observed in the preceding M7d single-open sample. The pool returned to **1/2 available**, and no accepted call in this sample lacked a terminal result. These are two concurrent openings on a shared Windows machine, not a controlled before/after latency distribution. The request's cold opening and the warm replenishment are different work; the trace does not demonstrate unbounded parallelism.

The Connector daemon stopped through its CLI. The Nexus fixture recorded `DRAINED`, no resources or error codes, and `lifespan_finished` at 01:44:27 UTC. The browser closed and neither port 8202 nor 8204 was listening afterward. UI-B still needs an embedded comparison, queue-depth and deadline observation, agent creation during recovery, and a larger load/harness matrix.
