# UI-A: installed harnesses, interrupted server and automatic recovery

Date: 2026-10-18. A disposable copy of the previous local UI fixture ran Nexus 0.3.1, Connector 0.0.10 and Core 0.0.12 from installed wheels on `127.0.0.1:8204`. The global Nexus on port 8202 remained stopped. The copied fixture retained a remote Pi agent without its Connector process and local Pi, Claude and Codex agents. The expired Claude execution grant was renewed through Agents > Connections in this copy; its real connection test passed and the connection was saved.

In the already-open browser tab, Agents showed the remote Pi `Offline` and the three active local agents `Online`. The operator sent one short, unique request to each local agent through the Meta-harness, sequentially to keep host memory above the established 4 GiB free-memory floor. All three yielded exact final responses and 1/1 ACK:

| Agent | Request message | Exact final reply |
| --- | --- | --- |
| `m5m-pi-new` | `msg_3fb6339c531c489da925861161474c34` | `UIA_PI_RESTART_OK` |
| `m7-claude` | `msg_e5abb6cb74514f5ba06eac7d5f3dfe06` | `UIA_CLAUDE_RESTART_OK` |
| `m7-codex` | `msg_7df53ae14f0048019eb64e83c7f4424f` | `UIA_CODEX_RESTART_OK` |

The conversation session sidebar showed the new sessions ended. The Claude and Codex terminals rendered their incoming message, assistant answer and turn completion; the Pi terminal was inspected after the additional restart below. The remote Pi remained Offline while the local agents answered, demonstrating isolation of that unavailable connection in this fixture.

The disposable Nexus process tree was then terminated abruptly while a Pi warm slot existed. The open browser changed from `LIVE` to `RECONNECTING`. The same fixture was started again; the tab returned to `LIVE` without a reload, and Agents again showed the three local agents Online while the remote Pi remained Offline. A new Meta-harness message to Pi returned `UIA_PI_ABRUPT_OK` with 1/1 ACK. Its one-shot call ended `SUCCEEDED`, the consumed slot closed, and the pool returned to one `WARM` slot. The Pi terminal showed harness ready, the formatted incoming message, exact assistant reply and turn completion. No Recover action or manual binding review was used.

This verifies the specified **real UI flows** for UI-A on the installed Windows/local-host topology: startup, replies from all three harnesses, terminal inspection, restart/recovery and isolation of an unavailable connection. It does not prove every technical M2/M3 acceptance item. In particular, the pre-authorization and consumed-capacity failure matrix, remaining crash-frontier/platform qualifications and L12 attribution remain tracked under those milestones. UI-A therefore remains linked to their technical completion rather than being used to mark M2/M3 complete.

The disposable Nexus and browser were stopped. Neither port 8202 nor 8204 had a listener afterward. Private database and raw logs remain only in ignored `build/runtime-uia-ui/`.
