"""Transactional persistence for explicitly authorized external observations.

Records are detached dictionaries, treated as immutable by callers. Every method
uses the caller's UoW, never commits, emits events, reads a clock or authenticates
a request. Management authorization and event emission belong to the service.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .ports import UnitOfWork


class ObservationRepo(Protocol):
    def create_source(self, uow: UnitOfWork, *, agent_id: str, source_kind: str,
                      workspace_ids: list[str], registration_ref: str, now: str,
                      source_limit: int = 32, installation_limit: int = 4096) -> dict: ...

    def get_source(self, uow: UnitOfWork, *, source_id: str) -> dict | None: ...

    def list_sources(self, uow: UnitOfWork, *, agent_id: str | None = None,
                     after: str | None = None, limit: int = 100) -> list[dict]: ...

    def update_source(self, uow: UnitOfWork, *, source_id: str, expected_revision: int,
                      now: str, workspace_ids: list[str] | None = None,
                      enabled: bool | None = None) -> dict: ...

    def revoke_source(self, uow: UnitOfWork, *, source_id: str,
                      expected_revision: int, now: str) -> dict: ...

    def create_instance(self, uow: UnitOfWork, *, source_id: str, expected_revision: int,
                        workspace_id: str, external_instance_ref: str, now: str,
                        instance_limit: int = 4096) -> dict: ...

    def rotate_instance(self, uow: UnitOfWork, *, source_id: str, expected_revision: int,
                        observed_instance_id: str, expected_generation: int, now: str) -> dict: ...

    def retire_instance(self, uow: UnitOfWork, *, source_id: str, expected_revision: int,
                        observed_instance_id: str, expected_generation: int, now: str) -> dict: ...

    def list_instances(self, uow: UnitOfWork, *, source_id: str,
                       after: str | None = None, limit: int = 100) -> list[dict]: ...

    def issue_token(self, uow: UnitOfWork, *, source_id: str, expected_revision: int,
                    token_hash: str, instance_grants: list[dict], issuer_agent_id: str | None,
                    now: str, expires_at: str, max_live: int = 8) -> dict: ...

    def revoke_token(self, uow: UnitOfWork, *, source_id: str, token_id: str,
                     now: str) -> dict: ...

    def get_token_by_hash(self, uow: UnitOfWork, *, token_hash: str) -> dict | None: ...

    def list_tokens(self, uow: UnitOfWork, *, source_id: str,
                    after: str | None = None, limit: int = 100) -> list[dict]: ...

    def get_publish_facts(self, uow: UnitOfWork, *, token_hash: str) -> dict | None:
        """Return {token, source, agent, grants, instances, heads} in <=4 SELECTs.

        grants/instances/heads are maps keyed by observed_instance_id. No expiry
        filtering: the service must distinguish missing, expired and revoked.
        """
        ...

    def get_head(self, uow: UnitOfWork, *, observed_instance_id: str) -> dict | None: ...

    def check_sequence(self, uow: UnitOfWork, *, observed_instance_id: str,
                       generation: int, sequence: int, report_hash: str) -> dict | None:
        """Return unchanged receipt on exact replay, None on new, else CONFLICT."""
        ...

    def store_report(self, uow: UnitOfWork, *, report: dict, report_hash: str,
                     source_revision: int, publisher_token_id: str,
                     received_at: str, valid_until: str) -> dict:
        """Fence again and store new head; exact replay returns original receipt."""
        ...

    def consume_budget(self, uow: UnitOfWork, *, source_id: str | None, agent_id: str,
                       cost: int, now: str, rates: dict | None = None) -> dict:
        """All-or-none buckets; rates={source|agent|installation:(per_minute,burst)}.

        Returns {allowed, retry_after_seconds}. A refusal performs no write.
        """
        ...

    def list_current(self, uow: UnitOfWork, *, agent_id: str | None = None,
                     workspace_id: str | None = None, source_id: str | None = None,
                     after: str | None = None, limit: int = 100) -> list[dict]: ...

    def count_prunable(self, uow: UnitOfWork, *, now: str) -> dict: ...

    def prune(self, uow: UnitOfWork, *, now: str, limit: int = 500) -> dict:
        """Bounded token/bucket cleanup; never deletes live head replay fences."""
        ...

    def prune_events(self, uow: UnitOfWork, *, cutoff: str, max_events: int = 20000,
                     limit: int = 500) -> int:
        """Delete observation.* events only, by age and global family row cap."""
        ...

    def count_prunable_events(self, uow: UnitOfWork, *, cutoff: str,
                              max_events: int = 20000) -> int: ...
