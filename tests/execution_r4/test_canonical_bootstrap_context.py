"""Native delivery carries canonical public identity and exact correlation."""
import json
from dataclasses import asdict
from pathlib import Path

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_handoff import prepare
from test_canonical_result_publication import current_turn


@pytest.mark.parametrize('intent', ['conversation', 'handoff_execute'])
@pytest.mark.parametrize('local_setup', ['codex_app_server', 'claude_stream', 'pi_rpc'], indirect=True)
def test_native_delivery_preserves_identity_purpose_and_message_correlation(connected_local, monkeypatch, intent):
    from test_vertical_inventory import _Native
    setup, binding, native = connected_local
    deps = setup[0]
    payloads = []
    original = _Native.send

    async def capture(peer, verb, payload, operation_id, **kwargs):
        payloads.append(payload)
        return await original(peer, verb, payload, operation_id, **kwargs)

    monkeypatch.setattr(_Native, 'send', capture)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET role='reviewer',capabilities=?,metadata=? WHERE agent_id='subject'",
            (json.dumps({'review': True}), json.dumps({'keep': 'private-profile'})))
        before = asdict(deps.repos.agents.get(uow, 'subject'))
    if intent == 'conversation':
        enable(setup, binding)
        created = send(setup, monkeypatch)
    else:
        _, _, claim, _ = prepare(setup, binding, monkeypatch)
        created = claim()
    assert created['ok'], created
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    assert native.opens == 1 and len(payloads) == 1
    payload = payloads[0]
    wire = payload if isinstance(payload, str) else payload['text']
    envelope = json.loads(wire.split('\n', 1)[1])
    context = envelope['runtime_context']
    assert context['schema_version'] == 1
    assert context['agent'] == dict(agent_id='subject', role='reviewer', capabilities=['review'])
    assert context['intent'] == intent
    assert context['workspace_id'] == envelope['workspace_id']
    assert context['endpoint_id'] == binding['endpoint_id']
    assert context['completion']['automatic_on_turn_end'] is False
    assert 'authenticated Nexus tools' in context['instructions']
    assert 'available capabilities' in context['instructions']
    assert 'untrusted' not in context['instructions']
    assert 'not an executable' not in context['instructions']
    assert envelope['sender_agent_id'] == 'operator' and envelope['recipient_agent_id'] == 'subject'
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stored = json.loads(uow.connection.execute('SELECT envelope FROM delivery_outbox').fetchone()[0])
        assert stored['runtime_context'] == context
        for field in ('operation_id', 'root_operation_id', 'message_id', 'subject'):
            assert envelope[field] == stored[field]
        profile = uow.connection.execute('SELECT p.profile_id,p.revision FROM runtime_profiles p '
            'JOIN agent_endpoints e ON e.profile_id=p.profile_id WHERE e.endpoint_id=?', (binding['endpoint_id'],)).fetchone()
        assert context['execution_profile'] == dict(profile)
        after = asdict(deps.repos.agents.get(uow, 'subject'))
        before.pop('last_seen_at')
        after.pop('last_seen_at')
        assert after == before
    for private in ('api_key_hash', 'secret_refs', 'comm_scope', 'private-profile'):
        assert private not in wire
    wait_receipt(setup, admit(setup, binding, 'context-close', 'runtime.close',
                             session_id=turn['session_id']), stages=('SUCCEEDED',))


@pytest.mark.parametrize('surface', ['rest', 'mcp'])
@pytest.mark.parametrize('local_setup', ['codex_app_server', 'claude_stream', 'pi_rpc'], indirect=True)
def test_enabled_managed_adapters_open_send_and_close_through_public_routes(connected_local, monkeypatch, surface):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    setup, binding, native = connected_local
    _, _, client, headers, *_, root = setup
    client.headers['host'] = '127.0.0.1:8000'
    key = headers['subject']['Authorization'].removeprefix('Bearer ')
    kind = {'codex_app_server': 'codex', 'claude_stream': 'claude_code', 'pi_rpc': 'pi'}[setup[5].adapter_id]
    args = dict(agent_id='subject', kind=kind, endpoint_id=binding['endpoint_id'], project_root=str(root),
                idempotency_key='enabled-open')
    if surface == 'mcp':
        opened = tool(client, key, 'harness_open', args)
    else:
        response = client.post('/api/v1/harness/sessions', headers=headers['subject'], json=args)
        assert response.status_code == 200, response.text
        opened = response.json()
    assert opened['ok'], opened
    wait_receipt(setup, opened['data'])
    sid = opened['data']['scope']['session_id']
    for verb, extra in [('send', {'payload': {'text': 'Current managed adapter'}}), ('close', {})]:
        args = dict(idempotency_key='enabled-' + verb, **extra)
        if surface == 'mcp':
            result = tool(client, key, 'harness_' + verb, dict(session_id=sid, **args))
        else:
            response = client.post(f'/api/v1/harness/sessions/{sid}/{verb}', headers=headers['subject'], json=args)
            assert response.status_code == 200, response.text
            result = response.json()
        assert result['ok'], result
        wait_receipt(setup, result['data'], stages=('SUCCEEDED',) if verb == 'close' else ('SUBMITTED', 'SUCCEEDED'))
    assert native.opens == 1 and native.native.stopped and len(native.native.sent) == 1
