"""Assemble the existing-Home-authorized entries reader and its read routes."""
from ..adapters.inbound.http.home_entries import build_router
from ..adapters.outbound.sqlite.home_entries import SqliteHomeEntryRelations
from ..application.home_entries import HomeEntriesService


def install_home_entries(app, home_service):
    app.state.home_entries = HomeEntriesService(home_service, queries=SqliteHomeEntryRelations())
    if not getattr(app.state, 'home_entries_routes_installed', False):
        app.include_router(build_router(), prefix='/api/v1')
        app.state.home_entries_routes_installed = True
    return app.state.home_entries
