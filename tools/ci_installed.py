"""Install and exercise built Nexus artifacts without editable/source imports.

The Connector wheel is a hash-pinned test dependency, never a Nexus runtime
dependency. This regression runner does not qualify providers or remote hosts.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def input_hashes():
    paths = [ROOT / name for name in ('pyproject.toml', 'uv.lock', 'README.md', 'vendor/ci/manifest.json')]
    for directory in ('tests', 'src', 'docs', 'plans/r4_execution', 'plans/contratos'):
        paths.extend(p for p in (ROOT / directory).rglob('*')
                     if p.is_file() and p.suffix in ('.py', '.json', '.md', '.sql')
                     and 'evidence' not in p.parts and '__pycache__' not in p.parts)
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths)) if p.is_file()}


def dependency_wheels():
    manifest = json.loads((ROOT / 'vendor/ci/manifest.json').read_text(encoding='utf-8'))
    wheels = []
    for item in manifest['artifacts']:
        wheel = ROOT / item['path']
        assert wheel.is_file() and hashlib.sha256(wheel.read_bytes()).hexdigest() == item['sha256'], wheel
        wheels.append(wheel)
    return wheels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('install', 'smoke', 'test'))
    parser.add_argument('--tests', nargs='+', default=['tests'])
    parser.add_argument('--wheel', type=Path, help='Existing built wheel; defaults to the single dist wheel')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/ci',
                        help='Directory for this campaign reports')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    wheels = dependency_wheels()
    nexus = [args.wheel.resolve()] if args.wheel else list((ROOT / 'dist').glob('okto_nexus-*.whl'))
    assert len(nexus) == 1, 'Build exactly one Nexus wheel in dist first'
    wheel = nexus[0]
    if args.action == 'install':
        # The base distribution must bootstrap before any serve/Core extras.
        subprocess.run([sys.executable, '-m', 'pip', 'install', str(wheel)], check=True)
        with tempfile.TemporaryDirectory(prefix='nexus-ci-base-') as temp:
            probe = '''import importlib.util, json, sys
for module in ("nexus_connector_core", "okto_nexus_connector", "torch"):
    assert importlib.util.find_spec(module) is None, module
from okto_nexus.bootstrap.dependencies import bootstrap
deps = bootstrap({}, ["--home", sys.argv[1]])
assert deps.approvals is not None
assert deps.native_decisions is None
print(json.dumps({"base_boot_without_core": True, "connector_installed": False,
                  "torch_installed": False, "provider_qualified": False}))
'''
            result = subprocess.run([sys.executable, '-I', '-c', probe, str(Path(temp)/'home')],
                                    cwd=temp, capture_output=True, text=True)
            (output / 'base-without-core.log').write_text(result.stdout + result.stderr, encoding='utf-8')
            if result.returncode:
                print(result.stdout + result.stderr, file=sys.stderr)
                raise SystemExit(result.returncode)
        subprocess.run([sys.executable, '-m', 'pip', 'install',
            '--find-links', str(ROOT / 'vendor/wheels'),
            str(wheel) + '[serve-lite,dev]', str(wheels[0])], check=True)
        # Prove the local package boots before adding the remote application's
        # test-only dependency. This must run in a fresh CI environment.
        with tempfile.TemporaryDirectory(prefix='nexus-ci-local-') as temp:
            probe = '''import importlib.util, json, pathlib, sys
assert importlib.util.find_spec("okto_nexus_connector") is None
assert importlib.util.find_spec("torch") is None
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.adapters.inbound.http.app import build_app
from fastapi.testclient import TestClient
deps = bootstrap({}, ["--home", sys.argv[1]])
with TestClient(build_app(deps)) as client:
    protocol = client.get("/v1/connections/protocol")
    assert protocol.status_code == 200, protocol.text
    assert client.get("/").status_code == 200
    assert client.get("/v1/connections/me").status_code == 401
print(json.dumps({"local_boot_without_connector": True, "torch_installed": False,
                  "protocol_status": protocol.status_code, "provider_qualified": False}))
'''
            result = subprocess.run([sys.executable, '-I', '-c', probe, str(Path(temp)/'home')],
                                    cwd=temp, capture_output=True, text=True)
            (output / 'local-without-connector.log').write_text(result.stdout + result.stderr, encoding='utf-8')
            if result.returncode:
                print(result.stdout + result.stderr, file=sys.stderr)
                raise SystemExit(result.returncode)
        subprocess.run([sys.executable, '-m', 'pip', 'install', str(wheels[1]) + '[test]'], check=True)
        return
    # Independent cwd and -I: pytest itself may import repo-owned helpers, but
    # no pytest pythonpath setting may replace the installed application.
    with tempfile.TemporaryDirectory(prefix='nexus-ci-installed-') as temp:
        verification = '''import hashlib, importlib, importlib.metadata, json, pathlib, sys, zipfile
results = {}
for artifact, module in ARTIFACTS:
    package = pathlib.Path(importlib.import_module(module).__file__).resolve().parent
    assert "site-packages" in str(package), str(package)
    with zipfile.ZipFile(artifact) as archive:
        for name in archive.namelist():
            if name.startswith(module + "/") and not name.endswith("/"):
                assert (package / name.split("/", 1)[1]).read_bytes() == archive.read(name), name
    results[module] = {"path": str(package), "wheel_sha256": hashlib.sha256(pathlib.Path(artifact).read_bytes()).hexdigest()}
requirements = importlib.metadata.requires("okto-nexus") or []
assert not any(r.lower().startswith("okto-nexus-connector") for r in requirements)
from okto_nexus.adapters.inbound.cli.main import main
assert main(["--help"]) == 0
pathlib.Path(REPORT).write_text(json.dumps(results, indent=2) + "\\n", encoding="utf-8")
'''
        modules = ['okto_nexus', 'nexus_connector_core', 'okto_nexus_connector']
        artifacts = list(zip(map(str, [wheel, *wheels]), modules))
        probe = 'ARTIFACTS=' + repr(artifacts) + '\nREPORT=' + repr(str(output / 'installed.json')) + '\n' + verification
        subprocess.run([sys.executable, '-I', '-c', probe], cwd=temp, check=True)
        if args.action == 'test':
            before = input_hashes()
            campaign = dict(started_at=datetime.now(timezone.utc).isoformat(),
                            tests=args.tests, input_hashes=before, status='RUNNING')
            campaign_path = output / 'campaign.json'
            campaign_path.write_text(json.dumps(campaign, indent=2) + '\n', encoding='utf-8')
            config = Path(temp) / 'pytest.ini'
            # Retain declared markers while deliberately excluding checkout
            # pythonpath: installed tests must not import application source.
            declared = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
            markers = declared['tool']['pytest']['ini_options'].get('markers', [])
            config.write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n'
                              + 'markers=\n' + ''.join('    ' + marker + '\n' for marker in markers), encoding='utf-8')
            command = [sys.executable, '-I', '-m', 'pytest', '-c', str(config),
                       '--rootdir=' + str(ROOT), '--confcutdir=' + str(ROOT / 'tests'),
                       *[str(ROOT / p) for p in args.tests], '-q', '--tb=short',
                       '--junitxml=' + str(output / 'tests.xml')]
            result = subprocess.run(command, cwd=temp)
            after = input_hashes()
            changed = sorted(path for path in before.keys() | after.keys()
                             if before.get(path) != after.get(path))
            campaign.update(ended_at=datetime.now(timezone.utc).isoformat(),
                            command=command, exit_code=result.returncode,
                            changed_inputs=changed,
                            status='INPUTS_CHANGED' if changed else 'PASS' if result.returncode == 0 else 'FAIL')
            campaign_path.write_text(json.dumps(campaign, indent=2) + '\n', encoding='utf-8')
            raise SystemExit(result.returncode or (2 if changed else 0))


if __name__ == '__main__':
    main()
