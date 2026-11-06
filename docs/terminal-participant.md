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
for recovery; automated cleanup/removal is not part of this increment.

**Configuration applied is not client ready.** Output separates authenticated
identity, entry present, credential in the client context, client reload, MCP
negotiation and work submitted. Vault storage does not make the variable
available to a launcher or GUI. The latter levels remain unknown. A dedicated
participant launcher, participant doctor and cooperation smoke are pending;
managed `doctor` does not inspect these profiles. Do not start a model to resolve
that uncertainty. The external client still needs secure environment delivery,
project trust/reload and reconnect before its readiness can be verified.

One identity has one logical delivery: an additional client is not guaranteed to
consume every message, and deliveries are not broadcast to every channel. Its
existing runtime remains configured. A separate identity requires an explicit
operator decision.

The proposed `entry` is reference-only manual guidance. The complete JSON
response/profile contains host paths and identity context; it is a local
receipt, **not a portable template**.
