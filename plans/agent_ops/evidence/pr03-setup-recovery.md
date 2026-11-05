# PR-03 — recover the existing Server-hosted setup

Windows 11 `10.0.26300`, Python 3.13.1; Nexus `0.3.3`, Connector `0.0.12`,
Core `0.0.14`. All three remote mains were fetched and remain ancestors of the
feature branches. The full fixed R3 plan, PR-03 and M1 remain incomplete.
Connector commit `e365e9a` is pushed on `feature/v0.0.12`.

Nexus exposes an operator-only read of the existing `connection_setup_commits`
record, scoped to the canonical audit actor and setup request ID. The matching
recovery route normalizes the complete saved request exactly as Test and Finish,
then checks the durable hash. It returns the original result without applying
configuration, issuing another grant, or consulting a missing test cache.
The existing Finish retry lookup now uses the same audit identity as its commit.
No new database, migration, credential authority or execution mechanism is added.

Connector saves `prepared`, `test_submitted`, `finish` and `done` checkpoints in
its existing non-secret preferences. A submitted Test is only observed on resume;
a missing result reports possible effect and never submits another model turn.
Legacy `test` checkpoints are treated as possibly submitted. Resume first matches
the durable Finish receipt. Missing receipt support, authorization failure,
changed content and malformed receipts do not trigger setup replay. A confirmed
absence of Finish permits the existing canonical Finish path, with its original
request and revision checks. The Server-hosted wizard restores the saved review
before discovery or questions and rejects explicitly conflicting choices.

## Validation

- Nexus final focused source run: **9 passed**.
- Connector source run: **32 passed**, including wizard resume.
- Final installed coordinated run: **65 passed, zero skips/failures/errors**.
- Ruff and whitespace checks cover the changed code.

The first Nexus run had 28 passes and two fixture failures: creating a local
binding with an actor-less human context is not supported by every existing
creation service. The test was corrected to create through the normal operator
path and then exercise actor-less receipt recovery. A later test-only run lacked
the explicit asyncio marker for the three new integration cases; adding the
marker produced the nine-pass source result. These earlier runs are not acceptance
evidence. The final installed suite repeats all 24 canonical setup tests, all nine
recovery cases and the Connector cases.

The integration cases use the real Connector HTTP client, Nexus HTTP handlers,
authentication and canonical SQLite setup transaction. A transport bridge injects
lost replies after Test and Finish; only the harness's draft model turn is
simulated. After Finish reply loss and test-cache removal, the original binding
and single grant are recovered with no second Test or Finish. After Test reply
loss, the existing test is observed; removing its cache produces explicit
uncertainty without a second test. Server tests also cover both operator HTTP
prefixes, actor scoping, authorization, read-only recovery and changed-request
conflicts. Connector unit cases use the real atomic StateStore.

Installed validation uses a fresh environment at
`C:\Users\jpamb\AppData\Local\Temp\r3-setup-recovery-c4msbzfr\validation`,
with tests copied outside all checkouts. All three package origins are asserted
inside that environment before invoking `python -I -m pytest`. The final wheels'
415 Nexus, 114 Connector and 130 Core Python files are compared byte-for-byte
with source. Hashes are recorded in `pr03-setup-recovery-wheels.json`; the Nexus
CI Connector wheel/manifest are coordinated. Core source and its wheel are unchanged.

Commands: Nexus `.venv/Scripts/python.exe -m pytest
tests/execution_r4/test_connection_setup_recovery.py -q`; Connector uses the same
interpreter with `tests/unit/test_connection_config.py tests/unit/test_configure.py`.
Installed selection additionally includes `test_connection_setup.py`.
JUnit records: `pr03-setup-recovery-nexus-final.xml`,
`pr03-setup-recovery-connector.xml`, `pr03-setup-recovery-installed.xml`.

## Remaining scope

This is the existing Server-hosted setup path. The main Nexus `connect` entry,
versioned project preset, unified identity creation/review, actual restart
campaign, complete terminal work/decisions/results and productive local/remote
acceptance remain open. Test results themselves remain in memory. Cache loss was
injected; this increment does not claim a real process-restart campaign or a
durable provider-test journal. Older Servers cannot recover through the new
matching route and leave attempts unconfirmed. Existing Connector-hosted
proposal/approval behavior is unchanged. No real provider credential, inference,
personal native task registration, release or merge was used.
