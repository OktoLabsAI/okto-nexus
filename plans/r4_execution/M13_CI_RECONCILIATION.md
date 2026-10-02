# M13 CI and regression reconciliation — October 1, 2026

This is preparation evidence, not M13 acceptance or a final artifact freeze.

## Staged package installation and current Connector failures

The installation runner now starts with the base wheel in a fresh environment,
proves bootstrap without Core/Connector/Torch, then installs serve-lite and
proves HTTP bootstrap without Connector/Torch, before adding Connector test
dependencies. All three installed trees are compared with their wheels.
Ten installed NS01/import-boundary checks passed on Windows/Python 3.13;
see `evidence/m13-staged.json` and its logs/JUnit.

NS01's obsolete .38 packaging expectation now checks the current manifest hash,
the installed Core version and Nexus extras metadata together. Its bootstrap
subprocess no longer prepends checkout src. The absent-Core fixture now models
find_spec returning None while still prohibiting actual imports; a separate
fresh base-only environment confirmed that the real bootstrap already worked.
These test edits happened while the historical .51 R4 campaign remained live,
so its final source snapshot cannot establish an immutable test revision.

Connector run 36950960934 completed: all Linux cells passed, all Windows cells
failed. Windows/Python 3.11 reports 11 failures, 662 passes and two skips. The
new diagnostic exposes WinError 5 at daemon manager CreateProcess (the launcher
requests CREATE_BREAKAWAY_FROM_JOB), plus R4 observation timeouts and a lease
expiry. These remain unresolved; investigate process/job policy and fixture
timing before changing product guarantees. The two earlier LEASE_INVALID
integration failures no longer appear in this run.

## Hosted follow-up and remote laboratory availability

Core run 36950397170 finished with five successful platform/Python cells.
Windows/Python 3.12 alone failed W03 (1102 passed, 77 skipped). The test cancelled
open after 200 ms without confirming factory entry. Injecting 300 ms into the
receipt lookup reproduces that same failure on the installed .52 runtime:
there is no late handle to force-stop. Core test-only commit `85b25b8` waits for
factory entry, tests both admission delays and retains the held-close-barrier
and force-stop assertions. All 10 C7 audit cases passed locally; hosted rerun
is pending. No runtime artifact or consumer pin changes for this fixture fix.

The user confirmed a second computer on the same network with Connector already
installed and requested the two-machine test once preparation is complete.
Record it as an available laboratory candidate, not a qualified executor:
host identity, installed versions, connectivity and provider setup still need
verification before the campaign. Prepare and validate locally first. This
supersedes the earlier statement that no remote computer was identified.
The A/B/C independent-host isolation topology remains a separate requirement.

Current consumer runs: Connector `36950960934` at `acaa192` and Nexus
`36951078377` at `62e61c6`. Both were pending terminal results at this checkpoint.

## Core 0.2.52 consumer integration

Nexus now pins 0.2.52 in pyproject, uv.lock and the inventory version; Connector
commit `acaa192` uses the identical Core wheel. Its rebuilt test wheel is fixed
in `vendor/ci/manifest.json`. Connector installed integration/CLI checks passed
8 tests on Windows/Python 3.13. Hosted verification remains required, including
the Windows CLI PermissionError now reported with full stderr.

The isolated Nexus builder recompiles the dashboard without overwriting existing
worktree static assets, then produces wheel/sdist and a source-hash manifest.
The first preparation failed clean boot because inventory still required .51;
after correcting that pin and rebuilding, installation passed without Connector
or Torch, followed by 27 installed dispatch/bootstrap/import-boundary tests.
Package files for all three applications matched their wheels. Evidence and
exact artifact hashes: `evidence/m13-core052.json` and linked reports.

These checks do not qualify real providers or independent hosts. The previous
full R4 campaign still runs on .51; some tests start checkout subprocesses,
and consumer source pins changed while it was running. Its results must not be
represented as an immutable final .52 campaign. Core hosted run 36950397170
passed Linux 3.11/3.12/3.13 at this checkpoint; Windows jobs remain in progress.
Core test-only commit `9a3741d` corrects a reused 60-second stress-test context
and a Windows queued socket-handshake race without changing the .52 runtime.
Nine installed tests covering those fixtures passed before push.

## Clean local bootstrap and lease-boundary defect

A new Python 3.13 venv installed the NS15.05 Nexus wheel with `serve-lite,dev`
and Core before the Connector test dependency. With neither Connector nor Torch
installed, the HTTP lifecycle served protocol/dashboard (200) and denied an
unauthenticated identity request (401). The CI runner now enforces this order and
installs Connector's test extra afterward for asyncio regression support.
Three installed import-boundary tests also passed. Evidence:
`evidence/m13-local-without-connector.json` and its log. This is bootstrap-only
evidence, not native lifecycle/provider acceptance or the final release tuple.

Connector's Windows CI exposed a reproducible Core arithmetic defect:
`(100.002 + 120.0) - 100.002` exceeds 120 due to floating-point subtraction.
Core commit `e0745bb` publishes 0.2.52.dev0, comparing absolute deadlines instead
of introducing any tolerance. A new regression accepts the exact maximum but
rejects the next representable deadline before native open. All 63 installed
runtime tests passed in a separate fresh venv; the wheel SHA-256 is
`470eb23b28d917a3a154c2ef7cd9fdddf972ca6402c0668961b4c01909f1b732`.
The wheel is at `C:/Users/jpamb/AppData/Local/Temp/okto-core-lease-052-dist/`.
Consumer pins/artifacts must now be updated and the affected integration rerun.
The live Nexus R4 campaign still uses the unchanged 0.2.51 tuple; at this
checkpoint session `1133` was alive past 70%, with failures pending its terminal
report. Do not change that interpreter while it is running.

## Nexus hosted regression workflow

The Nexus workflow now builds the dashboard from its lockfile, builds wheel and
sdist, installs the wheel with `serve-lite,dev`, and runs tests from a temporary
cwd with `-I` and an independent pytest configuration. Its matrix covers
Windows/Linux and Python 3.11–3.13. Logs, JUnit and packages are retained as
Actions artifacts even on failure. This does not claim that hosted checks have
already passed or replace live-provider and independent-host acceptance.

The private Connector repository is not implicitly accessible from a Nexus
Actions token. A small, SHA-pinned Connector wheel under `vendor/ci` supplies
the cross-repository test dependency instead. Its runtime bytes were compared
against current Connector source before copying; the corresponding provenance
and exact Core hash are documented in that directory. Nexus package requirements
are checked to ensure they do not acquire a Connector application dependency.

`tools/ci_installed.py` was exercised locally with the existing NS15.05 wheel:
all three installed package trees matched their wheels, CLI help exited zero,
and the three import-boundary checks passed from the temporary cwd. The workflow
YAML parses with the intended six-cell matrix. The full hosted install/build/test
path remains pending execution. No running local interpreter was reinstalled.

## Follow-up: hosted failures reproduced and fixtures corrected

Core run 36948182442 passed all three Linux/Python jobs. Windows reached the
tests after the R3 checkout correction and exposed native-schema CRLF conversion,
an owned crash fixture releasing its Job too early after effect return, and a
30 ms revocation timing assumption. Commit
`b5c66b93905c540275745776e0476a1d87e4d04b` fixes those fixture/checkout issues;
10 directed tests passed locally. The socket connection-refusal race observed
on Windows passed locally but is not yet declared resolved. Current hosted
verification: [36948904945](https://github.com/OktoLabsAI/okto-nexus-connector-core/actions/runs/36948904945).

Connector run 36948290057 completed its Linux jobs with nine failures and 662
passes on Python 3.11. The failures identified synthetic executables without
POSIX execute permission, an incomplete `__new__` host fixture, and expectations
predating Core's protected CODEX_HOME directory and POSIX Pi discovery. Commit
`7f9320832a0659b9eecc3b9376abdb576e7c313e` corrects those test inputs/expectations
without relaxing product checks. Local affected suite: 44 passed, one platform
skip. Current hosted verification:
[36948913588](https://github.com/OktoLabsAI/okto-nexus-connector/actions/runs/36948913588).

Nexus exec session `1133` was re-polled alive after 30% of the full R4 suite.
No terminal result is available yet. Do not replace or restart this campaign
without checking its process/handle and final manifest. The current artifact
tuple still contains the same production runtime bytes: the two external
increments above changed tests, documentation and checkout policy, not runtime
implementation. They do not constitute the final M13 artifact freeze.

## Verified findings and corrections

- Nexus HEAD before this increment: `28d38c6`. No workflows are currently
  registered in the checkout; hosted run listing for this branch was empty.
  Actions is enabled at repository level. A reproducible Nexus workflow remains
  required, including access to the private Connector repository or an explicit
  pinned test artifact for the cross-repository tests.
- Connector's previous workflow had all jobs disabled, Core `0.1.0.dev0`, a
  nonexistent `dist` dependency source and shell-specific line continuation.
  Commit `b01d9a959c0b17cb7c9ea0cdef98af813b433135` replaces those with the exact
  dependency from pyproject/vendor wheels, noneditable installation, read-only
  permissions, pinned actions and Windows/Linux Python 3.11–3.13 jobs. Build waits
  for successful tests. Local structural boundary checks: 13 passed.
- Core run [36868353381](https://github.com/OktoLabsAI/okto-nexus-connector-core/actions/runs/36868353381)
  failed Windows generated-R3 checks and Linux documentation checks. R3 JSON
  lacked the explicit LF checkout rule already used for R4, despite manifests
  hashing exact bytes. Public docs also omitted exported API names and advertised
  version `0.2.35.dev0` instead of `0.2.51.dev0`. Commit
  `faae3e851e8e38fec07a84a01833080c5840d5b5` fixes these without changing runtime
  source or contract bytes. Three public-documentation tests and the generated
  R3 byte check passed locally. The Linux 3.12 run additionally had a ten-second
  Pi optional-dependency probe timeout; it is not classified as resolved.

## Live campaign handles

At this checkpoint, these authoritative handles were observed running:

- Core hosted run [36948182442](https://github.com/OktoLabsAI/okto-nexus-connector-core/actions/runs/36948182442).
- Connector hosted run [36948290057](https://github.com/OktoLabsAI/okto-nexus-connector/actions/runs/36948290057).
- Nexus installed full `tests/execution_r4` campaign, local exec session `1133`:
  `rtk proxy python -X utf8 plans/r4_execution/run_ns15_05.py --resume --campaign all_r4`.
  Partial output is `evidence/ns15-05-all_r4.log`; final XML/manifest are written
  only when pytest exits. The process was polled live after the first 10% of
  tests. Do not restart based on this document alone: query the live session or
  process and final manifest first.

The installed campaign verifies wheel hashes and package bytes before tests.
Some historical tests explicitly start source-backed subprocesses; this suite
is regression evidence, not proof that every subprocess uses a clean wheel.
One known stale assertion still expects Core `0.2.38.dev0` in `test_ns01_03`;
the actual pyproject and vendored wheel use `0.2.51.dev0`, SHA-256
`4c4c0c58d25b93f4f08ba8515d8476ffc29d1f0a27cc577c9fccb610716d1d1c`.
The test file has not been edited during the running campaign.

## Remaining requirements

Await terminal campaign results, preserve failures, fix causal defects and rerun
the affected checks. Scenario promotion requires review of assertions against
the original matrix, not matching test names. No G0–G3 or M13 gate is closed.
Independent A/B/C host access has been requested for the real remote campaign;
no hosts, credentials or provider qualification are inferred from local fixtures.
