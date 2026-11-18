"""PREPARED: real foreground serve, synthetic version/Test/native protocol peer.

No TestClient, fake service inspection, agent-key operator login or authority SQL.
Execution requires a separately reviewed manifest and explicit Root gate.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--gate', choices=['ROOT_APPROVED_COMPAT_BATCH'], required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--phase', choices=['s3-current', 's4-old', 's4-current'], required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    assert sha(args.manifest) == args.manifest_sha256
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    assert manifest['status'] == 'PREPARED_BOUND_NOT_EXECUTED'
    assert args.phase in manifest['phases']
    expected = manifest['phases'][args.phase]
    prefix = Path(expected['prefix']).resolve()
    assert Path(sys.executable).resolve().is_relative_to(prefix)
    assert sys.flags.isolated and sys.dont_write_bytecode
    for name, pin in manifest['helper_sha256'].items():
        assert sha(Path(name)) == pin, name
    root, home = args.root.resolve(), args.home.resolve()
    assert root.name.startswith('nexus-hst-compat-') and home.is_relative_to(root)
    assert (root / 'control').is_dir() and (root / 'peer-root').is_dir()
    assert (root / 'control').parent == root
    assert 1024 <= args.port <= 65535
    # Product imports occur only after the explicit gate and prefix/helper pins.
    import nexus_connector_core
    import okto_nexus_connector
    from nexus_connector_core import InstallationCandidate, availability
    from nexus_connector_core.discovery import fingerprint

    import okto_nexus
    from okto_nexus.adapters.inbound.cli.serve import run_serve
    from okto_nexus.adapters.inbound.http import app as http_app
    from okto_nexus.application import execution_local_observations
    from okto_nexus.bootstrap import embedded_inventory

    origins = {m.__name__: m.__file__ for m in (okto_nexus, nexus_connector_core, okto_nexus_connector)}
    assert all(Path(p).resolve().is_relative_to(prefix) for p in origins.values())
    binary = root / 'candidate' / 'codex.exe'
    assert binary.is_file() and sha(binary) == manifest['synthetic_candidate_sha256']
    candidate = InstallationCandidate('codex_app_server', str(binary), fingerprint(binary),
        'explicit', 'untrusted', architecture='x86_64')

    def discover(**options):
        rows = () if options.get('adapter_ids') and candidate.adapter_id not in options['adapter_ids'] else (candidate,)
        return SimpleNamespace(candidates=rows)

    # These exact fixture seams are synthetic and never certify a real build,
    # version, provider login, configuration Test or process containment policy.
    embedded_inventory.discover_local_candidates = discover
    availability.qualified_build = lambda *a, **kw: True
    availability.can_probe_protocol = lambda *a, **kw: True
    availability.containment_preflight = lambda **kw: {'job_objects': 'ok'}

    async def probe(selected):
        assert selected.executable == str(binary) and selected.trust == 'selected'
        with (root / 'control/effects.jsonl').open('a', encoding='utf-8') as log:
            log.write(json.dumps({'kind': 'synthetic_version_probe'}) + '\n')
        return replace(selected, version='0.159.0')

    execution_local_observations.probe_version = probe
    protocol = load('compat_protocol_fixture', Path(manifest['protocol_fixture']))
    peer_source = load('compat_peer_source', Path(manifest['peer_source']))
    base = protocol.BASE_SOURCE
    source = peer_source.source(base, root / 'control')
    original_build = http_app.build_app

    def build(deps, *positional, **kwargs):
        application = original_build(deps, *positional, **kwargs)

        async def synthetic_test(entry, request, selected):
            assert selected.executable == str(binary)
            with (root / 'control/effects.jsonl').open('a', encoding='utf-8') as log:
                log.write(json.dumps({'kind': 'synthetic_setup_test', 'intent': request['client_intent_id']}) + '\n')
            entry.update(status='succeeded', stage='Synthetic connection verified')

        application.state.connection_tests.run = synthetic_test
        original_lifespan = application.router.lifespan_context

        @asynccontextmanager
        async def lifespan(app):
            async with original_lifespan(app):
                setup = (deps, app, None, None, {}, candidate, root / 'peer-root')
                peer_env = {k: v for k, v in os.environ.items()
                    if k.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT'}}
                peer_env.update(PATH='', HOME=str(root / 'peer-home'), USERPROFILE=str(root / 'peer-home'),
                    PYTHONDONTWRITEBYTECODE='1')
                protocol.install_native((setup, None, None), source, environment=peer_env)
                (root / 'control' / ('owner-imports-' + args.phase + '.json')).write_text(
                    json.dumps({'origins': origins, 'pid': os.getpid(), 'phase': args.phase,
                        'service': 'Actual foreground run_serve/ServeLock/ServiceLifecycle; no PID or readiness stub'}, indent=2),
                    encoding='utf-8')
                yield

        application.router.lifespan_context = lifespan
        return application

    http_app.build_app = build
    argv = ['--home', str(home), '--host', '127.0.0.1', '--port', str(args.port),
        '--embedding-mode', 'off', '--feature-harness-integrations', 'true',
        '--feature-hitl', 'true', '--runtime-handoff-auto-claim-enabled', 'false']
    raise SystemExit(run_serve(argv))


if __name__ == '__main__':
    main()
