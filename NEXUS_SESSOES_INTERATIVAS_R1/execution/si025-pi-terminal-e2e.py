"""Windows ConPTY, Nexus operator ticket, and the real Pi in one isolated run."""

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient

from nexus_connector_core.discovery import candidate_pi_node_cli
from nexus_connector_core.pi_extension_resource import pi_hosted_rpc_path
from okto_nexus.adapters.inbound.http import dashboard_session_presentations
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
EDITOR_FOLLOW_UP = 'Revisão do turno em andamento\nEnvie a resposta após a liberação'
EDITOR_REORIENTATION = 'Reorient the exact execution from the native Pi draft'
INTERRUPT_DRAFT = 'This unsent draft survives the interruption'
QUESTION_CHOICE = 'Choose the next step'
QUESTION_CONFIRM = 'Confirm a second step'
QUESTION_TEXT = 'Enter a note for the test'
QUESTION_ANSWER = 'isolated-text-answer-73ee5576'
QUESTION_FOLLOW_UP = 'Sim'


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
        f'(_context, options) => respond({json.dumps(str(signal))}, {json.dumps(answer)}, options?.signal)'
        for signal, answer in zip(signals, responses, strict=True)
    ]
    (agent / 'extensions' / 'synthetic-provider.js').write_text(f'''
import {{ fauxProvider, fauxAssistantMessage }} from {json.dumps(peer.as_uri())};
import {{ access }} from 'node:fs/promises';
import {{ setTimeout as delay }} from 'node:timers/promises';
export default (pi) => {{
  const faux = fauxProvider({{ provider: 'nexus-fixture', api: 'nexus-fixture' }});
  pi.registerProvider(faux.provider);
  async function respond(release, answer, signal) {{
    for (let count = 0; count < 1500; count++) {{
      if (signal?.aborted) return fauxAssistantMessage(answer);
      try {{ await access(release); return fauxAssistantMessage(answer); }}
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


def install_pi_questions(agent, root):
    result = root / 'question-results.json'
    extension = agent / 'extensions' / 'operator-questions.js'
    extension.write_text(f'''
import {{ rename, writeFile }} from 'node:fs/promises';
export default (pi) => {{
  let asked = false;
  pi.on('turn_start', async (_event, ctx) => {{
    if (asked) return;
    asked = true;
    const timeout = {{ timeout: 120000 }};
    const choice = await ctx.ui.select({json.dumps(QUESTION_CHOICE)}, ['Proceed', 'Hold'], timeout);
    const confirmation = await ctx.ui.confirm({json.dumps(QUESTION_CONFIRM)}, 'Continue with the isolated second step?', timeout);
    const text = await ctx.ui.input({json.dumps(QUESTION_TEXT)}, 'Type a synthetic note', timeout);
    const destination = {json.dumps(str(result))};
    await writeFile(destination + '.tmp', JSON.stringify({{choice, confirmation, text}}));
    await rename(destination + '.tmp', destination);
  }});
}};
''', encoding='utf-8')
    return result


def admit_session(client, headers, workspace, app, provider_home, expected_candidate, *, steer, interrupt):
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
        'actions': ['open', 'send', 'close'] + (['steer'] if steer else []) + (['interrupt'] if interrupt else []),
        'max_executions': 3,
        'expires_at': iso_plus(app.state.deps.clock.now_iso(), 600),
    })
    assert response.status_code == 200, response.text
    return binding


def enqueue_follow_up(client, data, generation, token, *, presenter_address=None, other_login=None, text=FOLLOW_UP):
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
            queued = link.send_pi_input(intent=intent_id, text=text, output=output.append)
            replay = link.send_pi_input(intent=intent_id, text=text, output=output.append)
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
                'content': [{'type': 'text', 'text': text}]}
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


def enqueue_question_work(client, scope, generation, token):
    client.cookies.set('nexus_operator_session', token)
    url = f"/api/v1/runtime-management/runtime/sessions/{scope['session_id']}"
    query = {key: value for key, value in scope.items() if key != 'session_id'} | {
        'expected_session_generation': generation}
    ui = {'X-Nexus-UI': '1'}
    intent = 'isolated-pi-human-question-turn'

    def revision():
        response = client.get(url + '/interaction', headers=ui, params=query)
        assert response.status_code == 200, response.text
        return response.json()['next_turn']['capability_revision']

    response = client.post(url + '/inputs', headers=ui, json={
        'scope': scope, 'expected_session_generation': generation, 'client_intent_id': intent,
        'capability_revision': wait_for(revision, seconds=12),
        'content': [{'type': 'text', 'text': PROMPT}],
    })
    assert response.status_code == 202, response.text

    def delivered():
        response = client.get(url + '/inputs/receipt', headers=ui, params=query | {'client_intent_id': intent})
        assert response.status_code == 200, response.text
        value = response.json()
        return value if value['operation_id'] else None

    return wait_for(delivered, seconds=15)


def pending_pi_question(client, workspace_id, title):
    def read():
        result = client.get('/api/v1/runtime-management/runtime/input-requests',
                            headers={'X-Nexus-UI': '1'}, params={'workspace_id': workspace_id})
        assert result.status_code == 200, result.text
        return next((item for item in result.json()['items']
                     if item['request_payload']['kwargs']['display']['params'].get('title') == title), None)

    return wait_for(read, seconds=15)


def answer_pi_questions(client, headers, data, generation, result_file, follow_up):
    url = '/api/v1/runtime-management/runtime'
    ui = {'X-Nexus-UI': '1'}
    decisions = []
    for title, method, decision, answer in (
        (QUESTION_CHOICE, 'select', 'approve', {'value': 'Proceed'}),
        (QUESTION_CONFIRM, 'confirm', 'deny', None),
        (QUESTION_TEXT, 'input', 'approve', {'value': QUESTION_ANSWER}),
    ):
        detail = pending_pi_question(client, data['workspace_id'], title)
        queued = follow_up()
        assert queued['status'] == 'QUEUED' and queued['operation_id'] is None, queued
        kwargs = detail['request_payload']['kwargs']
        key = kwargs['approval_key']
        assert all(key[name] == data[name] for name in ('server_id', 'executor_id', 'binding_id', 'workspace_id',
                                                       'agent_id', 'session_id')), key
        assert key['session_owner_generation'] == generation and key['kind'] == 'native_input'
        assert kwargs['recipient_agent_id'] == 'operator'
        assert kwargs['display']['params']['method'] == method
        assert not result_file.exists()
        attention = client.get('/api/v1/attention', headers=ui, params={
            'workspace_id': data['workspace_id'], 'kind': 'native_question_pending'})
        assert attention.status_code == 200, attention.text
        alert, = attention.json()['data']['items']
        assert alert['session_id'] == data['session_id'] and alert['category'] == 'action_required'
        assert alert['source_id'] == key['canonical_request_id']
        assert alert['allowed_actions'] == ['inspect_approval', 'respond_native']
        board = client.get('/api/v1/home/harness-board', headers=ui, params={
            'workspace_id': data['workspace_id'], 'presentation_version': 2})
        assert board.status_code == 200, board.text
        items = board.json()['data']['columns']['needs_you']['items']
        requests = [item['request'] for item in items if item['kind'] == 'request']
        requests.extend(entry['request'] for item in items if item['kind'] == 'harness'
                        for entry in item['requests_preview'])
        assert any(request['attention_id'] == alert['attention_id'] for request in requests), items
        body = {name: kwargs[name] for name in ('approval_key', 'expected_revision', 'request_hash', 'cas_token')}
        body |= {'client_intent_id': 'isolated-pi-native-' + method, 'decision': decision}
        if answer is not None:
            body['response'] = answer

        with client_cookie_removed(client, 'nexus_operator_session'):
            sibling = client.get('/v1/runtime/input-requests', headers=headers['subject'])
            assert sibling.status_code == 200 and sibling.json()['items'] == [], sibling.text
            assert client.post('/v1/runtime/approval-decisions', headers=headers['subject'], json=body).status_code == 403
        stale = body | {'expected_revision': body['expected_revision'] + 1}
        assert client.post(url + '/approval-decisions', headers=ui, json=stale).status_code == 409
        if method == 'select':
            invalid = body | {'response': {'value': 'Unavailable option'}}
            assert client.post(url + '/approval-decisions', headers=ui, json=invalid).status_code == 422
        accepted = client.post(url + '/approval-decisions', headers=ui, json=body)
        assert accepted.status_code == 202, accepted.text
        record = accepted.json()
        replay = client.post(url + '/approval-decisions', headers=ui, json=body)
        assert replay.status_code == 200 and replay.json()['decision_id'] == record['decision_id'], replay.text
        assert replay.json()['native_operation_id'] == record['native_operation_id']

        def receipt():
            view = client.get(url + '/approval-decisions/' + record['decision_id'], headers=ui)
            assert view.status_code == 200, view.text
            value = view.json()
            assert value['native_stage'] not in ('REFUSED_BEFORE_EFFECT', 'OUTCOME_UNKNOWN'), value
            return value if value['native_stage'] == 'SUBMITTED' else None

        decisions.append(wait_for(receipt, seconds=12))

    wait_for(result_file.is_file, seconds=12)
    assert json.loads(result_file.read_text(encoding='utf-8')) == {
        'choice': 'Proceed', 'confirmation': False, 'text': QUESTION_ANSWER}
    assert len({item['native_operation_id'] for item in decisions}) == len(decisions)
    return decisions


@contextmanager
def client_cookie_removed(client, key):
    value = client.cookies.get(key)
    client.cookies.delete(key)
    try:
        yield
    finally:
        client.cookies.set(key, value)


def run(node, release, conpty_helpers, *, queue, queue_surface, steer=False, steer_editor=False, interrupt=False,
        interrupt_surface='web', questions=False):
    sys.path.insert(0, str(conpty_helpers))
    from okto_nexus.adapters.inbound.cli.session_commands import execute_session_command, recover_pi_input, recover_pi_interrupt
    from owned_engine_probe import environment
    from pty_probe import ProbeConsole
    from session_command_probe import write_input

    root = Path(tempfile.mkdtemp(prefix='nexus-si025-terminal-e2e-')).resolve()
    print(f'Isolated Pi terminal proof directory {root}', flush=True)
    workspace = root / 'workspace'
    workspace.mkdir()
    steering = steer or steer_editor
    interrupt_editor = interrupt and interrupt_surface == 'editor'
    has_follow_up = queue or questions
    results = [RESULT, FOLLOW_UP_RESULT] if has_follow_up or steering or interrupt else [RESULT]
    follow_up_text = EDITOR_REORIENTATION if steer_editor else (EDITOR_FOLLOW_UP if queue_surface == 'editor' else FOLLOW_UP)
    if questions:
        follow_up_text = QUESTION_FOLLOW_UP
    agent, signals, sandbox = isolated_provider(root, release, workspace, results)
    question_results = install_pi_questions(agent, root) if questions else None
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
                          '--runtime-session-interaction-enabled', 'true']
                     + (['--feature-hitl', 'true'] if questions else []))
    deps.local_discovery = discovery
    with pytest.MonkeyPatch.context() as patch, socket.socket() as listener:
        patch.setattr(ApprovedLocalLaunch, 'environment', isolated_environment)
        recorded_interrupts = []
        if interrupt_editor:
            original_interrupt = dashboard_session_presentations.request_exact_human_interrupt

            def record_editor_intent(**kwargs):
                operation = original_interrupt(**kwargs)
                recorded_interrupts.append((kwargs['client_intent_id'], operation[0]))
                return operation

            patch.setattr(dashboard_session_presentations, 'request_exact_human_interrupt', record_editor_intent)
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
                binding = admit_session(client, headers, workspace, app, agent.parent.parent, expected_candidate,
                                        steer=steering, interrupt=interrupt)
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
write = os.environ['NEXUS_PROBE_PI_WRITE'] == 'yes'
result = attach_session(call, binding, session_id=session, interactive=True, write=write)
assert result['scope']['session_id'] == session
assert result['attach_strategy'] == ('pi_local_write' if write else 'pi_local_read')
assert [_mode(handle) for handle in handles] == saved
print('PI_DETACHED_AND_CONSOLE_RESTORED', flush=True)
''', encoding='utf-8')

                @contextmanager
                def viewer(name, *, write=False):
                    env, cwd = environment(root / name, 'http://127.0.0.1:1')
                    env.update(PYTHONPATH=os.environ['PYTHONPATH'], NEXUS_PROBE_BINDING=json.dumps(binding),
                               NEXUS_PROBE_SESSION=data['session_id'], NEXUS_PROBE_ADDRESS=address,
                               NEXUS_PROBE_OPERATOR=token, NEXUS_PROBE_PI_WRITE='yes' if write else 'no')
                    console = ProbeConsole([sys.executable, '-B', str(child)], env, cwd)
                    try:
                        yield console
                    finally:
                        console.close()
                        (root / (name + '.txt')).write_bytes(console.output)

                def active_attachment():
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        return uow.connection.execute("SELECT attachment_id FROM session_attachments WHERE state='ACTIVE'").fetchone()

                def await_text(console, text, *, start=0):
                    expected = text.encode()

                    def check():
                        found = expected in console.output[start:]
                        # ConPTY output can reach the collector after exit is visible.
                        if not found and console.wait(0) not in (None, 0):
                            raise AssertionError(bytes(console.tail).decode('utf-8', 'replace'))
                        return found
                    wait_for(check, seconds=15)

                def detach(console):
                    write_input(console.input, b'\x03')
                    await_text(console, 'PI_DETACHED_AND_CONSOLE_RESTORED')
                    assert console.wait(5000) == 0
                    wait_for(lambda: not active_attachment(), seconds=8)

                print('Opening the operator viewer in Windows ConPTY', flush=True)
                with viewer('first-viewer') as first:
                    first_attachment = wait_for(active_attachment, seconds=15)[0]
                    sent = (enqueue_question_work(client, data, scope.generation.value, token) if questions
                            else admit(setup, binding, 'isolated-pi-turn', 'turn.submit', session_id=data['session_id'], text=PROMPT))
                    if questions:
                        pending_pi_question(client, data['workspace_id'], QUESTION_CHOICE)
                    else:
                        await_text(first, PROMPT)
                    detach(first)
                state = client.portal.call(owner.read_native_pi_presentation_state, scope)
                assert state['is_streaming'] and state['pending_message_count'] == 0
                assert client.portal.call(owner.prove_native_presentation_owner, scope) == before
                follow_up = None
                if questions:
                    print('Answering the Pi dialogs as the originating operator', flush=True)
                    follow_up = enqueue_follow_up(client, data, scope.generation.value, token, text=follow_up_text)
                    native_decisions = answer_pi_questions(
                        client, headers, data, scope.generation.value, question_results, follow_up)
                    assert follow_up()['status'] == 'QUEUED'
                if interrupt:
                    print('Interrupting the reviewed Pi run with a continuation in the queue', flush=True)
                    url = f"/api/v1/runtime-management/runtime/sessions/{data['session_id']}"
                    generation = scope.generation.value
                    query = {key: value for key, value in data.items() if key != 'session_id'}
                    query['expected_session_generation'] = generation
                    ui = {'X-Nexus-UI': '1'}
                    follow_up = enqueue_follow_up(client, data, generation, token)

                    def review_interrupt():
                        response = client.get(url + '/interrupt', params=query, headers=ui)
                        assert response.status_code == 200, response.text
                        return response.json()['control']

                    control = wait_for(review_interrupt, seconds=12)
                    assert control['target']['kind'] == 'observed_run', control
                    interrupt_body = {'scope': data, 'expected_session_generation': generation,
                        'target': control['target'], 'capability_revision': control['capability_revision'],
                        'expected_queue_revision': control['queue_revision'], 'client_intent_id': 'isolated-pi-interrupt'}

                    def queue_page():
                        response = client.get(url + '/inputs', params=query, headers=ui)
                        assert response.status_code == 200, response.text
                        return response.json()

                    def set_interrupt_queue_pause(paused):
                        page = wait_for(lambda: view if (view := queue_page())['pause_capability_revision'] else None,
                                        seconds=12)
                        response = client.post(url + '/inputs/queue-state', headers=ui, json={
                            'scope': data, 'expected_session_generation': generation, 'paused': paused,
                            'capability_revision': page['pause_capability_revision'], 'expected_queue_revision': page['queue_revision'],
                        })
                        assert response.status_code == 200 and response.json()['paused'] is paused, response.text

                    wrong = interrupt_body | {'target': {'kind': 'observed_run', 'run_ref': 'prun_' + '0' * 32}}
                    assert client.post(url + '/interrupt', json=wrong, headers=ui).status_code == 409
                    assert not queue_page()['paused']
                    if interrupt_editor:
                        with viewer('interrupt-editor', write=True) as editor:
                            wait_for(active_attachment, seconds=15)
                            await_text(editor, PROMPT)
                            write_input(editor.input, b'\x1b[200~' + INTERRUPT_DRAFT.encode() + b'\x1b[201~')
                            await_text(editor, INTERRUPT_DRAFT)

                            def review_editor_interrupt():
                                start = len(editor.output)
                                write_input(editor.input, b'\x18')
                                await_text(editor, 'Interrupt this Pi execution and pause the message queue?', start=start)

                            review_editor_interrupt()
                            write_input(editor.input, b'\r')
                            write_input(editor.input, b'\x0e')
                            await_text(editor, 'Interruption cancelled. Your draft is available.')
                            assert not recorded_interrupts and not queue_page()['paused']
                            assert client.portal.call(owner.read_native_pi_presentation_state, scope)['is_streaming']

                            review_editor_interrupt()
                            set_interrupt_queue_pause(True)
                            write_input(editor.input, b'\x19')
                            await_text(editor, 'The interruption review changed. Your draft is available.')
                            assert not recorded_interrupts and queue_page()['paused']
                            set_interrupt_queue_pause(False)

                            review_editor_interrupt()
                            before_confirm = len(editor.output)
                            write_input(editor.input, b'\x19')
                            await_text(editor, 'The selected Pi execution was interrupted. The message queue is paused.')
                            await_text(editor, INTERRUPT_DRAFT, start=before_confirm)
                            assert len(recorded_interrupts) == 1
                            interrupt_intent, interrupted = recorded_interrupts[0]
                            detach(editor)
                        interrupt_receipt_path = '/presenter/interrupt/receipt'
                        api = RemoteOperatorHTTP(address, token=token, server_id=data['server_id'])
                        assert recover_pi_interrupt(api, data, generation, interrupt_intent)['receipt']['operation_id'] == interrupted['operation_id']
                        for other in ('/interrupt/receipt', '/terminal/interrupt/receipt'):
                            assert client.get(url + other, headers=ui, params=query | {'client_intent_id': interrupt_intent}).status_code == 404
                    elif interrupt_surface == 'cli':
                        api = RemoteOperatorHTTP(address, token=token, server_id=data['server_id'])
                        prompts = []

                        def command(answer):
                            return execute_session_command(api, binding, data['session_id'], 'interrupt', interactive=True,
                                message_file=None, read=lambda prompt: prompts.append(prompt) or answer, write=lambda _: None)

                        assert command('n')['state'] == 'cancelled'
                        assert not queue_page()['paused']
                        submitted = command('y')
                        assert submitted['state'] == 'recorded', submitted
                        assert prompts == ['Interrupt the selected Pi run and pause the queue? [y/N] '] * 2
                        interrupted = submitted['receipt']
                        interrupt_intent = submitted['client_intent_id']
                        interrupt_receipt_path = '/terminal/interrupt/receipt'
                    else:
                        response = client.post(url + '/interrupt', json=interrupt_body, headers=ui)
                        assert response.status_code == 202, response.text
                        interrupted = response.json()
                        interrupt_intent = interrupt_body['client_intent_id']
                        interrupt_receipt_path = '/interrupt/receipt'
                    assert queue_page()['paused']
                    receipt(sent, 'CANCELLED')
                    receipt(interrupted, 'SUBMITTED')

                    def exact_receipt():
                        result = client.get(url + interrupt_receipt_path, headers=ui,
                            params=query | {'client_intent_id': interrupt_intent})
                        assert result.status_code == 200, result.text
                        return result.json()

                    def confirmed_interrupt():
                        evidence = exact_receipt()
                        assert evidence['interrupt']['queue_paused'] and evidence['interrupt']['pending_count'] == 1
                        return evidence if evidence['interrupt']['target_status'] == 'interrupted' else None

                    wait_for(confirmed_interrupt, seconds=12)
                    assert follow_up()['status'] == 'QUEUED' and follow_up()['operation_id'] is None
                    assert client.portal.call(owner.prove_native_presentation_owner, scope) == before
                    set_interrupt_queue_pause(False)
                if steer:
                    print('Reviewing and promoting an exact Pi run through the operator HTTP API', flush=True)
                    follow_up = enqueue_follow_up(client, data, scope.generation.value, token)
                    pending = follow_up()
                    assert pending['status'] == 'QUEUED'
                    url = f"/api/v1/runtime-management/runtime/sessions/{data['session_id']}"
                    generation = scope.generation.value
                    query = {key: value for key, value in data.items() if key != 'session_id'}
                    query |= {'input_id': pending['input_id'], 'expected_session_generation': generation}
                    ui = {'X-Nexus-UI': '1'}

                    def read_steer():
                        review = client.get(url + '/steer', headers=ui, params=query)
                        assert review.status_code == 200, review.text
                        return review.json() if review.json()['control'] else None

                    review = wait_for(read_steer, seconds=12)
                    control = review['control']
                    assert control['target']['kind'] == 'observed_run' and control['effect'] == 'next_boundary', control
                    assert review['queued_input']['input_id'] == pending['input_id']
                    promotion = {
                        'scope': data, 'expected_session_generation': generation, 'target': control['target'],
                        'capability_revision': control['capability_revision'],
                        'expected_queue_revision': control['queue_revision'],
                        'expected_input_revision': pending['input_revision'],
                        'confirmed_effect_revision': control['effect_revision'],
                    }
                    path = url + '/inputs/' + pending['input_id'] + '/promote'
                    wrong = promotion | {'target': {'kind': 'observed_run', 'run_ref': 'prun_' + '0' * 32}}
                    assert client.post(path, json=wrong, headers=ui).status_code == 409
                    assert follow_up() == pending
                    with ThreadPoolExecutor(max_workers=2) as writers:
                        attempts = [writers.submit(client.post, path, json=promotion, headers=ui) for _ in range(2)]
                        responses = [attempt.result(timeout=10) for attempt in attempts]
                    assert all(response.status_code == 202 for response in responses), [r.text for r in responses]
                    delivery = responses[0].json()
                    assert delivery['input_id'] == pending['input_id'] and delivery['operation_id']
                    assert responses[1].json()['operation_id'] == delivery['operation_id']
                    replay = client.post(path, json=promotion, headers=ui)
                    assert replay.status_code == 202 and replay.json()['operation_id'] == delivery['operation_id']
                    receipt(delivery, 'SUBMITTED')
                    assert follow_up()['steer_submitted']

                    def steer_facts():
                        with deps.connection_factory.unit_of_work(write=False) as uow:
                            return [tuple(row) for row in uow.connection.execute("""
                                SELECT json_extract(payload_json,'$.payload.stage'),
                                       json_extract(payload_json,'$.payload.run_id'),
                                       json_extract(payload_json,'$.payload.turn_operation_id')
                                FROM execution_event_ingress WHERE session_id=? AND stream_epoch=?
                                  AND json_extract(payload_json,'$.native_type')='nexus_pi_steer'
                                  AND json_extract(payload_json,'$.operation_id')=?
                                ORDER BY sequence
                            """, (data['session_id'], before[0].stream_epoch, delivery['operation_id']))]

                    run_ref = control['target']['run_ref']
                    expected_fact = [(stage, run_ref, sent['operation_id']) for stage in ('queued', 'consumed')]
                    assert wait_for(steer_facts, seconds=12) == expected_fact[:1]
                    assert follow_up()['steer_boundary'] == 'awaiting_boundary'
                if queue:
                    print('Enqueuing a follow-up while the Pi turn is streaming', flush=True)
                    if queue_surface == 'editor':
                        with viewer('native-editor', write=True) as writer:
                            wait_for(active_attachment, seconds=15)
                            await_text(writer, PROMPT)
                            pasted = (follow_up_text.replace('\n', '\r\n') + 'X').encode('utf-8')
                            write_input(writer.input, b'\x1b[200~' + pasted + b'\x1b[201~')
                            await_text(writer, follow_up_text.splitlines()[-1] + 'X')
                            with deps.connection_factory.unit_of_work(write=False) as uow:
                                assert uow.connection.execute('SELECT COUNT(*) FROM session_interaction_inputs').fetchone()[0] == 0
                            write_input(writer.input, b'\x7f\r')
                            await_text(writer, 'Message recorded as sin_')
                            input_id = re.search(rb'Message recorded as (sin_[0-9a-f]{32})', bytes(writer.output))[1].decode()
                            detach(writer)
                        client.cookies.set('nexus_operator_session', token)
                        query = {key: value for key, value in data.items() if key != 'session_id'}
                        query |= {'input_id': input_id, 'expected_session_generation': scope.generation.value}
                        url = f"/api/v1/runtime-management/runtime/sessions/{data['session_id']}/presenter/inputs/receipt"

                        def follow_up():
                            response = client.get(url, params=query, headers={'X-Nexus-UI': '1'})
                            assert response.status_code == 200, response.text
                            value = response.json()
                            assert value['scope'] == data and value['input_id'] == input_id, value
                            return value
                    else:
                        presenter = queue_surface == 'presenter'
                        follow_up = enqueue_follow_up(client, data, scope.generation.value, token,
                            presenter_address=address if presenter else None,
                            other_login=auth.login('operator', password) if presenter else None)
                    wait_for(lambda: not active_attachment(), seconds=8)

                with viewer('second-viewer', write=steer_editor) as second:
                    second_attachment = wait_for(active_attachment, seconds=15)[0]
                    assert second_attachment != first_attachment
                    await_text(second, PROMPT)
                    if has_follow_up and follow_up:
                        queued = follow_up()
                        assert queued['status'] == 'QUEUED' and queued['operation_id'] is None, queued
                        state = client.portal.call(owner.read_native_pi_presentation_state, scope)
                        assert state['is_streaming'] and state['pending_message_count'] == 0
                    if interrupt:
                        await_text(second, FOLLOW_UP)
                        successor = wait_for(review_interrupt, seconds=12)
                        assert successor['target'] != control['target']
                        stale = interrupt_body | {'expected_queue_revision': successor['queue_revision'],
                                                  'client_intent_id': 'isolated-pi-old-run'}
                        assert client.post(url + '/interrupt', json=stale, headers=ui).status_code == 409
                        assert not queue_page()['paused']

                        async def receive_stale_abort():
                            local = await owner.sessions[data['session_id']]['executor']._runtime()
                            peer = local._sessions[before[1].key].native._connector._transport
                            return await asyncio.to_thread(peer.request, 'abort',
                                {'nexus_expected_run_id': control['target']['run_ref']}, timeout_s=8)

                        refused = client.portal.call(receive_stale_abort)
                        assert refused['success'] is False and refused['nexus_refused_before_abort'] is True
                        assert client.portal.call(owner.read_native_pi_presentation_state, scope)['is_streaming']
                        if interrupt_surface == 'web':
                            replay = client.post(url + '/interrupt', json=interrupt_body, headers=ui)
                            assert replay.status_code == 200 and replay.json()['operation_id'] == interrupted['operation_id']
                    if steer_editor:
                        print('Reviewing the native Pi draft in Windows ConPTY', flush=True)
                        client.cookies.set('nexus_operator_session', token)
                        url = f"/api/v1/runtime-management/runtime/sessions/{data['session_id']}"
                        generation = scope.generation.value
                        query = {key: value for key, value in data.items() if key != 'session_id'}
                        query['expected_session_generation'] = generation
                        ui = {'X-Nexus-UI': '1'}

                        def set_queue_paused(paused):
                            response = client.get(url + '/inputs', params=query, headers=ui)
                            assert response.status_code == 200, response.text
                            view = response.json()
                            changed = client.post(url + '/inputs/queue-state', headers=ui, json={
                                'scope': data, 'expected_session_generation': generation, 'paused': paused,
                                'capability_revision': view['pause_capability_revision'],
                                'expected_queue_revision': view['queue_revision'],
                            })
                            assert changed.status_code == 200 and changed.json()['paused'] is paused, changed.text

                        def review_draft():
                            start = len(second.output)
                            write_input(second.input, b'\x12')
                            await_text(second, 'Ctrl+Y confirms. Ctrl+N cancels.', start=start)

                        def retained():
                            with deps.connection_factory.unit_of_work(write=False) as uow:
                                return [dict(row) for row in uow.connection.execute("""
                                    SELECT input_id,client_intent_id,content,operation_id FROM session_interaction_inputs
                                    WHERE session_id=? AND surface='native_terminal'
                                """, (data['session_id'],))]

                        write_input(second.input, b'\x1b[200~' + follow_up_text.encode() + b'\x1b[201~')
                        await_text(second, follow_up_text)
                        review_draft()
                        write_input(second.input, b'\r')
                        write_input(second.input, b'\x0e')
                        await_text(second, 'Reorientation cancelled. Your draft is available.')
                        assert retained() == []
                        review_draft()
                        set_queue_paused(True)
                        write_input(second.input, b'\x19')
                        await_text(second, 'The reorientation review changed. Your draft is available.')
                        assert retained() == []
                        set_queue_paused(False)
                        review_draft()
                        assert retained() == []
                        write_input(second.input, b'\x19')
                        await_text(second, 'Pi queued the reorientation for the next boundary.')
                        rows = retained()
                        assert len(rows) == 1 and rows[0]['content'] == follow_up_text
                        editor_receipt = rows[0]
                        receipt(editor_receipt, 'SUBMITTED')
                        terminal_api = RemoteOperatorHTTP(address, token=token, server_id=data['server_id'])
                        assert recover_pi_input(terminal_api, data, generation,
                            editor_receipt['client_intent_id'])['receipt']['steer_boundary'] == 'awaiting_boundary'
                    signals[1 if interrupt else 0].touch()
                    await_text(second, FOLLOW_UP_RESULT if interrupt else RESULT)
                    if steer:
                        wait_for(lambda: steer_facts() == expected_fact, seconds=12)
                        assert follow_up()['steer_boundary'] == 'applied'
                        signals[1].touch()
                        await_text(second, FOLLOW_UP_RESULT)
                    if steer_editor:
                        await_text(second, 'Pi applied the reorientation.')
                        assert recover_pi_input(terminal_api, data, generation,
                            editor_receipt['client_intent_id'])['receipt']['steer_boundary'] == 'applied'
                        write_input(second.input, b'\r')
                        signals[1].touch()
                        await_text(second, FOLLOW_UP_RESULT)
                    if interrupt:
                        receipt(follow_up(), 'SUCCEEDED')
                    else:
                        receipt(sent, 'SUCCEEDED')
                    if has_follow_up and follow_up:
                        await_text(second, follow_up_text.splitlines()[0])
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
                    tickets = 3 if interrupt_editor or queue and queue_surface in ('presenter', 'editor') else 2
                    assert [row[0] for row in uow.connection.execute('SELECT state FROM session_attachments')] == ['DETACHED'] * tickets
                    assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == (1 if steering else len(results))
                    assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.steer'").fetchone()[0] == int(steering)
                    assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.interrupt'").fetchone()[0] == int(interrupt)
                    input_count = 2 if questions else int(queue or steering or interrupt)
                    assert uow.connection.execute('SELECT COUNT(*) FROM session_interaction_inputs').fetchone()[0] == input_count
                    if questions:
                        rows = uow.connection.execute("""SELECT semantic_payload FROM execution_operations
                            WHERE action='input.provide'""").fetchall()
                        assert len(rows) == len(native_decisions) and all(QUESTION_ANSWER not in row[0] for row in rows)
                    if has_follow_up:
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
                if interrupt:
                    assert messages[2]['stopReason'] == 'aborted'
                    kept = [messages[index]['content'][0]['text'] for index in (1, 3, 4)]
                    assert kept == [PROMPT, FOLLOW_UP, FOLLOW_UP_RESULT]
                else:
                    expected = [PROMPT, RESULT, follow_up_text, FOLLOW_UP_RESULT] if has_follow_up or steering else [PROMPT, RESULT]
                    assert [message['content'][0]['text'] for message in messages[1:]] == expected
                print(json.dumps({'real_pi': True, 'actual_windows_conpty': True, 'operator_tickets': tickets,
                                  'same_running_pi_process_after_detach': True, 'synthetic_responses': len(results),
                                  'confirmed_operator_steer_in_same_run': steering,
                                  'steer_surface': 'editor' if steer_editor else 'http' if steer else None,
                                  'interrupt_paused_queue_and_refused_stale_run': interrupt,
                                  'interrupt_surface': interrupt_surface if interrupt else None,
                                  'operator_native_decisions': len(native_decisions) if questions else 0,
                                  'follow_up_queued_until_settled': has_follow_up,
                                  'queue_surface': 'web' if questions else queue_surface if queue else None,
                                  'canonical_close': 'SUCCEEDED', 'console_modes_restored': True}), flush=True)
            finally:
                server.should_exit = True
                listener_task.result(timeout=15)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--pi-release', type=Path, required=True)
    parser.add_argument('--conpty-helpers', type=Path, required=True)
    scenario = parser.add_mutually_exclusive_group()
    scenario.add_argument('--queue', action='store_true', help='Exercise the canonical queue with a synthetic follow-up.')
    scenario.add_argument('--steer', action='store_true', help='Promote queued text into a reviewed Pi boundary steer.')
    scenario.add_argument('--steer-editor', action='store_true', help='Review and confirm a native Pi draft.')
    scenario.add_argument('--interrupt', action='store_true', help='Interrupt the exact Pi run with a durable queue barrier.')
    scenario.add_argument('--questions', action='store_true', help='Answer the owned Pi dialogs through canonical decisions.')
    parser.add_argument('--queue-surface', choices=('web', 'presenter', 'editor'), default='web')
    parser.add_argument('--interrupt-surface', choices=('web', 'cli', 'editor'), default='web')
    args = parser.parse_args()
    logging.getLogger('httpx').setLevel(logging.WARNING)
    run(args.node.resolve(strict=True), args.pi_release.resolve(strict=True),
        args.conpty_helpers.resolve(strict=True), queue=args.queue, queue_surface=args.queue_surface,
        steer=args.steer, steer_editor=args.steer_editor, interrupt=args.interrupt, interrupt_surface=args.interrupt_surface,
        questions=args.questions)
