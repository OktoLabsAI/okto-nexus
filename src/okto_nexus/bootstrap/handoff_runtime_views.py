"""Compose read-only runtime projections independently of the scheduler."""
from ..adapters.outbound.sqlite.handoff_runtime_views import SqliteHandoffRuntimeViewRepository
from ..application.handoff_runtime_views import HandoffRuntimeViews


def build_handoff_runtime_views(deps):
    return HandoffRuntimeViews(SqliteHandoffRuntimeViewRepository(), automation_enabled=bool(
        deps.config.runtime_handoff_auto_claim_enabled and deps.config.feature_harness_integrations))


def handoff_runtime_metrics(deps):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return build_handoff_runtime_views(deps).metrics(uow)
