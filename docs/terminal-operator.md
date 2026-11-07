# Human operator access to a remote Server

Run these commands on the operator's client, where the operator account and OS
credential store are available. Do not copy this profile or its session to the
Connector or harness host. The Connector keeps its existing agent connection,
approval, runtime setup and vault workflow.

Configure the human account through the Server's existing operator account flow.
Then sign in without putting a password in arguments:

```sh
okto-nexus operator login --profile team-server --server https://nexus.example --username human
okto-nexus operator status --profile team-server
```

Interactive login uses a hidden prompt. Automation may explicitly choose
`--password-stdin`. Passwords are not saved. Only the resulting eight-hour human
session is stored through the existing protected Windows Credential Manager,
macOS keyring or Secret Service backend. An unavailable/locked vault is reported;
there is no plaintext file fallback. The client needs the existing vault
dependencies included in the Server installation extras.

The non-secret profile under `HOME/terminal/operators` pins the normalized origin,
Server installation ID and username. `--home` selects the operator client's
configuration directory, not a directory on the remote host. HTTPS certificate
verification is required. HTTP is accepted only for loopback/localhost origins.
URLs cannot contain credentials, paths, queries or fragments. Redirects and
implicit environment proxies are not used for these authenticated requests.

For an already approved native binding, associate a local project shortcut:

```sh
okto-nexus connect --operator-profile team-server --profile project-review --agent reviewer --binding-id BINDING_ID
okto-nexus work status --profile project-review --json
okto-nexus work send --profile project-review --message "Inspect the project" --json
okto-nexus work watch --profile project-review
okto-nexus work authorize --profile project-review
```

The binding supplies the canonical executor, workspace and harness. The local
current folder (or `--project`) identifies the operator's shortcut; it is not sent
as a remote launch path. Existing host configuration is preserved. `--client`,
`--workspace-id` and `--candidate-ref`, when provided, must match the binding.
For a new remote project, use the [two-terminal setup flow](remote-project-setup.md):
the host exports a draft, this client reviews identity/workspace creation and
delivers the agent key once, and the host resumes with the public handoff.
Connector proposal approval is also available below for its existing onboarding
requests.

Later `connect` and `work` recover the saved operator topology before resolving
local service startup. An unavailable Server, expired session, conflicting
profile or changed Server identity produces a diagnostic; it never starts a
local Server or selects another identity. Local service flags cannot configure
the remote target. Work, authorization, native decisions and receipt recovery
use the canonical APIs described in [terminal work](terminal-work.md). Configured
binding, ready session and completed work remain distinct states.

After session expiry or password rotation, sign in again and rerun `connect` or
`work`; saved work IDs and receipts are preserved. Operator cookies are accepted
only by the operator API, never as an agent key, MCP capability or Connector
credential. The client requires the Server's explicit session-only request support,
so even an open loopback Server cannot substitute local trust for an expired
operator session.

```sh
okto-nexus operator logout --profile team-server
```

Logout revokes the selected session and removes its vault entry. If the Server
is unreachable, the local entry is removed and remote revocation is reported as
unconfirmed (exit 3); the Server's session expiry still applies. Non-secret
origin/identity metadata is retained for a later login. Status and successful
login/logout return JSON and exit 0. Invalid grammar exits 2; unavailable or
unconfirmed states exit 3; interrupted secret input exits 130. These commands
do not change the operator password or rotate an agent key.

## Decide a Connector connection request

The Connector's `connect`/`configure` flow submits its existing immutable proposal
and prints its approval ID. Keep that ID; resuming the request does not create a
new proposal. On the operator's own authenticated client:

```sh
okto-nexus operator approval APPROVAL_ID --profile team-server
okto-nexus operator approval APPROVAL_ID --profile team-server --decision approve
```

The first command only inspects. The second shows the canonical agent, executor,
workspace, installation, configuration and execution limits, proposal revision
and expiry, then asks for explicit confirmation. Use `--decision reject` to refuse.
The Server revalidates authority, expiry and current policy when committing the
decision. A participant cannot decide by confirming a local prompt.

For automation, inspect with `--json`, then provide the exact `review_revision`
as `--confirm REVISION` together with `--decision approve|reject`. Noninteractive
commands without that reviewed revision refuse to decide. Output escapes terminal
control characters in human-readable proposal text.

If the decision response is lost, inspect the same ID and repeat the same decision
and revision. A committed matching decision is recovered from its canonical
receipt without another POST; a different decision or actor produces a conflict.
Inspection, rejection and approval do not launch work. The Connector's existing
background continuation applies the approved proposal and its scoped grant using
its original participant credential and request IDs. Human operator credentials
remain on the operator client. After binding application, use the existing binding
ID with `connect --operator-profile` to reach the terminal work flow.
