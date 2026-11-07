"""Close the measured PR10b evidence without rewriting either candidate history."""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = REPO / 'plans/agent_ops/evidence/pr10-correlation'
BENCH = BASE.parent / 'pr10b-installed-benchmark-v4-s7u3zpr_'
sha = lambda data: hashlib.sha256(data).hexdigest()
read = lambda path: json.loads(path.read_text(encoding='utf-8'))
reports = read(OUT / 'reports.json')
assert reports['collection_phase'] == 'partial_closed_reports'
assert reports['candidate_v2']['installed_followup_closed']


def retain(source, relative):
    assert source.is_file()
    assert 'private' not in source.name.lower()
    assert source.suffix.lower() not in ('.db', '.sqlite', '.sqlite3', '.key', '.whl', '.pyc')
    assert not source.name.endswith(('-wal', '-shm'))
    data = source.read_bytes()
    assert not re.search(rb'nxobs_[0-9a-f]{64}|nxs_[0-9a-f]{48}', data)
    target = OUT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == data, relative
    else:
        target.write_bytes(data)
    path = target.relative_to(REPO).as_posix()
    if not any(row['path'] == path for row in reports['retained_inputs']):
        reports['retained_inputs'].append(dict(path=path, original_path=str(source),
            bytes=len(data), sha256=sha(data), original_sha256=sha(data),
            exact_original_bytes=True, credential_pattern_matches=0))


proof = read(OUT / 'candidate-v2/package-proof.json')
for name, row in proof['files'].items():
    assert sha((REPO / 'src/okto_nexus' / name).read_bytes()) == row['source_sha256'], name
    assert sha((Path(proof['installed_package']) / name).read_bytes()) == row['installed_sha256'], name


def cases(relative):
    root = ET.parse(OUT / relative).getroot()
    rows = list(root.iter('testcase'))
    assert all(all(c.find(tag) is None for tag in ('failure', 'error', 'skipped')) for c in rows)
    ids = {(c.get('classname', '').removeprefix('tests.'), c.get('name')) for c in rows}
    assert len(ids) == len(rows)
    return ids


v1_groups = {name: cases('installed/' + name + '/installed.xml')
    for name in ('correlation', 'regression', 'diagnostics')}
assert {name: len(ids) for name, ids in v1_groups.items()} == dict(correlation=458, regression=203, diagnostics=75)
v1 = set.union(*v1_groups.values())
v2 = cases('candidate-v2/installed.xml')
assert len(v1) == 736 and len(v2) == 237
assert len(v1 | v2) == 756 and len(v1 & v2) == 217 and len(v1 - v2) == 519
qualification = read(OUT / 'candidate-v2/qualification.json')
assert qualification['exit_code'] == 0
assert qualification['xml_sha256'] == sha((OUT / 'candidate-v2/installed.xml').read_bytes())
assert len(cases('frontend/final.xml')) == 130
ruff = read(BASE / 'changed-python-ruff-final.json')
assert ruff['exit_code'] == 0 and len(ruff['paths']) == 40

manifest = read(BENCH / 'manifest.json')
assert manifest['wheel_sha256'] == proof['wheel_sha256']
assert manifest['samples_total'] == 90
assert manifest['samples_successful'] + manifest['budget_refusals'] == 90
assert manifest['measurement_driver_exact_bytes_equal_v3']
rows = dict(manifest['files'])
rows['manifest.json'] = dict(sha256=sha((BENCH / 'manifest.json').read_bytes()))
for name, row in rows.items():
    source = (BENCH / name).resolve()
    assert source.is_relative_to(BENCH) and source.is_file()
    assert sha(source.read_bytes()) == row['sha256'], name
    retain(source, 'benchmark/candidate-v2/' + name)
assert (OUT / 'benchmark/candidate-v1/benchmark_installed.py').read_bytes() == (OUT / 'benchmark/candidate-v2/benchmark_installed.py').read_bytes()

retain(BASE / 'changed-python-ruff-final.json', 'checks/changed-python-ruff-final.json')
for name in ('collect_evidence.py', 'collect_followup.py', 'retain_browser.py',
             'retain_benchmark_v1.py', 'check_changed_python_final.py',
             'finalize_collection.py', 'verify_artifacts.py',
             'close_ledger.py', 'close_evidence_doc.py', 'stage_milestone.py'):
    retain(BASE / name, 'drivers/' + name)

reports['initial_wheel_sha256'] = reports['wheel_sha256']
reports['wheel_sha256'] = proof['wheel_sha256']
reports['final_candidate'] = 'candidate-v2'
reports['installed_qualification'] = dict(
    candidate_v1=dict(distinct_passes=len(v1), suites={name: len(ids) for name, ids in v1_groups.items()}),
    candidate_v2=dict(distinct_passes=len(v2), repeated_v1_identities=len(v1 & v2), new_identities=len(v2 - v1)),
    qualified_union=len(v1 | v2), unchanged_v1_cases_not_repeated=len(v1 - v2),
    interpretation='756 distinct identities across candidates, not 756 executions on V2. V2 requalifies both changed attention modules; 679 package files and Core are byte-identical. Source and frontend suites are separate, not additive.')
reports['browser']['candidate'] = 'candidate-v1'
reports['browser']['candidate_v2_applicability'] = 'All seven static assets and HTTP/projection payloads are byte-identical; affected attention SQL is separately covered by 237 V2 installed cases. No second browser campaign is claimed.'
reports['benchmark_candidate_v2'] = dict(
    report='plans/agent_ops/evidence/pr10-correlation/benchmark/candidate-v2/benchmark-installed.json',
    samples=manifest['samples_total'], passed=manifest['samples_successful'],
    attention_budget_refusals=manifest['budget_refusals'], repeated_samples=0,
    same_driver_bytes_as_v1=True,
    scope='1/64 native sessions, 64/512/4096 correlated observations, half blocked/half working, 3 samples/read. A separate frozen follow-up campaign, not retries of the V1 samples or a general SLO.')
reports['candidate_v2']['measurement_followup'] = 'closed'
reports['limits'] = [line for line in reports['limits'] if 'must close before' not in line]
reports['limits'].append('V1 and V2 measurements remain separate. Any measured budget refusal is retained; the admission deadline is unchanged and no all-workload latency claim is made.')
reports['collection_phase'] = 'closed_qualified_milestone'
(OUT / 'reports.json').write_text(json.dumps(reports, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(artifacts=len(reports['retained_inputs']), installed_distinct_union=len(v1 | v2),
    candidate_v2_passes=len(v2), measured_successes=manifest['samples_successful'],
    measured_budget_refusals=manifest['budget_refusals'], final_wheel=proof['wheel_sha256']), indent=2))
