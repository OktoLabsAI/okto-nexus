"""Read-only public-artifact verification. Never imports product or runs tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = Path(__file__).parent
BASE = '5545dbde'
EVIDENCE = 'plans/agent_ops/evidence/'
PLAN = 'PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md'
PLAN_HASH = '20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996'

def git(*args, repo=ROOT):
    return subprocess.check_output(['rtk', 'proxy', 'git', '-C', str(repo), *args])

def sha(data):
    return hashlib.sha256(data).hexdigest()

def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()

tree = {}
for item in git('ls-tree', '-r', '-z', BASE).split(b'\0'):
    if item:
        meta, path = item.split(b'\t', 1)
        tree[path.decode()] = meta.split()[2].decode()

read_paths = {}
worktree_changes_during_read = []
def read(path):
    path = str(path).replace('\\', '/')
    local = ROOT / path
    data = local.read_bytes() if local.is_file() else b''
    if blob(data) != tree.get(path):
        worktree_changes_during_read.append(path)
        data = git('show', f'{BASE}:{path}')
    read_paths[path] = sha(data)
    return data

def load(path):
    return json.loads(read(path).decode('utf-8-sig'))

ledger = load('plans/agent_ops/ledger.json')
plan = read(PLAN)
assert sha(plan) == PLAN_HASH
counts = {k: len(ledger[k]) for k in ('tasks', 'scenarios', 'invariants', 'completion_criteria')}
assert counts == {'tasks': 59, 'scenarios': 132, 'invariants': 28, 'completion_criteria': 17}

refs = {}
def walk(value, pointer=''):
    if isinstance(value, dict):
        for k, v in value.items():
            walk(v, pointer + '/' + k)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            walk(v, pointer + '/' + str(i))
    elif isinstance(value, str):
        if '\n' not in value and len(value) < 500 and re.match(r'^(?:plans|docs|src|tests|tools|vendor)/[^ ]+$', value):
            refs.setdefault(value, []).append(pointer)
walk(ledger)
missing_refs = [p for p in refs if p.split('#')[0] not in tree and not any(t.startswith(p.rstrip('/') + '/') for t in tree)]

manifests = []
for p in sorted(tree):
    if not p.startswith(EVIDENCE) or Path(p).name not in ('artifact-manifest.json', 'manifest.json'):
        continue
    d = load(p)
    entries = d.get('files', d.get('artifacts', d.get('entries', d)))
    if p.endswith('/patch/manifest.json'):
        manifests.append({'path': p, 'kind': 'patch_lineage_not_artifact_allowlist', 'entries': len(entries)})
        continue
    if isinstance(entries, dict):
        entries = [{'path': k, **(v if isinstance(v, dict) else {'sha256': v})} for k, v in entries.items()]
    parsed, failures, outside = [], [], []
    for entry in entries:
        name = entry['path'].replace('\\', '/')
        target = name if name.startswith('plans/') else (Path(p).parent / name).as_posix()
        if '..' in Path(target).parts or not target.startswith(EVIDENCE):
            outside.append(name)
            continue
        expected = entry.get('sha256', entry.get('artifact_sha256'))
        if target not in tree:
            failures.append({'path': target, 'error': 'not_in_baseline_tree'})
            continue
        data = read(target)
        expected_bytes = entry.get('bytes', entry.get('size', entry.get('artifact_bytes')))
        if sha(data) != expected:
            failures.append({'path': target, 'error': 'hash_mismatch', 'expected': expected, 'observed': sha(data)})
        if expected_bytes is not None and len(data) != expected_bytes:
            failures.append({'path': target, 'error': 'size_mismatch', 'expected': expected_bytes, 'observed': len(data)})
        parsed.append(target)
    directory = Path(p).parent.as_posix() + '/'
    tracked_below = {t for t in tree if t.startswith(directory)}
    unlisted = sorted(tracked_below - set(parsed) - {p})
    manifests.append({'path': p, 'kind': 'artifact_allowlist', 'entries': len(entries), 'verified': len(parsed), 'failures': failures, 'outside_public_tree': outside, 'tracked_files_not_listed': unlisted})

integration = load(EVIDENCE + 'r3-joint-contracts/integration.json')
xml_cache, cases, case_errors = {}, [], []
for case, rel in integration['case_reports'].items():
    path = EVIDENCE + 'r3-joint-contracts/' + rel
    if path not in xml_cache:
        root = ET.fromstring(read(path))
        xml_cache[path] = {n.attrib.get('classname', '') + '::' + n.attrib.get('name', ''): n for n in root.iter('testcase')}
    node = xml_cache[path].get(case)
    passed = node is not None and not any(node.find(k) is not None for k in ('failure', 'error', 'skipped'))
    cases.append({'case': case, 'report': path, 'passed': passed})
    if not passed:
        case_errors.append(case)

pins = []
for entry in load('vendor/ci/manifest.json')['artifacts']:
    data = read(entry['path'])
    pins.append({**entry, 'observed_sha256': sha(data), 'matches': sha(data) == entry['sha256']})
repos = {}
for name, location, module, wheel in (
    ('connector', 'D:/Projetos/Techridy/okto-nexus-connector', 'okto_nexus_connector', 'vendor/ci/okto_nexus_connector-0.0.12-py3-none-any.whl'),
    ('core', 'D:/Projetos/Techridy/okto-nexus-connector-core', 'nexus_connector_core', 'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'),
):
    repo = Path(location)
    diffs, compared, requirements = [], 0, []
    with zipfile.ZipFile(ROOT / wheel) as z:
        for name_in_zip in z.namelist():
            if name_in_zip.endswith('.dist-info/METADATA'):
                requirements = [x.removeprefix('Requires-Dist: ') for x in z.read(name_in_zip).decode().splitlines() if x.startswith('Requires-Dist: ')]
            if name_in_zip.startswith(module + '/') and not name_in_zip.endswith('/'):
                source = repo / 'src' / name_in_zip
                compared += 1
                if not source.is_file() or source.read_bytes() != z.read(name_in_zip):
                    diffs.append(name_in_zip)
    repos[name] = {'head': git('rev-parse', 'HEAD', repo=repo).decode().strip(), 'status_porcelain': git('status', '--porcelain', repo=repo).decode().splitlines(), 'wheel': wheel, 'payload_files_compared': compared, 'source_payload_mismatches': diffs, 'requires_dist': requirements}

public_suspicious_extensions = [p for p in tree if p.startswith(EVIDENCE) and Path(p).suffix.lower() in {'.db', '.sqlite', '.sqlite3', '.wal', '.shm', '.pfx', '.p12', '.key'}]
result = {
    'baseline': {'nexus': git('rev-parse', BASE).decode().strip(), 'plan_sha256': sha(plan), 'fixed_id_counts': counts, 'repositories': repos},
    'method': 'Read-only tracked files and stored XML; no product imports, test execution, providers, credentials or service calls. Baseline git blob bytes used when worktree differs.',
    'ledger_references': {'unique_literal_local_references': len(refs), 'occurrences': sum(map(len, refs.values())), 'missing': missing_refs, 'references': refs},
    'artifact_manifests': manifests,
    'joint_case_validation': {'declared_unique_passed': integration['unique_passed_cases'], 'observed_unique_passed': sum(c['passed'] for c in cases), 'errors': case_errors, 'cases': cases},
    'pins': pins,
    'suspicious_public_file_extensions': public_suspicious_extensions,
    'worktree_files_read_from_baseline_instead': sorted(set(worktree_changes_during_read)),
    'inspected_public_file_hashes': read_paths,
}
(OUT / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'baseline': result['baseline'], 'refs_unique': len(refs), 'missing_refs': missing_refs, 'manifest_entries': sum(m.get('entries', 0) for m in manifests if m['kind'] == 'artifact_allowlist'), 'manifest_errors': [m for m in manifests if m.get('failures') or m.get('outside_public_tree')], 'manifest_unlisted': [{'path': m['path'], 'unlisted': m['tracked_files_not_listed']} for m in manifests if m.get('tracked_files_not_listed')], 'joint_passed': result['joint_case_validation']['observed_unique_passed'], 'joint_errors': case_errors, 'pins': pins, 'suspicious_public_extensions': public_suspicious_extensions, 'baseline_reads': result['worktree_files_read_from_baseline_instead']}, ensure_ascii=False, indent=2))
