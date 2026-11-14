# v12 supplemental normal stop and neutral closure

This is a separate, explicitly selected cleanup operation for one retained v12
campaign. It does not modify any original source, receipt, proposal, reservation,
checkpoint, profile or product wheel. The prior normal stop returned before
`ServiceLifecycle.stop` reached the adapter's `request_stop`: pinned stdout reported degraded /
SERVICE_UNREACHABLE, with no shutdown or wait result; installed source hashes
match the proposal; control remained desired=running with no generation.
The original failed stop remains evidence, not a successful or replayed action.

Root reviewed a new **normal** selection. `stop_once.py` gates the exact original
proposal/receipt and frozen product/source pins, then checks the retained old
stop output, pristine control hash and checkpoint hash. It requires the exact
READY owner, PID 35400, birth 134391426803083035, generation
d8122008262b10e75ec4d1124dd91417, instance and native task digest. An exact process
handle remains held through the CLI. After one exclusive reservation it checks
control/checkpoint and live owner again, then executes only the canonical normal
stop argv already pinned in the proposal. There is no force, restart, direct
POST, custom service control write, provider call or automatic resubmission.

The reservation, child record, stdout/stderr and returned receipt go into this
candidate's ACL-protected `runtime-private`, outside the campaign. A failed spawn
or refusal after reservation preserves the reservation and prevents replay. The
canonical CLI bounds its observation; the parent never kills a timed-out child.
Invalid/non-object JSON output still records wrapper exit, returncode and hashes,
but reported state becomes unknown. No physical owner exit is inferred from CLI
exit. Root retains the original watcher and uses original physical cleanup and
uninstall helpers afterward.

Only after those actual proofs exist, root invokes `reconcile_final.py snapshot`.
It requires six fully returned local-only selections including Nexus uninstall,
the completed supplemental normal stop receipt, all final original cleanup
artifacts, no Connector/operator state, the unchanged sealed controller and
retained local profile. The snapshot stores actual hashes computed at that time.
There is no future-proof placeholder. It includes existence/hash of
`terminal/profiles/m1v12-local.json`, without exporting or interpreting profile
contents or reading authentication tokens.

Root then passes the snapshot's actual hash to `observe`, which reuses the
original selected Nexus physical-exit/uninstall checks, validates canonical
absence of both exact components, absence of both exact tasks and exclusive
instantaneous port availability. Original Connector generation-empty-string
validation remains strict. Inputs are compared again after observation. The
supplement exclusively creates `public/final-presence-reconciled.json`, never
pretending the original failure-only branch accepted configured setup.

`close` revalidates the supplemental evidence and unchanged snapshot inputs and
exclusively appends `public/closure.json` with status
`CLOSED_RECONCILED_CLEANUP_ACCEPTANCE_NOT_INFERRED`. It retains configured setup,
DEADLINE120, eight cumulative reservations, 22,178 newly observed tokens and
111,651 cumulative minimum observed tokens, and settled setup. No useful work,
permission cycle, final billing or M1 acceptance is inferred. The checkpoint and
profile remain available for an explicitly scoped future handoff without
repeating setup. Cleanup does not itself qualify that handoff.

All commands use the exact installed v12 Python with `-I -B -X utf8`, the original
four proposal/approval options and `--manifest execution-manifest.json
--manifest-sha256 <actual qualified hash>`. Run stop once. After physical cleanup
and uninstall, run `reconcile_final.py snapshot`, then `observe` and `close` with
`--proof-snapshot-sha256 <actual snapshot hash>`. These execution steps belong to
root; preparation ran none of them against the campaign.

Qualification is synthetic offline testing only. Initial 25 tests passed; root
requested preservation of the wrapper receipt for malformed output, then 27
passed. Root subsequently requested positive directory/profile retention guards;
29 tests passed. A final isolated-entrypoint import correction and two help-only subprocess tests produced 31 passing tests. All earlier XML results are retained. Changes, not a
failed test, justified each subsequent run. No real stop, cleanup, snapshot,
observation, closure or inference was performed during preparation.
