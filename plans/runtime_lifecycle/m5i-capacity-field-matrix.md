# M5i physical capacity field matrix

The existing separate-process local Connector test now holds its authentic
durable `startup.refuse` publication and sends six distinct protocol-valid
reports over the current authenticated control channel. Each changes exactly
one physical capacity fact: reservation ID, attempt ID, host boot ID, affinity
digest, request TTL, or consumed turn intent hash. The Server defers all six
against its canonical admission. While the forged reports are held, the
opening remains `OPEN_PENDING` with no terminal receipt. The original report
is then accepted, releases the matching capacity, and the next handoff opens
and sends once.

Focused source-tuple campaign:

```text
python -m pytest -q tests/execution_r4/test_remote_startup_refusal.py -k forged_capacity
1 passed, 9 deselected in 49.83s
```

This extends the M5h real-process test without changing production code or
claiming a new installed-wheel or independent-machine qualification. It does
not yet cover native-action races, replacement-owner races, managed-adapter
containment, or the full reconnect/revoke/reset differential. Those remain
required before M5 and its real Nexus UI gate can close. The global Nexus
installation stayed stopped during this test.
