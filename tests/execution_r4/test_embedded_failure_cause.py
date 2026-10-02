"""Concurrent producer failures preserve the first actionable diagnostic."""
import asyncio
from types import SimpleNamespace

import pytest
from nexus_connector_core import CoreError
from okto_nexus.bootstrap.embedded_dispatch import EmbeddedDispatchOwner


@pytest.mark.asyncio
@pytest.mark.parametrize("later_producer", ["execute", "renew", "maintain"])
async def test_secondary_producer_failure_preserves_first_cause(later_producer):
    # Unit boundary: isolate producer error arbitration from real containment,
    # which provider-vault and shutdown integration suites exercise separately.
    owner = object.__new__(EmbeddedDispatchOwner)
    owner.failure = None
    owner._stopping = asyncio.Event()
    first_seen = asyncio.Event()
    observed = []
    primary = CoreError("PROVIDER_AUTH_REQUIRED", "provider_vault", retry_safe=True)
    secondary = RuntimeError("The embedded Core host is shutting down.")

    async def contain():
        observed.append(owner.failure)
        first_seen.set()

    async def execute(frame):
        if frame == "primary":
            raise primary
        await first_seen.wait()
        raise secondary

    async def renew(**kwargs):
        await first_seen.wait()
        raise secondary

    def page():
        raise secondary

    owner.failed = contain
    owner._execute = execute
    owner._page = page
    owner.channel = SimpleNamespace(connection_id="fixture", connection_generation=1)
    owner._request_grant = None
    session = dict(gate=asyncio.Lock(), executor=SimpleNamespace(renew_r4=renew), scope={}, renew_at=None)
    owner.sessions = {"session": session}

    async def later():
        await first_seen.wait()
        if later_producer == "execute":
            await owner._execute_owned("secondary")
        elif later_producer == "renew":
            await owner._renew_owned("session", session)
        else:
            await owner._maintain()

    await asyncio.wait_for(asyncio.gather(owner._execute_owned("primary"), later()), 5)
    assert observed == [primary, primary]
    assert owner.failure is primary
    assert owner.failure.retry_safe and not owner.failure.possible_effect
