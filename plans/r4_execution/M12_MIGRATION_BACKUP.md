# M0 consistent operator database backup

The public maintenance command is:

    okto-nexus admin backup --db-path D:/path/to/nexus.db --output D:/backups/nexus-before-r4

Both paths are explicit. The output directory must not exist, and its parent
must already exist. The command opens the existing database read-only, pins a
read snapshot and uses SQLite's backup API, including committed WAL data.
It does not call runtime bootstrap, apply migrations, issue keys or spawn providers.

The resulting directory contains nexus.db and manifest.json. The manifest
records the database SHA-256, original schema/user-version header values,
snapshot schema digest, migration ledger, index names, every table's count and
streamed row digest, and counts of disabled/unapproved endpoints and denied
connection methods. Row contents, keys and message bodies are not printed or
included in the manifest. They remain in the database backup.

SQLite may change the destination schema cookie during backup. Source and
snapshot header values are recorded separately; data/DDL equality is checked
independently. The new command does not add an SQL migration. The currently
shipped runner ends at 091; a subsequent schema change must rediscover the next
free number at implementation time.

The backup is integrity-checked before publication. A manifest is published last;
a directory without that manifest is incomplete. Existing destinations are
refused using exclusive directory creation. Failed attempts may retain a unique
.nexus-backup-* staging directory for explicit inspection. Source files and
previous backups are never replaced by this command.

## Verification

The installed campaign passes four backup cases plus 40 existing admin,
key-issuance, retention, replay and architecture cases. Tests retain an active WAL
connection, compare the complete preserved inventory, check binary message data,
keep disabled policies unchanged, refuse overwrite/missing/corrupt source, and
invoke the real module CLI in an isolated subprocess against the complete current
schema. A spawn sentinel and bootstrap sentinel guard the in-process backup case.
All three source/wheel/installed package trees are compared by the runner.

Initial failures are preserved: read-only fsync is invalid on Windows; an
accidentally literal newline broke JSON output; comparing SQLite's destination
schema cookie directly with the source was incorrect; the first subprocess test
used a package without a __main__ instead of the actual CLI module. These were
corrected before the final installed run. Initial passes overlap the final count.

## Remaining NS15 scope

This is the M0 Nexus database snapshot, not a coordinated snapshot of Connector
vaults or Core journals. M1's additive schema is existing work; resumable M2/M3
catalog/endpoint backfill, migration_map population, controlled runtime cutover,
coordinated restore and normative TR4-15-01 remain open. The migration does not
activate a binding or reinterpret historical hashes. Full delivery gates remain
open.
