# Browser-only V2 — qualified launch-option counterpart, not executed

This preserves the first browser-only failure and its concrete Chrome diagnostic.
It does not infer why that Chrome classified the explicitly supplied own Temp
profile as default. No App/Server/peer/prefix/provider is used.

The only intended behavioral change is the explicit browser configuration,
copied from the successful executor's **stored launch options** in
`experience-batch/browser-launch-ro-r8.json`, SHA
`1fd039751c08f2d9618429b81bea557c3fe15296420cc25c212430d016733820`:

- browserName chromium; channel chrome; headless true;
- chromiumSandbox true;
- args exactly `["--disable-blink-features=AutomationControlled"]`;
- the separately pinned Program Files Chrome executablePath.

The successful executor's userDataDir is deliberately **not copied**. The same
CLI `--profile=NEW_OWN_TEMP/browser-profile` creates the diagnostic's own profile.
No CDP, extension, personal profile, environment restoration, browser install,
npx or npm is added. The comparison source did not capture its full launch argv;
these are its recorded custom launch options, not a claim about all defaults.
The first diagnostic already logged headless mode; spelling it explicitly here
is not evidence that headless caused the original problem.

The prior controller, direct pinned Node/CLI entry,192-file CLI closure,
NO_UPDATE_NOTIFIER=1, private pw:browser/pw:api DEBUG, owner90s, open50/read10/
close10, bounded own birth/exe cleanup and pre/post guards are unchanged. The
only code diff accepts the reviewed full config instead of only executablePath.
No scenario/assertion expectation is relaxed. Any timeout/force/drift remains
FAIL/inconclusive, without an H01/Home/performance claim.

Root must issue a new gate/cut ID with approvedtrue/root,
kind=BROWSER_ONLY_ABOUT_BLANK, owner_seconds90, allow_own_containmenttrue and
this V2 manifest SHA. No approved gate is supplied here.

Proposed commands, **NOT RUN**:

```powershell
rtk proxy python -B .../browser-only-v2/run.py --gate NEW_ROOT_GATE.json
rtk proxy python -B .../browser-only-v2/curate.py --root OWN_DIAGNOSTIC_TEMP
```

All previous cuts, gates, manifests and package prefixes remain intact. This
functional configuration comparison requires Root review before execution; it
is not a diagnosed fix to product or a new performance campaign.
