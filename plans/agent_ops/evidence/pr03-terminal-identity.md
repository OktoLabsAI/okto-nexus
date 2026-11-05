# PR-03 — reviewed identity creation in project setup

Windows 11 `10.0.26300`, Python 3.13.1; Nexus `0.3.3` on
`feature/v0.3.3`. Connector `0.0.12` and Core `0.0.14` are unchanged in this
increment. All three current `origin/main` heads were fetched and confirmed
contained in their feature branches before continuing this work. R3, PR-03 and
M1 remain incomplete.

`okto-nexus connect` now proposes a persistent project identity when no existing
agent is explicitly selected. The saved review includes the concrete ID,
suggested harness/project display name, generalist role, explicit coordination
permissions, workspace, installation, provider home and bounded runtime grant.
`--agent` selects an existing identity; `--new-agent` / `--name` customize the
new proposal. Reopening an uncommitted review retains its original identity ID
and refuses contradictory reuse/creation choices.

Preview and the authorized model connection test do not create an agent. The
draft uses the authenticated operator's existing identity for passive host
discovery and the explicitly approved installation version check. It does not
create a temporary identity or grant. New identity validation is operator-only,
rejects reserved/existing IDs and validates the reviewed defaults hash. Test and
Finish recheck current authority/defaults; a colliding identity is never adopted.

Finish shares its existing database transaction and durable receipt with the
ordinary agent-creation routine, extracted from the Agents API. Identity, key
hash, workspace, binding, policies and execution grant commit together; a later
failure rolls them back. Key initialization uses the canonical issuer, with no
root key exported to the profile, HTTP Finish result or receipt. Existing REST
creation retains its one-time key response and capability/permission rules.
Managed execution continues to use the current scoped capability authority.

The new identity receives explicit coordination flags: direct/channel messages,
handoffs, artifacts, events, its own profile and permitted workspace information.
Broadcasts, channel creation, capability changes, workspace paths and experimental
memory are disabled; communication limits are 60 messages/minute and 10 recipients.
No administration or self-approval authority is introduced. Automatic handoff
claiming is explicitly off for the new identity even if enabled globally. Native
tool decisions remain enabled and the review requests 60 minutes / 20 runtime
actions. Existing identities retain their role, name, permissions and handoff
policy. Reconnect reads canonical state without reapplying the preset or grant.

The request is an additive extension of existing Test/Finish/recovery. Omitted
`agent_creation` preserves older request hashes. Lost Finish responses recover
the same identity/key/grant from the durable receipt after test-cache loss. The
original successful test remains readable after commit, while a new Test POST
cannot recreate the committed identity. No new template/identity storage or
distributed transaction is introduced. The dashboard reads the same agent and
binding; its onboarding introduction remains a separate unfinished requirement.

## Validation

Final source identity suite: **14 passed, zero skips/failures/errors**.
**159 distinct installed cases validated:** the broad run passed 158 and retained one development presence assertion failure; after copying the corrected test, `--lf` passed that one case. Both reports are retained. No production code or wheel changed between these runs. No tests were skipped; final results cover all 159 cases.

The installed campaign uses copied tests, `python -I -m pytest` and a fresh venv
outside the checkouts. It asserts Nexus, Connector and Core module origins inside
that environment. The 420 Nexus, 114 Connector and 130 Core Python payloads match
source byte-for-byte. Exact artifacts/hashes are in
`pr03-terminal-identity-wheels.json`. Environment:
`C:\Users\jpamb\AppData\Local\Temp\r3-terminal-identity-ugln_3j_\validation`.

The new cases exercise preview without writes, authorized draft Test before
identity creation, transactional Finish, root-key non-disclosure, lost Finish
reply/cache recovery, collisions before/after Test, stale defaults, invalid draft
fields, participant/reserved-ID refusal, late rollback and CLI-generated profile
stability. A later Agents API edit of name/role/permissions survives reconnect.
The globally enabled handoff-claim case confirms no `execute_work` grant for the
new preset. Regression covers existing setup/receipts/terminal transport, canonical
permissions/capability catalog, key issuance and operator authentication.

The existing disposable real-process CLI case starts/reuses one Server generation,
reaches real HTTP, reports an intentionally missing explicitly selected agent and
ends in `DRAINED` after explicit stop. It disables harness integrations. Setup
integration uses real HTTP/auth/SQLite transactions with simulated qualification,
version command and model response. No provider login/inference is qualified.

Development test corrections addressed column names, the HTTP validation envelope,
the reviewed provider-home identity and ordinary authentication presence updates
(`last_seen_at`). Identity/authority comparisons exclude only that presence field;
production authorization/transaction checks were not weakened. Final reports
supersede those failed development assertions.

JUnit: `pr03-terminal-identity-source.xml`, `pr03-terminal-identity-installed.xml`,
`pr03-terminal-identity-authority.xml`.
Ruff and whitespace checks cover changed files; usage is in
`docs/terminal-connect.md`.

## Scope still required

Full terminal work/conversation, questions, decisions, results and return are
still required, as are start-at-login review, remote topology, participant init,
operator-session CLI authentication, preset upgrade diffs and the dashboard
introduction. The actual harness context/coordination and productive local/remote
campaigns have not run. These tests do not establish the full DX-18 preset or M1.
The original prepared native service campaign still awaits its separately
requested authorization; no task was registered or personal runtime modified.
