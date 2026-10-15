"""Production lifespan must retain the owner and journal through native drain."""
import asyncio
import threading
import time

import pytest

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
from okto_nexus.application.runtime_shutdown import shutdown_runtime
from okto_nexus.domain.base import iso_plus
from okto_nexus.errors import OktoNexusError
from test_pr34_remediation import runtime as runtime_fixture, open_rest

runtime = runtime_fixture








def test_lifespan_refuses_startup_when_another_owner_holds_store(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    deps.config.feature_harness_integrations = True
    repo = SqliteRuntimeOutboxRepo()
    now = deps.clock.now_iso()
    with deps.connection_factory.unit_of_work() as uow:
        epoch = repo.acquire_owner(uow, owner_id="fixture-first", now=now,
                                   lease_expires_at=iso_plus(now, 40))

    async def try_start():
        app = build_app(deps)
        async with app.router.lifespan_context(app):
            pytest.fail("contending owner exposed a serving app")

    with pytest.raises(RuntimeError, match="Another runtime owner"):
        asyncio.run(try_start())
    assert deps.runtime_dispatcher.epoch is None
    assert deps.harness_supervisor.list_live() == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert repo.owns(uow, owner_id="fixture-first", epoch=epoch, now=deps.clock.now_iso())
