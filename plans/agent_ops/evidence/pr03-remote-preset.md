# PR-03 — Remote project preset and policy review

Remote existing-identity onboarding persists project-generalist revision 1 outside portable JSON and includes its native-decision policy effect in the immutable operator review. Approval and Finish revalidate current policy; explicit false values, pins and legacy provenance are preserved. Configuration, origin, grant and optional policy initialization share one transaction; live policy refresh follows the outer commit. Typed uncertain outcomes resume the same apply intent through Connector background recovery without restoring later disablement or revoked grants. 22 Nexus and 37 Connector source tests passed; 127 Nexus and 285 Connector tests passed in fresh installed artifacts. New remote identity bootstrap, real two-host provider qualification and full M1 remain open.

New default Connector-hosted wizard requests use per-sender sessions, the existing
native permission path, ask for Nexus tools, and request 60 minutes/20 actions.
Preferences remain editable. The origin marker is stored with the durable binding
intent and sent separately from portable configuration. Schema 16 preserves old
intents without adding a preset. Imported JSON and old saved wizard requests do
not implicitly request policy initialization. New origin revisions are refused.

The Server resolves the exact native-decision policy revision during prepare.
The operator summary names Server-wide human review and its effect on native
decisions and matching coordination approval rules. Participant confirmation
cannot authorize it. Even automatic replacement of another machine requires an
operator review when this new effect is requested. Explicit stored false, CLI/env
pins and ambiguous legacy context are preserved. Policy drift before approval or
application refuses the stale review. Existing enabled policy is not rewritten.

The shared canonical Finish runs inside the binding transaction. It stores origin,
configuration, grant, policy and receipt together. A late binding write failure
rolls all of them back and leaves the live policy unchanged. After commit, a
separate refresh reads current stored policy. Failure at this boundary returns
OUTCOME_UNKNOWN with possible_effect/retry_safe so the original apply can resume.
Receipt replay never regrants or overwrites a later disablement/revocation.

The installed cross-repository test uses the real Connector StateStore, HTTP
client, background onboarding, Server authentication, approval API, Finish and
SQLite transaction. It reopens Connector state after the human terminal decision,
injects postcommit cache failure, then recovers the original apply intent. The
Connector sends only its participant credential; the human cookie stays on the
operator client. One proposal, approval, binding and grant remain.

## Validation

- Nexus focused source: **22 passed**. Connector focused source:
  **37 passed**. The final background cache-loss injection was added after the
  Nexus source run and is included in the installed campaign.
- Final installed Nexus: **127 passed**; final installed Connector:
  **285 passed**, no failures/errors/skips. Suites cover remote
  presets, operator review, machine replacement, canonical setup, local policy
  and terminal regression; Connector covers schema migrations, HTTP contracts,
  saved onboarding, login review and daemon admission/control. Counts overlap
  source runs and are not summed as unique coverage.
- The first source run exposed an error-handler assumption that empty details
  were a dict (15 failures/7 passes); it now handles None and preserves refusal
  responses. A Connector test initially used an invalid session policy (1 failure/
  36 passes); it now uses supported shared sessions to check imported overrides.
  Both focused suites passed after correction. No failed candidate is pinned.
- Ruff E9/F and whitespace checks passed on the changed production and focused
  test modules. The fixed R3 ledger is checked before commit. The 431/116/130
  package Python payloads match source bytes; python -I imports resolve inside
  the fresh installed environment, outside both checkouts.

Campaign: `C:\Users\jpamb\AppData\Local\Temp\r3-remote-preset-f67w6ml_`.
Commands: `rtk proxy .venv/Scripts/python.exe <campaign>/prepare.py`, then
`rtk proxy .venv/Scripts/python.exe <campaign>/validate.py connector` and `nexus`.
The prepare script builds both changed packages, audits Python payloads and
installs the three exact wheels into a fresh venv. Tests are copied outside the
checkouts with their contract schemas. Reports and hashes accompany this record.
Connector source commit: `143ae44918733a46c2233caefc2905ea11340205`.
Connector wheel SHA-256: `65c400bafc97f7489717905b7f5c81af8f6f2e4cbdb409cb25749478f7b4e07c`.
The same tested Connector wheel replaces the Nexus CI pin. Core source, version
and wheel are unchanged. The three fetched origin/main heads are already ancestors
of their feature branches; versions remain 0.3.3 / 0.0.12 / 0.0.14.

HTTP transports, inventory, protected vault and native peers use isolated test
fixtures. This establishes authorization, persistence and recovery contracts;
it does not qualify a real provider turn or a deployment across two hosts. No
personal service, native task registration, real credential access, paid inference,
release or merge was performed. The native campaign authorization remains pending.
New remote identity bootstrap, participant initialization, preset evolution,
dashboard introduction, full productive M1, ATN and OBS remain open. R3 scope and
acceptance criteria are unchanged; no full task or milestone is marked complete.
