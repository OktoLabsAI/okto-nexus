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
cases, two canonical boot/tool cases, and the one-slot handoff case. The
remaining CI failures are tracked in `m8-ci-triage.md`. They remain a release
blocker. This UI-C checkpoint is local evidence, not final M8 acceptance or a
global rollout.
