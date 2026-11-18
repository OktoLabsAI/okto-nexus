"""Read-only Root gate. No allocation, product imports, browser or native launch.

An approved gate must bind the complete prepared manifest, immutable R9 package
READY, one case and its deadline. A template is never approval.
"""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SOURCE = 'f07163ab7fd618b2ff4247ba6cdb2547b5d4e038'
WHEEL = 'e870ea400435d5b736093990af9b56544661e205ad657bbff83f830421a3e628'


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
    assert manifest['runtime_binding']['source_commit'] == SOURCE
    assert manifest['runtime_binding']['wheel_sha256'] == WHEEL
    gate = json.loads(Path(gate_path).read_text(encoding='utf-8'))
    assert gate.get('approved') is True and gate.get('approved_by') == 'root'
    assert gate['manifest_sha256'] == sha(manifest_path)
    assert gate['case'] == 'H03' and gate['deadline_seconds'] == 180
    assert gate['provider_invocations'] == 0
    assert gate['source_commit'] == SOURCE and gate['wheel_sha256'] == WHEEL
    assert gate['cut_id'].startswith('hst-security-')
    assert gate['runtime_mode'] == 'baseline', 'H03 uses one canonical registered binding'
    assert gate['allow_own_containment'] is True
    assert gate['browser_environment_policy']=='windows-path-allowlist-app-env-own-v1'
    browser=manifest['browser_tooling']
    assert sha(browser['node'])==browser['node_sha256'] and sha(browser['chrome'])==browser['chrome_sha256']
    tool=Path(browser['node_modules']).resolve()
    actual={path.relative_to(tool).as_posix():sha(path)
        for package in ('@playwright/cli','playwright','playwright-core')
        for path in (tool/package).rglob('*') if path.is_file()}
    assert actual==browser['cli_payload_pins']
    assert Path(browser['entry']).resolve().is_relative_to(tool)
    assert json.loads((HERE/'playwright-cli.json').read_text())==browser['browser_config']
    assert gate.get('allow_exact_observation_inserts', False) is False
    for relative, expected in manifest['input_pins'].items():
        path = (REPO / relative).resolve()
        assert path.is_relative_to(REPO.resolve()) and path.is_file()
        assert sha(path) == expected, 'Prepared input drift: ' + relative
    ready_path = REPO / 'NEXUS_HOME_ESTADOS_R1/execution/package-hst-r9/READY.json'
    assert gate['ready_sha256'] == sha(ready_path)
    ready = json.loads(ready_path.read_text(encoding='utf-8'))
    assert ready['ready'] is True and ready['prefix_frozen'] is True
    assert ready['source_commit'] == SOURCE and ready['wheel_sha256'] == WHEEL
    assert ready['payload_files'] == 1031 and sha(ready['wheel']) == WHEEL
    source_path = ready_path.parent / 'evidence/source-pins-before.json'
    baseline = json.loads(source_path.read_text())
    build = json.loads((ready_path.parent / 'evidence/build-manifest.json').read_text())
    qualification = json.loads((ready_path.parent / 'qualification.json').read_text())
    assert baseline == build['source_pins']
    assert len(baseline) == qualification['source_snapshot']['files'] == manifest['runtime_binding']['source_pin_count']
    assert baseline and all(name in baseline for name in (
        'pyproject.toml', 'uv.lock', 'src/okto_nexus/application/observations.py',
        'tests/home_states/test_results_boundary_completion.py',
    ))
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
