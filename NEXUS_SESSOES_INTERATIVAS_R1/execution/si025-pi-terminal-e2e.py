"""Windows ConPTY, Nexus operator ticket, and the real Pi in one isolated run."""

import argparse
from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient

from nexus_connector_core.discovery import candidate_pi_node_cli
from nexus_connector_core.pi_extension_resource import pi_hosted_rpc_path
from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.http.session_interaction_contract import ScopedSession
from okto_nexus.adapters.outbound.local_presenter_client import open_local_presentation, review_local_presentation
from okto_nexus.adapters.outbound.operator_client import RemoteOperatorHTTP
from okto_nexus.application.execution_local_launch import ApprovedLocalLaunch
from okto_nexus.application.execution_native_session_mapping import read_managed_native_session
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.bootstrap.local_discovery import split_discovery_args
from okto_nexus.domain.base import iso_plus
from test_binding_operator import prepare_operator
from test_embedded_dispatch import admit


PROMPT = 'Inspect the same Pi turn during viewer detach'
RESULT = 'Pi result delivered to the reattached Nexus terminal'
FOLLOW_UP = 'Submit the follow-up through the Nexus queue'
FOLLOW_UP_RESULT = 'Pi result after the canonical queue released the follow-up'


def wait_for(check, *, seconds=120):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if value := check():
            return value
        time.sleep(.05)
    raise AssertionError('The isolated Pi probe did not reach its expected state')


def isolated_provider(root, release, workspace, responses):
    """Constrain native file access and gate the in-process synthetic responses."""
    agent = root / 'profile' / '.pi' / 'agent'
    (agent / 'extensions').mkdir(parents=True)
    (workspace / '.pi').mkdir()
    (workspace / '.pi' / 'settings.json').write_text('{}', encoding='utf-8')
    (workspace / '.git').mkdir()
    (workspace / '.git' / 'HEAD').write_text('ref: refs/heads/probe\n', encoding='ascii')
    preload = root / 'pi-isolation.mjs'
    preload.write_text('''
import net from 'node:net';
const denied = () => { throw new Error('Outbound network is disabled in the isolated Pi test'); };
net.Socket.prototype.connect = denied;
globalThis.fetch = denied;
process.argv.push('--no-context-files', '--provider', 'nexus-fixture', '--model', 'faux-1',
                  '--api-key', 'synthetic-fixture-token');
''', encoding='utf-8')
    peer = release / 'node_modules/@earendil-works/pi-ai/dist/providers/faux.js'
    signals = [root / f'release-turn-{index}' for index in range(len(responses))]
    controlled_responses = [
        f'() => respond({json.dumps(str(signal))}, {json.dumps(answer)})'
        for signal, answer in zip(signals, responses, strict=True)
    ]
    (agent / 'extensions' / 'synthetic-provider.js').write_text(f'''
import {{ fauxProvider, fauxAssistantMessage }} from {json.dumps(peer.as_uri())};
import {{ access }} from 'node:fs/promises';
import {{ setTimeout as delay }} from 'node:timers/promises';
export default (pi) => {{
  const faux = fauxProvider({{ provider: 'nexus-fixture', api: 'nexus-fixture' }});
  pi.registerProvider(faux.provider);
  async function respond(signal, answer) {{
    for (let count = 0; count < 1500; count++) {{
      try {{ await access(signal); return fauxAssistantMessage(answer); }}
      catch (error) {{ if (error.code !== 'ENOENT') throw error; }}
      await delay(30);
    }}
    throw new Error('The controlled Pi turn was not released');
  }}
  faux.setResponses([{', '.join(controlled_responses)}]);
}};
''', encoding='utf-8')
    hosted = pi_hosted_rpc_path()
    options = ' '.join((
        '--permission', f'--allow-fs-read="{release.as_posix()}"', f'--allow-fs-read="{root.as_posix()}"',
        f'--allow-fs-read="{hosted.parent.as_posix()}"', f'--allow-fs-write="{root.as_posix()}"',
        f'--import={preload.as_uri()}',
    ))
    (root / 'scratch').mkdir()
    return agent, signals, {
        'HOME': str(root / 'profile'), 'USERPROFILE': str(root / 'profile'),
        'TEMP': str(root / 'scratch'), 'TMP': str(root / 'scratch'),
        'APPDATA': str(root / 'scratch'), 'LOCALAPPDATA': str(root / 'scratch'),
        'PATH': str(root / 'scratch'), 'PI_CODING_AGENT_DIR': str(agent), 'PI_OFFLINE': '1', 'NODE_OPTIONS': options,
    }


def admit_session(client, headers, workspace, app, provider_home, expected_candidate):
    inventory_owner = app.state.embedded_inventory_owner
    executor = '/v1/runtime/executors/' + inventory_owner.key.executor_id

    def snapshot():
        response = client.get(executor + '/inventory', headers=headers['operator'])
        assert inventory_owner.failure is None, inventory_owner.failure
        if response.status_code == 404:
            return None
        assert response.is_success, response.text
        view = response.json()
        if view.get('freshness') != 'FRESH':
            return None
        inventory = view['snapshot']
        if any(row['state'] not in ('PRESENT', 'ABSENT') for row in inventory['observations']):
            return None
        selected = next((row for row in inventory['evidence']
                         if row['candidate_ref'] == expected_candidate.installation_ref), None)
        assert selected is not None, 'The approved Pi release is absent from the complete inventory'
        return inventory, selected

    inventory, selected = wait_for(snapshot, seconds=300)
    response = client.post(executor + '/realizations', headers=headers['operator'], json={
        'client_intent_id': 'isolated-pi-configuration', 'agent_id': 'subject', 'workspace_root': str(workspace),
        'workspace_id': None, 'workspace_label': 'Isolated Pi terminal proof', 'adapter_id': 'pi_rpc',
        'candidate_ref': selected['candidate_ref'], 'inventory_revision': inventory['inventory_revision'],
        'local_consent_id': 'isolated-pi-synthetic-consent', 'approved': True,
        'provider_home': str(provider_home), 'secret_bindings': {},
    })
    assert response.status_code == 201, response.text
    realization = response.json()
    _, apply = prepare_operator(client, headers, {
        'client_intent_id': 'isolated-pi-binding', 'agent_id_hint': 'subject',
        'executor_id': realization['executor_id'], 'adapter_id': 'pi_rpc', 'candidate_ref': selected['candidate_ref'],
        'inventory_revision': inventory['inventory_revision'], 'realization_ref': realization['realization_ref'],
        'workspace_id': realization['workspace_id'], 'alias': 'isolated-pi',
    })
    response = client.post('/v1/connections/bindings:apply', json=apply, headers=headers['operator'])
    assert response.status_code == 200, response.text
    binding = response.json()
    response = client.post('/api/v1/harness/grants', headers=headers['operator'], json={
        'actor_agent_id': 'subject', 'endpoint_id': binding['endpoint_id'],
        'actions': ['open', 'send', 'close'], 'max_executions': 3,
        'expires_at': iso_plus(app.state.deps.clock.now_iso(), 600),
    })
    assert response.status_code == 200, response.text
    return binding


def enqueue_follow_up(client, data, generation, token, *, presenter_address=None, other_login=None):
    client.cookies.set('nexus_operator_session', token)
    path = f"/api/v1/runtime-management/runtime/sessions/{data['session_id']}"
    query = {key: value for key, value in data.items() if key != 'session_id'}
    query['expected_session_generation'] = generation
    headers = {'X-Nexus-UI': '1'}

    def capability():
        view = client.get(path + '/interaction', params=query, headers=headers)
        assert view.status_code == 200, view.text
        return view.json()['next_turn']['capability_revision']

    intent_id = 'isolated-pi-queued-follow-up'
    if presenter_address is not None:
        api = RemoteOperatorHTTP(presenter_address, token=token, server_id=data['server_id'])
        scope = {'scope': data, 'expected_session_generation': generation}
        writer = review_local_presentation(api, **scope, presentation='pi', write=True)
        output = []
        with open_local_presentation(api, **scope, capability_revision=writer.capability_revision,
                                     client_intent_id='isolated-pi-writer', writer=writer, pi_viewport=(80, 24)) as link:
            output.append(link.read_pi_output())
            queued = link.send_pi_input(intent=intent_id, text=FOLLOW_UP, output=output.append)
            replay = link.send_pi_input(intent=intent_id, text=FOLLOW_UP, output=output.append)
            assert replay == queued and PROMPT.encode() in b''.join(output)
        receipt_path = '/presenter/inputs/receipt'
        selector = query | {'client_intent_id': intent_id}
        for other_surface in ('/inputs/receipt', '/terminal/inputs/receipt'):
            assert client.get(path + other_surface, params=selector, headers=headers).status_code == 404
        client.cookies.set('nexus_operator_session', other_login)
        assert client.get(path + receipt_path, params=selector, headers=headers).status_code == 404
        client.cookies.set('nexus_operator_session', token)
    else:
        body = {'scope': data, 'expected_session_generation': generation, 'client_intent_id': intent_id,
                'capability_revision': wait_for(capability, seconds=10),
                'content': [{'type': 'text', 'text': FOLLOW_UP}]}
        response = client.post(path + '/inputs', json=body, headers=headers)
        assert response.status_code == 202, response.text
        queued = response.json()
        replay = client.post(path + '/inputs', json=body, headers=headers)
        assert replay.status_code == 202 and replay.json()['input_id'] == queued['input_id'], replay.text
        receipt_path = '/inputs/receipt'
    assert queued['status'] == 'QUEUED' and queued['operation_id'] is None and not queued['possible_effect'], queued

    def read():
        response = client.get(path + receipt_path, params=query | {'client_intent_id': intent_id}, headers=headers)
        assert response.status_code == 200, response.text
        value = response.json()
        assert value['scope'] == data and value['input_id'] == queued['input_id'], value
        return value

    return read


def run(node, release, conpty_helpers, *, queue, queue_surface):
    sys.path.insert(0, str(conpty_helpers))
    from owned_engine_probe import environment
    from pty_probe import ProbeConsole
    from session_command_probe import write_input

    root = Path(tempfile.mkdtemp(prefix='nexus-si025-terminal-e2e-')).resolve()
    print(f'Isolated Pi terminal proof directory {root}', flush=True)
    workspace = root / 'workspace'
    workspace.mkdir()
    results = [RESULT, FOLLOW_UP_RESULT] if queue else [RESULT]
    agent, signals, sandbox = isolated_provider(root, release, workspace, results)
    native_environment = ApprovedLocalLaunch.environment

    async def isolated_environment(launch, prepared):
        assert Path(launch.workspace_root).samefile(workspace), 'The launch must use the disposable workspace'
        assert prepared.intent.adapter_id == 'pi_rpc'
        assert not launch.record['configuration']['secret_bindings'], 'The proof has no provider credentials'
        internal_refs = {launch.tools['cap']['capability_ref']} if launch.tools is not None else set()
        assert set(prepared.secret_refs) == internal_refs, 'Only the temporary Nexus native-action grant is allowed'
        approved = await native_environment(launch, prepared)
        assert isinstance(approved, dict), 'No HTTP tools or MCP preset are configured for this test'
        return approved | sandbox

    install_root = release.parent.parent
    # Read the reviewed dependency closure before the inventory freshness clock
    # starts. Core's regular discovery and selection still revalidate it.
    print('Reading the exact Pi installation before starting the fixture server', flush=True)
    selected_cli = release / 'node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js'
    expected_candidate = candidate_pi_node_cli(node, selected_cli, trusted_roots=(node.parent, install_root))
    discovery, rest = split_discovery_args([
        '--harness-root', str(node.parent), '--harness-root', str(install_root),
        '--pi-install-root', str(install_root), '--pi-node', str(node),
    ])
    assert not rest
    deps = bootstrap({}, ['--home', str(root / 'nexus'), '--feature-harness-integrations', 'true',
                          '--runtime-session-interaction-enabled', 'true'])
    deps.local_discovery = discovery
    with pytest.MonkeyPatch.context() as patch, socket.socket() as listener:
        patch.setattr(ApprovedLocalLaunch, 'environment', isolated_environment)
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        address = f'http://127.0.0.1:{listener.getsockname()[1]}'
        app = build_app(deps, runtime_owner_api_url=address)
        headers = {}
        with deps.connection_factory.unit_of_work() as uow:
            for actor in ('operator', 'subject'):
                uow.connection.execute('INSERT OR IGNORE INTO agents(agent_id,created_at) VALUES (?,?)',
                                       (actor, deps.clock.now_iso()))
                headers[actor] = {'Authorization': 'Bearer ' + app.state.auth.issue_key(uow, agent_id=actor)}
        with TestClient(app, base_url=address, client=('127.0.0.1', 12345)) as client:
            server = uvicorn.Server(uvicorn.Config(app, loop='asyncio', ws='wsproto', lifespan='off',
                                                   log_level='warning', access_log=False, proxy_headers=False))
            listener_task = client.portal.start_task_soon(server.serve, [listener])
            try:
                wait_for(lambda: server.started, seconds=10)
                binding = admit_session(client, headers, workspace, app, agent.parent.parent, expected_candidate)
                setup = (deps, app, client, headers)
                owner = app.state.embedded_dispatch_owner
                print('Admitting the exact local Pi opening', flush=True)
                opened = admit(setup, binding, 'isolated-pi-open', 'runtime.start', new_session=True)

                def receipt(resolution, *stages):
                    def read():
                        view = client.get('/v1/runtime/operations/' + resolution['operation_id'], headers=headers['subject']).json()
                        assert view.get('executor_stage') not in ('FAILED', 'REJECTED', 'OUTCOME_UNKNOWN'), view
                        assert owner.failure is None, repr(owner.failure)
                        return view if view.get('executor_stage') in stages else None
                    return wait_for(read, seconds=180)

                receipt(opened, 'SUBMITTED', 'SUCCEEDED')
                data = {name: opened['scope'][name] for name in (
                    'server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id', 'workspace_binding_id', 'session_id')}
                scope = ScopedSession.model_validate({'scope': data,
                    'expected_session_generation': opened['scope']['session_owner_generation']}).input_scope()

                def projected_open():
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        mapping = read_managed_native_session(uow, scope)
                        return mapping and mapping.stream_epoch

                wait_for(projected_open, seconds=30)
                before = client.portal.call(owner.prove_native_presentation_owner, scope)
                auth = app.state.operator_auth
                password = 'isolated-pi-terminal-operator'
                assert auth.configure('operator', password, local=True)
                token = auth.login('operator', password)
                assert token

                child = root / 'viewer.py'
                child.write_text('''
import json, msvcrt, os, sys
from okto_nexus.adapters.inbound.cli.session import attach_session
from okto_nexus.adapters.inbound.cli.windows_viewer_terminal import _mode
from okto_nexus.adapters.outbound.operator_client import RemoteOperatorHTTP
binding = json.loads(os.environ['NEXUS_PROBE_BINDING'])
session = os.environ['NEXUS_PROBE_SESSION']
call = RemoteOperatorHTTP(os.environ['NEXUS_PROBE_ADDRESS'], token=os.environ['NEXUS_PROBE_OPERATOR'], server_id=binding['server_id'])
handles = [msvcrt.get_osfhandle(f.fileno()) for f in (sys.stdin, sys.stdout)]
saved = [_mode(handle) for handle in handles]
assert sys.stdin.isatty() and sys.stdout.isatty()
result = attach_session(call, binding, session_id=session, interactive=True)
assert result['scope']['session_id'] == session and result['attach_strategy'] == 'pi_local_read'
assert [_mode(handle) for handle in handles] == saved
print('PI_DETACHED_AND_CONSOLE_RESTORED', flush=True)
''', encoding='utf-8')

                @contextmanager
                def viewer(name):
                    env, cwd = environment(root / name, 'http://127.0.0.1:1')
                    env.update(PYTHONPATH=os.environ['PYTHONPATH'], NEXUS_PROBE_BINDING=json.dumps(binding),
                               NEXUS_PROBE_SESSION=data['session_id'], NEXUS_PROBE_ADDRESS=address,
                               NEXUS_PROBE_OPERATOR=token)
                    console = ProbeConsole([sys.executable, '-B', str(child)], env, cwd)
                    try:
                        yield console
                    finally:
                        console.close()
                        (root / (name + '.txt')).write_bytes(console.output)

                def active_attachment():
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        return uow.connection.execute("SELECT attachment_id FROM session_attachments WHERE state='ACTIVE'").fetchone()

                def await_text(console, text):
                    def check():
                        assert console.wait(0) is None or text.encode() in console.output, bytes(console.tail).decode('utf-8', 'replace')
                        return text.encode() in console.output
                    wait_for(check, seconds=15)

                def detach(console):
                    write_input(console.input, b'\x03')
                    await_text(console, 'PI_DETACHED_AND_CONSOLE_RESTORED')
                    assert console.wait(5000) == 0
                    wait_for(lambda: not active_attachment(), seconds=8)

                print('Opening the operator viewer in Windows ConPTY', flush=True)
                with viewer('first-viewer') as first:
                    first_attachment = wait_for(active_attachment, seconds=15)[0]
                    sent = admit(setup, binding, 'isolated-pi-turn', 'turn.submit', session_id=data['session_id'], text=PROMPT)
                    await_text(first, PROMPT)
                    detach(first)
                state = client.portal.call(owner.read_native_pi_presentation_state, scope)
                assert state['is_streaming'] and state['pending_message_count'] == 0
                assert client.portal.call(owner.prove_native_presentation_owner, scope) == before
                follow_up = None
                if queue:
                    print('Enqueuing a follow-up while the Pi turn is streaming', flush=True)
                    presenter = queue_surface == 'presenter'
                    follow_up = enqueue_follow_up(client, data, scope.generation.value, token,
                        presenter_address=address if presenter else None,
                        other_login=auth.login('operator', password) if presenter else None)
                    wait_for(lambda: not active_attachment(), seconds=8)

                with viewer('second-viewer') as second:
                    second_attachment = wait_for(active_attachment, seconds=15)[0]
                    assert second_attachment != first_attachment
                    await_text(second, PROMPT)
                    if follow_up:
                        queued = follow_up()
                        assert queued['status'] == 'QUEUED' and queued['operation_id'] is None, queued
                        state = client.portal.call(owner.read_native_pi_presentation_state, scope)
                        assert state['is_streaming'] and state['pending_message_count'] == 0
                    signals[0].touch()
                    await_text(second, RESULT)
                    receipt(sent, 'SUCCEEDED')
                    if follow_up:
                        await_text(second, FOLLOW_UP)
                        delivery = follow_up()
                        assert delivery['status'] in ('DISPATCHING', 'ACCEPTED_NATIVE') and delivery['operation_id'], delivery
                        signals[1].touch()
                        await_text(second, FOLLOW_UP_RESULT)
                        receipt(delivery, 'SUCCEEDED')
                        delivered = follow_up()
                        assert delivered['status'] == 'ACCEPTED_NATIVE' and delivered['operation_id'] == delivery['operation_id']
                    detach(second)
                assert client.portal.call(owner.prove_native_presentation_owner, scope) == before
                closed = admit(setup, binding, 'isolated-pi-close', 'runtime.close', session_id=data['session_id'])
                receipt(closed, 'SUCCEEDED')
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    tickets = 3 if queue and queue_surface == 'presenter' else 2
                    assert [row[0] for row in uow.connection.execute('SELECT state FROM session_attachments')] == ['DETACHED'] * tickets
                    assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == len(results)
                    assert uow.connection.execute('SELECT COUNT(*) FROM session_interaction_inputs').fetchone()[0] == int(queue)
                    if queue:
                        native_turn_events = [tuple(row) for row in uow.connection.execute("""
                            SELECT json_extract(payload_json,'$.native_type'),json_extract(payload_json,'$.operation_id')
                            FROM execution_event_ingress
                            WHERE session_id=? AND stream_epoch=?
                            AND json_extract(payload_json,'$.native_type') IN ('agent_start','agent_settled')
                            ORDER BY sequence
                        """, (data['session_id'], before[0].stream_epoch))]
                        assert native_turn_events == [
                            ('agent_start', sent['operation_id']), ('agent_settled', sent['operation_id']),
                            ('agent_start', delivery['operation_id']), ('agent_settled', delivery['operation_id']),
                        ], native_turn_events
                histories = list((agent / 'sessions').rglob('*.jsonl'))
                assert len(histories) == 1
                records = [json.loads(line) for line in histories[0].read_text(encoding='utf-8').splitlines()]
                assert records[0]['id'] == before[0].native_session_id
                messages = [record['message'] for record in records if record['type'] == 'message']
                assert [message['role'] for message in messages] == ['system'] + ['user', 'assistant'] * len(results)
                expected = [PROMPT, RESULT, FOLLOW_UP, FOLLOW_UP_RESULT] if queue else [PROMPT, RESULT]
                assert [message['content'][0]['text'] for message in messages[1:]] == expected
                print(json.dumps({'real_pi': True, 'actual_windows_conpty': True, 'operator_tickets': tickets,
                                  'same_running_pi_process_after_detach': True, 'synthetic_turns': len(results),
                                  'follow_up_queued_until_settled': queue,
                                  'queue_surface': queue_surface if queue else None,
                                  'canonical_close': 'SUCCEEDED', 'console_modes_restored': True}), flush=True)
            finally:
                server.should_exit = True
                listener_task.result(timeout=15)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--pi-release', type=Path, required=True)
    parser.add_argument('--conpty-helpers', type=Path, required=True)
    parser.add_argument('--queue', action='store_true', help='Exercise the canonical queue with a synthetic follow-up.')
    parser.add_argument('--queue-surface', choices=('web', 'presenter'), default='web')
    args = parser.parse_args()
    logging.getLogger('httpx').setLevel(logging.WARNING)
    run(args.node.resolve(strict=True), args.pi_release.resolve(strict=True),
        args.conpty_helpers.resolve(strict=True), queue=args.queue, queue_surface=args.queue_surface)
