"""Install and exercise built Nexus artifacts without editable/source imports.

The Connector wheel is a hash-pinned test dependency, never a Nexus runtime
dependency. This regression runner does not qualify providers or remote hosts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


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
    args = parser.parse_args()
    wheels = dependency_wheels()
    nexus = [args.wheel.resolve()] if args.wheel else list((ROOT / 'dist').glob('okto_nexus-*.whl'))
    assert len(nexus) == 1, 'Build exactly one Nexus wheel in dist first'
    wheel = nexus[0]
    if args.action == 'install':
        subprocess.run([sys.executable, '-m', 'pip', 'install',
            '--find-links', str(ROOT / 'vendor/wheels'),
            str(wheel) + '[serve-lite,dev]', *map(str, wheels)], check=True)
        return
    output = ROOT / 'build/ci'
    output.mkdir(parents=True, exist_ok=True)
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
            config = Path(temp) / 'pytest.ini'
            config.write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n', encoding='utf-8')
            command = [sys.executable, '-I', '-m', 'pytest', '-c', str(config),
                       '--rootdir=' + str(ROOT), '--confcutdir=' + str(ROOT / 'tests'),
                       *[str(ROOT / p) for p in args.tests], '-q', '--tb=short',
                       '--junitxml=' + str(output / 'tests.xml')]
            result = subprocess.run(command, cwd=temp)
            raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
