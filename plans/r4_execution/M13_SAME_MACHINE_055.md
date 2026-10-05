# Same-machine discovery and native acceptance, Core .55

Independent-machine acceptance is reserved for a manual session with the user.
These campaigns use this machine, Windows and WSL environments, and separate
Server/Connector processes over loopback HTTP/WSS. All five installed campaigns
below recorded unchanged monitored inputs. No release gate is closed.

## Discovery correction

Core `beed295` (0.2.55.dev0) deduplicates identical observations at the discovery
facade boundary. Automatic managed Pi discovery and an explicit Pi root previously
produced the same installation reference twice. Two Windows regression cases
failed against .54 before the correction. Conflicting observations of one
reference still refuse with PROFILE_DRIFT; distinct installations stay distinct.
Installed Core checks passed 62 on Windows and 60 with two Windows-only skips on
Linux. Connector `7cf54e1` adopts .55; 31 directed checks passed on each OS.
Their repositories retain DISCOVERY_055.md and the underlying JUnit evidence.

Nexus installed checks cover local discovery, Core inventory, daemon startup and
HTTP inventory refresh: 21 passed on Windows (88.44 s), 21 on WSL Linux (52.24 s).
Evidence: `evidence/discovery-055-windows/` and `evidence/discovery-055-linux/`.

## Real provider results and open failure

- `evidence/native-054-connector-codex-pi/`: Codex 0.159.0 passed its public CLI
  cycle, lease renewal, three native approvals, completed handoff and successful
  close. Pi failed control readiness with VALIDATION_ERROR. Combined result:
  one pass, one failure (407.66 s). This uses the earlier .54 artifact tuple.
- `evidence/native-055-connector-pi/`: control publication and opening succeeded;
  lease reached serial 2. The native turn then failed the unchanged assertion
  against `core.event_pump_failed` (385.11 s). Control remained ready.
- `evidence/native-055-connector-pi-diagnostic/`: the same package bytes passed
  with the existing opt-in stream diagnostic enabled (305.69 s). Lease renewal,
  three native approvals, completed handoff and successful close were observed.
  No stream failure was captured. This is not evidence that the intermittent
  failure was corrected: no production change separates these two .55 runs.

Each native attempt recorded zero-exit daemon/server cleanup and removal of its
campaign credentials. Read-only inspection of the failed .55 executor journal
found 890 native/lease events followed by event 891, `core.event_pump_failed`,
with EVENT_STREAM_UNAVAILABLE. There were 849 message_update events, four tool
starts/ends and four turn_end events; the fifth turn had no terminal event.
The retained incident has no original exception cause. Event volume alone does
not establish overflow, timeout or provider death; root cause remains open.

## Development artifacts

| Artifact | SHA-256 |
| --- | --- |
| Core 0.2.55.dev0 wheel | `b1a389d247a470571c485e27adfa7277b11b4ae39382a52ebefc0ef0cc76453f` |
| Connector 0.5.0.dev0 wheel | `1c799154b2998035617bcfe2301cd9f4be7f3982dd7e797d7fd33b8dff6b252a` |
| Nexus 0.2.0 wheel | `1f53365cc024c7fbf13b2748255f8cffdc6200ae0fc4d5ec609b086ca760bc67` |
| Nexus sdist | `bc0e1168e8713ccc57f187e730f27f85d72f7b468ef682e6cf8e3d965bf170e1` |

The build manifest is retained as `evidence/discovery-055-build.json`.
Windows Python 3.13.1 and WSL Python 3.12.13 used isolated installed packages;
the user's global Connector installation was not upgraded by these campaigns.
Claude/Codex .54 success is not automatically qualification of this .55 tuple.

The Connector issue list was rechecked: its only open issue is
[#1, macOS containment](https://github.com/OktoLabsAI/okto-nexus-connector/issues/1).
The documentation/doctor workaround and discovery corrections are tracked;
native macOS containment remains unavailable. The issue was not closed.

Remaining acceptance includes Pi failure diagnosis, final artifact freeze and
clean installation, current full regressions/CI, first-use embedded UI and
runtime operations, fault/platform/provider matrix and the later manual
independent-machine session. NS15.05, M13 and G0–G3 remain open.
