# V13 authorization import reconciliation

The original `authorize_local review` exited 1 while importing `publication`,
before controller construction, internal reservation or HTTP dispatch. Its
original reservation, stdout, stderr and returned receipt remain unchanged.

The supplement binds that failure and the exact empty controller checkpoint.
It reuses the original `invoke.dispatch` to hold the child process and write a
separate durable ledger in this directory's `runtime-private`. Only the child
entry changes: the shim loads the pinned `publication.py`, then calls the
unchanged original authorization driver with its original arguments. This is
an explicitly changed import environment, not a claim that the original failed
invocation succeeded.

Root uses the original v13 proposal and technical receipt arguments, plus:

```text
<installed-python> -I -B supplement.py --manifest <manifest.json> --manifest-sha256 <SHA> <original common args> review
```

Run review once. If the grant is canonically available with at least 240 seconds
remaining, use it without issue. If it is canonically expired with zero of 20
actions used, root may write the original exact review selection and run the
same command with `apply`. All original scope/CAS/recover-before-issue/freshness
and one-issuance guards remain. No model or setup request is introduced.

After the selected supplement phases have returned, root runs `verify-exits`
with the same arguments **before** the original final-presence and closure.
This creates `CONTROL/public/authorize-import-supplement-exits.json`, binding
the separate retained child-exit ledger and preserving the original exit 1.
Retain this sidecar with the original presence/closure evidence; it proves exit,
not successful authorization. A missing returned receipt refuses the proof.

Qualification: 17 passed, including fresh `-I -B` subprocesses with no pytest
path inheritance: the original fails at `publication`, while the pinned preload
confirms the exact module origin and reaches a synthetic controller boundary.
No controller, service, HTTP, provider, credentials or model is accessed by the
test. Attempt 001 had 15 passes and two fixture failures because replacing the
`Popen` class with a function broke a stdlib subclass during import; the fixture
now retains the class interface and refuses actual construction. The failure
XML and original manifest are retained.
