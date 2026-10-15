"""Compose diagnostics without granting runtime or handoff authority."""
from ..application.capacity_observations import CapacityObservationView
from ..adapters.outbound.sqlite.capacity_observations import SqliteCapacityObservationScopes


def build_capacity_observation_view(deps):
    return CapacityObservationView(deps.runtime_availability,
                                   SqliteCapacityObservationScopes(deps.connection_factory))
