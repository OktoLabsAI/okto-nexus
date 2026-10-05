# TN-40 supported recovery after backfill and execution

TN-40 PASSED at legacy_acceptance on Windows/Python 3.13 against the installed
NS15.05 artifact tuple. `test_ns15.py::test_tn40` reuses the NS15.04 restore
workflow with a nonempty legacy profile, versioned policy, pinned Agent policy
binding and restricted Agent permissions seeded before catalog backfill.

The real backfill completes without activating execution. Public canonical
binding/open/turn admission then reaches actual Core with a synthetic native
peer. The peer records one send and raises an uncertain-effect error. After
owner shutdown, the offline procedure snapshots and restores into a new home.
Nonempty policies, versions, bindings, migration map and canonical execution
history compare exactly before/after recovery. Public identity reads retain
permissions and authorization/configuration/credential revisions. The previous
operation remains non-retryable and no second native effect occurs.

Unsafe cases remain refused: no explicit quiescence acknowledgement, destination
overwrite and a snapshot missing a referenced Core journal even when its file
manifest is recalculated. Restored admission is disabled while uncertain effects
are inspected. This proves supported same-version snapshot recovery; it does
not claim reverse SQL migration, old-binary compatibility with a new schema, or
that restoring data undoes an external effect. Those unsupported operations are
explicitly excluded by the migration runbook.

`run_ns15_05.py --resume --campaign recovery` verified the installed wheel bytes
before running TN-40 and both original NS15.04 cases: **3 passed**. See
`evidence/ns15-05-recovery.xml`, `evidence/ns15-05-installed.json` and
`test_runs_20261001_tn40.json` for artifact/test hashes and command evidence.

All four scenarios attached to NS15.05 now have scoped passing evidence. Task
dependency acceptance and final M13/G0–G3 qualification remain open. The peer
and qualification flag are synthetic; this is not a live-provider or independent
remote-host campaign.
