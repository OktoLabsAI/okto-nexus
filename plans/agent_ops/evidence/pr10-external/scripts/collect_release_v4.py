"""Retain final PR10a evidence without replacing earlier candidate bytes."""
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus').resolve()
OUT = REPO / 'plans/agent_ops/evidence/pr10-external'
reports = json.loads((OUT / 'reports.json').read_text(encoding='utf-8'))
sha = lambda data: hashlib.sha256(data).hexdigest()


def retain(source, name):
    data, target = source.read_bytes(), OUT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == data, name
    else:
        target.write_bytes(data)
    path = target.relative_to(REPO).as_posix()
    row = dict(path=path, original_path=str(source), bytes=len(data), sha256=sha(data),
               original_sha256=sha(data), exact_original_bytes=True)
    old = next((r for r in reports['retained_inputs'] if r['path'] == path), None)
    if old:
        assert old['sha256'] == row['sha256']
    else:
        reports['retained_inputs'].append(row)
    return path


# Preserve the previous root's V3-only scope rather than relabeling its bytes.
old_scope = OUT / 'final/release-scope.json'
v3_scope = OUT / 'candidate-v3/release-scope.json'
if old_scope.exists():
    prior = json.loads(old_scope.read_text(encoding='utf-8'))
    if len(prior.get('candidate_wheels', [])) == 3:
        assert old_scope.resolve().is_relative_to(REPO) and v3_scope.resolve().is_relative_to(REPO)
        assert not v3_scope.exists()
        old_scope.rename(v3_scope)

proofs = [json.loads((ROOT / name / 'package-proof.json').read_text(encoding='utf-8'))
          for name in ('qualified', 'qualified-v2', 'qualified-v3', 'qualified-v4')]
assert proofs[-1]['wheel_sha256'] == '280c0e0cca2b02ae0fa69443ed44889609988f4432af928d839013c2618bf035'
changes = []
for before, after in zip(proofs, proofs[1:]):
    assert set(before['files']) == set(after['files'])
    changes.append([name for name in before['files'] if before['files'][name] != after['files'][name]])
assert set(changes[0]) == {'application/attention_external.py', 'application/observations.py',
    'adapters/outbound/sqlite/attention.py', 'adapters/outbound/sqlite/attention_external.py'}
assert changes[1] == changes[2] == ['adapters/outbound/sqlite/attention.py']
for proof in proofs:
    assert proof['counts'] == dict(python=497, migrations=165, static=7, total=672)
    assert proof['all_raw_bytes_equal'] and proof['exact_relative_sets_equal']
    assert sha(Path(proof['wheel']).read_bytes()) == proof['wheel_sha256']
    assert proof['core_wheel_sha256'] == proofs[0]['core_wheel_sha256']
    assert proof['pyproject_sha256'] == proofs[0]['pyproject_sha256']
for name, values in proofs[-1]['files'].items():
    assert sha((REPO / 'src/okto_nexus' / name).read_bytes()) == values['source_sha256']
    assert sha((Path(proofs[-1]['installed_package']) / name).read_bytes()) == values['installed_sha256']
retain(ROOT / 'qualified-v4/package-proof.json', 'final/package-proof.json')
for name in ('build_release_v4.py', 'qualify_installed_v4.py', 'collect_release_v4.py'):
    retain(ROOT / name, 'scripts/' + name)
scope = dict(candidate_wheels=[p['wheel_sha256'] for p in proofs], counts=proofs[-1]['counts'],
    production_changes_by_candidate=changes, unchanged_static_assets=7, unchanged_migrations=165,
    current_source_and_final_installed_bytes_verified=True,
    browser_scope='V1 real-browser campaign; frontend assets unchanged through V4. Changed backend contracts are separately requalified.',
    retired_memo_scope='V3 was measured but never functionally tested installed. Its memo and nine private tests were removed; original sources/reports retained as historical evidence.',
    correlation_scope='Pure domain only; no OBS12 wiring/precedence acceptance.')
(OUT / 'final/release-scope.json').write_text(json.dumps(scope, indent=2), encoding='utf-8')

if sys.argv[1] == 'closed-reports':
    for version, destination in [('qualified-v2', 'candidate-v2'), ('qualified-v4', 'final')]:
        xml = ROOT / version / 'pr10-external-installed-final.xml'
        cases = list(ET.parse(xml).getroot().iter('testcase'))
        assert cases and not any(c.find(tag) is not None for c in cases for tag in ('failure', 'error', 'skipped'))
        proof = json.loads((ROOT / version / 'installed-qualification.json').read_text(encoding='utf-8'))
        assert proof['exit_code'] == 0 and proof['xml_sha256'] == sha(xml.read_bytes())
        path = retain(xml, destination + '/installed.xml')
        retain(ROOT / version / 'installed-qualification.json', destination + '/installed-qualification.json')
        rid = 'installed_' + destination
        assert not any(r['id'] == rid for r in reports['reports'])
        reports['reports'].append(dict(id=rid, path=path, sha256=sha(xml.read_bytes()), tests=len(cases),
            passed=len(cases), failures=0, errors=0, skipped=0))
        if destination == 'final':
            assert len([c for c in cases if c.get('classname', '').endswith('test_attention_snapshot_query')]) == 12
            required = ['test_attention_api', 'test_attention_stream', 'test_attention_native', 'test_attention_operations',
                        'test_attention_results', 'test_attention_approvals', 'test_attention_authority']
            assert all(any(c.get('classname', '').endswith(name) for c in cases) for name in required)
            final_count = len(cases)
    identities = set()
    for row in reports['reports']:
        if row['id'].startswith('installed'):
            for case in ET.parse(REPO / row['path']).getroot().iter('testcase'):
                identities.add((case.get('classname', '').removeprefix('tests.'), case.get('name')))
    reports['overlap_policy'].update(installed_distinct_cases_all_candidates=len(identities),
        installed_final_candidate_cases=final_count, installed_v2_candidate_cases=110,
        installed_v3_cases=0, installed_reruns_not_summed=True)
    bench = Path('C:/Users/jpamb/AppData/Local/Temp/pr10a-benchmark-62d6a4cfee/benchmark-readonly-single-query.json')
    data = json.loads(bench.read_text(encoding='utf-8'))
    assert data['stages'][0]['instances'] == 4096
    reads = data['stages'][0]['reads']
    assert all(value['successful_samples'] == 4 for value in reads.values())
    retain(bench, 'benchmark/' + bench.name)
    reports['final_benchmark'] = {key: dict(median_ms=value['median_ms'], maximum_ms=value['maximum_ms'],
        successful_samples=value['successful_samples']) for key, value in reads.items()}
    reports['collection_phase'] = 'closed_qualified_milestone'
    reports['acceptance_claim'] = 'OBS11 Windows installed, synthetic peers and UI. OBS12 wiring, real providers/clients/native service and full R3 remain open.'
    reports['final_package'] = dict(wheel_sha256=proofs[-1]['wheel_sha256'], counts=proofs[-1]['counts'],
        package_proof='plans/agent_ops/evidence/pr10-external/final/package-proof.json',
        release_scope='plans/agent_ops/evidence/pr10-external/final/release-scope.json')

for row in reports['retained_inputs']:
    assert sha((REPO / row['path']).read_bytes()) == row['sha256'], row['path']
(OUT / 'reports.json').write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps(dict(phase=sys.argv[1], retained_inputs=len(reports['retained_inputs']),
    final_wheel=proofs[-1]['wheel_sha256'])))
