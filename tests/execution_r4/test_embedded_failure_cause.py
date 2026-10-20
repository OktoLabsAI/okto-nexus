"""Producer diagnostics remain scoped and retain their first actionable cause."""
import asyncio
from types import SimpleNamespace

import pytest
from nexus_connector_core import CoreError
from okto_nexus.bootstrap.embedded_dispatch import EmbeddedDispatchOwner, SessionAuthorityGate
from okto_nexus.bootstrap.embedded_agent_recovery import EmbeddedAgentRecovery


def owner_fixture():
    owner = object.__new__(EmbeddedDispatchOwner)
    owner.failure = None
    owner.active_operations = set()
    owner._stopping = asyncio.Event()
    owner.capacity_waiter = SimpleNamespace(version=0)
    owner.capacity_publication = SimpleNamespace(tick=lambda: None)
    owner.channel = SimpleNamespace(connection_id="fixture", connection_generation=1)
    owner._request_grant = None
    owner.verify = lambda: None
    owner._recovery_event = lambda *args, **kwargs: None
    owner.agents = EmbeddedAgentRecovery(owner)
    owner.agents._state = lambda *args: None
    return owner


@pytest.mark.asyncio
@pytest.mark.parametrize("later_producer", ["execute", "renew"])
async def test_secondary_session_failure_preserves_first_cause_without_failing_host(later_producer):
    owner = owner_fixture()
    primary = CoreError("PROVIDER_AUTH_REQUIRED", "provider_vault", retry_safe=True)
    secondary = RuntimeError("The embedded Core host is shutting down.")
    async def execute(frame, **options):
        raise primary if frame["operation_id"] == "primary" else secondary
    async def renew(**kwargs):
        raise secondary
    async def host_failed():
        raise AssertionError("Agent failure must not contain other agents")
    owner._execute = execute
    owner.failed = host_failed
    session = dict(gate=asyncio.Lock(), executor=SimpleNamespace(renew_r4=renew),
                   authority_gate=SessionAuthorityGate(), scope={"agent_id": "subject"}, renew_at=None)
    owner.sessions = {"session": session}
    observed = []
    def recover_session(session_id, *, error=None):
        assert session_id == "session"
        session['recovering'] = True
        if error is not None:
            session.setdefault('recovery_error', error)
        observed.append(error)
    owner.agents.recover_session = recover_session

    await owner._execute_owned({"agent_id": "subject", "session_id": "session", "operation_id": "primary", "action": "turn.submit"})
    if later_producer == "execute":
        await owner._execute_owned({"agent_id": "subject", "session_id": "session", "operation_id": "secondary", "action": "turn.submit"})
    else:
        await owner._renew_owned("session", session)
    assert owner.failure is None
    assert owner.agents.blocked == set()
    assert session['recovery_error'] is primary
    assert observed == ([primary, secondary] if later_producer == "execute" else [primary, None])
    assert primary.retry_safe and not primary.possible_effect


@pytest.mark.asyncio
async def test_current_failure_is_persisted_without_overwriting_first_cause():
    from nexus_connector_core.native.adapter_types import NativeAdapterError, ErrorCode
    owner = owner_fixture()
    states, events = [], []
    owner.agents._state = lambda *args: states.append(args)
    owner._recovery_event = lambda *args, **kwargs: events.append(args)
    first = NativeAdapterError(ErrorCode.CONFIG_ERROR, 'Do not log provider credentials',
                               {'reason':'version_probe_timeout'})
    current = CoreError('RECONCILIATION_REQUIRED','embedded_agent_containment')
    await owner.agents.fail('subject',first)
    await owner.agents.fail('subject',current)
    assert states[-1] == ('subject','RECOVERING',current)
    assert owner.agents.errors['subject'] is first
    assert owner.agents.current_errors['subject'] is current
    assert 'embedded_agent_containment' in events[-1][1] and 'version_probe_timeout' in events[-1][1]
    assert 'Do not log' not in events[-1][1]


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
        await owner._execute_owned({"agent_id": "subject", "session_id": "session", "operation_id": "secondary"})
    elif later_producer == "renew":
        await owner._renew_owned("session", session)
    else:
        await owner._maintain()
    assert observed == [primary]
    assert owner.failure is primary
