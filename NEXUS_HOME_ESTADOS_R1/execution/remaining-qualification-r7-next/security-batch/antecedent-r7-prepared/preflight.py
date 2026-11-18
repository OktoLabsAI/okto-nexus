"""Read-only Root gate. No allocation, product imports, browser or native launch.

An approved gate must bind the complete prepared manifest, immutable R7 package
READY, one case and its deadline. A template is never approval.
"""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SOURCE = '01b0de385398950ac4547aa8a5dcbc29473c12cb'
WHEEL = '18c948b49844c7c551360732970fdc2ba91cba50075b73c1a7472571775d7681'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_pins():
    paths = []
    for folder in ('src', 'frontend/src', 'frontend/public', 'tests'):
        paths.extend(path for path in (REPO / folder).rglob('*') if path.is_file()
                     and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.pyo'))
    paths.extend(REPO / name for name in (
        'pyproject.toml', 'README.md', 'LICENSE', 'uv.lock', 'vendor/ci/manifest.json',
        'tools/ci_installed.py', 'tools/build_validation_artifacts.py',
    ))
    paths.extend(path for path in (REPO / 'frontend').glob('*') if path.is_file()
                 and path.suffix in ('.json', '.ts', '.js', '.mjs', '.html'))
    return {path.relative_to(REPO).as_posix(): sha(path) for path in sorted(set(paths)) if path.is_file()}


def check(gate_path):
    manifest_path = HERE / 'prepared-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    gate = json.loads(Path(gate_path).read_text(encoding='utf-8'))
    assert gate.get('approved') is True and gate.get('approved_by') == 'root'
    assert gate['manifest_sha256'] == sha(manifest_path)
    assert gate['case'] in {'S1', 'S2'} and gate['deadline_seconds'] == 180
    assert gate['provider_invocations'] == 0
    assert gate['source_commit'] == SOURCE and gate['wheel_sha256'] == WHEEL
    assert gate['cut_id'].startswith('hst-security-')
    assert gate['runtime_mode'] == 'baseline', 'First increment has no live question'
    assert gate['allow_own_containment'] is True
    for relative, expected in manifest['input_pins'].items():
        path = (REPO / relative).resolve()
        assert path.is_relative_to(REPO.resolve()) and path.is_file()
        assert sha(path) == expected, 'Prepared input drift: ' + relative
    ready_path = REPO / 'NEXUS_HOME_ESTADOS_R1/execution/package-hst-r7/READY.json'
    assert gate['ready_sha256'] == sha(ready_path)
    ready = json.loads(ready_path.read_text(encoding='utf-8'))
    assert ready['ready'] is True and ready['prefix_frozen'] is True
    assert ready['source_commit'] == SOURCE and ready['wheel_sha256'] == WHEEL
    assert ready['payload_files'] == 1031 and sha(ready['wheel']) == WHEEL
    source_path = ready_path.parent / 'evidence/source-pins-before.json'
    baseline = json.loads(source_path.read_text())
    assert len(baseline) == 1828
    expected = dict(baseline)
    additions = gate.get('source_additions', {})
    assert set(additions).isdisjoint(expected)
    for name, digest in additions.items():
        assert name.startswith('tests/home_states/') and len(digest) == 64
    expected.update(additions)
    current = source_pins()
    assert current == expected, 'Full source drift/addition/deletion outside Root gate'
    prefix = Path(ready['python']).resolve().parent.parent
    payload_path = ready_path.parent / 'evidence/payload-manifest.json'
    payload = json.loads(payload_path.read_text(encoding='utf-8'))
    assert sum(len(items) for items in payload.values()) == 1031
    for items in payload.values():
        for name, expected in items.items():
            path = (prefix / 'Lib/site-packages' / name).resolve()
            assert path.is_relative_to(prefix) and sha(path) == expected
    return {
        'status': 'READY_TO_ALLOCATE_ONLY', 'case': gate['case'],
        'cut_id': gate['cut_id'], 'python': ready['python'],
        'source_commit': SOURCE, 'wheel_sha256': WHEEL,
        'allocated': False, 'started': False, 'provider_invocations': 0,
        'source_pin_count': len(current), 'source_pins_sha256': hashlib.sha256(
            json.dumps(current, sort_keys=True).encode()).hexdigest(),
        'gate_sha256': sha(gate_path),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--gate', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.gate), indent=2))
