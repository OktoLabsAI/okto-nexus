"""Offline additive migration composition, without provider/runtime startup."""
from pathlib import Path
from ..config import NexusConfig
from ..adapters.outbound.sqlite.connection import ConnectionFactory
from ..adapters.outbound.sqlite.migrations import MigrationRunner
from ..adapters.outbound.sqlite.execution_legacy_migration import (
    load_backup_manifest, require_preserved_baseline, backfill_catalog_batch, migration_baseline, require_idle_migration_owner,
)


def migrate_execution_catalog(source, backup, *, batch_size=100):
    source = Path(source).resolve()
    if not source.is_file():
        raise ValueError("The source database must already exist.")
    manifest = load_backup_manifest(backup)
    factory = ConnectionFactory(NexusConfig(home_dir=source.parent, db_path=source))
    # Confirm preserved data before applying an additive schema update.
    baseline = migration_baseline(manifest)
    with factory.unit_of_work(write=False) as uow:
        require_idle_migration_owner(uow.connection)
        require_preserved_baseline(uow.connection, baseline)
    applied = MigrationRunner(factory).apply()
    report = backfill_catalog_batch(factory, manifest, batch_size=batch_size)
    return {**report, "applied_schema_versions": applied}
