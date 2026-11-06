# Existing participant configuration

Use `okto-nexus init --mode participant` (or `connect --mode participant`) on
the machine that runs the external MCP client. Select an existing agent and
workspace on an explicit Server. Missing identities require explicit operator
creation. Init does not start a service/model, submit work, create/rotate a key,
change runtime policy or replace an execution binding.

Install Nexus with its `serve-lite` extra on this client host to include the
platform credential/ACL dependencies (pywin32 on Windows, keyring elsewhere).
This dependency installation does not require starting a local Server.

```sh
okto-nexus init --mode participant --profile reviewer --server https://nexus.example --agent reviewer --workspace-id WORKSPACE_ID --client claude --project . --plan
okto-nexus init --mode participant --profile reviewer --approve REVIEW_REVISION
```

Read the existing `nxs_` key through a hidden prompt, `--key-stdin`, or
`--key-env NAME` to authorize one environment variable. No literal-key argument
is accepted. Review does not store the key, so supply it again when applying.
Approval stores it in a dedicated OS vault entry. Unavailable vaults stop the
operation; there is no plaintext fallback. Never paste secrets into shell
arguments or committed client files.

Server selection requires HTTPS, except explicit loopback HTTP on this host.
Loopback HTTP is plaintext. Only Bearer headers carry the key; redirects are
refused. Preparation confirms the selected authenticated identity, workspace
and MCP policy. Canonical authentication may update last-seen timestamps.

Claude uses project `.mcp.json`; Codex uses `.codex/config.toml` and requires
project trust before loading it. `--config-file PATH` selects a file explicitly.
`--entry-name NAME` defaults to `nexus`. `--client-version VERSION` records an
observed build; omission is unknown, never qualification. `--client generic`
returns reference-only manual instructions, with no client file effect.

The review shows the proposed entry, selected file/hash, changed fields,
identity/workspace and local effects. Other entries' secrets are not printed or
stored in the checkpoint. Apply requires the exact review revision and refuses
a changed source. It does not take ownership of an existing same-name entry.
Unrelated JSON values and TOML bytes/comments are preserved. Protected backup
precedes atomic replacement; Windows replacement access policy is verified
before bytes are written. New files and backups are private. Cooperating
writers share the Core lock; external writers can still race the final check.

Profiles live in private `HOME/terminal/participants/`, separately from managed
profiles. `--home` chooses this metadata root. Profiles retain a nonsecret
`setup_run_id` and `credential_pending`, `credential_stored`, `file_pending`,
`done` checkpoints. Server, vault and file are separate systems, not one atomic
transaction. Rerun the same profile after failure. Exact file postimage recovery
avoids repeating a completed write; intervening edits stop recovery and are
preserved. Completed profiles allow unrelated later edits while checking their
still-owned entry.

`--plan` displays saved historical evidence without HTTP or credential reads;
authentication is then unknown. `--refresh --plan` replaces only an unapproved
review. Approved uncertain operations retain their checkpoints. Local failure
never deletes the Server identity. Vault entries and protected backups remain
for recovery until explicitly removed through the local removal flow below.

**Configuration applied is not client ready.** Output separates authenticated
identity, entry present, credential in the client context, client reload, MCP
negotiation and work submitted. Vault storage does not make the variable
available to a launcher or GUI. Use the foreground launcher below for secure
delivery to a new terminal process. Cooperation smoke remains pending. Use
`doctor --mode participant` to inspect this profile; managed doctor selects
managed profiles. The external client still needs secure environment delivery,
project trust/reload and reconnect before its readiness can be verified.

One identity has one logical delivery: an additional client is not guaranteed to
consume every message, and deliveries are not broadcast to every channel. Its
existing runtime remains configured. A separate identity requires an explicit
operator decision.

The proposed `entry` is reference-only manual guidance. The complete JSON
response/profile contains host paths and identity context; it is a local
receipt, **not a portable template**.

## Foreground client launch

```sh
okto-nexus participant launch --profile reviewer --plan
okto-nexus participant launch --profile reviewer --approve LAUNCH_REVIEW_REVISION
```

Launch uses the completed participant profile and its existing protected vault
entry. The first review authenticates a preparation GET and passively selects
the sole discovered Claude/Codex native executable. If discovery is ambiguous,
select `--executable PATH`. Windows shell wrappers are not launched. The review
shows the executable, project, configuration, environment reference and effects;
it does not execute the client. Displaying a saved `--plan` performs no vault or
network access. In an interactive terminal, omit `--plan` to review and confirm
in one command. Automation approves the exact launch revision.

Apply rechecks the Server/identity, binary bytes, physical project directory,
file bytes/access policy and client home selectors before starting. It delivers
the key only in a new child's environment and removes other participant token
references from that child. It does not modify the calling shell or publish an
export command. The client keeps its ordinary provider login, native policies,
settings, other MCP servers, hooks and plugins; review those through the client.
Nexus sends no prompt or work. The foreground client owns terminal input/output;
`--json` formats Nexus review/receipt messages, not the intervening client output.

Codex is launched with `--no-daemon` so an older shared daemon cannot discard the
new environment. A version that does not support this flag fails without a
fallback. Supported Codex file locations are the selected project's
`.codex/config.toml` and the actual user `config.toml` in its existing Codex home;
an arbitrary selected file is refused. Project trust remains required. Claude
uses its project `.mcp.json`, or `--mcp-config` for an explicitly selected other
file, with its ordinary trust/approval flow. Existing GUIs and other running
clients do not inherit this environment.

The private `<profile>.launch.json` receipt records `review`, `starting`,
`started`, and `exited`. The intent is saved before spawn. Repeating the same
approval returns the retained attempt, including uncertain attempts, without
starting another process. A PID is only a historical hint; Nexus does not kill
or adopt it. If the launcher is interrupted, inspect the client before using
`--new` to explicitly review another launch, which may overlap the old one.
Use `--new` also after a completed launch or changed review. The latest receipt
retains the previous revision/state and process hints, not a complete history.

Successful spawn proves that Nexus supplied the environment to that owned
process. It does not prove client reload, MCP authentication, participation or
work, and a zero exit code is not readiness. Those levels remain independent.

## Local removal and partial-setup compensation

```sh
okto-nexus participant remove --profile reviewer --plan
okto-nexus participant remove --profile reviewer --approve REMOVAL_REVIEW_REVISION
```

Removal is local and works even when the Server is unreachable or the agent key
has been revoked. Its review performs no network requests, secret reads or file
edits. It saves a nonsecret removal plan with the exact source/postimage hashes
and fields of the owned entry. Apply removes only that entry using Core's CAS,
protected backup and atomic file replacement, then removes the isolated vault
entry for this setup. Other client entries/preferences, other vault entries,
Server identity/key validity, runtime, bindings and grants are preserved.
Whole backups are never restored. TOML bytes outside the owned table remain,
including a separator blank line; JSON retains unrelated values.

The existing private profile records removal stages `review`, `file_pending`,
`vault_pending` and `done`. Approval retires the profile before either effect;
init, connect and launch then refuse to reactivate it. If only the vault stage
remains, later file edits are preserved while it resumes. A lost file reply is
recovered only from the exact reviewed postimage and access policy; intervening
edits stop recovery for inspection. A locked/inaccessible vault remains pending,
and is never treated as confirmed absence. Rerun `participant remove` to resume
the same approved intent. Replay of a finished removal is a historical receipt,
not a new assertion that no one subsequently changed the file or vault.

Incomplete setup is compensated only for stages that could have taken effect.
An unconfirmed file write must match its original or exact postimage before
ownership is established. The unapproved removal review can be replaced with
`--refresh --plan`, including when init advanced after that review. An approved
removal keeps its original checkpoints and cannot be replaced by refresh.

If the entry is absent, modified, manual, or its file cannot safely be removed,
inspect it first. `--keep-config --plan` explicitly proposes leaving all client
files untouched while retiring the profile and deleting its own vault entry.
Use `--refresh --keep-config --plan` to change an unapproved removal choice.
The same option can compensate a setup whose local file became unavailable.
This does not certify that a manual configuration was removed.

Existing clients may retain the credential in memory, and removing a local key
does not revoke it on the Server. Close or reconfigure those clients explicitly.
Nexus does not kill a process based on a historical PID. Protected backups,
nonsecret setup/removal/launch receipts and directories remain for inspection;
there is no recursive cleanup. Doctor of a retired profile reports its removal
state and performs no active credential/MCP checks. A new connection uses a new
profile and an explicitly reviewed init.

## Independent participant checks

```sh
okto-nexus doctor --mode participant --profile reviewer --json
okto-nexus doctor --mode participant --profile reviewer --check-server --json
okto-nexus doctor --mode participant --profile reviewer --check-mcp --json
```

Default inspection reads only the retained profile and selected client file.
It does not read the vault/environment secret, use HTTP, start the client or
service, repair a file, create a profile, or advance setup checkpoints. Missing
profiles and unobserved levels are unknown; a confirmed changed entry is a
separate failure that does not hide other useful evidence.

`--check-server` explicitly reads the existing protected key and authenticates
the selected identity/workspace through the preparation GET. `--check-mcp`
includes that check, then initializes MCP and lists its tools. It checks the
required names/basic input fields, not the success or authorization of tool
calls. No tool, model, agent session, message or handoff is invoked. The temporary
MCP transport session is closed separately from Nexus agent participation.

The MCP stage has a time limit, at most 16 HTTP requests, four tool-list pages,
512 advertised tools and one MiB per response stream. It accepts only the exact
same-origin `/mcp` to `/mcp/` mount redirect; other redirects and compressed
payloads are refused. Raw SDK remote payload diagnostics are suppressed for
this check, so credentials/session identifiers cannot be echoed by those logs.
`--timeout` is the budget per active stage, up to 30 seconds.

`--check-environment` inspects only the named reference in **this doctor
process**. Missing or malformed values fail that check. With `--check-server`
or `--check-mcp`, that exact value is authenticated instead of reading the vault.
There is no fallback from a missing environment variable to the vault. A pass
is labeled `doctor_process`; it does not prove that a different terminal,
already-running daemon or GUI inherited anything. Do not print the key or add
it to shell arguments to obtain this evidence.

MCP success is labeled `participant_doctor`. Client reload, actual harness
environment, participation, handoff and work remain separate unknown levels.
No single aggregate state is a promise that the external client is ready.
