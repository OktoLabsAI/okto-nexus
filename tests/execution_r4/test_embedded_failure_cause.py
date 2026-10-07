"""Producer diagnostics remain scoped and retain their first actionable cause."""
import asyncio
from types import SimpleNamespace

import pytest
from nexus_connector_core import CoreError
from okto_nexus.bootstrap.embedded_dispatch import EmbeddedDispatchOwner
from okto_nexus.bootstrap.embedded_agent_recovery import EmbeddedAgentRecovery


def owner_fixture():
    owner = object.__new__(EmbeddedDispatchOwner)
    owner.failure = None
    owner._stopping = asyncio.Event()
    owner.channel = SimpleNamespace(connection_id="fixture", connection_generation=1)
    owner._request_grant = None
    owner.verify = lambda: None
    owner._recovery_event = lambda *args, **kwargs: None
    owner.agents = EmbeddedAgentRecovery(owner)
    owner.agents._state = lambda *args: None
    return owner


@pytest.mark.asyncio
@pytest.mark.parametrize("later_producer", ["execute", "renew"])
async def test_secondary_agent_failure_preserves_first_cause_without_failing_host(later_producer):
    owner = owner_fixture()
    primary = CoreError("PROVIDER_AUTH_REQUIRED", "provider_vault", retry_safe=True)
    secondary = RuntimeError("The embedded Core host is shutting down.")
    async def execute(frame):
        raise primary if frame["operation_id"] == "primary" else secondary
    async def renew(**kwargs):
        raise secondary
    async def host_failed():
        raise AssertionError("Agent failure must not contain other agents")
    owner._execute = execute
    owner.failed = host_failed
    session = dict(gate=asyncio.Lock(), executor=SimpleNamespace(renew_r4=renew),
                   scope={"agent_id": "subject"}, renew_at=None)
    owner.sessions = {"session": session}

    await owner._execute_owned({"agent_id": "subject", "operation_id": "primary"})
    if later_producer == "execute":
        await owner._execute_owned({"agent_id": "subject", "operation_id": "secondary"})
    else:
        await owner._renew_owned("session", session)
    assert owner.failure is None
    assert owner.agents.blocked == {"subject"}
    assert owner.agents.errors == {"subject": primary}
    assert primary.retry_safe and not primary.possible_effect


@pytest.mark.asyncio
@pytest.mark.parametrize("later_producer", ["execute", "renew", "maintain"])
async def test_secondary_shared_failure_preserves_first_host_cause(monkeypatch, later_producer):
    owner = owner_fixture()
    primary = CoreError("JOURNAL_UNAVAILABLE", "shared_journal", retry_safe=True)
    secondary = RuntimeError("The embedded Core host is shutting down.")
    owner.failure = primary
    observed = []
    async def contain():
        observed.append(owner.failure)
    async def fail(*args, **kwargs):
        raise secondary
    def page(*args):
        raise secondary
    owner.failed = contain
    owner._execute = fail
    owner.agents.fail = fail
    owner.deps = SimpleNamespace()
    session = dict(gate=asyncio.Lock(), executor=SimpleNamespace(renew_r4=fail),
                   scope={"agent_id": "subject"}, renew_at=None)
    owner.sessions = {"session": session}
    from okto_nexus.application import runtime_recovery
    monkeypatch.setattr(runtime_recovery, "drain_pending", page)
    if later_producer == "execute":
        await owner._execute_owned({"agent_id": "subject"})
    elif later_producer == "renew":
        await owner._renew_owned("session", session)
    else:
        await owner._maintain()
    assert observed == [primary]
    assert owner.failure is primary
