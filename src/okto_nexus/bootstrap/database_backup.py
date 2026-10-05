"""Operator backup composition; deliberately bypasses runtime bootstrap."""
from ..adapters.outbound.sqlite.migration_backup import create_migration_backup


def backup_database(source, destination):
    return create_migration_backup(source, destination)
