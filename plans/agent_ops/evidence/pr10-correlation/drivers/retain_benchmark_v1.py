"""Preserve the first installed measurement, including its four budget refusals."""
import hashlib
import json
from pathlib import Path
import re

REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = REPO / 'plans/agent_ops/evidence/pr10-correlation'
SOURCE = Path('C:/Users/jpamb/AppData/Local/Temp/pr10b-installed-benchmark-v3-fr9dtadn')
sha = lambda data: hashlib.sha256(data).hexdigest()
manifest = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8'))
assert manifest['samples_total'] == 90 and manifest['samples_successful'] == 86 and manifest['budget_refusals'] == 4
report_path = OUT / 'reports.json'
reports = json.loads(report_path.read_text(encoding='utf-8'))
assert reports['collection_phase'] == 'partial_closed_reports'
rows = dict(manifest['files'])
rows['manifest.json'] = dict(sha256=sha((SOURCE / 'manifest.json').read_bytes()))
for name, item in rows.items():
    source = (SOURCE / name).resolve()
    assert source.is_relative_to(SOURCE) and source.is_file()
    assert 'private' not in source.name.lower() and source.suffix not in ('.db', '.whl', '.key')
    data = source.read_bytes()
    assert sha(data) == item['sha256']
    assert not re.search(rb'nxobs_[0-9a-f]{64}|nxs_[0-9a-f]{48}', data)
    target = OUT / 'benchmark/candidate-v1' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == data
    else:
        target.write_bytes(data)
    relative = target.relative_to(REPO).as_posix()
    if not any(row['path'] == relative for row in reports['retained_inputs']):
        reports['retained_inputs'].append(dict(path=relative, original_path=str(source), bytes=len(data),
            sha256=sha(data), original_sha256=sha(data), exact_original_bytes=True, credential_pattern_matches=0))
reports['benchmark_candidate_v1'] = dict(report='plans/agent_ops/evidence/pr10-correlation/benchmark/candidate-v1/benchmark-installed.json',
    samples=90, passed=86, attention_budget_refusals=4, repeated_samples=0,
    scope='1/64 native sessions, 64/512/4096 correlated observations, half blocked/half working, 3 samples/read.',
    followup='Reduce attention correlation preload to the exact relevant current head keys, preserving the five-second deadline.')
report_path.write_text(json.dumps(reports, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(retained_files=len(rows), samples=90, passed=86, budget_refusals=4)))
