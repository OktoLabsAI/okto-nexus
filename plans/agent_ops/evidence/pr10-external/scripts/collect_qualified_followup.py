"""Retain original V4 failure and its focused correction without merging XMLs."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = REPO / 'plans/agent_ops/evidence/pr10-external'
reports = json.loads((OUT / 'reports.json').read_text(encoding='utf-8'))
assert reports['collection_phase'] == 'partial_closed_reports_and_package_evidence'
sha = lambda value: hashlib.sha256(value).hexdigest()
identity = lambda case: (case.get('classname', '').removeprefix('tests.'), case.get('name'))
failed_identity = ('test_attention_authority', 'test_migration_161_to_162_backfills_metadata_only_and_never_changes_161')


def retain(source, relative):
    data, target = source.read_bytes(), OUT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == data, relative
    else:
        target.write_bytes(data)
    path = target.relative_to(REPO).as_posix()
    if not any(row['path'] == path for row in reports['retained_inputs']):
        reports['retained_inputs'].append(dict(path=path, original_path=str(source), bytes=len(data),
            sha256=sha(data), original_sha256=sha(data), exact_original_bytes=True))
    return path


def report(source, relative, rid):
    path = retain(source, relative)
    cases = list(ET.parse(source).getroot().iter('testcase'))
    counts = {tag: sum(case.find(tag) is not None for case in cases) for tag in ('failure', 'error', 'skipped')}
    assert cases and not counts['error'] and not counts['skipped']
    assert not any(row['id'] == rid for row in reports['reports'])
    reports['reports'].append(dict(id=rid, path=path, sha256=sha(source.read_bytes()), tests=len(cases),
        passed=len(cases)-counts['failure'], failures=counts['failure'], errors=0, skipped=0))
    return cases


proof = json.loads((ROOT / 'qualified-v4/package-proof.json').read_text(encoding='utf-8'))
assert proof['wheel_sha256'] == '280c0e0cca2b02ae0fa69443ed44889609988f4432af928d839013c2618bf035'
for name, values in proof['files'].items():
    assert sha((REPO / 'src/okto_nexus' / name).read_bytes()) == values['source_sha256']
    assert sha((Path(proof['installed_package']) / name).read_bytes()) == values['installed_sha256']

v2 = report(ROOT / 'qualified-v2/pr10-external-installed-final.xml', 'candidate-v2/installed.xml', 'installed_candidate-v2')
assert len(v2) == 110 and not any(case.find('failure') is not None for case in v2)
v2_proof = json.loads((ROOT / 'qualified-v2/installed-qualification.json').read_text(encoding='utf-8'))
assert v2_proof['exit_code'] == 0 and v2_proof['xml_sha256'] == sha((ROOT / 'qualified-v2/pr10-external-installed-final.xml').read_bytes())
retain(ROOT / 'qualified-v2/installed-qualification.json', 'candidate-v2/installed-qualification.json')

initial = report(ROOT / 'qualified-v4/pr10-external-installed-final.xml', 'final/initial/installed.xml', 'installed_final_initial')
initial_proof = json.loads((ROOT / 'qualified-v4/installed-qualification.json').read_text(encoding='utf-8'))
assert len(initial) == 292 and initial_proof['exit_code'] == 1
assert initial_proof['xml_sha256'] == sha((ROOT / 'qualified-v4/pr10-external-installed-final.xml').read_bytes())
assert [identity(c) for c in initial if c.find('failure') is not None] == [failed_identity]
retain(ROOT / 'qualified-v4/installed-qualification.json', 'final/initial/installed-qualification.json')
retain(ROOT / 'qualified-v4/tests/test_attention_authority.py', 'final/initial/test_attention_authority.py.txt')

followup = report(ROOT / 'qualified-v4-followup/pr10-external-installed-final.xml', 'final/followup/installed.xml', 'installed_final_followup')
followup_proof = json.loads((ROOT / 'qualified-v4-followup/installed-qualification.json').read_text(encoding='utf-8'))
assert [identity(c) for c in followup] == [failed_identity] and followup[0].find('failure') is None
assert followup_proof['exit_code'] == 0 and followup_proof['xml_sha256'] == sha((ROOT / 'qualified-v4-followup/pr10-external-installed-final.xml').read_bytes())
assert set(initial_proof['test_files']) == set(followup_proof['test_files'])
assert [name for name in initial_proof['test_files'] if initial_proof['test_files'][name]['sha256'] !=
        followup_proof['test_files'][name]['sha256']] == ['test_attention_authority.py']
retain(ROOT / 'qualified-v4-followup/installed-qualification.json', 'final/followup/installed-qualification.json')
retain(ROOT / 'qualified-v4-followup/tests/test_attention_authority.py', 'final/followup/test_attention_authority.py.txt')
for name in ('qualify_installed_v4_followup.py', 'collect_qualified_followup.py'):
    retain(ROOT / name, 'scripts/' + name)
source = report(ROOT / 'authority-migration-source.xml', 'source-authority-migration.xml', 'authority_migration_final')
assert [identity(c) for c in source] == [failed_identity] and source[0].find('failure') is None
source_ids = set()
for row in reports['reports']:
    if row['id'] in reports['overlap_policy']['source_final_selection']:
        source_ids.update(identity(c) for c in ET.parse(REPO / row['path']).getroot().iter('testcase') if c.find('failure') is None)
assert len(source_ids) == 340 and failed_identity not in source_ids
reports['overlap_policy']['source_final_selection'].append('authority_migration_final')
reports['overlap_policy']['source_successful_unique_cases'] = 341
reports['overlap_policy']['source_historical_successful_unique_cases'] = 350
reports['overlap_policy']['source_case_breakdown']['portable_authority_upgrade'] = 1

passing = {identity(c) for c in initial if c.find('failure') is None} | {identity(c) for c in followup}
assert len(passing) == 292 and passing == {identity(c) for c in initial}
assert sum(c.get('classname', '').endswith('test_attention_snapshot_query') for c in initial) == 12
for module in ('test_attention_api', 'test_attention_stream', 'test_attention_native', 'test_attention_operations',
               'test_attention_results', 'test_attention_approvals', 'test_attention_authority'):
    assert any(c.get('classname', '').endswith(module) for c in initial)
installed_ids = set()
for row in reports['reports']:
    if row['id'].startswith('installed'):
        installed_ids.update(identity(c) for c in ET.parse(REPO / row['path']).getroot().iter('testcase') if c.find('failure') is None)
reports['overlap_policy'].update(installed_distinct_cases_all_candidates=len(installed_ids),
    installed_final_candidate_cases=292, installed_v2_candidate_cases=110, installed_v3_cases=0,
    installed_final_initial_passed=291, installed_final_initial_failed=1, installed_final_corrected_passed=1,
    installed_final_qualification='291 passing cases in the broad run plus the corrected migration case; original XMLs are separate, never synthesized into one green run.',
    installed_reruns_not_summed=True)
reports['diagnostics'].append(dict(kind='installed_authority_upgrade_test_checkout_dependency',
    reports=['installed_final_initial', 'installed_final_followup', 'authority_migration_final'],
    factual_xml='The broad V4 run passed 291 cases and failed one with FileNotFoundError for checkout-relative migration SQL.',
    correction='The test now reads importlib.resources from the imported package and expects migrations 162,163,164,165. Its backfill, privacy and immutable-161 assertions are preserved. The focused source and installed runs each pass one case.',
    scope='No production, wheel, frontend or migration bytes changed. All original failure XML, proof and copied test bytes are retained.'))
bench = ROOT.parent / 'pr10a-benchmark-62d6a4cfee/benchmark-readonly-single-query.json'
data = json.loads(bench.read_text(encoding='utf-8'))
assert data['stages'][0]['instances'] == 4096
reads = data['stages'][0]['reads']
assert all(row['successful_samples'] == 4 for row in reads.values())
retain(bench, 'benchmark/' + bench.name)
reports['final_benchmark'] = {key: dict(median_ms=row['median_ms'], maximum_ms=row['maximum_ms'],
    successful_samples=row['successful_samples']) for key, row in reads.items()}
reports['collection_phase'] = 'closed_qualified_milestone'
reports['acceptance_claim'] = 'OBS11 Windows installed, synthetic peers and UI. OBS12 wiring, real providers/clients/native service and full R3 remain open.'
reports['final_package'] = dict(wheel_sha256=proof['wheel_sha256'], counts=proof['counts'],
    package_proof='plans/agent_ops/evidence/pr10-external/final/package-proof.json',
    release_scope='plans/agent_ops/evidence/pr10-external/final/release-scope.json')
for row in reports['retained_inputs']:
    assert sha((REPO / row['path']).read_bytes()) == row['sha256'], row['path']
(OUT / 'reports.json').write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps(dict(source=341, installed_final_unique=len(passing), installed_union=len(installed_ids),
    retained_inputs=len(reports['retained_inputs']), original_failure_retained=True)))
