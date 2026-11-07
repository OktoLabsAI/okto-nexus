"""Collect closed PR10a candidates and verify their exact release scope."""
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = REPO / 'plans/agent_ops/evidence/pr10-external'
REPORTS = OUT / 'reports.json'
report = json.loads(REPORTS.read_text(encoding='utf-8'))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def copy(source, relative):
    data = source.read_bytes()
    target = OUT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == data, f'Refusing to replace different evidence: {relative}'
    else:
        target.write_bytes(data)
    path = target.relative_to(REPO).as_posix()
    entry = dict(path=path, original_path=str(source), bytes=len(data), sha256=digest(data),
                 original_sha256=digest(data), exact_original_bytes=True)
    existing = next((row for row in report['retained_inputs'] if row['path'] == path), None)
    if existing:
        assert existing['sha256'] == entry['sha256']
    else:
        report['retained_inputs'].append(entry)
    return path


def read_proof(directory):
    return json.loads((ROOT / directory / 'package-proof.json').read_text(encoding='utf-8'))


proofs = [read_proof(name) for name in ('qualified', 'qualified-v2', 'qualified-v3')]
expected = [
    '48eee2b5136f40ed3f37e4df73896d8d4d91bbc064d2cf918d2dfa85c461292d',
    'ed6223c0de0d333e7fd108175d1f15dd0a4e72c8e489782ac9869e0284f9a245',
    'a5d040eb7bce0deffdbf24f3506000eb5e493e9f36d8cf2116b7057e57746d7c',
]
for proof, sha in zip(proofs, expected):
    assert proof['wheel_sha256'] == sha
    assert proof['counts'] == dict(python=497, migrations=165, static=7, total=672)
    assert proof['source_unchanged_during_build'] and proof['all_raw_bytes_equal']
    assert proof['exact_relative_sets_equal'] and digest(Path(proof['wheel']).read_bytes()) == sha
    assert proof['core_wheel_sha256'] == proofs[0]['core_wheel_sha256']
    assert proof['pyproject_sha256'] == proofs[0]['pyproject_sha256']
    assert set(proof['files']) == set(proofs[0]['files'])
changed12 = [name for name in proofs[0]['files'] if proofs[0]['files'][name] != proofs[1]['files'][name]]
changed23 = [name for name in proofs[1]['files'] if proofs[1]['files'][name] != proofs[2]['files'][name]]
assert set(changed12) == {'application/attention_external.py', 'application/observations.py',
    'adapters/outbound/sqlite/attention.py', 'adapters/outbound/sqlite/attention_external.py'}
assert changed23 == ['adapters/outbound/sqlite/attention.py']
for name, hashes in proofs[2]['files'].items():
    assert digest((REPO / 'src/okto_nexus' / name).read_bytes()) == hashes['source_sha256']
    assert digest((Path(proofs[2]['installed_package']) / name).read_bytes()) == hashes['installed_sha256']
copy(ROOT / 'qualified-v3/package-proof.json', 'final/package-proof.json')
for name in ('build_release_v3.py', 'qualify_installed_v3.py', 'collect_final.py'):
    copy(ROOT / name, 'scripts/' + name)
scope = dict(candidate_wheels=expected, counts=proofs[2]['counts'], changed_v1_to_v2=changed12,
    changed_v2_to_v3=changed23, unchanged_static_assets=7, migrations_unchanged_between_candidates=True,
    current_source_and_final_installed_bytes_verified=True,
    browser_scope='Real browser campaign used V1; all frontend assets unchanged through V3. Four backend files changed and affected contracts are separately requalified.',
    pure_correlation_scope='Domain only; unchanged since V1 and not OBS12 acceptance.')
(OUT / 'final/release-scope.json').write_text(json.dumps(scope, indent=2), encoding='utf-8')

if sys.argv[1] == 'closed-reports':
    for directory, expected_count, name in [('qualified-v2', 110, 'candidate-v2'), ('qualified-v3', 71, 'final')]:
        xml = ROOT / directory / 'pr10-external-installed-final.xml'
        tree = ET.parse(xml).getroot()
        cases = list(tree.iter('testcase'))
        assert len(cases) == expected_count
        assert not any(list(case.iter('failure')) + list(case.iter('error')) + list(case.iter('skipped')) for case in cases)
        qualification = json.loads((ROOT / directory / 'installed-qualification.json').read_text(encoding='utf-8'))
        assert qualification['exit_code'] == 0 and qualification['xml_sha256'] == digest(xml.read_bytes())
        path = copy(xml, name + '/installed.xml')
        copy(ROOT / directory / 'installed-qualification.json', name + '/installed-qualification.json')
        report_id = 'installed_' + name
        assert not any(row['id'] == report_id for row in report['reports'])
        report['reports'].append(dict(id=report_id, path=path, sha256=digest(xml.read_bytes()),
            tests=len(cases), passed=len(cases), failures=0, errors=0, skipped=0))
    installed = [row for row in report['reports'] if row['id'].startswith('installed')]
    identities = set()
    for row in installed:
        for case in ET.parse(REPO / row['path']).getroot().iter('testcase'):
            identities.add((case.get('classname', '').removeprefix('tests.'), case.get('name')))
    assert len(identities) == 210, len(identities)
    report['overlap_policy'].update(installed_distinct_cases_all_candidates=210,
        installed_final_candidate_cases=71, installed_v2_candidate_cases=110,
        installed_reruns_not_summed=True, installed_candidate_scope='Final release scope proves unchanged files and identifies affected reruns; 210 is the union across three candidates, not 210 tests rerun on V3.')
    bench = Path('C:/Users/jpamb/AppData/Local/Temp/pr10a-benchmark-62d6a4cfee/benchmark-readonly-memo.json')
    measurements = json.loads(bench.read_text(encoding='utf-8'))
    reads = measurements['stages'][0]['reads']
    assert measurements['stages'][0]['instances'] == 4096
    assert all(value['successful_samples'] == 4 for value in reads.values())
    copy(bench, 'benchmark/benchmark-readonly-memo.json')
    report['final_benchmark'] = {key: dict(median_ms=value['median_ms'], maximum_ms=value['maximum_ms'],
        successful_samples=value['successful_samples']) for key, value in reads.items()}
    report['collection_phase'] = 'closed_qualified_milestone'
    report['acceptance_claim'] = 'OBS11 Windows installed/synthetic-peer/UI scope only. OBS12 wiring, real providers/clients/native service and full R3 remain open.'
    report['final_package'] = dict(wheel_sha256=expected[2], package_proof='plans/agent_ops/evidence/pr10-external/final/package-proof.json',
        release_scope='plans/agent_ops/evidence/pr10-external/final/release-scope.json', counts=proofs[2]['counts'])

for entry in report['retained_inputs']:
    assert digest((REPO / entry['path']).read_bytes()) == entry['sha256'], entry['path']
REPORTS.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps(dict(phase=sys.argv[1], retained_inputs=len(report['retained_inputs']), final_wheel=expected[2])))
