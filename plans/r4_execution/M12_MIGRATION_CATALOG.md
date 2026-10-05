# M2 resumable legacy catalog backfill

After creating the M0 backup, invoke:

    okto-nexus admin migrate-execution --db-path D:/path/to/nexus.db --backup D:/backups/nexus-before-r4 --batch-size 100

Each call commits at most one batch (1–1000 rows), returns processed/remaining
counts and reports execution_activated=false. Repeat until
CATALOG_BACKFILL_COMPLETE. This result describes catalog annotation only.

The command verifies the backup's file digest and its inventory against the
actual backup database. It compares preserved source columns to that baseline,
applies packaged additive migrations with the existing runner, ensures the
canonical embedded installation identity and records one transactional batch in
execution_migration_map. No new SQL migration was needed for this increment.

Profiles and endpoints retain their original rows, IDs, configuration, policy
and hashes. The migration-only closed map translates codex, pi,
claude_code.stream and claude_code.attach to their canonical Core IDs.
Unobserved known candidates become REDISCOVERY_REQUIRED, MCP remains TOOLS_ONLY,
and unknown IDs become MIGRATION_REVIEW_REQUIRED. Endpoint references preserve
the original agent and workspace and identify the embedded executor where
appropriate. Existing R4 bindings retain their existing executor/binding link.

Each record stores the original row digest and batch ID. Recorded source drift
or preserved baseline drift refuses further work. A failed transaction leaves
none of that batch's map entries; already committed batches remain intact.
Retries do not change earlier IDs, digests or batch IDs. No command string is
converted into executable argv, no profile is enabled and no provider is opened.

The source comparison intentionally permits additive schema-ledger changes and
the migration-map writes. Previously empty installation/executor tables may
receive the canonical installation identity. Other preexisting execution tables
remain part of the preserved-row comparison. Baseline validation is maintenance
work over the full preserved data set, not a runtime onboarding path.

## Verification

Eight installed migration/backup tests and 40 admin/architecture regressions
passed against the new Nexus wheel and unchanged Core/Connector wheels.
The catalog fixture begins at schema 065, with six legacy adapter IDs, denied
endpoints, a denied connection method, stored profile command text and an existing
agent key hash. Tests resume committed batches, repeat completed backfill twice,
inject an abort inside a batch, recover that batch, refuse source drift, and
refuse a tampered backup before schema expansion. A spawn sentinel rejects any
provider process creation. The installed runner compares all three source,
wheel and installation trees.

## Remaining work

M3 still needs the reviewed endpoint/workspace-to-binding transition and
canonical policy linkage, using actual Core rediscovery and consent. The map
records are not executable bindings. Full TR4-15-01 additionally requires its
historical-job fixture and complete M0–M3 acceptance. M4 runtime drain/cutover,
coordinated rollback and all delivery gates remain open. This command does not
replace those later stages or qualify a provider.
