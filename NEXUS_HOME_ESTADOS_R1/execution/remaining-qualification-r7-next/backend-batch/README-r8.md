# Backend batch: strict R8 rebind, not executed

This preparation preserves the seven reviewed cases and every R7 preparation file.
The new runner requires the explicit Root gate and the exact SHA256 of
`PREPARED-r8.json`. It does not allocate a fixture or import the product before
checking the gate and immutable package inputs.

Runtime: source `6eaa325ea3ddf1dec1b03475b27f373211c81e53`, wheel
`fc2afcccdf55236db21071a132a353a13cf1c56399767ea5223a69e50162902e`.
The runner verifies 1829 frozen base inputs, 1031 installed wheel payload files,
and raw equality of the 1024 nonstatic R7/R8 runtime files. This equality does
not turn previous R7 executions into R8 test results.

Each selected case runs installed Python with `-I -B`, closed stdin, own sibling
CWD/TMP, copied tests without checkout `src`, a 180-second owned-command deadline,
and start/end module-origin guards. The first unsuccessful case stops the batch.
The final audit runs in `finally`, including on case failure: frozen source and
payload, test copies, helper closure, TypeScript/compiler/presentation copies,
external tooling, and R7/R8 nonstatic bytes. Owned-command records retain cleanup
and containment facts; no provider or personal credentials are permitted.

The live-state snapshot covers six explicitly listed tables, not the entire DB.
Shared-work correlation and E16 capture/artifact records are historical read
facts. E16 canonical verification/seen actions and source-copy presentation are
distinct from real execution, an installed browser, or human acceptance.

After a separate explicit Root authorization, the future command is:

```powershell
rtk proxy python -B -X utf8 NEXUS_HOME_ESTADOS_R1/execution/remaining-qualification-r7-next/backend-batch/run_installed_r8.py --gate ROOT_APPROVED_BACKEND_BATCH_R8 --manifest-sha256 <PREPARED-r8.json SHA256> --case all
```

Only AST, Ruff, and JavaScript syntax checks qualify this preparation. No pytest
collection, application fixture, or execution has occurred for this batch.
