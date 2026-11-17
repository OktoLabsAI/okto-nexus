"""Record the built source cut; emit the package gate only after its commit."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATIC = ROOT / 'src/okto_nexus/adapters/inbound/http/static'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assets = {'index.html': sha(STATIC / 'index.html')}
    for name in re.findall(r'(?:src|href)="([^"]+\.(?:js|css))"', (STATIC / 'index.html').read_text()):
        name = name.lstrip('/')
        assert (STATIC / name).resolve().is_relative_to(STATIC.resolve())
        assets[name] = sha(STATIC / name)
    assert any(name.endswith('.js') for name in assets) and any(name.endswith('.css') for name in assets)
    if sys.argv[1] == 'record':
        report = {'at': datetime.now(UTC).isoformat(), 'version': '0.3.7', 'assets': assets,
                  'command': 'rtk proxy npm run build', 'result': 'PASS TypeScript and Vite production build',
                  'warnings': ['Vite chunk larger than 500kB; build success is not a performance qualification.'],
                  'limitations': ['Not installed/browser/provider/human qualification.']}
        (HERE / 'frontend-global/build.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    elif sys.argv[1] == 'gate':
        command = ['rtk', 'proxy', 'git']
        product_paths = ['src', 'frontend', 'tests', 'pyproject.toml', 'uv.lock', 'vendor', 'tools']
        dirty = subprocess.check_output(command + ['status', '--porcelain', '--', *product_paths], cwd=ROOT, text=True)
        assert not dirty.strip(), dirty
        commit = subprocess.check_output(command + ['rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        gate = HERE / 'package-hst/SOURCE_ASSET_READY.json'
        assert not gate.exists(), 'An antecedent gate must be preserved.'
        gate.write_text(json.dumps({'source_asset_ready': True, 'version': '0.3.7',
                                   'source_commit': commit, 'assets': assets}, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'gate': str(gate), 'source_commit': commit, 'assets': list(assets)}))
    else:
        raise SystemExit('record or gate required')


if __name__ == '__main__':
    main()
