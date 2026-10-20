# M7n: real Claude and Codex warm/cold calls through Nexus UI

On 2026-10-18, the disposable installed Nexus 0.3.1 at `127.0.0.1:8204` used Connector 0.0.10 and Core 0.0.12. Claude Code 2.1.301 and Codex CLI 0.162.1 were discovered and verified through Agents > Connections. Two new agents in workspace M6D, `m7-claude` and `m7-codex`, were configured through the UI as embedded one-shot, maximum 2 parallel instances, 1 preinitialized instance, queue capacity 1, and the inherited 300-second start deadline. Both real connection tests passed. Agents showed each Online and 1/2 available before the calls.

For each agent, two separate Meta-harness tabs submitted short exact-marker requests concurrently. All four messages received 1/1 ACK and exact responses. Read-only SQLite inspection correlated the native `turn.submit` operation's session and marker with the one-shot call; the earlier `runtime.open` distinguishes the warm session from the cold session opened after admission.

| Harness | Route | Marker | Enqueue to execution start | Enqueue to final result | Session |
| --- | --- | --- | ---: | ---: | --- |
| Claude | warm | `M7_CLAUDE_B_OK` | 1.606 s | 11.622 s | `ses_78ac3546…68b27` |
| Claude | cold | `M7_CLAUDE_A_OK` | 47.310 s | 55.989 s | `ses_8c9111f9…fd123` |
| Codex | warm | `M7_CODEX_A_OK` | 2.024 s | 16.509 s | `ses_dce76719…6b02` |
| Codex | cold | `M7_CODEX_B_OK` | 56.306 s | 64.420 s | `ses_b8bca048…41557` |

Claude's warm session opened around 06:36 UTC, before the 06:47 burst; its cold session's `runtime.open` was created at 06:47:17 UTC. Codex's warm session opened around 06:43 UTC, before the 06:52 burst; its cold session's `runtime.open` was created at 06:52:27 UTC. Afterwards Agents showed both pools back at 1/2 available without operator repair. The four native responses establish basic warm/cold behavior and independent sessions; four samples do not establish the requested p50/p95/p99 load distribution.

The test fixture is local and isolated from the global Nexus home/listener. The observed timings include host and provider variability and are not baseline comparisons.
