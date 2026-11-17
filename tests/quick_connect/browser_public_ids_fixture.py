"""Finite own loopback browser fixture: real IDs/HTTP/SQLite, no model/native CLI.

Admission/WSS/native input uses the established UI scenario's inert peer. Extra
registered bindings and historical result are explicitly synthetic read facts.
Public IDs are associated through the canonical metadata service before the
passive baseline; no provider, Setup Test, Finish or grant is run for browsing.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT), str(ROOT / 'tests/execution_r4')]

import pytest  # noqa: E402
import uvicorn  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

spec = importlib.util.spec_from_file_location('qc05_ui_fixture', ROOT / 'NEXUS_UI_R1/execution/fixtures.py')
fixtures = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixtures
spec.loader.exec_module(fixtures)

TABLES = ('agents', 'execution_bindings', 'runtime_execution_grants', 'execution_sessions',
          'execution_operations', 'connection_setup_commits', 'execution_results',
          'execution_native_requests', 'connection_public_ids')


def snapshot(s):
    with s.factory.unit_of_work(write=False) as uow:
        return {table: dict(count=len(rows), sha256=hashlib.sha256(json.dumps(rows, sort_keys=True,
            default=str).encode()).hexdigest()) for table in TABLES
            for rows in [[list(row) for row in uow.connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]]}


def seed(s):
    from okto_nexus.application.connection_public_ids import associate_existing
    from okto_nexus.application.execution_binding_views import read_execution_binding
    from okto_nexus.bootstrap.execution_authority import build_execution_access
    from tests.ui_simplification.test_entry_relations import link_handoff
    access = build_execution_access(s.deps)
    ids = []
    for binding, name in (('binding', 'reviewer'), ('ui-binding-2', 'builder')):
        current = read_execution_binding(s.factory, server_id=s.connections[0].server_id,
            binding_id=binding, context=s.operator, access=access)
        if current['state'] != 'APPROVED':
            raise RuntimeError('Canonical fixture binding is not approved: ' + binding + ':' + current['state'])
        reference = {key: current[key] for key in ('server_id', 'executor_id', 'binding_id', 'endpoint_id',
                     'agent_id', 'workspace_id', 'workspace_binding_id')}
        ids.append(associate_existing(s.deps, s.operator, dict(approved=True,
            client_intent_id='qc05-associate-' + name, connect_id=name, expected_binding_ref=reference,
            expected_binding_revision=current['binding_revision'])))
    with s.factory.unit_of_work() as uow:
        c, now = uow.connection, s.clock.now_iso()
        c.execute("DELETE FROM execution_session_containment WHERE session_id='ui-session-2'")
        c.execute("UPDATE workspaces SET display_name='QC05 project' WHERE workspace_id='ws'")
        c.execute("UPDATE agents SET metadata=? WHERE agent_id='subject'", (json.dumps({'display_name': 'QC05 collaborator'}),))
        link_handoff(c, now)
        c.execute("INSERT INTO execution_domain_deliveries(server_id,executor_id,operation_id,domain_operation_id) "
                  "VALUES(?,?,'ui-success','entry-domain')", (s.connections[0].server_id, s.connections[0].executor_id))
        c.execute("INSERT INTO execution_event_ingress VALUES(?,?,'ui-session-2','ui-historical-epoch',10,"
                  "'qc05-result-event','turn.completed','{}',?)", (s.connections[0].server_id, s.connections[0].executor_id, now))
        c.execute("INSERT INTO execution_results VALUES(?,?,'ui-success','ui-session-2','ui-historical-epoch',10,"
                  "'QC05 synthetic retained delivery',0,1,'success',?)", (s.connections[0].server_id, s.connections[0].executor_id, now))
    return dict(public_ids=ids, legacy_binding='qc05-legacy-binding', workspace_id='ws',
                question_session=s.sessions[0], historical_session=s.sessions[1],
                synthetic_read_facts=True, real_provider_calls=0, native_binary_calls=0)


async def serve(s, args, identities):
    requests = []
    before = snapshot(s)
    static = ROOT / 'src/okto_nexus/adapters/inbound/http/static'
    if args.expected_bundle not in (static / 'index.html').read_text(encoding='utf-8'):
        raise RuntimeError('Frozen bundle mismatch')

    async def readonly(scope, receive, send):
        if scope['type'] != 'http':
            return await s.app(scope, receive, send)
        row = dict(method=scope['method'], path=scope['path'], query=scope.get('query_string', b'').decode())
        requests.append(row)
        if scope['method'] not in {'GET', 'HEAD', 'OPTIONS'}:
            row['status'] = 405
            return await JSONResponse({'fixture': 'passive read-only cut; canonical write not invoked'}, status_code=405)(scope, receive, send)

        async def logged(message):
            if message['type'] == 'http.response.start':
                row['status'] = message['status']
            await send(message)
        return await s.app(scope, receive, logged)

    server = uvicorn.Server(uvicorn.Config(readonly, host='127.0.0.1', port=0, lifespan='off',
        log_level='warning', timeout_graceful_shutdown=3))
    sock = server.config.bind_socket()
    files = [Path(__file__), ROOT / 'NEXUS_UI_R1/execution/fixtures.py',
        ROOT / 'src/okto_nexus/application/connection_public_ids.py',
        ROOT / 'src/okto_nexus/adapters/outbound/sqlite/home_entries.py',
        ROOT / 'src/okto_nexus/adapters/outbound/sqlite/connection_catalog.py',
        static / 'index.html', *sorted((static / 'assets').glob('*'))]
    ready = dict(url='http://127.0.0.1:' + str(sock.getsockname()[1]), pid=os.getpid(), home=str(args.home),
        identities=identities, before=before, source_pins={str(p.relative_to(ROOT)).replace('\\', '/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        controlled_clock=s.clock.now_iso(), read_only=True, personal_auth=False, installed_qualification=False)
    args.ready.write_text(json.dumps(ready, indent=2), encoding='utf-8')
    print('READY ' + ready['url'], flush=True)

    async def watch():
        deadline = asyncio.get_running_loop().time() + args.duration
        while not server.should_exit:
            if args.stop.exists() or asyncio.get_running_loop().time() >= deadline:
                server.should_exit = True
                return
            await asyncio.sleep(.2)
    watcher = asyncio.create_task(watch())
    try:
        await server.serve(sockets=[sock])
    finally:
        watcher.cancel()
        sock.close()
        args.final.write_text(json.dumps(dict(before=before, after=snapshot(s), requests=requests,
            source_drift=[str(p) for p in files if hashlib.sha256(p.read_bytes()).hexdigest()
                != ready['source_pins'][str(p.relative_to(ROOT)).replace('\\', '/')]]), indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    for name in ('ready', 'stop', 'final'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expected-bundle', required=True)
    parser.add_argument('--duration', type=int, default=600)
    args = parser.parse_args()
    if not 30 <= args.duration <= 900:
        parser.error('duration 30..900 required')
    args.home = Path(tempfile.mkdtemp(prefix='nexus-qc05-browser-'))
    import test_open_bootstrap as opening
    original = opening.setup_authority

    def setup(*a, **kw):
        state = original(*a, **kw)
        with state[0].connection_factory.unit_of_work() as uow:
            c = uow.connection
            endpoint = c.execute("SELECT * FROM agent_endpoints WHERE endpoint_id='ep'").fetchone()
            binding = c.execute("SELECT * FROM execution_bindings WHERE binding_id='binding'").fetchone()
            fixtures._copy(c, 'agent_endpoints', endpoint, endpoint_id='qc05-legacy-endpoint')
            fixtures._copy(c, 'execution_bindings', binding, binding_id='qc05-legacy-binding', endpoint_id='qc05-legacy-endpoint')
        return state

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(opening, 'setup_authority', setup)
        clock = fixtures.ControlledClock(datetime.now(timezone.utc).isoformat())
        with fixtures.scenario(args.home, recipient='operator', clock=clock) as scenario:
            identities = seed(scenario)
            asyncio.run(serve(scenario, args, identities))
    print('CLOSED owned WSS/lifespan/factory normally', flush=True)


if __name__ == '__main__':
    main()
