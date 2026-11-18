# Native 200% zoom: preparation only

No browser, app, probe server, runtime, profile or home has been started or
allocated for this preparation. This is not an I05 PASS and is not an AT test.
The first future gate covers only browser-native zoom proof, before Nexus.

## Primary reference and unknown WebUI shape

[Google Chrome Help](https://support.google.com/chrome/answer/96810?hl=en)
documents changing default page zoom through Settings / Appearance / Page zoom.
The script operates that real control. It does not call Chrome private APIs,
edit preferences files, use CSS zoom, set deviceScaleFactor, or send page-scale
emulation commands. Current Chromium source was consulted for WebUI context,
but source-fetch/version drift means no internal DOM ID is assumed. The actual
accessible combobox must be observed. If it is absent, disabled, not a native
select, or has no200% option, stop with NOT_RUN/UNQUALIFIED and no Nexus startup.

## Proposed gate A: `ROOT_NATIVE_ZOOM_BROWSER_GUARD`

Bind R9 READY/source/wheel and full1031 installed payload; retain all R8/R9
evidence. After Root's explicit gate only:

1. Use the already qualified `browser-hst/prepare_runtime.py` against R9 to
   allocate a new own `nexus-hst-browser-*` Temp root. This copies prepared
   fixture files and writes metadata only. Do NOT call `Owned.start` or import
   Nexus. Do NOT create any canonical identities, grants or sessions yet.
2. Run `probe_server.py` from the frozen installed Python with `-I -B`, a
   sanitized own environment and dedicated process group. It serves only a fixed
   HTML page at127.0.0.1, stops on its own stopfile or90s, and never imports Nexus.
   This is a geometry calibration page, not a mocked Home response or dataset.
3. Launch one named Playwright CLI Chrome session with the qualified workflow
   and the new own `browser-profile` path. No existing profile/session is used.
   Example session `hst-native-zoom-guard-r9`; browser choice chrome. Set the
   requested viewport720x1000 once before both samples. No device scale option.
4. Take a fresh `chrome://settings/appearance` snapshot. Substitute only public
   config into `native-settings-guard.js`: gate string, probeOrigin and own
   outputPrefix. The script locates the real Page zoom combobox (English or
   Portuguese labels), records its actual AX/options, selects100% via the UI,
   navigates to the own HTTP page and records baseline geometry. It repeats with
   the real200% option, forwarding no network DTO and changing no app preference.
5. Require Settings selected200%, DPR ratio approximately2, innerWidth ratio
   approximately0.5, visualViewport.scale1, unchanged requested viewport and
   stable outer/screen geometry. Target: requested720, actual CSS about360.
   It is NOT a360 outer viewport (which would be about180 CSS at200%). Record
   both values; never relabel them. No timing or SLO claim.
6. On first failure, preserve AX/metrics/error, do not fall back to simulated
   zoom, and do not start Nexus. On success, publish only native browser proof
   and pause for Root review before any application phase.
7. Close the own CLI session, signal `zoom-probe-stop`, wait normal process
   exit, then verify actual PID/birth, own profile processes and listener absent.
   Preserve the disposable own profile data and its native zoom setting for
   review; no personal preferences or Windows display settings are touched.

All runtime commands remain gated; the only validation during preparation is
syntax parsing. Proposed process invocation after allocation:

```
<R9-python> -I -B probe_server.py --root <ownRoot> --window ROOT_NATIVE_ZOOM_BROWSER_GUARD
npx --yes --package @playwright/cli playwright-cli --session=hst-native-zoom-guard-r9 open chrome://settings/appearance --browser=chrome --profile=<ownRoot/browser-profile>
```

Agent shell commands must carry the RTK prefix. The future outer driver must
record launcher/provider isolation and actual Chrome argv, use unique CLI log
step names and prove physical exit. No executable outer orchestration has been
run or implied by these command shapes.

## Future gate B: application at native200%, measured CSS360

Only after native proof and a separate Root gate, reuse that own profile (or
revalidate200% through Settings if reopening) with a fresh R9 fixture authority.
Use the qualified small canonical long-name dataset, no pending question needed:
two registered harnesses/projects, one exact inert-protocol session/output.
The app phase should request viewport720, verify actual innerWidth~360 and the
same native DPR factor, then inspect all three stacked columns and actual
document overflow. Do not claim a360 outer viewport.

Close any visible navigation overlay through the HEADER button role
`Collapse navigation` when aria-expanded is true, then wait for `nav-sidebar`
to be hidden. These are actual App controls; do not invent a mobile-close testid.
Take screenshots showing the uncovered start of each column. Use hit-tests for
visible read-only actions. Open the known singleton via Follow activity, compare
the entire real RuntimeSession.scope, exact target and output marker, close and
verify the same project/context. No provider call, decision, Test or Finish from
the browser; normal canonical teardown and honest unknown outcomes remain gates.

This app phase is a plan, not implemented/executed by gate A. I04 light/dark
semantic badges may later be compared at real fixture phases with the existing
assertions, but no extra state producer or I04 matrix is added to the native-zoom
guard. Narrator, personal Chrome, global Windows settings, logout/reboot and
human invitations are outside this batch.
