"""Disposable native question browser fixture: no native executable/provider.

The test-only identity endpoint exposes only a newly generated fixture key on
this own loopback listener. Never run against a personal or production home.
"""
import argparse
import asyncio
import json
import hashlib
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace

import pytest
import uvicorn

sys.path.insert(0, str(Path(__file__).parents[1]))
from test_attention_native import native_fixtures  # noqa: E402
from ns14_load import maintain_peer_heartbeat  # noqa: E402
from okto_nexus.bootstrap import embedded_inventory  # noqa: E402
from okto_nexus.domain.runtime_context import RuntimeRequestContext  # noqa: E402
import okto_nexus  # noqa: E402


async def serve(app, stop, ready, frozen):
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=0,
        lifespan='off', log_level='warning', timeout_graceful_shutdown=3))
    sock = server.config.bind_socket()
    package=Path(okto_nexus.__file__).resolve().parent
    pins=['src/okto_nexus/application/home.py','src/okto_nexus/adapters/outbound/sqlite/home.py',
        'src/okto_nexus/application/execution_native_decisions.py',
        'src/okto_nexus/adapters/inbound/http/static/index.html']
    ready.write_text(json.dumps({'url':f'http://127.0.0.1:{sock.getsockname()[1]}',
        'synthetic':True,'provider_calls':0,'frozen_time':frozen,
        'installed_product': 'site-packages' in str(package),
        'source_pins':{name:hashlib.sha256((package/Path(name).relative_to('src/okto_nexus')).read_bytes()).hexdigest() for name in pins}}), encoding='utf-8')
    deadline=time.monotonic()+600
    async def watch():
        while not server.should_exit:
            if stop.exists() or time.monotonic()>deadline:
                server.should_exit = True
            await asyncio.sleep(.1)
    watcher = asyncio.create_task(watch())
    try:
        await server.serve(sockets=[sock])
    finally:
        watcher.cancel()
        sock.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',choices=['input','form','agent_input'],required=True)
    parser.add_argument('--ready',type=Path,required=True)
    parser.add_argument('--stop',type=Path,required=True)
    args=parser.parse_args()
    temporary=Path(tempfile.mkdtemp(prefix='home-r1-native-question-'))
    monkeypatch=pytest.MonkeyPatch()
    monkeypatch.setattr(embedded_inventory,'discover_local_candidates',lambda **_:SimpleNamespace(candidates=()))
    opening=native_fixtures.opening.__wrapped__(temporary,monkeypatch,SimpleNamespace(param=None))
    state=next(opening)
    frozen=state[0].clock.now_iso()
    monkeypatch.setattr(type(state[0].clock),'now_iso',lambda _:frozen)
    deps,app,_=native_fixtures.decision_state.__wrapped__(state,SimpleNamespace(param=args.case))
    @app.get('/__fixture_test_identity')
    def identity():
        return {'key':app.state.test_agent_keys['operator'],'frozen_time':frozen}
    try:
        baseline=app.state.home.read(context=RuntimeRequestContext('operator','http_loopback',trusted_local_operator=True))
        assert baseline['work']['total']==1
        assert args.case=='agent_input' or baseline['attention']['total']==1
        with maintain_peer_heartbeat(app,state[5]):
            asyncio.run(serve(app,args.stop,args.ready,frozen))
    finally:
        opening.close()
        deps.connection_factory.close()
        monkeypatch.undo()


if __name__=='__main__':
    main()
