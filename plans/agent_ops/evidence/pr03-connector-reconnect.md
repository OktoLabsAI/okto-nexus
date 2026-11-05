# PR-03 — Reuse the saved Connector project

Connector connect resolves a retained canonical project association before credential entry or discovery; bare connect restores its Server, identity and request, while --identity selects an imported identity. The existing vault key is authenticated against current Server/agent/credential revision; approved binding scope and physical root are checked before service effects for completed requests. Reconnect does not reimport a key, reprobe, reapply defaults or renew grants. Revocation, disabled binding, changed mapping and concurrent local edits refuse reuse without fallback. 67 source Connector and 8 source Nexus integration tests passed; the final focused Connector suite passed 37 tests, overlapping those runs. Final installed artifacts passed 180 Connector and 75 Nexus tests. New remote identity bootstrap and full real-provider M1 remain open.

The previous connect path always requested/imported a key and required --server,
even when a reviewed project and applied binding already existed. It also required
the user to remember the setup ID. The new resolver uses the retained canonical
association, not a guessed identity from a folder/name. It restores the same
request before invoking the existing configure/checkpoint path. Ambiguous saved
connections require a choice. --identity selects an imported identity, including
for a new project; explicit credential source flags still invoke canonical import.

Reuse reads the existing protected vault entry and authenticates /me without
rewriting it. It pins Server origin/ID, agent and credential epoch. Completed
requests read current binding consent, validate its stable IDs against the local
record and recheck physical root/launch configuration. Current authorization and
configuration revisions may advance; they are reported without resetting settings.
Concurrent identity/request/mapping changes refuse the observed snapshot. Current
disabled/revoked/stale consent never starts the daemon, creates a replacement or
falls back to a new credential prompt. Pending requests retain their original
checkpoint and ID. The existing lifecycle starts/reuses the daemon only after
the completed association has passed these checks; native startup policy remains
owned by the existing service implementation. Runtime start still requires --start
and canonical admission; configuration reuse is not provider/session readiness.

The installed cross-repository case uses the actual Connector CLI handler,
StateStore, HTTP client and background onboarding against the real Server handlers,
authentication, operator decision and SQLite. After the original approval it
reopens connect with only a project path. Only GET requests are sent, local state
bytes stay unchanged, and the same binding/grant remains. A later Server disable
and grant revocation refuse reuse and remain intact. Human credentials never
enter Connector requests. Daemon/process effects in this new test are injected.

## Validation and limits

- Source Connector: **67 passed**, then **37 focused cases passed**
  after adding explicit import compatibility and final startup-status refresh.
  Source Nexus integration: **8 passed**. The runs overlap.
- Installed Connector: **180 passed**; installed Nexus:
  **75 passed**, no failures/errors/skips. This includes vault/import,
  identity, CLI, onboarding, binding revocation, native-policy recovery and remote
  operator regressions, plus a disposable real detached lifecycle regression.
- The initial installed Connector run passed 109 tests and stopped at an old
  JSON status fixture missing daemon.state. A full follow-up passed 179 tests
  and found the same omission in the human-output fixture. Both fixtures were
  corrected and the suite repeated against the identical package. The two
  earlier reports remain separate and are not added to final coverage.
- CLI process help exposes optional --server and --identity. A bare connect in
  an isolated empty state returns SERVER_REQUIRED/exit 1 before credential input.
- Ruff E9/F, whitespace, manifest hashes and the fixed R3 ledger are checked.
  All **431/117/130** Python files match the source bytes. Isolated python -I
  imports resolve inside the installed venv, outside the checkouts.

Campaign: `C:\Users\jpamb\AppData\Local\Temp\r3-connector-reconnect-5ocz5qta`.
Reproduction: `rtk proxy .venv/Scripts/python.exe <campaign>/prepare.py`, followed
by `validate.py connector`, `validate.py nexus` and `check_cli.py` through the
same interpreter/proxy. Tests and schemas are copied outside the repositories.
The prepare script builds Connector and byte-audits the previously qualified
unchanged Nexus/Core wheels before installing all three in a fresh environment.
Connector source commit: `09eb5f303c8ad4081c3ae9ed413ea81a4ea93458`.
Connector wheel SHA-256: `42c7a189b8f7b7a7f8da3e7b724180f23c9944e340cbccaa99bfae53faa21d91`.
The exact tested wheel and hash replace the Nexus CI pin. Versions/branches stay
0.3.3 / 0.0.12 / 0.0.14. Nexus production code and Core are unchanged this increment.

The investigation of new remote identity setup exposed this existing-identity
reuse gap. Fixing it does not complete new identity bootstrap: the Connector
still needs a canonical agent key for its initial registration, and that new
operator-authorized provisioning path remains to be implemented. No alternate
credential type or anonymous enrollment authority was introduced in this increment.
Remote provider/two-host work, actual OS-vault/native login qualification,
participant initialization, preset evolution, dashboard introduction, ATN and OBS
remain open. Native campaign authorization remains pending. No personal service,
real credential access, paid inference, package release or merge was performed.
The fixed plan, full M1 and remaining acceptance criteria are not marked complete.
