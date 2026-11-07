# CLI usage guide

## Choose the task

| Task | Command | Effect |
|---|---|---|
| Check address/version | `reach --server URL` | Public HTTP probe, no key required |
| First guided connection | `connect --server URL --agent AGENT` | Imports key and guides remote runtime setup |
| Return to a configured project | `connect` | Validates the saved identity/binding and reuses the original request |
| Configure with an imported identity or JSON | `configure --identity ALIAS` | Interactive wizard on this computer by default |
| See actual connection progress | `status` | Queries server and daemon |
| Inspect failures | `logs --errors`, `doctor --probe` | Local logs and diagnostic probes |
| Keep the daemon running | `daemon start`, `service install` | Background process / user autostart |
| Run a turn explicitly | `runtime start`, `runtime submit` | Requires an approved binding and execution authorization |
| Start over locally | `clean` | Confirmed local reset; server records remain |

See the [complete syntax reference](cli-reference.md) for every flag, including advanced and legacy commands.

## Names, keys and IDs

| Value | Meaning | Example |
|---|---|---|
| Agent ID | Canonical identity on Nexus | `claude-coder` |
| Agent key | Secret authenticating that identity; obtain from Nexus | Enter at hidden prompt |
| Identity alias | Local name for an imported key/server pair; used by `--identity` | `assistant` |
| Connection alias | Local name of a configured binding; used by runtime commands | `claude` |
| Connector ID | Persistent local machine registration identity | Returned by diagnostics |
| Executor ID | Server-side registration of the execution host | Returned by `executor register/list` |
| Request/client intent ID | Stable identifier used to resume the same request | Printed by the wizard |
| Session ID | A runtime conversation, not an agent or binding | Returned by runtime status/start |

`--agent` checks a name against the key; it does not authenticate by itself. `--identity` selects a stored identity alias, not a raw key. Do not place keys in URLs or command arguments. Machine approvals use the registered Connector ID, not IP or hostname. Clearing state creates a new machine ID.

## Global options and shells

```sh
okto-nexus-connector --help
okto-nexus-connector configure --help
okto-nexus-connector --json status
okto-nexus-connector status --verbose
okto-nexus-connector status --json
okto-nexus-connector identity list --json
okto-nexus-connector --state-dir /absolute/connector-state status
```

`--json` and `--verbose` work before or after any command or subcommand. Other global flags (`--state-dir`, `--non-interactive`) precede the command. Quote paths with spaces. Examples use single-line commands compatible with ordinary POSIX shells and PowerShell; replace example addresses, aliases, IDs and paths. Do not type placeholder names literally. `configure` and `connect` are interactive and reject JSON/non-interactive mode. Do not use interactive wizards as unattended scripts.

Default output groups related information and uses readable tables for status, discovery and diagnostics. `--verbose` includes technical details such as connection IDs, timestamps and pending request IDs. Errors and suggested actions remain visible in the summary. `--json` takes precedence over `--verbose` and keeps the existing data fields. Interaction remains unchanged: supported prompts use stderr, including vault consent during identity import. Use `--non-interactive` before the command to prohibit questions and supply explicit arguments and credential input for automation. Help and version retain their standard text output; log streams retain JSON Lines.

Color is automatic on compatible interactive terminals, including Windows terminals with virtual terminal support. Redirected output and pipes contain no color codes. Set `NO_COLOR` (even an empty value) or `TERM=dumb` to disable color. Tables use ASCII separators and wrap long values; narrow terminals use labeled rows. Status words always convey meaning without color. No additional terminal library is required.

JSON status contains `connections` and is useful for automation. Exit code 0 indicates the command completed, not necessarily that every connection is online; inspect result/status fields. Exit codes: 1 application error, 2 usage/interruption, 3 daemon/executor unavailable or inaccessible state/log, 4 uncertain outcome. `status` returns 3 when the local lifecycle is neither confirmed ready nor stopped, in human and JSON modes. Streaming JSON output uses one record per line where supported.

`status`, `logs` and default `doctor` observe the selected instance without creating its state directory, lock, vault or daemon. `status` may read existing credentials to query the configured Server; it honors recorded vault consent. `doctor --probe` explicitly enables Server and selected-binary checks, and also honors that consent. An unknown/starting/degraded daemon stays distinct from a confirmed stopped daemon; unavailable IPC or logs do not prove absence of work.

`doctor --diagnostic-format v1 --json` opts into the common `okto.diagnostics`
report (`format_version: 1`). The default `--diagnostic-format legacy` preserves
the existing JSON fields, lowercase statuses, summary and exit conventions.
The selector changes presentation only: `--probe` remains the explicit choice
for existing Server/credential and selected-candidate checks. A returned Server
identity must match the saved profile in both formats, even when its agent ID
matches.

The v1 report gives each scoped check a `PASS`, `FAIL`, `UNKNOWN` or
`NOT_APPLICABLE`, a bounded code, reason and next action. Its counts include all
four states. `failed_checks`, `incomplete` and `checks_passed` summarize those
proofs; they are not a universal readiness or completed-work guarantee. A stopped
instance fails the readiness predicate, an unconfirmed instance stays unknown,
and a large journal can be a successful size observation with warning severity.
An unsupported required executor capability is a failure, not an inapplicable
check. `severity` is independent of proof status.

The Connector still returns exit 0 when it produces a report, including reports
with failed or unknown checks. Automation using v1 should inspect `counts.FAIL`
and the check relevant to its intended action. Nexus retains its own exit-code
convention. Unknown observations never initiate repairs, credential replacement,
provider login or productive work. Raw exception messages are excluded from v1.
The returned state-schema check concerns the snapshot's schema compatibility;
the snapshot may be an in-memory default when no state file exists.

The shared schema, catalog and hand-authored synthetic vectors live under
`tests/fixtures/diagnostics_v1`; they are contract fixtures, not runtime or
provider qualification. Their digest is pinned by the pure diagnostic adapter.

`logs` reads at most the newest 256 KiB per poll and emits only complete records up to 16 KiB. The JSON Lines stream includes `daemon_log_status` records for availability, rotation and truncation, alongside `daemon_log` records. Missing logs are a successful observation; inaccessible logs return 3 without `--follow`. A follower reports the access failure and continues observing. Byte limits, oversized records or slow readers can omit records; rotation backups remain available for separate inspection. Ctrl+C ends observation without stopping the daemon.

## Import and maintain identity

```sh
okto-nexus-connector identity add --server https://nexus.example.com --agent claude-coder --alias assistant
okto-nexus-connector identity list
okto-nexus-connector identity show assistant
okto-nexus-connector identity replace-credential assistant
```

`add` and credential replacement read a hidden prompt by default. Automation can use `--credential-stdin` or `--credential-env VARIABLE_NAME`; the variable must already be securely populated. `connect` additionally supports explicit MCP-entry import with `--mcp-entry` and `--mcp-entry-name`.

The OS keyring is preferred. Restricted-file fallback requires explicit consent and stores permission-restricted plaintext. `identity remove ALIAS` removes local identity material; it does not revoke the canonical key on Nexus. Credential replacement must authenticate as the same agent.

## Configure and approve

Follow [the connection guide](connection-configuration.md). Normal Connector setup needs the target agent key, not an operator key. The operator approves in Nexus. The daemon completes current submitted requests asynchronously; the wizard prints a request ID for recovery. A pending approval is not a usable binding.

Nexus **Remote machine policy** controls a second machine requesting the same agent: manual replacement approval (default), automatic denial, or automatic acceptance with revocation of the previous machine. Automatic replacement retains approved preferences and remaining authorization limits; it is not a fresh unlimited grant.

Model/reasoning/native approval preferences belong to the harness. Nexus tool access and execution authorization are separate. Selecting automatic native approval does not waive Nexus authorization. See [harness settings](harness-configuration.md).

## Daily operation

```sh
okto-nexus-connector status --agent claude-coder
okto-nexus-connector logs --tail 100
okto-nexus-connector logs --follow
okto-nexus-connector doctor --probe
okto-nexus-connector daemon status
okto-nexus-connector service install --dry-run
okto-nexus-connector service install
okto-nexus-connector service status
```

`daemon start` starts detached; `daemon run` owns the foreground until stopped. `daemon stop` drains/stops the daemon. `service uninstall` disables the OS autostart registration. The service uses the selected state directory and OS account; inspect its plan for logout/boot behavior. A running process is not proof of a live server connection.

## Runtime sessions

Use the acknowledged connection alias and returned IDs:

```sh
okto-nexus-connector runtime start claude --client-intent-id open-1 --text "Reply with Ready."
okto-nexus-connector runtime status --alias claude
okto-nexus-connector runtime inspect SESSION_ID --alias claude
okto-nexus-connector runtime submit SESSION_ID "Summarize your last response." --alias claude --client-intent-id turn-1
okto-nexus-connector runtime operation --alias claude --client-intent-id turn-1
okto-nexus-connector runtime interrupt SESSION_ID --alias claude --client-intent-id interrupt-1 --current-run
okto-nexus-connector runtime stop SESSION_ID --alias claude --client-intent-id close-1 --reason "Work completed"
```

Admission is not completion; query the operation for its result. Reuse the same intent only to recover the exact same request. Use a new ID for intentional new work. `--new-session` explicitly requests a new compatible conversation. `steer` and interrupt targeting depend on native adapter support; inspect `--help` for `--expected-turn-id` versus `--current-run`.

`runtime logs SESSION_ID` is a legacy stream surface, not a complete R4 event viewer. Use canonical operation/session status and Nexus execution logs for R4. Automatic Nexus delivery does not require manually starting a session for every message.

## Proxy and transport

```sh
okto-nexus-connector proxy set --url http://proxy.example.com:8080 --no-proxy ".internal.example.com"
okto-nexus-connector proxy show
okto-nexus-connector proxy set --url-env NEXUS_PROXY_URL
okto-nexus-connector proxy set --direct
okto-nexus-connector proxy clear
```

For authentication, securely populate `NEXUS_PROXY_URL` with the URL-encoded proxy URL first. Only its variable name is saved; the daemon/service must receive the variable too. A missing configured variable fails rather than silently connecting directly. Restart the daemon after changing proxy settings/environment.

Without saved configuration, proxy discovery uses HTTPS_PROXY for HTTPS/WSS, HTTP_PROXY for HTTP/WS, then ALL_PROXY. NO_PROXY or `--no-proxy` accepts hosts, domain suffixes, host:port entries or `*`. Loopback bypasses proxies. HTTP(S) proxies and Basic authentication are supported; SOCKS/NTLM are not. Corporate CA roots can use SSL_CERT_FILE/SSL_CERT_DIR. TLS verification remains enabled.

Nexus global transport policy decides whether HTTP/WS is allowed or HTTPS/WSS is mandatory. Provider API/MCP traffic uses the harness's network settings; Connector proxy configuration covers Connector-to-Nexus traffic and is not exported in portable JSON.

## Advanced R4 automation

The wizard is recommended. Explicit commands expose individual steps for tooling; registering an executor alone does not authorize runtime execution. Obtain each ID/revision/digest from the preceding response, not from example text.

1. Import identity using a protected source, then `executor register --identity ALIAS --label HOST_LABEL`.
2. Use `executor configure-discovery --server-id SERVER_ID --harness-root ABSOLUTE_DIRECTORY` as needed; this replaces configured discovery roots, not the system PATH. `discover --server-id SERVER_ID --verbose` shows candidates.
3. Run `executor probe` with the selected harness, candidate ref and inventory revision.
4. Stage consent using `executor configure-launch --identity ALIAS --harness ADAPTER --local-consent-id CONSENT_ID --profile-revision 1`, optionally selecting provider home/secret references.
5. Start the daemon. Publish `executor realize` with the same identity, adapter, candidate, inventory revision, configuration digest and an explicit project/label. Retain the returned realization reference.
6. `bind prepare --identity ALIAS --realization-ref REF --alias CONNECTION --client-intent-id PREPARE_ID`; review the exact diff and obtain required operator approval.
7. `bind apply --identity ALIAS --prepare-intent-id PREPARE_ID --client-intent-id APPLY_ID --approved-diff-hash HASH --operator-proof-ref APPROVAL_REF` when a proof is required.

These low-level binding commands do not include the wizard's complete configuration/authorization bundle. Execution may still require operator configuration and a valid grant in Nexus. Do not equate a binding acknowledgment with permission to run. Use [the syntax reference](cli-reference.md) for all required realization/probe flags.

## Compatibility command boundaries

`bind create/list/show/remove` manage the older local binding surface; they are not the canonical R4 prepare/apply workflow. `approvals list/decide` is a daemon-mediated HITL surface, not a way for an agent key to approve its own remote access; use Nexus Approvals for onboarding. `mcp-config plan/apply/remove` manages selected direct-HTTP client configuration, not a Connector MCP server. It requires an explicit server-issued capability reference and supported client format; Pi uses its native tools bridge. Preserve ownership/CAS checks when changing existing client files.

## Clean reset

```sh
okto-nexus-connector clean
okto-nexus-connector --non-interactive clean --yes
```

The interactive default is No. See [cleanup scope and recovery cautions](runbook.md#reset-abandoned-local-configuration) before confirming. The command is local and does not cancel/revoke records in Nexus. For a transient network failure, use diagnostics and resume the original request instead.

## Reconnect all connections

Run okto-nexus-connector reconnect to gracefully stop and restart the daemon for the selected state directory. Configurations and credentials are preserved. Active harness executions may be interrupted during shutdown. The command returns when the daemon is ready; server connections complete asynchronously. Check okto-nexus-connector status and okto-nexus-connector logs --errors for progress. If shutdown cannot finish within 30 seconds, no second daemon is started.

Automatic connection retries use delays of 2, 4, 8, 16 and 30 seconds, then continue every 30 seconds until the daemon is stopped, including reconciliation failures. Pending socket cleanup is retried before opening another connection. Retrying does not replay submitted work or bypass Nexus authorization.
