"""Prepare private runtime files only; never launch a process or browser.

The explicit window flag is supplied only after Root releases the perf window.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package-ready', type=Path, required=True)
    parser.add_argument('--mode', choices=['baseline', 'idle_three', 'question', 'verification', 'delayed_info'], default='baseline')
    parser.add_argument('--browser-window-open', action='store_true')
    args = parser.parse_args()
    assert args.browser_window_open, 'Root BROWSER_WINDOW_OPEN is required even for runtime allocation'
    package = json.loads(args.package_ready.read_text(encoding='utf-8'))
    # The package READY shape is intentionally not guessed or normalized here.
    # Supply its literal python/wheel fields after checking the frozen document.
    python = Path(package['python']).resolve()
    wheel = Path(package['wheel']).resolve()
    assert digest(wheel) == package['wheel_sha256']
    prefix = python.parent.parent
    static = prefix / 'Lib/site-packages/okto_nexus/adapters/inbound/http/static'
    html = (static / 'index.html').read_text(encoding='utf-8')
    import re
    js = static / re.search(r'(?:src="|src=\")(/assets/[^" ]+\.js)', html).group(1).lstrip('/')
    css = static / re.search(r'href="(/assets/[^" ]+\.css)', html).group(1).lstrip('/')
    root = Path(tempfile.mkdtemp(prefix='nexus-hst-browser-')).resolve()
    for name in ['helpers', 'control', 'home', 'project', 'cwd', 'tmp', 'os-home']:
        (root / name).mkdir()
    for name in ['peer_source.py', 'canonical_controls.py', 'browser_surface.py']:
        shutil.copyfile(HERE / name, root / 'helpers' / name)
    shutil.copyfile(HERE / 'protocol_fixture.py.txt', root / 'helpers/protocol_fixture.py')
    shutil.copyfile(HERE / 'fixture.py', root / 'fixture.py')
    allocation = dict(root=str(root), prefix=str(prefix), mode=args.mode,
                      start_authorized=True, allow_native_decision_post=False)
    (root / 'allocation.json').write_text(json.dumps(allocation, indent=2) + '\n', encoding='utf-8')
    config = dict(approved_to_start=True, python=str(python), wheel=str(wheel),
                  wheel_sha256=digest(wheel), js_asset=str(js), js_sha256=digest(js),
                  css_asset=str(css), css_sha256=digest(css), provider_invocations=0,
                  fixture_sha256=digest(root / 'fixture.py'), root=str(root),
                  helper_pins={p.name:digest(p) for p in (root / 'helpers').iterdir()},
                  package_ready_sha256=digest(args.package_ready))
    (root / 'runtime-ready.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(root=str(root), runtime_ready=str(root / 'runtime-ready.json'), launched=False)))


if __name__ == '__main__':
    main()
