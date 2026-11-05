# PR-03 — human operator profiles and remote binding reuse

Windows 11 `10.0.26300`, Python 3.13.1; Nexus `0.3.3`, branch
`feature/v0.3.3`. Connector `0.0.12` and Core `0.0.14` are unchanged.
This increment implements the human operator client and reuse of an existing
approved binding on a selected Server. It does not complete Connector onboarding,
the remote productive campaign or M1.

`operator login/status/logout` reuse the Server's existing human account/session
API. Password input is hidden or explicitly read from stdin, never accepted as
an argument or persisted. A separate operator namespace in the existing protected
OS vault stores only the canonical session cookie. The local JSON stores origin,
Server installation ID and username. Origin changes require a different profile;
the vault key also binds the client home, profile name and normalized origin.
An unavailable vault has no file fallback. A failed new vault write revokes the
new login and preserves the previous stored session.

The transport requires verified HTTPS except for loopback, rejects URL credentials,
paths, queries and fragments, disables implicit proxies and follows no redirects.
The cookie is attached only to the selected origin's operator API. An additive
session-required header prevents the Server from falling back to local trust or
agent-key authentication. Operator status advertises support; an older Server
without that support is refused by this client. The account/status routes also
respect the restriction. The operator credential is not sent to MCP, Connector
control lanes or native harness initialization.

`connect --operator-profile NAME --agent ID --binding-id ID` associates an
operator-side project shortcut with a canonical, already approved binding.
Identity, executor, workspace, harness and installation are checked and pinned.
No remote path is inferred from the operator's current directory, and no setup,
model probe, grant or configuration change occurs during this association.
`connect` and `work` subsequently select the saved topology before local service
resolution. Unavailability, expired authentication or identity/scope drift cannot
start a local Server, reset identity or substitute a different endpoint.

The existing work facade handles requests, results, native questions and grant
reviews over this transport. Unknown operation replies recover the same canonical
receipt. A human cookie remains a human operator session: execution still uses
the represented subject's grant and is recorded as operator/subject, not as an
impersonated subject. Existing local command behavior remains in the regression
campaign. Remote host discovery/registration, proposal approval and a unified
new-identity review are still pending; Connector retains its existing workflow.

Logout removes the local vault entry. If transport is unavailable, its response
explicitly leaves remote revocation unconfirmed while canonical expiry still
bounds the remote session. Non-secret metadata remains available for login.

## Evidence

- `pr03-remote-operator-source.xml`: 24 passing new-client and existing operator
  authentication cases before the added decision/vault-failure cases.
- `pr03-remote-operator-decisions.xml`: two passing cases for human-session grant
  renewal/native approval and failed vault-write recovery.
- `pr03-remote-operator-installed.xml`: broad coordinated-wheel campaign: **167 passed, zero failures/errors/skips**.
- `pr03-remote-operator-final.xml`: two passing installed cases for offline logout
  and a real loopback HTTP redirect to a distinct origin. These updated test-only
  cases use the same installed artifact, with no production code change.

The campaign directory is
`C:\Users\jpamb\AppData\Local\Temp\r3-remote-operator-egwhbpv6`.
All tests/contract fixtures are copied outside checkout. `python -I` verifies
Nexus, Connector and Core imports from the fresh validation environment.
All 427/114/130 Python payloads match their source bytes; exact hashes are recorded
in `pr03-remote-operator-wheels.json`. Nexus SHA-256 is
`03c49114df967a4aa640f4226b301a834038a7912a880a6b4fa0d36b2ef6abb1`.

HTTP handlers, human session authentication, SQLite transactions, operation
admission, dispatch and native-decision handling are real. The network bridge
uses an HTTPS-origin request with forwarded remote provenance and disables local
trust. The vault is an isolated memory backend; native/model peers are synthetic.
The redirect check uses a real disposable loopback HTTP server. This is not a
real TLS deployment, OS-vault accessibility, provider or two-host Connector
qualification campaign. Reports remain separate and overlapping tests are not
added as distinct coverage.

Ruff E9/F passes the new code and the other touched modules. The full touched-file
check reports one pre-existing F401 (`JSONResponse`) in `operator_auth.py`; its
unused import was not introduced or changed by this increment. Whitespace and
fixed-plan ledger coverage are checked before commit.

## Remaining acceptance

Unified new remote identity/setup and operator approval of Connector proposals,
real provider context/results, remote native host execution, start-at-login review,
participant initialization, preset evolution, dashboard introduction and remaining
ATN/OBS work remain open. The existing isolated native-service approval request is
unchanged. No personal service, actual user vault entry, real credential, native
task, package release or protected-branch merge is touched by this campaign.
