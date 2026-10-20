# M8 UI-C installed checkpoint (2026-10-19)

Scope: one disposable Windows Nexus 0.3.1 instance on `127.0.0.1:8204`, with
Core 0.0.12 and Connector 0.0.10 installed in the same isolated environment.
The database was copied from the earlier UI-A fixture; the global Nexus home
was not modified. Nexus wheel SHA-256:
`339416e60441455740813284e4e1905cd5fa3e7cfe187aca52b60bfda0153f68`.

Real UI observations:

- Agents showed the local Pi, Claude and Codex connections Online and the
  disconnected remote Pi Offline. The three local harnesses each returned the
  exact UI-C marker sent from Meta-harness. Claude's completed terminal showed
  formatted turn and assistant events.
- Pi's injected `agent_list` returned seven agents, including connection
  status. Claude's MCP `agent_list` was initially denied by Claude Code because
  this fixture's Nexus tool access was `ask`. In the Connections wizard, the
  operator changed it to `always_allow`, passed the connection test, chose
  **Close sessions and save** for one READY warm session, and repeated the
  request. Claude then reported Codex online and the remote Pi offline.
- An initial 99,032-byte attachment failed with 404 because this registered
  fixture workspace has no `root_realpath`. The upload route incorrectly
  required one even though managed artifact storage is keyed by workspace ID.
  The route and ArtifactService now accept a registered rootless workspace.
  A focused HTTP test passed. After rebuilding and reinstalling Nexus, the
  same document uploaded as a managed artifact (HTTP 200), and Meta-harness
  sent it to Pi (HTTP 200, one delivery). Pi read the complete document and
  replied with `UIC_LARGE_BEGIN`, `UIC_LARGE_END`, and 1002 lines without
  reproducing the body.
- After restarting the disposable server with the rebuilt wheel, Agents again
  showed Claude Online, its `always_allow` setting remained stored, and the
  earlier `UIC_CLAUDE_OK` request and response remained visible in Meta-harness.

The Core 0.0.12 platform matrix and SBOM job passed. Connector 0.0.10's
installed CI passed on Linux and macOS, but Windows 3.12 and 3.13 each had one
failing race test; those are being triaged before acceptance.
The Nexus full installed matrix for commit `9792a4c` was still running, but
Ubuntu 3.12 and 3.13 shard 0 had failed. The 3.12 shard recorded 41 failed,
1043 passed, 26 skipped and 6 errors; 3.13 had overlapping failure classes.
The Nexus run was cancelled after both Ubuntu shard-0 jobs failed, avoiding
additional runner use. Focused installed Windows verification of the CI
corrections passed: 11 preopen recovery cases, 12 registered adapter and
retirement cases, the migration case, four inventory/realization/shutdown
cases, two canonical boot/tool cases, the one-slot handoff case, and four
renewal containment commit cuts. The
remaining CI failures are tracked in `m8-ci-triage.md`. They remain a release
blocker. This UI-C checkpoint is local evidence, not final M8 acceptance or a
global rollout.

## Current wheel restart check (2026-10-19)

The current Nexus 0.3.1 wheel, SHA-256
`8c18c8d4a8fcbf93322bf857d1e87a991309a1818cb0b5b9b3b0a8b62a972502`,
was force-installed into the isolated `build/m3k-owner-env` environment. Its
`embedded_dispatch.py` bytes match the current source, including the shutdown
retry correction. Core 0.0.12 and Connector 0.0.10 remained installed. The
same disposable UI-C home ran on loopback port 8204; the global instance stayed
stopped.

From Meta-harness, a real Claude turn returned exactly
`UIC_M8_PRE_RESTART_OK` with 1/1 ACK. The disposable server process tree was
then terminated abruptly, without touching other Nexus instances or user
processes, and the same installed wheel and home were restarted. The original
browser tab retained both the request and answer. Agents showed Claude
**Local · Online** and runtime **Ready**; a new Meta-harness turn returned
exactly `UIC_M8_POST_RESTART_OK` with 1/1 ACK. This verifies an interrupted
server restart and subsequent delivery; the graceful shutdown retry path is
covered by focused installed tests, not by this UI check. The scoped browser
and server process tree were stopped afterward, and port 8204 is free.

The full installed Nexus matrix `39292190027` on `1902baa` was still running
when this UI checkpoint was recorded. Final M8 acceptance and global rollout
remain open.

## Current product wheel: three real harnesses through Meta-harness

On 2026-10-19, the disposable UI-C home ran on `127.0.0.1:8204` with Nexus
0.3.1 wheel SHA-256
`0d4c1adea040e012611584f185227605c9bc0fe9a5b7ad3d76bde1452ec0638a`,
Core 0.0.12 and Connector 0.0.10 installed in `build/m3k-owner-env`. The
installed `capacity_link.py` bytes matched the current product source. The
global Nexus instance stayed stopped. A new Playwright browser drove the
actual Agents, Meta-harness, session terminal and Graph pages; the source
tree was not imported as the installed application.

Agents showed the selected local Pi, Claude and Codex as **Local · Online**
with current `Ready` runtime contact. The disconnected remote Pi remained
**Remote · Offline**. Three sequential private messages from the UI returned
the exact requested marker and 1/1 recipient ACK:

| Agent | Request message | Session | Exact final response |
| --- | --- | --- | --- |
| `m7-claude` | `msg_a62f60c899b64aa295911039ffe3f82b` | `ses_0c8f0bc19358d6451b73922ffacebd02` | `UIC_M8_FINAL_20261019_OK` |
| `m7-codex` | `msg_9d93936d74fb4daca42430b53fb631b4` | `ses_0505271b822d65c8ce4ab1463d7282b5` | `UIC_M8_FINAL_CODEX_OK` |
| `m5m-pi-new` | `msg_c14cdc9bf7b04db58819fc9b34a64fae` | `ses_64cba8d4941c36fa1a1e74f67f9d72c1` | `UIC_M8_FINAL_PI_OK` |

A read-only database check after the UI responses found three `read` deliveries,
three `PUBLISHED` exact results and all three sessions `CLOSED/CLOSED` with
`local_retirement_json` present. The Meta-harness session drawer showed those
same three sessions as Ended. Pi's terminal displayed the incoming text,
subject, sender, recipient and workspace as structured fields, then the exact
assistant response and a completed turn; it did not present the input as raw
JSON. Agents continued to show all three local runtimes Online, and Graph
showed their green online indicators. Evidence images:
[conversation](m8-final-meta-results-20261019.png),
[Pi terminal](m8-final-pi-terminal-20261019.png),
[Agents](m8-final-agents-20261019.png) and
[Graph](m8-final-graph-20261019.png).

The Playwright browser and scoped server were closed after observation; port
8204 was free and no Nexus process command line referenced the disposable
home. This checkpoint verifies the current product wheel's real three-harness
message/result/status flow. The earlier UI-C permission, MCP and large-artifact
checks remain in the section above; this short campaign did not repeat them.
Final installed CI, same-load comparison and controlled rollout remain open.
