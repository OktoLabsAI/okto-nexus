# M00 execution audit — September 29, 2026

M00 is in progress. `acceptance_inventory.json` records all 85 tasks and 164
scenarios, source commits, versions, lock hashes, dirty state and collected
test entry points. A candidate node ID is not proof that a scenario's complete
acceptance criteria are implemented. Unreviewed scope remains unverified.

## Observed environment

Windows 11 build 26200, AMD64, CPython 3.13.1. CPython 3.11.14 and 3.12.12
are also installed. WSL lists Ubuntu and docker-desktop; Docker selects
desktop-linux. These observations do not prove host isolation, Linux provider
availability, outbound firewall configuration or the A/B/C topology.

Provider executables report Codex CLI 0.159.0, Pi 0.87.1 and Claude Code
2.1.282. Credential contents were not read. Authentication, native protocol,
containment, build fingerprints and capabilities remain to be qualified.
No remote laboratory host or separate Server C has been verified yet.

Follow-up probes confirmed a running Ubuntu WSL2 kernel
5.15.146.1-microsoft-standard-WSL2 on x86_64. Codex reports logged in and
Claude reports logged in through claude.ai. Only status booleans/methods
were recorded, without credential values. Pi has a local auth file, but its
usable authentication remains unverified. None of these probes makes a
provider invocation or qualifies a build.

Nexus collection uses its existing development venv. Core and Connector
collection use an isolated CPython 3.13.1 venv with the pinned Core wheel
0.2.22.dev0 and a non-editable Connector installation. Collection emulates
`python -m pytest` for test helpers in the current repository; it does not
add sibling application source directories. Final artifact acceptance still
requires execution outside all clones.

## Collection and regression findings

Initial Nexus collection failed because a legacy backup regression imported
an operator tool from a deleted planning directory. The tool's exact bytes
were recovered from HEAD into `tools/offline_runtime_backup.py`, and the
regression now imports that maintained path. The user's planning deletions
were preserved. This tool still covers the legacy runtime journal; extending
joint backup to Core/R4 stores remains required in M12.

After that correction, complete collection succeeds: Nexus 2,829 node IDs,
Connector 240, Core 925. These are collected cases, not passing tests.
The inventory distinguishes proposed commands from actually collected
commands, including descriptive function names and the separate receipts
test module. TN/J mappings are candidates for review, not inherited passes.

Executed in this audit:

| Command from Nexus root | Result | Scope |
|---|---|---|
| `rtk proxy .venv/Scripts/python.exe -X utf8 -m pytest tests/execution_r4/test_ns00.py -q` | 5 passed | Baseline, crosswalk, direct HTTP/revision fence, historical codec, technical peer |
| `rtk proxy .venv/Scripts/python.exe -X utf8 -m pytest tests/test_runtime_backup_restore.py -q` | 11 passed | Legacy combined backup/restore, corruption, ownership and uncertain-delivery fences |

Neither execution proves provider behavior or the distributed product.
The existing Starlette/httpx deprecation warning remains visible.

The subsequent broad regressions and failures are recorded in
`test_runs_20260929.json` and `M01_DECISION_CONFORMANCE.md`. Nexus stopped
after ten failures with 831 passed and 71 skipped; 1,917 collected cases
were not reached. This is not a full green baseline. Connector completed
with 237 passed, two skipped and one packaging failure; its stale sibling
wheel selection was corrected and both packaging checks then passed.

## Capacity baseline and remaining decisions

The R4 contract limits operation payloads to 65,536 canonical UTF-8 bytes
and lease grants to 120,000 ms. Current Nexus dispatch reservations default
to four regular items/256 KiB and two control items/16 KiB per executor.
Those reservation bounds are not a complete queue/journal budget: durable
pending admission, event retention and native buffers need their own limits.
The 16 KiB control reservation also needs review against accepted input
payloads so accepted work cannot remain permanently unschedulable.

Before closing M00, finish criterion-level code review of every task and
external deliverable, enumerate the actual environment for each campaign,
and measure idle/load control latency and shutdown. Record explicit SLOs
for M11 using those measurements. Missing provider credentials or remote
hosts are environment prerequisites; missing dispatch/lease integration is
implementation work. M00 is not complete merely because collection passes.

## Reproduction

Run `collect_tests.py <report.json>` with each repository as cwd and its
test interpreter. It executes `pytest --collect-only`, writes actual node
IDs, import errors, interpreter/platform and installed versions, and
preserves pytest's exit code. Then run `audit_delivery.py` with
`--nexus-collection`, `--connector-collection`, `--core-collection`, and
`--output`; optional root arguments support non-sibling checkouts.
The original normative backlog and test statuses are not overwritten.
