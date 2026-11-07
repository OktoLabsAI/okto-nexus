"""Passive canonical facts supplied to the optional correlation service."""
from typing import Protocol


class ObservationCorrelationProjection(Protocol):
    def load(self, uow, *, observed_instance_ids: list[str], check_budget=None) -> dict:
        """Read private facts for authorized IDs in the caller's snapshot."""
        ...


class ObservationCorrelationFacts(Protocol):
    def session(self, uow, *, server_id: str, executor_id: str, session_id: str) -> dict | None:
        """Read the exact namespace and its current bindings in the caller's UoW."""
        ...
