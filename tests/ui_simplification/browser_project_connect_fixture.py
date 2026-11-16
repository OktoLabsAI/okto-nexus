"""Finite UI039 loopback: real setup APIs/SQLite, synthetic verification peer.

Never executes a harness. The only substituted effect is ConnectionTests.run,
as in test_terminal_connect; start/get/verified/Finish and authorization remain
canonical. No personal provider directory discovery or credentials are used.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests/execution_r4')]

import pytest
from fastapi.responses import JSONResponse
import uvicorn

import test_terminal_connect as terminal_fixtures
import nexus_connector_core


TABLES = ('agents', 'execution_bindings', 'runtime_execution_grants',
          'execution_sessions', 'execution_operations', 'connection_setup_commits')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ready-file', type=Path, required=True)
    parser.add_argument('--stop-file', type=Path, required=True)
    parser.add_argument('--final-file', type=Path, required=True)
    args = parser.parse_args()
    temporary = Path(tempfile.mkdtemp(prefix='nexus-ui039-browser-'))
    with ExitStack() as stack:
        patch = stack.enter_context(pytest.MonkeyPatch.context())
        synthetic_provider_home=temporary/'synthetic-provider-home'
        synthetic_provider_home.mkdir()
        patch.setattr(nexus_connector_core, 'discover_provider_home',
            lambda adapter: str(synthetic_provider_home) if adapter=='claude_stream' else None)
        generator = terminal_fixtures.local_setup.__wrapped__(temporary, patch, SimpleNamespace())
        setup = next(generator)
        stack.callback(generator.close)
        checking = terminal_fixtures.checking.__wrapped__(setup, patch)
        from okto_nexus.bootstrap import embedded_inventory
        from nexus_connector_core.discovery import fingerprint
        binary = temporary/'claude.exe'
        binary.write_text('UI039 inert Claude candidate; never executed',encoding='utf-8')
        claude = nexus_connector_core.InstallationCandidate('claude_stream',str(binary),fingerprint(binary),
            'explicit','selected',version='2.1.0',architecture='x86_64')
        codex = checking[6]
        patch.setattr(embedded_inventory,'discover_local_candidates',lambda **kwargs:SimpleNamespace(candidates=tuple(
            item for item in (replace(codex,fingerprint=fingerprint(Path(codex.executable))),claude)
            if not kwargs.get('adapter_ids') or item.adapter_id in kwargs['adapter_ids'])))
        t = terminal_fixtures.terminal.__wrapped__(checking, setup, patch)
        # A is created by real canonical Test/Finish before the browser journey.
        document = t.flow.review(t.selection | {'agent':'collaborator-a', 'client':'codex', 'create_agent':True, 'label':'UI039 project'})
        configured = t.flow.apply(document, approval=document['review_revision'])
        assert configured['state'] == 'configured', configured
        app, deps = t.app, t.deps
        calls = []
        faults = {'test': False, 'finish': False}

        def facts():
            with deps.connection_factory.unit_of_work(write=False) as uow:
                rows = {table:[dict(row) for row in uow.connection.execute('SELECT * FROM '+table)] for table in TABLES}
                # Preserve comparison without exporting generated credential material.
                endpoints=[dict(row) for row in uow.connection.execute("SELECT * FROM agent_endpoints WHERE agent_id='collaborator-a'")]
                a_endpoint_ids={row['endpoint_id'] for row in endpoints}
                a_subset={
                    'binding':[row for row in rows['execution_bindings'] if row['endpoint_id'] in a_endpoint_ids],
                    'grant':[row for row in rows['runtime_execution_grants'] if row['actor_agent_id']=='collaborator-a'],
                    'endpoint':endpoints,
                    'profile':[dict(row) for row in uow.connection.execute('SELECT * FROM runtime_profiles') if row['profile_id'] in {e['profile_id'] for e in endpoints}],
                }
                return dict(counts={key:len(value) for key,value in rows.items()},
                    agents=[row['agent_id'] for row in rows['agents']],
                    bindings=[{key:row.get(key) for key in ('binding_id','agent_id','executor_id','workspace_id','workspace_binding_id','adapter_id')} for row in rows['execution_bindings']],
                    row_digests={key:hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest() for key,value in rows.items()},
                    a_agent_digest=hashlib.sha256(json.dumps([row for row in rows['agents'] if row['agent_id']=='collaborator-a'],sort_keys=True,default=str).encode()).hexdigest(),
                    a_configuration_digests={key:hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest() for key,value in a_subset.items()},
                    turns=list(t.turns), probes=len(t.probes), calls=calls)

        before = facts()

        async def synthetic_controls(request, call_next):
            path = request.url.path
            if path == '/_ui039/state':
                return JSONResponse(facts())
            if path.startswith('/_ui039/arm/') and request.method == 'GET':
                kind = path.rsplit('/',1)[-1]
                if kind not in faults:
                    return JSONResponse({},status_code=404)
                faults[kind] = True
                return JSONResponse({'armed':kind})
            if request.method not in {'GET','HEAD','OPTIONS'}:
                allowed = ('setup:test','setup:finish','setup:recover','installations:check')
                if not path.endswith(allowed):
                    return JSONResponse({'fixture':'Only canonical reviewed setup writes allowed'},status_code=405)
                body = await request.json()
                calls.append({'method':request.method,'path':path,'intent':body.get('client_intent_id'),
                              'agent':body.get('agent_id'),'workspace':body.get('workspace_id')})
            response = await call_next(request)
            for kind in faults:
                if faults[kind] and path.endswith('setup:'+kind) and response.status_code < 300:
                    faults[kind] = False
                    return JSONResponse({'error':{'code':'OUTCOME_UNKNOWN','message':'Synthetic response lost after canonical effect'}},status_code=503)
            return response

        async def serve():
            from starlette.middleware.base import BaseHTTPMiddleware
            browser_app = BaseHTTPMiddleware(app, dispatch=synthetic_controls)
            config = uvicorn.Config(browser_app,host='127.0.0.1',port=0,lifespan='off',log_level='warning')
            server = uvicorn.Server(config)
            sock = config.bind_socket()
            async def stop():
                deadline = asyncio.get_running_loop().time()+1800
                while not server.should_exit:
                    if args.stop_file.exists() or asyncio.get_running_loop().time()>deadline:
                        server.should_exit = True
                        return
                    await asyncio.sleep(.2)
            watcher = asyncio.create_task(stop())
            args.ready_file.parent.mkdir(parents=True,exist_ok=True)
            assets = ROOT/'src/okto_nexus/adapters/inbound/http/static/assets'
            args.ready_file.write_text(json.dumps(dict(url=f'http://127.0.0.1:{sock.getsockname()[1]}',
                fixture_home=str(temporary), synthetic_peer=True, real_provider_calls=0,
                configured=configured,before=before,
                source_pins={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in [Path(__file__),ROOT/'frontend/src/projectConnectFlowModel.ts',ROOT/'frontend/src/components/onboarding/ProjectConnectFlow.tsx',*assets.glob('*')]}),indent=2),encoding='utf-8')
            print('READY '+str(args.ready_file),flush=True)
            try:
                await server.serve(sockets=[sock])
            finally:
                watcher.cancel()
                sock.close()
                args.final_file.write_text(json.dumps(dict(before=before,after=facts(),fixture_home=str(temporary)),indent=2),encoding='utf-8')
        asyncio.run(serve())
    print('STOPPED '+str(temporary),flush=True)


if __name__ == '__main__':
    main()
