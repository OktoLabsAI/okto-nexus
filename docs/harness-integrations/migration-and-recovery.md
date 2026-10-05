# Migration and recovery for 0.2.0

Use the reviewed 0.2.0 binary and an explicitly selected store. R4 migrations
are additive; do not reverse migrations or reactivate the old delivery callback.
The [operator guide](operator-guide.md) covers approved profiles/endpoints, and
[runtime administration](runtime-administration.md) specifies current recovery
requests, revision checks and risk acknowledgements.

## Prepare an offline recovery point

Record the installed version, configured home/database path, migration ledger,
canonical agent/profile inventory, endpoints, sessions and nonterminal operations.
Record journal checkpoint/watermark and unresolved unknown/unconfirmed effects.
Do not treat a saved RUNNING row, PID or expired owner lease as process evidence.

Stop new admissions, drain captured events and stop all database writers and
owned runtimes. Detach external attach sessions without killing their processes.
Use the repository procedure with matching code and dependencies:

```powershell
rtk proxy .venv/Scripts/python.exe tools/offline_runtime_backup.py backup SOURCE_HOME NEW_BACKUP_DIR --db-path SOURCE_DATABASE --all-writers-and-native-owners-stopped
rtk proxy .venv/Scripts/python.exe tools/offline_runtime_backup.py validate NEW_BACKUP_DIR
```

Replace placeholders with reviewed absolute paths. The acknowledgement records
operator-confirmed quiescence; it does not stop processes. The tool also checks
journal locking and owner lease state. Keep the backup under the source store's
access restrictions: it contains private data. Version 2 snapshots include
`nexus.db`, `runtime-journal-v1`, artifacts, the embedded `core-runtime` SQLite
journals/slot ledger and Server-owned `session-mcp` configuration. Core databases
are copied using SQLite backup under source exclusion locks; WAL contents are
included. Validation reads the copied databases without creating new WAL files.
Missing referenced embedded journals are refused, including in older snapshots.
Standalone operator-key files, OS-vault credentials, ambient provider homes and
arbitrary home configuration are not included. Remote Connector stores are also
separate: quiesce and preserve those owners and their Core journals before any
coordinated recovery. This Server snapshot cannot replace them. The detailed
[backup procedure](../../tools/offline_runtime_backup.py)
describes checksums, references, fsync limits and failure handling.

## Upgrade and enable one binding at a time

1. Stop incompatible old serve/stdio writers before replacing the binary. Start
   the new version with `--feature-harness-integrations false` explicitly. Schema
   migration alone does not authorize native execution or historical inbox replay.
2. Inspect the canonical inventory and migration diagnostics. Legacy events
   without trustworthy correlation remain legacy/unlinked. Ambiguous endpoint
   history stays disabled pending review. Restore a damaged profile only from
   reviewed trustworthy evidence; do not infer its old permissions or skills.
3. Validate configuration in a disposable store with synthetic peers first.
   Enable the integration, approved profile and endpoint explicitly in the
   intended environment. Issue grants and approve boot after configuration edits;
   old grants and boot approvals are revoked by those edits.
4. Send a new marked conversation and inspect operation, attempt, native event
   and durable result correlation. Confirm supported controls and cleanup before
   enabling additional bindings. Do not dispatch all old unread messages.
5. For managed work, test canonical claim, result and separate verification.
   Attach requires its approved external Nexus session proof and explicit ACK
   before completion; a socket write alone remains unconfirmed.

Writer capability guards refuse incompatible old writes when the integration
requires new invariants. Migration064 additionally fences old writers consuming
or completing external attach work. Never register compatibility SQL functions
manually to defeat the guard. Closed sessions referenced by external work remain
as audit identities; retention continues pruning unrelated expired sessions.

## Disable, reconcile or restore

Before any native effect, a failed selected MCP configuration apply leaves the
original file and its backup intact. Regenerate the plan if its compare-and-swap
hash changed, then retry only that selected entry. Unrelated MCP entries are
preserved. A successful HTTP migration is not rolled back to MCP stdio.

R4 session configuration uses a digest-named directory with an exact owner
marker. Configuration publication is atomic and never replaces an existing
file. Retry an interrupted apply only for the same owner and content. A foreign
binding marker or modified config is a conflict; do not overwrite or adopt it.
An active session retains its original path until resolution. Do not rename or
move its home, rewrite its owner marker, or delete its journal to change versions.

Block new admission and dispatch claims, retain authorized inspection, and drain
journal/projection. Stop only owned processes and preserve exact attempt/claim
facts. Disabling a feature is not evidence that a native write was never accepted.

Use `cancel_pending` only where the service verifies pre-send eligibility.
`release_to_inbox` preserves the same conversation delivery and requires explicit
duplicate-risk acknowledgement for uncertain sends. Managed handoffs use their
separate canonical recovery operation; they cannot be released as conversations.
Include the current state/attempt/owner snapshot, idempotency key and reason as
specified in runtime administration. Do not retry uncertain execution by timeout,
lease expiry, configuration edit, process restart or restore.

When restoring is necessary, preserve the original store and use a new directory:

```powershell
rtk proxy .venv/Scripts/python.exe tools/offline_runtime_backup.py restore NEW_BACKUP_DIR NEW_RESTORED_HOME --all-writers-and-native-owners-stopped
```

The restored database is `NEW_RESTORED_HOME/nexus.db`; clear any old external
database override before selecting it. Start with the integration explicitly
disabled, inspect integrity and unknown effects, and prove previous owners cannot
still act before re-enabling. A restored snapshot cannot undo external effects.
Use an older binary only with demonstrated writer/schema compatibility; the
normal rollback is the corrected version with admission disabled, not reverse SQL.
After a possible native effect, a pre-effect snapshot is not a rollback of that
effect. Drain and reconcile first, then take a new combined recovery point.
Keep unresolved `RECONCILING`/unknown operations and their original IDs, receipts
and claims. Restoring preserves them; it never grants permission to replay them.
The tool refuses overwrite of an existing destination and requires explicit
acknowledgement that all original writers/native owners have stopped.

Restore does not rewrite absolute paths, session ownership, approved environment
digests or credentials. Preserve the original tree as evidence. Inspect history
with execution disabled; provision credentials and approve a new configuration
through the normal binding flow only after the old session is resolved. Never
enable both the original and restored owners against the same external work.

Current evidence and remaining qualification limits are in the
[remediation index](evidence-index.md). No personal store was used as a test fixture.
