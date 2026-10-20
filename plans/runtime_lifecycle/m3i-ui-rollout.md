# M3i global rollout and real UI checkpoint

Date: 2026-10-17. Product checkpoint: Nexus `1a39568`, Core `6e97362`,
Connector `b12b8b8`. Later Connector commits `a7dd588` and `0944a0e` change
qualification tests/documentation only. Feature branches only.

The joint installed campaign passed 115 tests with eight optional automated
browser skips and no failures. The exact qualified artifacts were subsequently
installed together in the existing global Python 3.13 user installation:

| Package | Version | SHA-256 |
|---|---|---|
| Nexus | 0.3.1 | 62917fdecc582f9d31a31d639d17ca713bf2f73c619b18f43a414abdcc86b99f |
| Core | 0.0.12 | 13d72e63d1406a8cd6fcb154ce31bb218c0e042cce0bf946cc8e0350f69a3b9a |
| Connector | 0.0.10 | 41331e7b9405e830d990141e48e7702d461559a779b66ee39ec8aedc9e52d7c2 |

All 542/158/99 installed package files respectively matched the artifacts and
their dependencies were compatible. No second global Nexus installation was
created. Historical qualification JSON remains a record of the pre-rollout
checkpoint; this document records the later deployment.

## Preserved shutdown and startup

Preflight at 07:44:34 UTC found no active one-shot calls or pending runtime
deliveries. Five sessions were READY (four idle Pi warm sessions and Claude).
The exact old server PID/birth/path and launcher were checked before Ctrl+C at
07:44:36.211 UTC. Generation 72 drained at 07:44:40 and exited at 07:44:41,
without force termination. The full offline backup passed before installation;
it includes databases, runtime journals, artifacts and session configuration.

Generation 73 started with launcher PID 39500 and server PID 32480 on port 8202.
Codex became READY at 07:46:17.722 UTC, Claude at 07:46:18.768 and Pi at
07:46:24.543. Four Pi opens were admitted between 07:46:32.817 and
07:46:32.958. An initial warm backoff was observed and cleared automatically;
no database values or pool state were edited. This is one startup observation,
not a controlled cold/warm performance benchmark.

Comparison with the offline backup preserved all seven agent endpoints, seven
execution bindings, eight local realizations and ten workspace bindings exactly.
The seven agents differed only in expected last-seen observations at comparison
time. No credential/configuration review was required. Production history was
not reset.

## Real tests through Meta-harness

Both requests were sent using the real UI to the Techridy workspace, asking
only for a fixed connectivity response and no tool use or file changes.

- Pi returned `M3I_PI_OK`, with 1/1 ACK. Call
  `op_b7afa27c93c2495ca6261d63ffa09e4b` reached RUNNING after 0.6952 seconds
  and SUCCEEDED after 10.2113 seconds. The consumed warm session closed and
  the pool returned to four WARM instances automatically.
- Claude returned `M3I_CLAUDE_OK`, with 1/1 ACK. Its session
  `ses_0b272acf718a85c2507027823a0ea4c3` was inspected through the
  conversation session terminal with live tail: ready at 07:47:57 UTC,
  turn started at 07:47:58, assistant response and completion at 07:48:01.
  The persistent session remaining open after success is expected.
- Agents displayed Pi, Claude and Codex Local Online, with Pi 4/5 available.
  No new Codex provider request was made because the existing quota finding
  L5 has not been cleared; Online is runtime readiness, not provider quota proof.

UI screenshots were captured in the browser tool output; no local screenshot
artifact is claimed. Local diagnostic artifacts are under
`build/runtime-m3i-live/` (installation, preflight, shutdown signal, observations
and preserved-config reports), with backup manifest under
`build/runtime-m3i-offline/`. These private build paths are not tracked.

## Follow-up on the reported all-Recovering state

At 07:52 UTC, read-only inspection found generation 73 CONTROL_READY, all three
local recovery rows READY, four Pi WARM slots and no warm backoff. The open
Agents page showed all three Online with current heartbeat observations. The
other existing tab also showed Online, but retained a last-contact observation
from 07:32 UTC. Neither tab was reloaded, and the server was not restarted for
this follow-up. The polling code skips hidden documents; display lag is observed,
but it does not establish the cause of the earlier all-Recovering report.
L12 remains open. The qualified rollout above must not be presented as proof
that the reported incident was diagnosed or fixed.

This completes the M3i deployment/UI checkpoint, not all M3 or UI-A acceptance.
Initial-readiness load qualification, automatic contained-owner replacement,
and the remaining plan gates remain pending. L17 reset behavior passed installed
tests, but still needs a real UI test against a disposable home, never a reset
of production history.

M6 now has an experiment ADR in Connector commit `0944a0e`:
`plans/runtime-lifecycle-m6-supervisor-adr.md`. It specifies the independent
supervisor comparison and Windows IPC requirements; no supervisor prototype or
adoption decision is claimed.
