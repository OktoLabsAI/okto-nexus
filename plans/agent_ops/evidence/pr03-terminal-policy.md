# PR-03 — reviewed native decision policy activation

Windows 11 `10.0.26300`, Python 3.13.1; Nexus `0.3.3`, branch
`feature/v0.3.3`. Connector `0.0.12` and Core `0.0.14` are unchanged.
This increment addresses the default-policy gap identified by terminal work.
R3, PR-03 and productive M1 acceptance remain incomplete.

The canonical setup read now describes the current `feature_hitl` policy and a
revision covering its effective value, source and stored record. A project
review can propose initialization only when no explicit setting exists. The
same terminal summary names the Server-wide effect: native decisions and
matching coordination approval rules become available, while actual decisions
retain their ordinary actor/recipient/expiry/scope authority. Nothing is approved
automatically and no administrative rights are given to the project agent.

An optional, strictly validated `native_decision_policy` request contains the
reviewed revision and initialization choice. Omission preserves old clients'
normalized request hashes and does not change policy. Test rechecks the policy
without applying it. Finish checks it again and uses the existing SettingsService
and transaction to persist initialization with identity, binding, grant and the
existing setup receipt. A late receipt failure rolls back the setting as well.
The live configuration is refreshed only after commit, under the same database
writer serialization as ordinary settings updates.

An already enabled policy is reused without rewriting it. Stored or CLI/env
`false` is preserved and diagnosed. A change between review, Test and Finish
rejects the stale request. Participants cannot initialize Server policy. Reconnect,
receipt recovery and repeated Finish do not re-enable a subsequently disabled
policy or reissue an execution grant. They may refresh the live cache from the
latest committed policy; the historical setup value is never replayed.

If the database commit succeeds but cache refresh fails, the API explicitly
reports a committed setup with pending activation and `possible_effect=true`.
Recovery uses the same receipt, then reads the current stored setting. Fault
injection verifies both recovery to the committed value and preservation of a
disable performed in that interval, without another model test or grant.

## Configuration provenance and service compatibility

Configuration resolution now retains which fields were supplied by CLI or
environment, including values equal to defaults. This closes the previous
heuristic gap where explicit `--feature-hitl false` could be treated as unset
and shadowed by a stored override. Programmatic configurations retain the
existing nondefault-value fallback.

Service arguments freeze all resolved values for reproducible launches. They
now carry separate, validated names of explicitly pinned settings. Detached and
scheduled entries pass that provenance through both bootstrap phases, so frozen
default arguments do not become operator policy. Reusing a saved context keeps
its provenance; only explicit new CLI overrides extend the known pins. Ambient
environment changes do not silently rewrite that saved service context.

Older contexts have no provenance metadata. They preserve their previous
stored-override behavior instead of disabling an already enabled policy during
upgrade/restart. Their ambiguous default cannot authorize project setup to
initialize a global policy. This is reported as `legacy-context`. The fallback
does not mutate a native task or replace the pending service-campaign plan.

## Validation

Retained development reports:

- `pr03-terminal-policy-source.xml`: 12 passing policy cases, before the added
  legacy-source case. The final installed suite includes that case too.
- `pr03-terminal-policy-regression.xml`: 82 passes and one real-process failure.
  It exposed the second bootstrap losing saved provenance; production code was
  corrected to propagate it to the actual dependencies used by the HTTP app.
- `pr03-terminal-policy-process.xml`: the corrected real-process case passed,
  including setting persistence after an explicit restart and final `DRAINED`.
- `pr03-terminal-policy-installed.xml`: final copied-test campaign against the
  coordinated wheels, including new and legacy service-context variants.

An earlier new-test import was accidentally named `setup_module`, a pytest xunit
hook. Renaming the module alias corrected test setup; no product behavior or
assertion was weakened. An additional development run of configuration, settings
and terminal connect passed 82 cases before final refinements. Overlapping runs
are not added together as a distinct coverage count.

The final environment is
`C:\Users\jpamb\AppData\Local\Temp\r3-terminal-policy-mwxt4l7a\validation`.
Tests and contract fixtures are copied outside checkout. `python -I -m pytest`
asserts all three package origins under that venv. All 423 Nexus, 114 Connector
and 130 Core Python wheel payloads match source bytes. Exact artifacts and
hashes are retained in `pr03-terminal-policy-wheels.json`; Nexus SHA-256 is
`7a3f3141e5065b5948f67102d296019d3c91859040ee0720a2bb5c8eccb59cf3`.

Installed targets cover terminal policy/connect/identity/work, canonical setup,
setup receipts/tests, HTTP-only CLI, settings, configuration, service launch,
user-service adapter, real CLI process and upgrade contracts. Runtime integration
uses real HTTP, authorization, SQLite, admission and Core with a synthetic native
peer. The new productive-control test performs reviewed initialization and then
delivers a canonical native approval without manually setting `feature_hitl`.
It is not qualification of real provider output or harness context.

Ruff `--select E9,F`, whitespace and the fixed-plan ledger coverage are checked.
No real provider, credential, personal service, native task registration, package
release or protected-branch merge is part of this increment.

## Remaining requirements

Terminal renewal of expired execution authorization is still open. Existing
configurations with explicitly disabled policy need a separately authorized
policy change; reconnect preserves those decisions. Remote operator/Connector
integration, participant setup, login-start review, preset evolution, dashboard
introduction and real local/remote provider/service campaigns remain required.
Generic coordination idempotency and the later ATN/OBS fronts are unchanged.
The pending isolated native-service campaign still awaits the original requested
authorization. This evidence does not complete DX-T39/40 or M1.

Final installed outcome: **267 passed, zero failures/errors/skips**.
