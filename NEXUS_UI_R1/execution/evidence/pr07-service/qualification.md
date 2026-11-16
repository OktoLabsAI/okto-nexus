# UI-R1 service regression qualification

These are **13 PASS and 3 retained fixture FAIL**, not a green 16-test campaign.
No product, ledger or Git changes were made by this qualification.

All four invocations used the packager's explicitly allocated isolated Python:
`C:/Users/jpamb/AppData/Local/Temp/nexus-ui-r1-packages-wry3ter9/venv/Scripts/python.exe -I -B -Xutf8`
with `tests/ui_simplification/run_service_qualification.py --surface <surface>`.
The stable installed cut was Nexus 0.3.5 / `index-CdDUCMon.js`, Nexus wheel SHA256
`d596027d5a75620c502cf1337c1b96196da51e82ddd6bb3780d324024cdc2972`
(reported by the packager), Connector 0.0.13 and Core 0.0.14. Each run records
its actual module origins, full installed-package payload digest before/after,
selected test source hashes and case outcomes. All package and selected-test
comparisons were unchanged. Checkout product `src` was not inserted into imports.
The packager deferred reinstalling until these processes had finished.

| Surface | Result | Scope | Evidence |
|---|---|---|---|
| nexus | 5 PASS, 345.69 s | Two actual CLI/service subprocess cases and three actual Server process replacements with inert remote native peers | `nexus-qualification.json`, `nexus-tests.xml` |
| nexus-passive | 4 PASS, 1.89 s | Canonical status on absent instance/missing discovery root, no Popen, and remote target not silently treated as local | `nexus-passive-qualification.json`, `nexus-passive-tests.xml` |
| connector-controls | 4 PASS, 5.37 s | Persisted enable/disable and upgrade controls with FakeTasks; actual CLI subprocess status/logs/doctor on an absent own instance | `connector-controls-qualification.json`, `connector-controls-tests.xml` |
| connector | 3 FAIL, 3.70 s | Existing configure-login fixtures fail the current bounded-supervisor proof; no real scheduler or process was started | `connector-qualification.json`, `connector-tests.xml` |

The real process tests assert that an absent-home plan creates no home, a
completed launcher leaves the Server alive, the next connect uses the same
PID/generation, restart changes generation while preserving stored settings,
and explicit stop reports drained. The legacy service-context variant also
passes. The connect target in these cases is deliberately missing: they do not
demonstrate creating an additional harness connection against that process.

The restart cases complete and close a synthetic native session first, then
crash the exact own Server process after verifying its PID, Windows birth time
and parent. They respect the previous dispatcher lease before replacement.
The same Connector daemon task reconnects; installation/identity, binding and
workspace tuples, profile/model, grants/budgets, old operations and receipts
remain unchanged. Expired/revoked grants remain refused without native effect;
the valid-grant positive control admits only explicit new work and spends one
additional unit. Six own Server identities have positive recorded crash exit or
canonical drained exit in `owners-test_server_restart_preserves_*.json`.
This does **not** demonstrate survival of an active native session or an
OUTCOME_UNKNOWN operation across the crash.

The three old login fixtures replace WindowsTasks, IPC, process status and
spawn, but declare a running supervised process without producing the current
bounded-parent receipt. Production returns
`DAEMON_UNAVAILABLE / SUPERVISOR_OUTCOME_UNCONFIRMED`. The failures were retained;
no guard was weakened and no additional mock was added to invent ownership.
The four passing lower-level controls do not replace the missing onboarding
composition test. That test needs a fixture that generates the real current
supervisor/control receipt with a correctly matched injected parent/child
identity, then exercises Resume/Add; no real login task is required to test that
composition, but its ownership proof cannot simply be omitted.

There were no native provider/harness executions, personal credentials, native
scheduled-task mutations, Windows session events or global service changes.
Native peers and task-driver boundaries are explicitly synthetic. The new Home
projection delta being built in parallel was not exercised or certified by
these installed CLI/lifecycle tests. Relay/rollback and full scenario limits
are listed in `scenario-audit.md`.

`cleanup.json` records no remaining own Python process and physical removal of
all four exact private allocations. Only sanitized metadata, JUnit reports and
owner proofs were retained. Private homes, generated credentials and server
logs were removed rather than copied into the repository.
