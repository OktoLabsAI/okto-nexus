# S1 explicit installed Chrome — instrumental counterpart, not executed

Original S1 `hst-security-r8-s1` remains FAIL/inconclusive with all3 browser
phases NOT_RUN. Its first `open` command failed because the sanitized
LOCALAPPDATA correctly pointed to ownTemp, where channel discovery found no
Chrome. No user environment is restored to bypass that boundary.

This counterpart keeps the approved base manifest `37f0fea6…5b7bf01`, its
scenario assertions,30-table comparison, code/prefix guards, canonical DELETE,
deadline, own environment/profile and cleanup unchanged. The only browser
launch alteration is `--config=OWN_TEMP/playwright-cli-explicit.json` containing
`browser.launchOptions.executablePath` for the existing Program Files Chrome.
No browser installation, CDP attachment, extension or personal profile is used.

Read-only discovery found:

`C:/Program Files/Google/Chrome/Application/chrome.exe`

SHA256 `5b835c10836045119334d9524e62437110e00e1bd20612c9072a0ae155f94a17`.
This pins the executable bytes only, not an inventory of all browser DLLs.
No `--version`, browser process or app was invoked during preparation.

The local CLI README documents `--config` and
`browser.launchOptions.executablePath`. Its `cli-client/session.js` forwards
`cliArgs.config` to the daemon. The bundled loader parses JSON, resolves
launchOptions.executablePath, merges it into launchOptions and passes those
options to browser launch. Contract file hashes are recorded separately.

Root must issue a **new S1 gate/cut ID**, not reuse the consumed original:

- Retain `manifest_sha256` = approved **base** `37f0fea6…5b7bf01` for its
  unchanged preflight/preparation/helpers.
- Add `instrumentation_manifest_sha256` = this directory's manifest SHA.
- Add `browser_executable_path`, `browser_executable_sha256` and
  `browser_config_sha256` matching the pinned records.
- New `cut_id` starts `hst-security-r8-s1-`; other Root S1/R8 fields remain.

`validate.py` checks these instrumental pins **before** the base preflight.
After both pass, an exclusive attempt marker consumes that cut ID before its
single allocation. Root may run `validate.check` read-only first; it does not
consume the marker. After cleanup the executable, config and instrumental
inputs are checked again. Drift or incomplete instrumentation cannot be green.

Proposed commands, **NOT RUN**:

```powershell
rtk proxy python -B .../explicit-chrome/run.py --gate NEW_ROOT_GATE.json
rtk proxy python -B .../explicit-chrome/curate.py --root NEW_OWN_TEMP
```

The derived `run.diff` is reviewable. All originals, previous gates/manifests,
prefixes and evidence remain byte-intact. S2 remains waiting. Raw auth/rows/logs
stay only in ownTemp; public curation adds only instrumental pins/cleanup proof.
