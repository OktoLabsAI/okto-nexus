# Quick Connect

From an existing project directory:

```sh
okto-nexus connect codex
okto-nexus codex
okto-nexus connect claude --id reviewer
```

The first two commands enter the same flow. The last command requests another
harness named `reviewer` in the selected project. It does not replace Codex.
Supported family tokens are `codex`, `claude` and `pi`; discovery, policy,
installation and provider authentication remain separate checks. An unavailable
harness can be changed explicitly in an interactive picker. Listing never
installs software or tests provider login.

The basic identifier is **ID do Harness** in the CLI and **Harness ID** in the
English dashboard. Its wire key is `connect_id`. Agent role, adapter family,
binding/session IDs and the technical local profile keep their existing meanings.
The ID starts with an ASCII letter, uses at most 64 letters/digits/underscores/
hyphens, and is normalized to lowercase. It is unique per Server and workspace,
including across execution hosts. Automatic names use the selected family;
additional names such as `codex-2` require an explicit addition and review.

## Project and execution directory

```sh
okto-nexus connect codex "My application"
okto-nexus connect codex "My application" --project /existing/execution/folder
```

The second positional is a logical project name. `--project` remains a physical
path. No directory, clone or repository is created. Explicit concordant choices
win, followed by an approved Nexus directory association, a local Git origin
name hint, the Git working-tree basename, then the physical directory basename.
Projects without a connection are included in the authorized directory. Duplicate
names, incomplete pagination and mismatched roots require resolution.

Git only suggests a name. It does not identify projects, merge clones/worktrees,
rename saved connections or expand a monorepo subdirectory's execution root.
Discovery is local and bounded: trusted absolute executable outside the project
repository, sanitized environment, no network/includes/hooks/configuration
writes, at most six commands sharing two seconds and 64 KiB per response.
Unavailable/ambiguous Git falls back explicitly. Origin URLs, credentials, query
strings and raw stderr are not retained in review/output metadata. `--help`,
grammar errors, `--plan` and retained-intent recovery never start Git.

## Review, add and resume

The final review includes project/name source, invocation and execution folders,
effective harness, public ID, host and canonical effects. Confirm, customize or
cancel. Customization creates a fresh proposal and review hash, preserving the
previous unapproved checkpoint as superseded. Its old approval cannot apply the
new intent. Selecting a menu item alone does not authorize the model test.

Repeating a connection offers resume or explicit addition. An occupied ID never
changes its harness, binding or grants. Choosing another family during a
collision is explicit and recomposes the review. `--new-connection` cannot use
resume as a substitute for adding. Revoked/disabled connections and uncertain
reservations continue to occupy their IDs. There is no automatic TTL recycling.

Resume validates the exact canonical reference; it does not select the latest
session, renew a grant, repeat a connection test or submit work. Native work and
session commands retain their separate approvals and pending-send recovery.
Remote operator CWD/Git cannot redefine a Connector's execution directory. New
remote host setup remains with its Connector; unavailability never creates a
replacement local Server.

## Scripts and recovery

Existing `--client`, `--project`, `--profile`, `--agent`, `--binding-id`, `--plan`,
`--approve`, `--json` and `--no-chat` remain available. Short positionals and `--id`
are managed-mode grammar; mixing them with participant mode is refused before
setup. Root aliases do not override product commands.

A bare `connect` enters Quick Connect. Commands using only legacy selectors,
such as `connect --client codex --project /existing/project`, keep their original
selection and recovery flow; they do not require public-ID adoption to resume.
Add a positional harness or `--id` to explicitly choose Quick Connect alongside
those flags. An exact saved Quick Connect profile retains its original flow.

For a stable scripted addition, choose a technical checkpoint explicitly:

```sh
okto-nexus connect codex "My application" --id implementer --profile build-worker --new-connection --plan --json
okto-nexus connect codex "My application" --id implementer --profile build-worker --new-connection --approve REVIEW_REVISION --json
```

Use the actual returned revision and unchanged choices. These commands are
syntax examples; approving a real model test requires its own budget and consent.
`--plan` never starts a stopped daemon, reserves a public ID, probes a version or
calls a model. A stopped service produces `service_not_ready`; it is not an empty
project inventory. JSON/non-TTY never reads a prompt or enters chat, and a new
scripted addition still requires a stable `--profile`. `--id` is not an
idempotency key. Exact flags must agree; no fuzzy or latest-session selection.

`quick_connect.version=1` separates proposed/reserved IDs from bound IDs.
`status=connected` requires `connect_id`, `connect_id_status=bound` and a
revalidated full canonical reference. It says configured/reused, with session
`not_checked` and work `not_submitted`. A successful exit also covers valid
plans and cancellation; exit code alone is not connection proof. `resume_argv`
is an unexecuted argument array that preserves spaces and metacharacters.
It includes the approved local `--project` or remote `--operator-profile`, plus
exact workspace/binding selectors. Human success output renders a public resume
command for POSIX `sh` or **PowerShell 7.3+**, retaining the selected installation
and execution context while hiding the technical profile. PowerShell uses its
standard native argument binder in a child scope; the command refuses older
PowerShell versions before invocation. This is not `cmd.exe` quoting. For Windows
PowerShell 5.1 or another shell, consume the JSON array through an argument-vector
API instead of pasting a command intended for a different shell. A pending local
shortcut repair still requires the same technical intent/profile from JSON.

`HARNESS_ID_ALREADY_EXISTS`, `CONNECT_ID_PENDING`,
`PROJECT_CATALOG_UNCONFIRMED` and `CONNECT_ID_UNSUPPORTED_SERVER` are distinct
refusals. A lost reservation or Finish response retains the same intent; inspect
or resume that checkpoint instead of allocating another identity. After Server
commit, a local disk failure returns `configured_shortcut_pending`; retry repairs
the shortcut from the canonical receipt, without another test or grant.

## Compatibility and rollback

Migration 168 adds persistent public-ID and project-draft metadata. Finish binds
the ID and receipt inside the existing setup transaction. Legacy requests omit
the optional `public_connection` member, preserving old request hashes/receipts.
Associating an ID with an existing binding is an approved metadata operation.
Passive catalog/Home reads assign no ID. Older connections retain their fallback
labels; the shared UI can explicitly show that a Harness ID is not assigned.

Set `OKTO_NEXUS_QUICK_CONNECT=off` to disable the new short entry points while
retaining the Server registry, bindings, grants, data and exact profile recovery.
Existing `connect --profile NAME` continues to work. Re-enable the entry by
removing that override. Do not drop metadata tables, delete profiles or roll back
the database as a presentation rollback. No new daemon or per-ID service is used.

Qualification is recorded separately under `NEXUS_QUICK_CONNECT_R1/`. Unit,
HTTP/SQLite, browser, PTY and installed-package evidence do not claim a real
provider campaign, human usability, screen-reader support or another OS.
