"""Compose connection inventory without importing adapters into application."""
from ..adapters.outbound.sqlite.connection_catalog import SqliteConnectionCatalogQueries
from ..application.connection_catalog import ConnectionCatalog
from .execution_authority import build_execution_access


def build_connection_catalog(deps):
    return ConnectionCatalog(factory=deps.connection_factory, access=build_execution_access(deps),
        queries=SqliteConnectionCatalogQueries(), clock=deps.clock)
