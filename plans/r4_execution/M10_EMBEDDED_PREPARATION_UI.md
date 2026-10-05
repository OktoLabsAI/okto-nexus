# Embedded preparation in the installed dashboard

An authenticated operator can select this Server's embedded executor and one
published installation, then configure an existing absolute workspace directory,
an optional provider home, and protected credential references. The panel makes
clear that paths belong to the Server computer, even when the browser is remote.
Only an explicit checkbox and approval action submit the local realization.
The Server retains all existing operator, freshness, directory identity and
candidate drift checks. No new backend authority or execution path was added.

The operator may select an existing workspace or give a new workspace a name.
An existing workspace's display name and identity are preserved. The returned
workspace becomes selected, enabling the separate binding review/apply flow.
Preparation does not probe, launch a provider, issue a grant or approve a binding.
Remote hosts continue to configure their own paths through Connector CLI.
Ambiguous preparations are not resolved by list order.

The complete request is saved in tab storage before sending. Lost replies and
reloads retain the same consent, directories and request identity. Storage failure
prevents submission. A first explicitly rejected request can be corrected after
renewed consent; a retry of an uncertain request keeps its original body. Periodic
and manual inventory reads preserve an in-progress form while disabling writes
during refresh. Inventory drift/revocation still invalidates the selection.

## Installed evidence

`evidence/embedded-preparation-ui-055/` retains the first 25-pass campaign
(168.23 s), before the final text/existing-workspace refinements.
`evidence/embedded-preparation-reviewed-ui-055/` passed 27 checks in 185.24 s:

- Actual packaged Edge UI against production HTTP handlers and SQLite, with a
  synthetic passive installation and actual embedded inventory lifecycle.
- New-workspace preparation, separate binding approval and zero runtime effects.
- Lost committed reply, tab reload and identical request replay without duplicate
  realization/workspace/binding creation.
- Existing-workspace identity/name retention, including punctuation in its name.
- Plaintext credential input and browser-storage failures refused before HTTP;
  missing directory and revoked authority refused without persisted preparation.
- Existing binding consent/reuse, selection invalidation and local realization
  regressions, plus the installed NS15.05 documentation audit.

Both campaigns recorded unchanged inputs and exact installed package bytes.
The reviewed form and resulting approved-binding screenshots were inspected.
They are retained alongside the reports. Browser SSE and real native execution
are outside this test's scope; this is Windows Python 3.13.1 / Edge evidence.
Preexisting worktree static assets were preserved: the build rebuilt frontend
assets in an isolated source copy and tested those wheel-delivered assets.

Reviewed Nexus wheel SHA-256:
`9fb819ef17983f51c21809568fdfe877bd23bc0f83bccce1de8ce9f30632c78b`.
Reviewed sdist:
`8bf97d83bf6a5a1963e7ffcee9f0b339ef249273cb0c8b0599f26561eefcf6df`.
Manifest: `evidence/embedded-preparation-reviewed-build.json`.
The 27-case UI campaign used the previously pinned Connector wheel
`1c799154b2998035617bcfe2301cd9f4be7f3982dd7e797d7fd33b8dff6b252a`.

## Requested discovery display and updated issue #1

Connector `0385ed0` now defaults to a harness/count/status table and exposes
full details with `discover --verbose`; JSON remains complete and unchanged.
Twenty-eight installed tests passed on each of Windows and WSL Linux. Actual
Windows discovery found Codex, Pi and Claude without launching them. Its README
now prominently states the existing Windows/Linux executor requirement and
links the open native macOS design question. Updated
[issue #1](https://github.com/OktoLabsAI/okto-nexus-connector/issues/1) reports
improved doctor/Claude discovery on macOS but still no native containment or
Codex/Pi candidates there. No issue closure or future support decision is inferred.

Nexus now vendors that Connector wheel, SHA-256
`5572e7fdaf8e36e17dc64a9b9e71f9c27d59b2762c812c5ebc2d8eab7e8df44b`.
With the reviewed Nexus wheel and unchanged Core .55 wheel
`b1a389d247a470571c485e27adfa7277b11b4ae39382a52ebefc0ef0cc76453f`,
21 installed Windows discovery/inventory/daemon/refresh checks passed in 104.60 s.
Evidence: `evidence/discover-summary-consumer-055/`, unchanged inputs.
This directed consumer run is distinct from the earlier UI campaign's tuple.

Build observation/probing in the embedded panel, runtime operations, ambiguous
selection, full onboarding/delegation and platform/provider/fault acceptance
remain open. Final freeze and current full CI/regression are not implied.
Independent-machine acceptance remains the later manual session with the user.
NS15.05, M13 and G0–G3 remain open.
