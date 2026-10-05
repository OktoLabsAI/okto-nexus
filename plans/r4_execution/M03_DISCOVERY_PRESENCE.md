# Installed providers missing from discovery — 2026-10-02

The user's report was reproduced: PowerShell found Claude, Codex, Pi and Node,
but the installed Core .53 inventory was empty. Trust filtering hid Claude;
Windows npm/managed launch layouts were not resolved for Codex/Pi. Empty
availability therefore incorrectly suggested NOT_INSTALLED for installed tools.

Core .54 (`1c7cf79`) separates passive observation from trust. PATH candidates
outside approved physical roots remain untrusted and require selection. Windows
fixed package payloads are read without executing/interpreting their wrappers.
Existing preparation/probe guards refuse untrusted candidates. Connector
`07e78f2` uses the same public facade for its standalone preview and registered
daemon. No macOS containment support or arbitrary wrapper interpreter was added.

Nexus now pins .54 in package dependencies, the executable inventory adapter,
the vendored wheel, CI artifact manifest and lockfile. Its local-discovery test
asserts visible-but-untrusted observation, followed by selected trust under an
approved root with the same physical reference. The lockfile was updated after
the campaigns and `uv lock --check --offline --find-links vendor/wheels` passed;
it is not shipped in the tested sdist and no application bytes changed afterward.

## Evidence

- Core installed Windows: 64 discovery/trust/layout checks and 15 inventory/
  conformance checks passed. Linux: 59 passed, five Windows-only skips.
- Connector installed Windows: 36 passed, one platform skip; Linux: 34 passed,
  three platform skips. Documentation audit: 34 commands and 12 links passed.
- Fresh Windows Python 3.13.1 environment, wheels plus declared dependencies,
  no editable packages: actual CLI in an independent working directory found
  all three providers in 13.50 seconds. All remained untrusted; Codex/Claude were
  NOT_PROBED, Pi 0.87.1 PREPARATION_REQUIRED. Installed Python bytes matched wheels
  and dependency check passed. See Connector's DISCOVERY_054.md and evidence.
- Nexus installed Windows/Python 3.13.1: **57 passed, 327.93 seconds**; WSL Linux/
  Python 3.12.13: **57 passed, 186.48 seconds**. Same three wheels on both systems;
  all package trees matched and monitored inputs remained unchanged. Covers local
  discovery, Core inventory/protocol, runtime-options, embedded inventory, local
  realization and HTTP refresh. See `evidence/discovery-054-adopted-{windows,linux}`.

The initial Nexus campaigns each had 19 failures, eight passes and 30 setup
errors: all failures/errors identified the internal .53 version check omitted
from the first dependency update. Those failed campaigns remain in
`evidence/discovery-054-{windows,linux}`. Updating the internal pin and rebuilding
produced the successful campaigns above. The assertion expecting absence before
trust was also updated to the new explicit visibility contract.

## Artifacts and limits

| Wheel | SHA-256 |
|---|---|
| Core 0.2.54.dev0 | `e79c4b9ccc5205bd2cfd05f750dbef543d771355e85c6853975f22367d36b9ff` |
| Connector 0.5.0.dev0 | `f5a5df5e38f52857f0ffa415b524507d86ceae3cde96ea7b6121d1ab09f43696` |
| Nexus 0.2.0 | `d58c5c04bd4d225597472ac0c07f5f8f543ae5462109ebb11f1b226593f06c10` |

Nexus sdist: `7b6c6df14915d8f2ba8cd164077cd34e6efb6e6d13a5d797349b2ace9dfad3e5`.
The build used an isolated copy and preserved the user's static assets/deletions.
The global development CLI separately has old Core .10 with an editable current
Connector; it was not replaced by this isolated validation. Updating that machine
requires the compatible pair, not just checking the shared development version
number of the Connector.

These are development artifacts. Hosted .54 CI, complete regression, all required
provider/OS/Python cells, independent-host runtime acceptance and full dashboard
onboarding remain open. G0–G3 are not closed. Prior .53 acceptance remains scoped
historical evidence rather than proof of the .54 final tuple.

User-directed acceptance boundary: cross-machine acceptance will be performed
manually with the user's participation. Continue automated/local and remote-process
testing on this machine for now. Do not count those results as independent-host
proof or repeatedly request the other machine while this work can progress.
