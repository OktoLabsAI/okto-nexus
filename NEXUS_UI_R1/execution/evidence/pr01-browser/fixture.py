"""Finite, own loopback GET-only UI-R1 shell qualification fixture; no lifespan."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tests.home_evolution.browser_fixture import seed, serve
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.bootstrap import embedded_inventory
from okto_nexus.adapters.inbound.http.app import build_app
from fastapi.responses import JSONResponse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stop-file', type=Path, required=True)
    parser.add_argument('--ready-file', type=Path, required=True)
    parser.add_argument('--memory', action='store_true')
    parser.add_argument('--attention-disabled', action='store_true')
    args = parser.parse_args()
    home = Path(tempfile.mkdtemp(prefix='nexus-ui-r1-shell-browser-'))
    embedded_inventory.discover_local_candidates = lambda **_: SimpleNamespace(candidates=())
    deps = bootstrap({}, ['--home', str(home), '--feature-harness-integrations', 'false', '--embedding-mode', 'off'])
    try:
        deps.config.feature_memory = args.memory
        deps.config.feature_attention = not args.attention_disabled
        seed(deps)
        with deps.connection_factory.unit_of_work() as uow:
            for workspace in ('home-alpha', 'home-beta'):
                deps.approvals.intercept(uow, workspace_id=workspace, agent_id='A', action='message_create',
                    policy_id='ui-r1-qual-policy', kwargs=dict(workspace_id=workspace, from_agent_id='A',
                        target=dict(strategy='direct', agent_id='B'), subject='UI-R1 approval '+workspace,
                        body='Disposable fixture request; never execute this approval.'))
            stamp = deps.clock.now_iso()
            uow.connection.execute("INSERT INTO messages(message_id,workspace_id,from_agent_id,subject,body,created_at) VALUES('ui-r1-operator-message','home-alpha','A','UI-R1 unread operator message','Disposable informational message',?)", (stamp,))
            uow.connection.execute("INSERT INTO message_deliveries(delivery_id,message_id,recipient_agent_id,status,created_at) VALUES('ui-r1-operator-delivery','ui-r1-operator-message','operator','unread',?)", (stamp,))
        app = build_app(deps)

        @app.middleware('http')
        async def read_only(request, call_next):
            if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
                return JSONResponse({'fixture': 'Own GET-only qualification; mutations disabled.'}, status_code=405)
            return await call_next(request)

        async def finite():
            async def deadline():
                await asyncio.sleep(240)
                args.stop_file.write_text('finite deadline', encoding='utf-8')
            task = asyncio.create_task(deadline())
            try:
                await serve(app, port=0, stop_file=args.stop_file, ready_file=args.ready_file, fixture_home=home)
            finally:
                task.cancel()
        asyncio.run(finite())
    finally:
        deps.connection_factory.close()


if __name__ == '__main__':
    main()
