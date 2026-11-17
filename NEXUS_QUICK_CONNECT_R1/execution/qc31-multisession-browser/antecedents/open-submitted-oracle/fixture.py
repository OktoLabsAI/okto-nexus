"""Canonical two-session fixture with full synthetic stdio protocol ownership."""
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ALLOCATION = json.loads((HERE / 'allocation.json').read_text())
ROOT = Path(ALLOCATION['root'])
PREFIX = Path(ALLOCATION['prefix']).resolve()
assert sys.flags.isolated and sys.dont_write_bytecode and Path(sys.prefix).resolve() == PREFIX
sys.path.insert(0, str(ROOT / 'helpers'))
from protocol_fixture import install_native, _FAKE_SERVER_SOURCE

import pytest
from fastapi.testclient import TestClient
import uvicorn
from nexus_connector_core import InstallationCandidate
import nexus_connector_core.availability as availability
from nexus_connector_core.discovery import fingerprint
from okto_nexus.bootstrap import embedded_inventory
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.mcp.tools.identity import build_service
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.application import execution_local_observations as observations
from okto_nexus.application.terminal_connection import TerminalConnection, ConnectionError


def write(name, value):
    (ROOT / 'control' / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def main():
    origins = {name: str(Path(importlib.import_module(name).__file__).resolve()) for name in
               ('okto_nexus', 'nexus_connector_core', 'okto_nexus_connector')}
    assert all(Path(p).is_relative_to(PREFIX) for p in origins.values())
    write('origins.json', dict(origins=origins, prefix=sys.prefix, sys_path=sys.path))
    patch = pytest.MonkeyPatch()
    binary = ROOT / 'inert-codex-candidate.exe'
    binary.write_bytes(b'QC31 inert candidate, never executed; actual peer is own Python stdio source')
    candidate = InstallationCandidate('codex_app_server', str(binary), fingerprint(binary), 'explicit', 'untrusted')
    candidate = replace(candidate, architecture='x86_64')
    patch.setattr(embedded_inventory, 'discover_local_candidates', lambda **kw: type('Candidates', (), {
        'candidates': (candidate,) if not kw.get('adapter_ids') or candidate.adapter_id in kw['adapter_ids'] else ()})())
    patch.setattr(availability, 'qualified_build', lambda *a, **k: True)
    patch.setattr(availability, 'can_probe_protocol', lambda *a, **k: True)
    patch.setattr(availability, 'containment_preflight', lambda **kw: {'job_objects': 'ok'})
    probes = []
    async def probe(selected):
        probes.append(selected.adapter_id)
        assert selected.trust == 'selected'
        return replace(selected, version='0.159.0')
    patch.setattr(observations, 'probe_version', probe)
    deps = bootstrap({}, ['--home', str(ROOT / 'home'), '--embedding-mode', 'off', '--metrics-mode', 'disabled',
        '--metrics-dir', str(ROOT / 'metrics'), '--feature-harness-integrations', 'true',
        '--runtime-handoff-auto-claim-enabled', 'false'])
    identity = build_service(deps)
    subject = 'qc31-collaborator'
    identity.agent_register(agent_id=subject, role='builder', metadata={'display_name': 'QC31 collaborator'})
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    with deps.connection_factory.unit_of_work() as uow:
        subject_key = auth.issue_key(uow, agent_id=subject)
    headers = dict(operator={'X-Nexus-UI': '1'}, subject={'Authorization': 'Bearer ' + subject_key})
    app = build_app(deps)
    tests = []
    async def simulated_connection_test(entry, request, selected):
        tests.append(request['client_intent_id'])
        entry.update(status='succeeded', stage='Synthetic connection Test boundary verified')
    peers, sessions, operations, browser_requests = [], [], [], []
    unknown = False
    started = time.monotonic()
    try:
        with TestClient(app, raise_server_exceptions=False, client=('127.0.0.1', 50000)) as client:
            async def inventory_ready():
                owner = app.state.embedded_inventory_owner
                async with asyncio.timeout(15):
                    while owner.published_batch is None or any(r.state == 'PENDING' for r in owner.published_batch.observations):
                        if owner.failure is not None:
                            raise owner.failure
                        await asyncio.sleep(.02)
            client.portal.call(inventory_ready)
            patch.setattr(app.state.connection_tests, 'run', simulated_connection_test)
            def call(method, path, body=None):
                response = client.request(method, path, json=body, headers=headers['operator'])
                value = response.json()
                if response.status_code >= 400:
                    error = value.get('error', {})
                    raise ConnectionError(error.get('code', 'HTTP_ERROR'), error.get('message', 'Canonical request refused'),
                                          stage=error.get('stage', 'fixture'), possible_effect=error.get('possible_effect', False))
                return value
            saved = []
            flow = TerminalConnection(call, lambda value: saved.append(value.copy()))
            selection = dict(agent=subject, client='codex', project=str(ROOT / 'project'), label='QC31 Multi-session Project',
                workspace_id=None, binding_id=None, candidate_ref=None, provider_home=str(ROOT / 'provider-home'))
            review = flow.review(selection)
            configured = flow.apply(review, approval=review['review_revision'])
            assert configured['state'] == 'configured' and len(tests) == len(probes) == 1
            binding = call('GET', '/api/v1/runtime-management/connections/bindings/' + configured['binding_id'])
            fields = ('server_id', 'executor_id', 'binding_id', 'endpoint_id', 'agent_id', 'workspace_id', 'workspace_binding_id')
            reference = {key: binding[key] for key in fields}
            association = call('POST', '/api/v1/runtime-management/connections/public-ids/associate-existing', dict(
                approved=True, client_intent_id='qc31-public-association', connect_id='session-reviewer',
                expected_binding_ref=reference, expected_binding_revision=binding['binding_revision']))
            assert association['state'] == 'bound' and association['canonical_ref'] == reference
            setup = (deps, app, client, headers, {}, candidate, ROOT / 'project')
            peer_env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT'}}
            peer_env.update(PATH='', HOME=str(ROOT / 'os-home'), USERPROFILE=str(ROOT / 'os-home'),
                PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHONSAFEPATH='1')
            peers, wire = install_native((setup, binding, None), _FAKE_SERVER_SOURCE, environment=peer_env)

            def admit(intent, intent_id, **extra):
                nonlocal unknown
                response = client.post('/v1/runtime/intents:resolve', headers=headers['subject'], json=dict(
                    client_intent_id=intent_id, intent=intent, binding_id=reference['binding_id'],
                    workspace_binding_id=reference['workspace_binding_id'], **extra))
                assert response.status_code == 200, (intent, response.status_code, response.text)
                resolution = response.json()
                assert resolution['can_submit'], resolution.get('blockers')
                response = client.post('/v1/runtime/operations', headers=headers['subject'], json={
                    k: resolution[k] for k in ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')})
                assert response.status_code == 202, (intent, response.status_code, response.text)
                operations.append(dict(intent=intent, operation_id=resolution['operation_id'], scope=resolution['scope']))
                write('admissions.json', operations)
                end = time.monotonic() + 30
                while True:
                    response = client.get('/v1/runtime/operations/' + resolution['operation_id'], headers=headers['subject'])
                    value = response.json()
                    if value.get('executor_stage') == 'SUCCEEDED':
                        return resolution
                    if value.get('executor_stage') in ('OUTCOME_UNKNOWN', 'FAILED', 'CANCELLED') or time.monotonic() >= end:
                        unknown = True
                        write('blocked-operation.json', dict(operation_id=resolution['operation_id'], intent=intent,
                            admission_state=value.get('admission_state'), executor_stage=value.get('executor_stage'),
                            retry_safe=value.get('retry_safe'), possible_effect=value.get('possible_effect'), failure=value.get('failure')))
                        raise RuntimeError('Canonical synthetic native operation did not succeed; no new admissions: ' + intent)
                    assert app.state.embedded_dispatch_owner.failure is None
                    time.sleep(.02)

            try:
                for label, text in [('A', 'QC31 Alpha retained exact output'), ('B', 'QC31 Beta current exact output')]:
                    opened = admit('runtime.start', 'qc31-open-' + label, new_session=True)
                    sid = opened['scope']['session_id']
                    sessions.append(dict(label=label, session_id=sid, text=text, closed=False))
                    admit('turn.submit', 'qc31-turn-' + label, session_id=sid, text=text)
                    if label == 'A':
                        admit('runtime.close', 'qc31-close-A', session_id=sid)
                        sessions[-1]['closed'] = True
                assert len(sessions) == 2 and sessions[0]['session_id'] != sessions[1]['session_id']
                histories = []
                for session in sessions:
                    sid = session['session_id']
                    end = time.monotonic() + 15
                    while True:
                        response = client.get(f'/api/v1/runtime-management/runtime/sessions/{sid}/events?executor_id={reference["executor_id"]}&after_sequence=0&limit=100', headers=headers['operator'])
                        value = response.json()
                        if response.status_code == 200 and session['text'] in json.dumps(value):
                            break
                        assert time.monotonic() < end, ('Canonical viewer events unavailable', sid, response.status_code)
                        time.sleep(.05)
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        watermarks = [dict(r) for r in uow.connection.execute('SELECT * FROM execution_event_watermarks WHERE session_id=?', (sid,))]
                        assert watermarks and all(r['committed_contiguous'] > 0 and r['gap_state'] == 'none' for r in watermarks)
                        frames = uow.connection.execute('SELECT COUNT(*) FROM execution_receipts WHERE canonical_frame IS NOT NULL '
                            'AND operation_id IN (SELECT operation_id FROM execution_operations WHERE session_id=?)', (sid,)).fetchone()[0]
                        assert frames > 0
                    histories.append(dict(label=session['label'], session_id=sid, events=value,
                                          watermarks=watermarks, nonnull_canonical_receipt_frames=frames))
                write('canonical-histories.json', histories)
                own_peers = []
                for peer in peers:
                    process = getattr(getattr(peer, '_transport', None), '_proc', None)
                    if process is not None:
                        own_peers.append(dict(pid=process.pid, poll=process.poll()))
                write('owned-peers.json', own_peers)
                server = None
                async def expose():
                    nonlocal server
                    async def readonly(scope, receive, send):
                        if scope['type'] != 'http':
                            return await app(scope, receive, send)
                        record = dict(method=scope['method'], path=scope['path'])
                        browser_requests.append(record)
                        async def logged(message):
                            if message['type'] == 'http.response.start':
                                record['status'] = message['status']
                            await send(message)
                        if scope['method'] not in ('GET', 'HEAD', 'OPTIONS'):
                            from starlette.responses import JSONResponse
                            return await JSONResponse({'fixture': 'Read-only browser surface'}, status_code=405)(scope, receive, logged)
                        return await app(scope, receive, logged)
                    server = uvicorn.Server(uvicorn.Config(readonly, host='127.0.0.1', port=0, lifespan='off', log_level='warning', access_log=False))
                    sock = server.config.bind_socket()
                    port = sock.getsockname()[1]
                    write('ready.json', dict(status='READY_CANONICAL_MULTISESSIONS', url='http://127.0.0.1:' + str(port),
                        reference=reference, connect_id='session-reviewer', sessions=sessions, provider_invocations=0,
                        fake_protocol=True, viewer_events_verified=True, browser_readonly=True, browser_deadline_seconds=180,
                        at=datetime.now(timezone.utc).isoformat()))
                    await server.serve(sockets=[sock])
                future = client.portal.start_task_soon(expose)
                end = time.monotonic() + 180
                while not (ROOT / 'control/stop').exists() and time.monotonic() < end and not future.done():
                    time.sleep(.1)
                if server is not None:
                    server.should_exit = True
                future.result(timeout=15)
                write('browser-requests.json', browser_requests)
            finally:
                if not unknown:
                    for session in sessions:
                        if not session['closed']:
                            admit('runtime.close', 'qc31-cleanup-' + session['label'], session_id=session['session_id'])
                            session['closed'] = True
                # The TestClient context owns normal dispatcher/native shutdown.
    finally:
        deps.connection_factory.close()
        patch.undo()
        peer_states = []
        for peer in peers:
            process = getattr(getattr(peer, '_transport', None), '_proc', None)
            if process is not None:
                peer_states.append(dict(pid=process.pid, exit_code=process.poll()))
        write('final.json', dict(status='CLEANUP_OBSERVED' if not unknown else 'BLOCKED_NATIVE_NOT_QUALIFIED',
            sessions=sessions, peers=peer_states, unknown=unknown, elapsed=time.monotonic() - started,
            provider_invocations=0, browser_requests=browser_requests))


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        write('failure.json', dict(type=type(error).__name__, message=str(error)))
        raise
