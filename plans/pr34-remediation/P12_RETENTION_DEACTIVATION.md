# Retention and canonical Agent deactivation

2026-09-24, feature/v0.2.0, parent7897abab75b78100af9e9eb82df1a4410e2c3fcc.
T-MIG-09 acceptance uses the actual authenticated HTTP/MCP app and disposable
stores. Only the external peer is synthetic; no provider or user store is used.

New test_runtime_retention_identity.py checks a pending unsent intent and an
uncertain attempt after a simulated write/response loss. Operator deactivates
the Agent and runs real REST admin pruning twice. An expired unrelated message
is removed; the original old message, delivery, outbox, attempt observations and
causal nodes survive exactly. Pull cannot claim the reserved delivery, FK checks
are clean, and reactivation does not replay an uncertain write. Pending test
pauses dispatch only; it does not claim that a safely unsent pending operation
can never resume under new explicit authorization.

A third test checks an old command idempotency key across pruning and Agent
deactivation/reactivation. It reproduced an authorization defect: operator
admission through an existing session omitted the represented Agent's active
flag. The existing open path and delegated paths already check this flag.

Behavioral REDs against parent production source:

- Windows18856:2 PASS/1 FAIL10.99s; repeated MCP send key was accepted while the
  represented Agent was inactive.
- Strengthened fresh REST admission assertion:1 FAIL/2 deselected5.72s. A new key
  returned200/PENDING instead of403. This proves the gap is not merely access to
  an old reply; a new command was admitted.

RuntimeAccessService.authorize now checks canonical target activity for open,
send, steer and execute_work before operator/boot/delegation selection and before
idempotent admission. It leaves read/interrupt/close recovery actions available.
No new table, migration, public field or second work queue is added. Pruning
itself required no correction: existing durable-reference exclusions held.

## Validation

Windows78221:44 PASS140.13s and Linux32819:44 PASS157.19s, both exit0, using:

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_retention_identity.py tests/test_runtime_grants.py tests/test_runtime_configuration_updates.py tests/test_runtime_commands.py
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short tests/test_runtime_retention_identity.py tests/test_runtime_grants.py tests/test_runtime_configuration_updates.py tests/test_runtime_commands.py
```

Ruff passes for both changed source/test files. No full suite or native campaign was repeated for this unit.
Remaining original matrix/crash/load/performance/build/install gates remain open.


After expanded gates, the test added explicit operator read and durable close
while the Agent is inactive. Production source was unchanged. Final module gates:
Windows35602:3 PASS13.14s / Linux32734:3 PASS16.42s, both exit0.

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_retention_identity.py
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short tests/test_runtime_retention_identity.py
rtk proxy ruff check src/okto_nexus/application/runtime_access.py tests/test_runtime_retention_identity.py
```

Exact final source hashes, expanded-test variant hash and outcomes are recorded
in evidence/p12-retention-deactivation.json. T-MIG-09 scoped acceptance PASS;
no phase/final gate promotion. No live processes remain from this unit.
