# Dashboard binding review and reuse — 2026-10-02

Runtime-options now returns a path-free preparation reference for an authorized
operator when exactly one current pending realization matches the selected scope.
It also returns the canonical binding view when the binding is unambiguous. Reads
still use one transaction, perform no provider I/O and grant no execution authority.
The HTTP application schema defines these optional projections; Core remains the
authority for its catalog and inventory schema.

The dashboard can prepare a proposal for a host-published realization, show the
agent/host/workspace/installation scope, request explicit approval and apply the
exact proposal revision and diff hash. It never asks for profile JSON, connection
keys or remote provider secrets. Existing bindings are reused on subsequent visits;
disabled/stale bindings are not described as ready to reuse. Connection names are
human aliases rather than caller-invented canonical IDs.

The client saves each immutable request in tab storage before sending it. Storage
failure prevents submission. A lost response retains the original apply identity;
the operator can retry that same request or read the known binding. No mutation
is retried automatically. Expired reviews require explicit renewal, and a saved
apply request remains uncertain on a recovered review until checked. The Server
continues to revalidate freshness, revocation, scope and authority on apply.

## Evidence and limits

Source runtime-options checks passed 14 cases and the initial browser consent
campaign passed three cases. The first installed campaign had **13 passes and
11 failures** with unchanged monitored inputs. Ten failures were a new test's
incorrect use of historical inventory schema v1 instead of the installed Core's
current schema; the other was a Playwright fault-injection expression that invoked
the throwing function before clicking. The package did not change to fix them.

After correcting those test inputs, **18 installed cases passed in 68.79 seconds**:
14 runtime-options checks and four real Edge consent cases. They cover explicit
approval, reuse without a second binding, response loss after actual Server commit
with same-body/id retry, stale inventory between review/apply, and storage failure
before transmission. Every installed package file matched its wheel. Campaign
hashing now includes `plans/contratos`, and corrected campaign inputs were unchanged.
The six unaffected directory-selection/NS04/OpenAPI cases from the first campaign
retain their pass scope: 24 distinct cases across both campaigns, not a fresh
24-pass full run. See [initial campaign](evidence/binding-consent/initial/campaign.json)
and [corrected campaign](evidence/binding-consent/corrected/campaign.json).

The browser uses the wheel's built HTML/JS/CSS, isolated Edge and real FastAPI
application routes via TestClient. The host inventory/control-ready state is a
synthetic fixture; SSE is stubbed. No native provider, independent host or real
network acceptance is claimed. One binding and no operation, session or execution
grant remain after successful consent. No Connector is installed by the UI.

Development wheel SHA-256:
`ddf275b2b837ffa1b3a3a819aa5f31f759f69497e2a4061cc3ff112fefe627ce`.
Development sdist SHA-256:
`f13badb873f6081caeddfd965455444af3a2f2db6159abd962e97a1f532ca25a`.
Both were built from an isolated source copy with fresh frontend compilation,
preserving the user's preexisting static worktree files. These are not M13 final
artifacts. [Build manifest](evidence/binding-consent/build-manifest.json).

NS13.02 remains partial: first-use embedded preparation, ambiguous preparation/
binding selection, full local/remote reuse journey and normative acceptance remain.
Runtime start/control, complete operator execution delegation and independent-host
acceptance also remain pending. M13/G0–G3 are not closed.

## Full CI regression finding

Nexus run `36966572607`, job `110711519150` (Ubuntu 24.04 / Python 3.12, commit
`0e9274b8b32a8072f75083399e4a5bbc387bcc42`) completed with **43 failures, 3,461 passes,
55 skips and one error** in 4,813.27 seconds. The whole matrix was still running
when inspected. Retained failing node IDs and the log hash are in
[CI findings](evidence/binding-consent/ci-linux312.json).
Failures include stale surface/migration expectations, retired stdio/legacy-native
paths, an undeclared `rtk` executable in a test subprocess, tool-description checks,
and authorization/lock cases that still need investigation. They are not all
classified as fixture-only. This evidence supersedes merely waiting for that cell;
the failed cell must be repaired and revalidated before release.
