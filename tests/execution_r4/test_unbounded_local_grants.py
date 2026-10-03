"""Explicit unbounded local delegation retains revocation and renewable leases."""
import pytest

from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from okto_nexus.domain.base import iso_plus
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError


def issue(setup, binding, *, expires_at=None, max_executions=None, actor='operator'):
    return setup[2].post('/api/v1/harness/grants', headers=setup[3][actor], json=dict(
        actor_agent_id='subject', endpoint_id=binding['endpoint_id'],
        actions=['open', 'send', 'steer', 'interrupt', 'close', 'discover'],
        expires_at=expires_at, max_executions=max_executions))


def test_unbounded_grant_opens_renews_and_revokes(connected_local):
    setup, binding, native = connected_local
    owner = setup[1].state.embedded_dispatch_owner
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at='revoked'")
    response = issue(setup, binding)
    assert response.status_code == 200, response.text
    grant = response.json()['data']
    assert grant['expires_at'] is None and grant['max_executions'] is None
    # Persisted legacy fields are deliberately expired/exhausted: flags, rather
    # than a distant timestamp or huge numeric allowance, define the policy.
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE runtime_execution_grants SET expires_at=?,used_executions=1001 WHERE grant_id=?',
            ('2000-01-01T00:00:00Z', grant['grant_id']))
        actor = setup[0].repos.agents.get(uow, 'subject')
    from okto_nexus.application.runtime_discovery import RuntimeDiscoveryService
    context = RuntimeRequestContext('subject', 'agent_key', credential_binding=actor.api_key_hash,
                                    execution_grant_id=grant['grant_id'])
    discovered = RuntimeDiscoveryService(access=owner.pump.access).list(context, agent_id='subject')
    assert discovered['agents'][0]['endpoints'][0]['endpoint_id'] == binding['endpoint_id']
    opened = admit(setup, binding, 'unbounded-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    sent = admit(setup, binding, 'unbounded-send', 'turn.submit', session_id=opened['session_id'], text='Hello')
    wait_receipt(setup, sent)
    setup[2].portal.call(owner._renew_owned, opened['session_id'], owner.sessions[opened['session_id']])
    assert not native.native.stopped and owner.failure is None
    # Session credentials retain a short lifetime even with indefinite consent.
    from okto_nexus.application.execution_capabilities import ExecutionCapabilityService
    capability = ExecutionCapabilityService(factory=setup[0].connection_factory, access=owner.pump.access)
    issued = capability.issue(context=context, session_id=opened['session_id'], request=dict(
        capability_request_id='unbounded-capability', binding_id=binding['binding_id'],
        audience='nexus-mcp-session', actions=['tools/call']), mcp_url='http://127.0.0.1:8202/mcp')
    assert 1 <= issued['expires_in'] <= 120
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute('SELECT * FROM runtime_execution_grants WHERE grant_id=?', (grant['grant_id'],)).fetchone()
        assert row['used_executions'] == 1002
        lease = uow.connection.execute('SELECT * FROM execution_leases ORDER BY lease_serial DESC LIMIT 1').fetchone()
        from okto_nexus.domain.base import iso_to_epoch
        assert 0 < iso_to_epoch(lease['valid_until_server']) - iso_to_epoch(lease['issued_at']) <= 120
    with setup[0].connection_factory.unit_of_work() as uow:
        owner.pump.access.grants.revoke(uow, grant_id=grant['grant_id'], now=setup[0].clock.now_iso())
    setup[2].portal.call(owner._renew_owned, opened['session_id'], owner.sessions[opened['session_id']])
    assert native.native.stopped and owner.failure is None


@pytest.mark.parametrize('no_expiry,unlimited', [(True, False), (False, True), (False, False)])
def test_independent_limits_remain_enforced(connected_local, no_expiry, unlimited):
    setup, binding, _ = connected_local
    response = issue(setup, binding,
        expires_at=None if no_expiry else iso_plus(setup[0].clock.now_iso(), 600),
        max_executions=None if unlimited else 2)
    assert response.status_code == 200, response.text
    grant_id = response.json()['data']['grant_id']
    access = setup[1].state.embedded_dispatch_owner.pump.access
    with setup[0].connection_factory.unit_of_work() as uow:
        actor = setup[0].repos.agents.get(uow, 'subject')
        context = RuntimeRequestContext('subject', 'agent_key', credential_binding=actor.api_key_hash,
                                        execution_grant_id=grant_id)
        uow.connection.execute('UPDATE runtime_execution_grants SET used_executions=2 WHERE grant_id=?', (grant_id,))
        if unlimited:
            access.authorize(context, action='send', endpoint_id=binding['endpoint_id'], uow=uow)
        else:
            with pytest.raises(OktoNexusError):
                access.authorize(context, action='send', endpoint_id=binding['endpoint_id'], uow=uow)
        uow.connection.execute("UPDATE runtime_execution_grants SET expires_at='2000-01-01T00:00:00Z' WHERE grant_id=?", (grant_id,))
        if no_expiry:
            access.authorize(context, action='open', endpoint_id=binding['endpoint_id'], uow=uow)
        else:
            with pytest.raises(OktoNexusError):
                access.authorize(context, action='open', endpoint_id=binding['endpoint_id'], uow=uow)


def test_unbounded_requires_operator_and_explicit_nulls(connected_local):
    setup, binding, _ = connected_local
    assert issue(setup, binding, actor='subject').status_code == 403
    for budget in (0, -1, 1001):
        assert issue(setup, binding, max_executions=budget).status_code == 422
    assert issue(setup, binding, expires_at='').status_code == 422
    assert issue(setup, binding, expires_at=iso_plus(setup[0].clock.now_iso(), 90000)).status_code == 422
