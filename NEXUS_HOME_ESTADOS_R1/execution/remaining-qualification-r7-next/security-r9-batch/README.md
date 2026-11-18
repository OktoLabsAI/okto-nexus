# Prepared S1 R9 — new sibling, no execution

Root review/gate required before any allocation/runtime/browser. R8 base37f0e,
all diagnostic antecedents, package prefixes and qualifiers remain immutable.
This cut is S1 only; S2 is not enabled. No provider or performance campaign.

## Read-only argv comparison

`argv-comparison-r8-failure-r9-working.json` compares the actual R9 working main
process argv with the diagnostic V2 private launch argv. Replacing **only** each
own Temp root by `<OWN_ROOT>` produces the same44 tokens in the same order,
with zero exclusive flags. Positive input is psutil argv; failed input is the
private Playwright joined launch line (remaining tokens had no whitespace).
This does not identify an environment/policy/flag cause of Chrome's refusal.

## Small browser strategy change

Use the already downloaded/pinned direct Node+CLI entry and full192-file CLI
closure, without npx/npm/update checker. Config matches the recorded working
browser: chromium/channelchrome/headlesstrue/chromiumSandboxtrue/custom
AutomationControlled arg, plus the pinned existing Program Files executable.
Never copy another profile or attach to a personal Chrome/CDP endpoint.

Only the browser command environment reads a declared allowlist of ordinary
Windows path/system keys from the host. It is **not** claimed byte-equivalent
to the working executor's uncaptured environment. Provider/token variables are
never copied. Browser TEMP/TMP stay own; CLI daemon and global-config paths are
forced own using the pinned CLI's supported PWTEST_DAEMON_SESSION_DIR and
PWTEST_CLI_GLOBAL_CONFIG overrides. A fresh cwd/.playwright directory prevents
upward workspace discovery. NO_UPDATE_NOTIFIER=1 prevents npm/skill checks.
No personal CLI config, provider config, stored browser profile or NPM setting
is opened by this driver.

The application still uses unchanged `Owned.start` with its **separate fully
ownTemp environment**, own credentials/config/DB, empty provider PATH and inert
guard/birth/handshake Python peer. The browser env dictionary never mutates the
host env or leaks into the application/peer environment.

After opening only about:blank, the supervisor reads already-owned process
births and requires exactly one main Chrome whose *actual* --user-data-dir
resolves to NEW_OWN_TEMP/browser-profile. It checks exact exe/birth, headless,
remote-debugging-pipe and configured args, and writes the own argv proof **before
loading the own cookie or navigating Home**. Missing/mismatched proof aborts;
there is no personal/default-profile fallback.

## Unchanged S1 assertions and limits

Rebinds to frozen R9 sourcef07163ab7fd618b2ff4247ba6cdb2547b5d4e038,
wheel e870ea400435d5b736093990af9b56544661e205ad657bbff83f830421a3e628,
1031 payload and1829 build-source pins. Same exact-target browser bodies,
full30-table private-row/public-hash snapshots, strict no-ignore comparison,
canonical DELETEgrant and revoked current-controls UI assertions. No heartbeat
or metadata drift is silently excused. Preserve first failure without replay.

Owner deadline180s, finite own cleanup. Retain runtime.close refusal and
closedfalse after revocation; embedded-owner lifespan physical exit does not
prove CLOSED lifecycle or canonical runtime.close PASS. Only scoped functional
results can be claimed, never a broad plan cleanup-cycle or H01-H10 completion.
All raw cookie/rows/DEBUG/error logs remain ownTemp. Curator allowlists only
public checks/hashes/column deltas/own-profile argv/cleanup, with no raw auth.

## Proposed gate and commands — NOT RUN

Root gate: approvedtrue/root, caseS1, runtime_modebaseline, deadline_seconds180,
allow_own_containmenttrue, browser_environment_policy
`windows-path-allowlist-app-env-own-v1`, source/wheel above, exact prepared
manifest SHA and R9 READY SHA, fresh hst-security-... cut ID. No OBS insert
permission. The preflight checks the192 CLI files and Node/Chrome/config pins
alongside full source/payload/helper before allocation and after cleanup.

```powershell
rtk proxy python -B .../security-r9-batch/run.py --gate ROOT_RUN_READY.json
rtk proxy python -B .../security-r9-batch/curate.py --root OWN_TEMP_FROM_RUN
```

No gate is supplied here. `run-r8-r9.diff` shows only rebind/browser transport
and own-profile-proof instrumentation; original scenario assertions are reused.
