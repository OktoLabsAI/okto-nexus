# Read uncertain operations after executor readiness loss — 2026-10-02

A real browser fault-injection test exposed two barriers to recovery after a
native effect lost its confirmation. First, the selector disabled recorded
installations whenever inventory became offline/stale. Second, runtime-options
omitted existing bindings whenever execution eligibility was false. Together
these prevented re-opening the operation panel after reload precisely when the
operator needed to inspect an uncertain operation.

The selector now allows read-only selection and retains an unchanged selection
when freshness alone changes. Preparation, binding approval and new runtime
start are marked unavailable. Runtime-options now projects an existing authorized
binding separately from execution eligibility. It still refuses ambiguous
bindings and keeps all eligibility flags false for offline/stale inventory,
disabled feature or disabled method. Neither reads nor UI selection consume a
grant. Revoked hosts continue to be removed from the selection directory.

## Installed evidence

`evidence/uncertain-runtime-ui-final/`: **17 passed in 195.34 s**, Windows/Python
3.13.1 and headless Edge, PASS/exit 0/changed_inputs=[]. Real installed HTTP,
Core, dispatch and SQLite services handle a synthetic native peer that executes
one send and then raises OUTCOME_UNKNOWN with possible_effect=true. The resulting
operation enters RECONCILING and readiness is lost. Two browser reloads and
explicit result checks preserve the stored request, create no additional POST,
admit exactly one turn and execute exactly one native send. The UI offers no
replacement or replay action for that uncertain operation.

The campaign also covers runtime-selection identity/order/revocation, existing
runtime-options policy cases, explicit binding visibility under readiness loss,
zero grant consumption and NS15.05. It does not forge successful resolution or
claim that a read repairs the native outcome.

Wheel SHA-256: `d07e746c8e71b842eb944ecd0244432cb66a7098bc0f599a91474c1422e30a44`.
Sdist: `0e210c4b371d34e668ec2ae5e581d537289eb722c3fa9febb8ee81ecac4d3549`.
The isolated build freshly compiled TypeScript/Vite and preserved preexisting
static assets. Shared Core .56 and Connector wheel hashes remain
`7f19885f28b16dbfce66b969ab42c79b9947246416c71147315006b6e618b1f6` and
`93d78a75c5ad81bbdd96e648be136f0f6b2cfd0a53f350266a1c9f96fc449104`.

Retained failed campaigns: `uncertain-runtime-ui-initial/` exposed the disabled
selector on the session-browser wheel; `uncertain-runtime-ui-reviewed/` had one
selection pass and one recovery failure after the UI-only fix because the API
still omitted the binding. The final change fixes both layers. Tests retain the
original effect-count and uncertainty assertions rather than relaxing them.
Reproduce using the installed runner and test selection in campaign.json, with
OKTO_NEXUS_UI_CAMPAIGN=1 and OKTO_NEXUS_UI_INSTALLED=1.

## Remaining scope

Recovery here means recovering visibility and the original request identity.
Native outcome reconciliation, arbitrary uncertain-process containment, archive
access when an installation disappears entirely, and old-epoch browsing remain
open. This evidence does not qualify real provider faults, independent hosts,
macOS, final clean installs or G0–G3. Hosted CI remains deferred.
