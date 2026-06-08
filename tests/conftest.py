"""Shared pytest fixtures.

These fixtures exercise the outbound SQLite adapters using only the stdlib
``sqlite3`` (via the adapters); they do NOT require the MCP SDK. Domain,
application, and SQLite tests can therefore run without ``mcp`` installed.
"""

from __future__ import annotations

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.config import NexusConfig


class FakeClock:
    """Deterministic :class:`Clock` implementation for tests.

    Starts at a fixed instant; :meth:`tick` advances the epoch (and is also
    reflected via :meth:`set_iso` for the ISO string when needed).
    """

    def __init__(
        self,
        iso: str = "2026-06-07T00:00:00Z",
        epoch: float = 1_780_000_000.0,
    ) -> None:
        self._iso = iso
        self._epoch = epoch

    def now_iso(self) -> str:
        return self._iso

    def now_epoch(self) -> float:
        return self._epoch

    def set_iso(self, iso: str) -> None:
        self._iso = iso

    def tick(self, seconds: float = 1.0) -> None:
        self._epoch += seconds


@pytest.fixture
def tmp_config(tmp_path) -> NexusConfig:
    """A :class:`NexusConfig` rooted under pytest's ``tmp_path``."""
    home = tmp_path / "okto_home"
    return NexusConfig(home_dir=home)


@pytest.fixture
def conn_factory(tmp_config: NexusConfig) -> ConnectionFactory:
    """A :class:`ConnectionFactory` over the temp config (home dir created)."""
    return ConnectionFactory(tmp_config)


@pytest.fixture
def migrated_factory(conn_factory: ConnectionFactory) -> ConnectionFactory:
    """A :class:`ConnectionFactory` whose database has all migrations applied."""
    MigrationRunner(conn_factory).apply()
    return conn_factory


@pytest.fixture
def fake_clock() -> FakeClock:
    """A deterministic clock implementing the :class:`Clock` port."""
    return FakeClock()
