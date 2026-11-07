"""Curate closed DX04 proofs only; never traverse homes, databases or venvs.

Run only after both browser flows, explicit snapshots and canonical shutdowns.
The command does not perform HTTP, snapshot a database, or stop a process.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
SCENARIOS = ('onboarding', 'agents')
KEY_PATTERN = re.compile(r'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}\b')
PRIVATE_FIELDS = {'api_key', 'password', 'cookie', 'cookies', 'access_token', 'refresh_token',
    'authorization', 'bearer', 'plaintext', 'secret', 'session_token'}
SCRIPTS = ('build_candidate.py', 'server_entry.py', 'servers.py', 'collect_installed.py')
CANDIDATE_FILES = ('build.log', 'venv.log', 'install.log', 'package-proof.json')
SERVER_FILES = ('launch.json', 'server.json', 'owner.json', 'import-proof.json', 'static-http-proof.json',
    'baseline.json', 'after-browser-snapshot.json', 'after-browser-proof.json', 'shutdown.json', 'server.log')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def assert_no_private_json(value):
    if isinstance(value, dict):
        for key, item in value.items():
            assert key.lower() not in PRIVATE_FIELDS or item in (None, '', False, [], {}), 'Private JSON field refused.'
            assert_no_private_json(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_private_json(item)


def frozen_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == data, 'Refusing to overwrite an existing artifact: ' + path.name
    else:
        with path.open('xb') as output:
            output.write(data)


def comparison(folder):
    before = json.loads((folder / 'baseline.json').read_text())
    after = json.loads((folder / 'after-browser-snapshot.json').read_text())
    assert before['home'] == after['home']
    assert set(before['tables']) == set(after['tables'])
    assert before['excluded_from_stable_hash'] == after['excluded_from_stable_hash']
    tables = []
    for name in before['tables']:
        if name == 'agents_raw':
            continue
        raw_name = 'agents_raw' if name == 'agents' else name
        old, new = before['tables'][name], after['tables'][name]
        raw_old, raw_new = before['tables'][raw_name], after['tables'][raw_name]
        tables.append(dict(table=name, before=old, after=new, unchanged=old == new,
            raw_before=raw_old, raw_after=raw_new, raw_unchanged=raw_old == raw_new,
            normalization=('only operator agent last_seen_at is set to null; all other agent fields and rows retained'
                if name == 'agents' else 'none'),
            projection=('agent_id, api_key_hash, is_active, deleted_at; values hashed in memory only'
                if name == 'agent_credentials' else 'all table columns')))
    changed = [item['table'] for item in tables if not item['unchanged']]
    result = dict(revision=1, scenario=folder.name, checked_comparisons=len(tables),
        canonical_unchanged=not changed, changed=changed,
        raw_agent_unchanged=before['tables']['agents_raw'] == after['tables']['agents_raw'],
        details=tables, row_values_or_credential_material_exported=False,
        limitation='Only the listed canonical tables are asserted. The reserved operator last_seen_at audit field is normalized for the stable agents comparison; raw hash is retained.')
    assert not changed, 'Canonical navigation invariant failed; no collection claim of success is allowed.'
    return result


def collect(candidate, destination):
    sources = [(ROOT / name, Path('drivers') / name) for name in SCRIPTS]
    sources.extend((candidate / name, Path('candidate-v1') / name) for name in CANDIDATE_FILES)
    comparisons = {}
    for scenario in SCENARIOS:
        folder = candidate / 'servers' / scenario
        stopped = json.loads((folder / 'shutdown.json').read_text())
        assert stopped['process_exited'] is True, 'Wait for the owned interpreter exit before collecting logs.'
        assert stopped['canonical_result']['shutdown']['state'] == 'DRAINED', 'Canonical drain was not confirmed.'
        comparisons[scenario] = comparison(folder)
        generated = ROOT / 'collection' / (scenario + '-table-comparison.json')
        frozen_write(generated, (json.dumps(comparisons[scenario], indent=2) + '\n').encode())
        sources.append((generated, Path('servers') / scenario / 'table-comparison.json'))
        sources.extend((folder / name, Path('servers') / scenario / name) for name in SERVER_FILES)
    artifacts = []
    for source, relative in sources:
        assert source.suffix in ('.py', '.json', '.log')
        assert not any(part in {'home', 'venv', 'build-source', 'wheels'} for part in source.relative_to(ROOT).parts)
        original = source.read_bytes()
        text = original.decode('utf-8')
        sanitized, redactions = KEY_PATTERN.subn('[SYNTHETIC_CREDENTIAL_REDACTED]', text)
        retained = sanitized.encode('utf-8')
        if source.suffix == '.json':
            assert_no_private_json(json.loads(sanitized))
        assert source.read_bytes() == original, 'Source changed during collection.'
        target = destination / relative
        frozen_write(target, retained)
        artifacts.append(dict(path=relative.as_posix(), source_path=str(source), source_sha256=sha(original),
            artifact_sha256=sha(retained), source_bytes=len(original), artifact_bytes=len(retained),
            redactions=redactions, byte_exact=original == retained))
    package = json.loads((candidate / 'package-proof.json').read_text())
    manifest = dict(revision=1, qualification='Installed DX04 guide browser fixture package; browser results retained separately',
        package=dict(version=package['version'], wheel_sha256=package['wheel_sha256'], core_sha256=package['core_sha256'],
            exact_source_stage_wheel_installed=package['exact_source_stage_wheel_installed'], file_count=package['file_count'],
            dashboard_bundle=package['dashboard_bundle'], dashboard_sha256=package['dashboard_sha256']),
        exclusions=['No home tree, SQLite database/WAL, vault, wheel, venv, user credential, cookie or one-shot material copied.'],
        redaction_rule=KEY_PATTERN.pattern, redaction_count=sum(item['redactions'] for item in artifacts),
        artifact_count=len(artifacts), artifacts=artifacts,
        aggregate_sha256=sha(json.dumps({item['path']: item['artifact_sha256'] for item in artifacts},
            sort_keys=True, separators=(',', ':')).encode()),
        comparisons={name: {key: value[key] for key in ('canonical_unchanged', 'checked_comparisons', 'raw_agent_unchanged')}
            for name, value in comparisons.items()}, canonical_shutdown='DRAINED plus own interpreter exit for both scenarios')
    frozen_write(destination / 'artifact-manifest.json', (json.dumps(manifest, indent=2) + '\n').encode())
    print(json.dumps({key: manifest[key] for key in ('artifact_count', 'redaction_count', 'aggregate_sha256', 'comparisons')}, indent=2))


def verify(destination):
    manifest = json.loads((destination / 'artifact-manifest.json').read_text())
    for item in manifest['artifacts']:
        assert sha((destination / item['path']).read_bytes()) == item['artifact_sha256']
        assert sha(Path(item['source_path']).read_bytes()) == item['source_sha256']
    assert sha(json.dumps({item['path']: item['artifact_sha256'] for item in manifest['artifacts']},
        sort_keys=True, separators=(',', ':')).encode()) == manifest['aggregate_sha256']
    print(json.dumps(dict(verified=True, artifact_count=manifest['artifact_count'], aggregate_sha256=manifest['aggregate_sha256'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--candidate', default='candidate-v1')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+', args.candidate)
    if args.verify:
        verify(args.destination.resolve())
    else:
        collect(ROOT / args.candidate, args.destination.resolve())
