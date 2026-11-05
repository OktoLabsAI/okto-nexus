# PR-03 — reviewed execution authorization from the terminal

Windows 11 `10.0.26300`, Python 3.13.1. Nexus `0.3.3`, branch
`feature/v0.3.3`; Connector `0.0.12` and Core `0.0.14` remain unchanged.
This is the terminal authorization subset of DX-15/17/19/20, not full M1 acceptance.

`work authorize` and `/authorize` show the existing project identity, grant states,
permitted actions, exact expiry and action budget. The operator approves the
displayed hash or explicitly answers `y`. The default is 60 minutes and 20
actions; bounded choices remain within the canonical 24-hour/1000-action limits.
The deadline starts at review. Waiting for approval or recovering a lost reply
does not move it. An available grant covering the project actions prevents a
redundant issuance. A narrower existing grant is preserved and its actions are
displayed before any explicitly reviewed project authorization.

The API uses `RuntimeAccessService.issue`, the existing policy checks and the
ordinary `runtime_execution_grants` table. Its review hash captures identity,
binding, endpoint/profile, policy and all existing grants, including consumed
budgets. It validates the subject's action authority before committing. The
existing setup and renewal share their project action set; Connector unlimited
limit normalization remains intact. The added migration 158 stores only issuance
receipts keyed by authenticated actor and stable client request ID.

Issuance and receipt commit together in one IMMEDIATE transaction. Same-ID
concurrent requests recover one grant; different stale reviews conflict after
the first commit. Changing an ID's content conflicts. A late receipt failure
rolls back the grant. Participants cannot review, issue or recover operator
authorizations. No administrative credential is distributed to the harness.

The terminal saves the request before HTTP. Unknown transport/server failures
retain the submitted checkpoint and report possible effect. Recovery authenticates
against the same Server and reads the original matching receipt before any retry.
This remains possible when the project configuration has changed after issuance.
A subsequent revocation is preserved: a receipt is evidence of historical
issuance, not proof of current readiness. Review presentation is bounded to 50
records and reports truncation; all grants participate in the server-side check.

Existing grants, leases and sessions are not revoked, rebound or replenished by
renewal. A new opening without an explicit source prefers a productive grant with
remaining budget; existing leases continue to require their exact source grant.
Expired/exhausted sessions do not silently gain the new authorization. The user
can inspect or explicitly close the old session and request a new one. Issuance,
observation, reconnect and service restart do not submit or resume project work.

## Validation and artifact provenance

- `pr03-terminal-authorization-source.xml`: 18 passing HTTP/SQLite/Core cases
  before the added limited-scope selection and generic-error presentation cases.
- `pr03-terminal-authorization-selection.xml`: the additional case proves that
  new productive work selects the newly reviewed grant while the old open-only
  grant remains unchanged.
- `pr03-terminal-authorization-uncertain.xml`: a generic failure injected after
  commit stays uncertain until recovery returns the one durable receipt.
- `pr03-terminal-authorization-installed.xml`: broad installed regression suite
  on the initial candidate: **247 passed, zero failures/errors/skips**.
- `pr03-terminal-authorization-final.xml`: focused installed validation of the
  final package, including the generic-error correction and clearer display of
  prior grant actions: **30 passed, zero failures/errors/skips**.

The initial installed candidate is under
`C:\Users\jpamb\AppData\Local\Temp\r3-terminal-authorization-lfcffm_9`;
Nexus SHA-256 is
`c27ed2f0ac3bf9486da74e122987769164087525893271b14dc2ae4a92ac7df4`.
The final candidate is in that directory's `final` subdirectory; Nexus SHA-256 is
`27b08d4aea423845eab600bcffd152df04262f17c0fee0fdabc967d705123fab`.
Each campaign installs coordinated Nexus/Connector/Core wheels in a fresh venv,
copies tests and contract fixtures outside checkout and checks all three imports
under site-packages with `python -I`. There are 424/114/130 Python payloads.
The final payload audit and exact hashes are retained in the accompanying wheels
JSON. Reports are separate; overlapping runs are not added as distinct coverage.

Development failures identified a missing dashboard route allowlist entry, a
test querying the lease grant from the wrong table, and a test snapshot taken
before its synthetic completion event was ingested. These were corrected without
weakening authority or the unchanged-session assertion. The existing Connector
limit normalizer was retained in its original module and is covered by regression.

The broad campaign covers terminal setup/identity/policy/work, canonical grants
and delegation, bounded/unbounded authorization, operator commands, session reuse,
leases/capabilities, migration history, HTTP-only CLI and retired-contract references.
The final campaign covers the full renewal suite, HTTP-only CLI and Connector
limit normalization. Native/model peers are synthetic; HTTP, authorization,
transactions, admission, dispatch and receipts are real.

## Remaining acceptance

Ruff `--select E9,F`, whitespace and fixed-plan ledger coverage are checked before
commit. This campaign does not qualify a real provider, external process context,
remote operator/Connector onboarding, native user-service registration or productive
local/remote M1 work. Start-at-login review, participant setup, preset evolution,
dashboard introduction and the remaining ATN/OBS fronts stay open. The pending
isolated native-service campaign retains its original approval request. No personal
service, provider credentials, native task, release or protected-branch merge is
changed by this increment.
