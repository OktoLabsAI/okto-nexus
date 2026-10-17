"""Disposable installed Nexus for real UI owner-containment qualification.

Creates a NEW home/workspace below this checkout's build directory. No HTTP
fault endpoint or native fake is added. Creating contain.request triggers one
normal dispatch-owner failure; stop.request requests normal retained shutdown.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--resume', action='store_true',
        help='Reuse a previously drained disposable home; create fresh private control files.')
    parser.add_argument('--port', type=int, default=8204)
    parser.add_argument('--harness-root', action='append', default=[])
    parser.add_argument('--pi-install-root')
    parser.add_argument('--pi-node')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    directory = args.directory.resolve()
    if not directory.is_relative_to((root / 'build').resolve()) or directory == root / 'build':
        parser.error('Use a new disposable directory below the checkout build directory.')
    if not 1024 <= args.port <= 65535 or args.port == 8202:
        parser.error('Use an unprivileged test port other than the production port 8202.')
    home, workspace = directory / 'home', directory / 'workspace'
    if args.resume:
        evidence = directory / 'evidence.jsonl'
        if not evidence.is_file() or not (home / 'nexus.db').is_file() or not workspace.is_dir():
            parser.error('Resume requires an existing disposable fixture home and evidence.')
        observations = [json.loads(line) for line in evidence.read_text(encoding='utf-8').splitlines()]
        if not observations or observations[-1].get('event') != 'lifespan_finished':
            parser.error('Resume requires the previous disposable run to have finished its lifespan.')
        controls = directory / 'controls' / secrets.token_hex(8)
        controls.mkdir(parents=True, exist_ok=False)
    else:
        directory.mkdir(parents=True, exist_ok=False)
        workspace.mkdir()
        controls = directory

    from okto_nexus.adapters.inbound.http import app as http_app
    from okto_nexus.adapters.inbound.cli.main import main as cli_main
    import okto_nexus
    assert 'site-packages' in Path(okto_nexus.__file__).resolve().parts
    original = http_app.build_app

    def record(event, **details):
        with (directory / 'evidence.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(at=datetime.now(timezone.utc).isoformat(),
                pid=os.getpid(), event=event, **details)) + '\n')

    def build_app(*a, **kw):
        app = original(*a, **kw)
        assert app.state.deps.config.home_dir.resolve() == home
        lifespan = app.router.lifespan_context
        @asynccontextmanager
        async def observed_lifespan(application):
            async with lifespan(application):
                stop = asyncio.Event()
                async def observe():
                    injected = False
                    previous = None
                    while not stop.is_set():
                        owner = application.state.embedded_dispatch_owner
                        state = dict(generation=owner.channel.connection_generation,
                            failed=owner.failure is not None, stopping=owner._stopping.is_set(),
                            pump_started=owner.pump is not None,
                            blocked_agents=sorted(owner.agents.blocked),
                            shutdown_state=owner.shutdown_status()['state'])
                        if state != previous:
                            record('owner_observation', **state)
                            previous = state
                        if not injected and (controls / 'contain.request').is_file():
                            injected = True
                            record('fault_requested', **state)
                            owner.failure = RuntimeError('Controlled disposable UI host-containment fault')
                            await owner.failed()
                            record('fault_applied', generation=owner.channel.connection_generation)
                        if (controls / 'stop.request').is_file():
                            coordinator = application.state.runtime_shutdown
                            await coordinator.request(timeout_seconds=0)
                            await coordinator.wait()
                            record('shutdown_drained', report=coordinator.status())
                            return
                        try:
                            await asyncio.wait_for(stop.wait(), .2)
                        except TimeoutError:
                            pass
                task = asyncio.create_task(observe(), name='disposable-ui-fault-observer')
                record('ready', home=str(home), workspace=str(workspace),
                       controls=str(controls),
                       package=str(Path(okto_nexus.__file__).resolve()))
                try:
                    yield
                finally:
                    stop.set()
                    await asyncio.shield(task)
            record('lifespan_finished')
        app.router.lifespan_context = observed_lifespan
        return app

    http_app.build_app = build_app
    arguments = ['serve', '--host', '127.0.0.1', '--port', str(args.port),
                 '--home', str(home), '--log-level', 'info']
    for path in args.harness_root:
        arguments.extend(['--harness-root', path])
    if args.pi_install_root:
        arguments.extend(['--pi-install-root', args.pi_install_root, '--pi-node', args.pi_node])
    record('launch', port=args.port, resume=args.resume, controls=str(controls))
    return cli_main(arguments)


if __name__ == '__main__':
    raise SystemExit(main())
