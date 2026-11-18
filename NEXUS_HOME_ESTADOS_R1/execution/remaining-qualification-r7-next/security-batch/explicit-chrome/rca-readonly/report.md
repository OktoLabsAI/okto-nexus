# Read-only RCA of S1 explicit-Chrome timeout

Status: **cause not established / no new execution**. The original cut remains
FAIL/inconclusive. No application/browser was started for this analysis and no
prefix, personal configuration or profile was changed/read. Only ownTemp logs,
package files, metadata and the already named executable bytes were inspected.

Cut `hst-security-r8-s1-explicit-chrome`, ownTemp
`nexus-hst-browser-ivittakz`: `open` exceeded the40s command deadline with zero
stdout bytes. No Home navigation,30-table comparison or revocation assertion
was executed. The application exited normally; its own CLI/browser processes
were contained by exact PID/birth/exe and all were absent afterward. Previous
qualification and instrumental manifests remain unchanged.

## Literal observations

- The effective npx cache contains `@playwright/cli` **0.1.24**, with
  `playwright`/`playwright-core` **1.66.0-alpha-1794252756000**. The package's bin
  maps `playwright-cli` to `playwright-cli.js`.
- All four prior contract hashes match: CLI README, CLI package.json,
  `playwright-core/lib/tools/cli-client/session.js` and `coreBundle.js`.
  This was not a different CLI/schema version.
- Own npm log records successful registry metadata/tarball responses. A
  separate CLI update-notifier `npm view @playwright/cli version` exited0.
  The main npm log has no terminal success record because the supervising cut
  ultimately contained its pending command.
- Controller birth: `1794955271.013036`; CLI daemon Node birth:
  `1794955275.9764152`; first Program Files Chrome birth:
  `1794955276.5212755`. Chrome therefore existed about5.508s after the controller
  began, well before its40s deadline. Package discovery/download did not prevent
  this launch. These timestamps are diagnostic phase metadata, **not** a
  latency/SLO benchmark or proof that downloads caused/no longer caused a wait.
- The own-profile `Last Version` says `157.0.8103.51`; no browser `--version`
  command was run. The explicit executable/config hashes remained intact.
- Daemon `.err` is zero bytes; no `.session` file survives. The CLI source
  collects daemon stdout while awaiting `Daemon listening on`; browser creation
  and backend initialization precede that marker. However, cleanup can remove
  session metadata. These post-exit files cannot distinguish browser handshake,
  backend initialization, daemon readiness, or the subsequent `open` tool wait.
  **No specific blocked function or incompatibility is proven.**

## Separate environment finding

The own npm debug logs contain a `config load:file:C:\Users\jpamb\.npmrc`
line even though HOME/USERPROFILE/APPDATA/LOCALAPPDATA and npm cache/userconfig
were own paths. This analysis did **not** inspect that personal file, establish
whether it exists, or read any credentials. A log mentioning an attempted
configuration path is not proof of its contents being consumed. The completed
cut must not be described as proving that npm considered only own config.

## Smallest justified next diagnostic, subject to a new Root gate

Do not rerun the full S1 fixture blindly or increase its deadline by inference.
The existing CLI JS in this own cache is available read-only:

`.../npm-cache/_npx/31e32ef8478fbf80/node_modules/@playwright/cli/playwright-cli.js`

Entry SHA256 `a174d071b97fd0480e9ff25625d7bc2880f8a795152236360a6808e74ccaf614`.
Installed Node executable `C:/Program Files/nodejs/node.exe` SHA256
`3331e1ffe19874215472217c5e94f5a0c6d8e18c4ac7111d3937aa0ad5e9b4a5`.

A new approved **browser-only** own about:blank diagnostic could invoke this
pinned entry with explicit Node and Chrome/config, own profile/environment and
`NO_UPDATE_NOTIFIER=1`. That avoids npx resolution and its observed npm config
search, including the CLI's optional npm update check. It is an instrumental
reduction, **not a proven fix** for the Chrome/daemon wait. Capture bounded
Playwright launch/connection debug logs plus exact own process births and normal
close/physical exit; preserve failures and secrets only in ownTemp. It requires
no Server, native peer, provider, package/browser installation, CDP attachment,
personal profile or environment restoration. Root must approve/bind it before
any execution. No such diagnostic or runner was executed/prepared here.
