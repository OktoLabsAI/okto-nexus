"""Registered adapters remain available through canonical product surfaces."""
from contextlib import contextmanager
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from nexus_connector_core.native import registry
from nexus_connector_core import ControlTargeting
from test_local_realization import local_setup
from test_embedded_dispatch import connect_local, wait_receipt, qualified_contract
from test_pr34_remediation import tool
from registered_native_peer import ADAPTER, RegisteredPeer


@pytest.fixture
def registered_setup(tmp_path, monkeypatch):
    monkeypatch.setitem(registry._SPECS, ADAPTER, registry.AdapterSpec(
        ADAPTER, ADAPTER, 'registered_native_peer', 'RegisteredPeer', 'managed', None,
        frozenset({sys.platform}),
        (ControlTargeting('turn.steer', False, 'forbidden', False),
         ControlTargeting('turn.interrupt', False, 'forbidden', False)),
        managed_contract=1, transport_binding_contract=1))
    monkeypatch.setattr(RegisteredPeer, 'instances', [])
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, SimpleNamespace(param=ADAPTER)) as setup:
        from okto_nexus.domain.ids import resolve_workspace_id
        workspace = resolve_workspace_id(str(setup[-1]))
        with setup[0].connection_factory.unit_of_work() as uow:
            setup[0].repos.workspaces.upsert(uow, workspace_id=workspace,
                root_realpath=str(setup[-1]), last_seen_at=setup[0].clock.now_iso())
        setup[4]['workspace_id'] = workspace
        _, binding, _ = connect_local(setup)
        setup[1].state.embedded_dispatch_owner.native_factory = None
        setup[1].state.test_owned_factories = []
        setup[2].headers['host'] = '127.0.0.1:8000'
        yield setup, binding
    for factory in setup[1].state.test_owned_factories:
        factory.close()


def subject_key(setup):
    return setup[3]['subject']['Authorization'].removeprefix('Bearer ')


def test_registered_adapter_self_discovery_connects_without_process(registered_setup, monkeypatch):
    setup, binding = registered_setup
    def forbidden(*args, **kwargs):
        raise AssertionError('A registered processless adapter must not spawn')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    available = tool(setup[2], subject_key(setup), 'harness_list',
        dict(view='connections', maintenance=dict(action='available')))
    assert available['ok'], available
    method = next(m for m in available['data']['methods'] if m['method'] == ADAPTER)
    assert method['available'], method
    arguments = method['endpoints'][0]['connect']['arguments']
    arguments['maintenance']['idempotency_key'] = 'registered-self-connect'
    opened = tool(setup[2], subject_key(setup), 'harness_list', arguments)
    assert opened['ok'], opened
    wait_receipt(setup, opened['data'])
    assert opened['data']['scope']['agent_id'] == 'subject'
    assert len(RegisteredPeer.instances) == 1
    assert RegisteredPeer.instances[0].sent == []


@pytest.mark.parametrize('surface', ['rest', 'mcp'])
def test_registered_adapter_public_open_and_send_have_correlated_result(registered_setup, monkeypatch, surface):
    setup, binding = registered_setup
    def forbidden(*args, **kwargs):
        raise AssertionError('A registered processless adapter must not spawn')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    args = dict(agent_id='subject', kind=ADAPTER, endpoint_id=binding['endpoint_id'],
        project_root=str(setup[-1]), idempotency_key='registered-open-' + surface)
    if surface == 'mcp':
        opened = tool(setup[2], subject_key(setup), 'harness_open', args)
        assert opened['ok'], opened
        opened = opened['data']
    else:
        response = setup[2].post('/api/v1/harness/sessions', headers=setup[3]['subject'], json=args)
        assert response.status_code == 200, response.text
        opened = response.json()['data']
    wait_receipt(setup, opened)
    args = dict(session_id=opened['scope']['session_id'], payload={'text': 'registered public command'},
        idempotency_key='registered-send-' + surface)
    if surface == 'mcp':
        sent = tool(setup[2], subject_key(setup), 'harness_send', args)
        assert sent['ok'], sent
        sent = sent['data']
    else:
        response = setup[2].post('/api/v1/harness/sessions/' + args['session_id'] + '/send',
            headers=setup[3]['subject'], json={k:v for k,v in args.items() if k != 'session_id'})
        assert response.status_code == 200, response.text
        sent = response.json()['data']
    wait_receipt(setup, sent, stages=('SUCCEEDED',))
    assert len(RegisteredPeer.instances) == 1
    commands = RegisteredPeer.instances[0].sent
    assert len(commands) == 1 and commands[0].operation_id == sent['operation_id']
    assert commands[0].payload == {'text': 'registered public command'}


@pytest.mark.parametrize('binding_contract', [1, None])
def test_registered_fallback_requires_versioned_binding_and_preserves_context(registered_setup, monkeypatch, binding_contract):
    from dataclasses import replace
    from nexus_connector_core.models import EffectNotSent
    from nexus_connector_core.native.runtime_bridge import CopiedAdapterFactory
    from test_canonical_identity_lifecycle import second_binding
    from test_canonical_delivery import enable, send
    from test_canonical_delivery_retry import wait_delivery
    from test_embedded_dispatch import admit
    from test_vertical_inventory import _Native

    setup, registered = registered_setup
    monkeypatch.setitem(registry._SPECS, ADAPTER,
        replace(registry._SPECS[ADAPTER], transport_binding_contract=binding_contract))
    monkeypatch.setattr(RegisteredPeer, 'binding_contract', binding_contract)
    clock = [setup[0].clock.now_iso()]
    monkeypatch.setattr(setup[0].clock, 'now_iso', lambda: clock[0])
    source = second_binding(setup, monkeypatch, name='source', adapter_id='pi_rpc')
    alternative = second_binding(setup, monkeypatch, name='alternative', adapter_id='codex_app_server')
    for binding in (source, registered, alternative):
        enable(setup, binding)
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET selection_group='registered-alternatives',priority=1")
        for binding, priority in ((source, 10), (registered, 5)):
            uow.connection.execute('UPDATE agent_endpoints SET priority=? WHERE endpoint_id=?',
                (priority, binding['endpoint_id']))
    async def environment(prepared):
        return {}
    bridge = CopiedAdapterFactory(environment)
    fallback_peer = _Native()
    class RefusingPeer(_Native):
        async def send(self, *args, **kwargs):
            raise EffectNotSent('fixture refuses before write', code='CAPACITY_EXCEEDED')
    class Factory:
        async def open(self, prepared, session_id, context, *, stream_epoch):
            if prepared.intent.adapter_id == ADAPTER:
                return await bridge.open(prepared, session_id, context, stream_epoch=stream_epoch)
            return RefusingPeer() if prepared.intent.adapter_id == 'pi_rpc' else fallback_peer
    setup[1].state.embedded_dispatch_owner.native_factory = Factory()
    try:
        wait_receipt(setup, admit(setup, source, 'registered-source', 'runtime.start', new_session=True))
        wait_receipt(setup, admit(setup, registered, 'registered-target', 'runtime.start', new_session=True))
        assert send(setup, monkeypatch)['ok']
        before = wait_delivery(setup, lambda row: row['reason'] == 'native_write_not_started')
        expected = registered if binding_contract == 1 else alternative
        assert json.loads(before['next_binding'])['endpoint_id'] == expected['endpoint_id']
        clock[0] = before['next_attempt_at']
        setup[0].runtime_dispatcher.wake()
        after = wait_delivery(setup, lambda row: row['status'] in ('ACCEPTED', 'COMPLETED'))
        assert after['endpoint_id'] == expected['endpoint_id']
        assert all(after[k] == before[k] for k in ('operation_id', 'message_id', 'delivery_id', 'envelope', 'request_hash'))
        commands = RegisteredPeer.instances[0].sent
        if binding_contract == 1:
            assert len(commands) == 1 and commands[0].verb == 'send_turn'
            text = commands[0].payload['text']
            context, current = text.split('\nNEXUS TRANSPORT BINDING: current server-owned attempt; the delivery context is its admission snapshot.\n')
            admitted_envelope = json.loads(before['envelope'])
            admitted_envelope.pop('trust', None)
            assert json.loads(context.split('\n', 1)[1]) == admitted_envelope
            assert json.loads(current)['endpoint_id'] == registered['endpoint_id']
            assert json.loads(current)['canonical_envelope_hash'] == before['request_hash']
            assert fallback_peer.sent == []
        else:
            assert commands == []
            assert len(fallback_peer.sent) == 1
    finally:
        # Keep containment capacity alive until the app has stopped its native
        # sessions, including when an assertion interrupts the test body.
        setup[1].state.test_owned_factories.append(bridge)
