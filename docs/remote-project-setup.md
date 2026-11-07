# Remote project setup from the two terminals

Use this flow to select or create a canonical agent and workspace for a project
on a Connector host. The human operator uses their own authenticated Nexus
client; the execution host receives only the selected agent's canonical key.
The operator account, password and session remain on the operator client.

The host draft, operator review, partial bootstrap and final configuration are
separate steps. Creating the identity and workspace does not configure the
binding or grant execution. The host submits the ordinary binding proposal;
the operator compares it with the confirmed review before deciding it. The
Connector then completes the canonical Finish. `configured` does not mean a
running session, provider login or completed project task.

Both clients and the Server must support remote setup. Unsupported versions
refuse the flow. Use a reachable HTTPS Server origin, such as
`https://nexus.example`; HTTP is accepted only for loopback in this setup flow.
On different computers, `localhost` identifies a different machine on each one.
The host needs an installed harness and its local project directory. Provider
login stays on that host and is not performed by this flow.

## 1. Save the draft on the execution host

Run the interactive Connector wizard on the computer that will execute work:

```sh
okto-nexus-connector connect --server https://nexus.example --harness codex_app_server --project . --request-id remote-project-01 --setup-draft ./host-draft.json
```

The wizard selects the local installation and directories and asks to save the
host draft. It does not need an agent key or an operator credential. Discovery
does not establish provider login or runtime readiness. Installation checks and
onboarding occur after the reviewed bootstrap. Do not add `--start`,
`--operator-identity` or `--operator-proof-ref` to this flow.

Keep the Connector state directory and the printed setup request ID. Repeating
the command with the same `--request-id` reexports the retained draft when the
choices still match. Do not invent another ID to recover an interrupted request.
`--setup-draft` and `--setup-receipt` are mutually exclusive; Connector `connect`
is interactive and does not accept `--json` or `--non-interactive`.

Transfer `host-draft.json` to the operator client. It contains the Server origin,
host and installation references, portable configuration and consent metadata,
not the key or the host's provider credentials. Keep local paths and the original
host state on the execution host. Labels and directory names do not select a
canonical identity or workspace.

## 2. Review on the operator client

Sign in using a protected operator profile if one is not already available:

```sh
okto-nexus operator login --profile OP --server https://nexus.example --username human
```

Enter the password at the hidden prompt. See [remote operator access](terminal-operator.md)
for session expiry, OS vault requirements and origin pinning. `OP` is the human
login profile; `NAME` below is a separate project setup profile.

```sh
okto-nexus connect --operator-profile OP --remote-draft ./host-draft.json --profile NAME --plan
```

Review the Server installation and origin, selected host and harness, identity
role and permissions, communication limits, workspace, configuration and
execution authorization. The review also names any Server-wide native-decision
policy initialization, the host's startup choice and any previous machine
authorizations that Finish will revoke. `--plan` persists the review
without bootstrapping the identity, checking the installation or submitting a
project task. Add `--json` when a machine-readable review is needed.

The default proposes a new identity with a retained generated ID. On the first
review, `--new-agent unused-id --name "Project helper"` selects its ID/name
explicitly. Use `--agent EXISTING_AGENT_ID` to select an existing identity without
rotating its key. Add `--workspace-id WORKSPACE_ID` to select a canonical
workspace; otherwise the review proposes a new one. Choosing an existing agent
does not make its key available: the host must already have it or import a copy
you possess. Its coordination permissions remain those shown in the review.

## 3. Confirm and receive the one-shot key

Resume the same profile in an interactive terminal:

```sh
okto-nexus connect --profile NAME --setup-receipt-output ./host-handoff.json --timeout 15 --no-chat
```

The saved profile selects the operator topology. The command displays the review
and asks for confirmation. Alternatively, supply `--approve REVIEW_REVISION`
using the exact displayed revision. `--plan` and `--approve` cannot be combined.
The output directory must already exist; an unrelated existing handoff file is
refused before bootstrap.

For a new identity, stdin, stdout and stderr must all be terminals, and `--json`
must be absent. Do not redirect, pipe or record this key-delivery command. A
headless attempt is refused before bootstrap and can be resumed with the same
profile in an interactive terminal. Headless review and existing-identity reuse
do not require issuing a key.

After the bootstrap commits, the command displays the canonical agent key once
in a dedicated terminal message. Transfer only that key through a protected
channel you control, then paste it into the Connector's masked prompt. Do not
put it in command arguments, shell history, the draft, the handoff or a review
document. The command does not store the key in its checkpoint, public JSON or
handoff. There is no automatic secret-transfer or claim-code channel.

`host-handoff.json` is the public handoff: it contains the setup, identity,
workspace, credential revision and child-request references. Transfer this file
to the original execution host. Without `--setup-receipt-output`, the command
uses `terminal/profiles/NAME.setup-handoff.json` under the selected Nexus home
and prints its location. A custom output path is a command option, not a saved
profile choice; supply it again when that destination is needed.

At this point, `awaiting_host` is expected. The identity and workspace are already
committed, while binding configuration and execution authorization are pending.
`--timeout` limits observation time; it does not cancel the setup.

## 4. Import on the host and complete the same request

On the original Connector host:

```sh
okto-nexus-connector connect --setup-receipt ./host-handoff.json --alias project
```

Enter the agent key at the masked prompt. Existing protected input options
`--credential-stdin` and `--credential-env NAME` are also available; the latter
names a variable and never takes the key itself as an argument. The Connector
checks the authenticated Server, agent and credential revision against the
handoff before importing. It prefers the OS keyring; a restricted plaintext
file fallback requires explicit approval and relies on the OS account boundary.

If this exact identity is already imported, select its existing alias with
`--identity ALIAS`. Retain the same alias on later calls. The host reuses its
saved installation, directories, root request and child IDs. It does not need
the operator's profile or administrative credential.

If the host reports `awaiting_operator_approval`, return to the operator client:

```sh
okto-nexus connect --profile NAME --timeout 15 --no-chat
```

The command compares the actual canonical proposal with the confirmed review.
Matching effects use the current operator authority and the existing binding
decision API. Changed effects require review; the host cannot approve itself.
`awaiting_finish` means the decision is recorded and host application is pending.

Resume the same host command, then observe from the operator client:

```sh
okto-nexus-connector connect --setup-receipt ./host-handoff.json --alias project
okto-nexus connect --profile NAME --timeout 15 --no-chat
```

Run the first line on the host and the second on the operator client. An already
imported key is reused. Finish commits the reviewed binding/configuration and
authorization. Subsequent reconnects inspect the retained canonical binding;
they do not restore grants or policy that were later revoked or changed. Use
[terminal work](terminal-work.md) separately when ready to submit project work.

## Revise local choices before Finish

On the host, review the affected choices explicitly while retaining the request:

```sh
okto-nexus-connector connect --setup-draft ./revised-draft.json --request-id remote-project-01 --review-current --project C:/Projects/revised-project
```

Replace the example directory with an existing absolute path on that host. Optional `--customize`, harness
selection and provider-directory options are available in this local review.
The command shows the changes and asks for confirmation. The canonical Server,
agent and workspace remain those of the original bootstrap. Changing a local
folder or its label does not rename the canonical workspace.

The revised choices remain pending. The previous draft, receipts and child IDs
stay retained, and the old pending child stops automatic continuation. Transfer
the revised draft to the operator client and use the same project profile:

```sh
okto-nexus connect --profile NAME --remote-draft ./revised-draft.json --review-current
```

Confirm the new displayed revision in a later command and export its current
handoff with `--setup-receipt-output`. On the host, resume `connect
--setup-receipt` with that handoff. Only a matching authenticated handoff promotes
the pending local choices. Changed realization or proposal requests receive new
Server child IDs; retries retain those IDs. Reexporting a pending draft uses the
same root and does not reopen its choices.

If the previous Finish commits during the local review, resuming its original
handoff recovers that result and archives the unapplied local revision. A setup
with a confirmed Finish cannot be amended by this command; use the existing
connection's explicit configuration controls. A changed concrete startup plan
while startup remains enabled is also refused before creating a pending review;
use the existing `service` controls for that change. The startup boolean can be
reviewed here. Omitting startup flags preserves the retained plan.
`--no-start-at-login` omits the startup request; it does not disable an integration
already installed. Use the explicit service controls to disable that integration.

## Pending states and recovery

| Situation | Resume behavior |
|---|---|
| Review response lost | Rerun the same operator profile. The saved request preserves the generated identity ID and review intent. Recovery displays the review again without confirming effects automatically. |
| Bootstrap response lost | Recover the same profile. Committed identity/workspace references remain available, but plaintext that was not received is unavailable. No second identity or automatic key rotation is requested. |
| Key was already displayed | Use the copy already received. The Server cannot reveal it again. The terminal distinguishes confirmed prior delivery from an unconfirmed delivery. |
| Host import or network interruption | Resume the same handoff on the same host and retain its state/vault. Inspect an incomplete import instead of deleting its checkpoint or changing the root ID. |
| Decision or Finish response lost | Resume the same operator profile and host request. Matching canonical receipts recover the effects without issuing another grant. |
| Operator session expired | Log in again with the same operator profile, then resume the project profile. No local-trust or agent-key fallback replaces the human session. |
| Origin, Server identity, credential or local selection changed | The retained request is refused or requires review. Do not edit IDs, credential revisions or digests in the exported files to bypass the mismatch. |

On the **Nexus operator client**, `okto-nexus connect --profile NAME --review-current`
shows a fresh review of a pending setup while retaining its original bootstrap.
Confirm the displayed revision in a later command; `--review-current` cannot be
combined with `--approve`. This does not itself update the host's retained draft
or authorize mismatched child requests. A host refusal remains pending until
the affected choices can be reconciled through the host review above; do not
create a new root as a retry.

A new agent's key is its ordinary canonical credential, not a credential
restricted to one host or workspace. Execution still needs the binding and
current canonical authorization. Losing the sole copy of a one-shot key cannot
be repaired by replaying this flow; no key rotation is included in setup recovery.

After an operator explicitly rotates the canonical key through the existing
identity controls, import the replacement through the host's masked prompt:

```sh
okto-nexus-connector identity replace-credential project
okto-nexus-connector connect --identity project
```

Run `connect` from the original project directory. This reuse is available only
after the setup and any chosen startup operation have completed. The Connector
authenticates the current credential and checks the exact approved binding and
retained local configuration. It keeps the original bootstrap, child requests
and Finish result; it does not register again, probe the installation, reapply
Finish or renew a grant. A pending local review or changed binding still refuses
reuse. The original `--setup-receipt` remains tied to its bootstrap credential
revision; use ordinary `connect --identity` for completed reuse after replacement.
An unfinished setup cannot adopt a different credential revision through this
path. Review execution authorization separately with `work authorize` when needed.

The Server retains at most 1,024 setups per authenticated operator and 32
revisions per setup, including the initial review. Each review is limited to
64 KiB. Capacity exhaustion refuses new allocation with `QUOTA_EXCEEDED` before
changing the current review. Existing matching replays and recovery remain
available. There is no automatic expiry or pruning. A database reset that
preserves agents also preserves these receipts; a full reset removes them
with the identities and configuration. Do not reset state to retry a request.

This guide describes the implemented setup contract. It does not establish
provider login, native process readiness, two-machine qualification or native
startup certification. The bootstrap does not submit a project task or start a
runtime. Optional host startup retains the limits of the existing Connector
service lifecycle and requires its reviewed local choice.
