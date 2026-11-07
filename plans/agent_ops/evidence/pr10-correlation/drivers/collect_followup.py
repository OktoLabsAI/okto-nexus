"""Retain the measured-policy follow-up separately from the original candidate."""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = REPO / 'plans/agent_ops/evidence/pr10-correlation'
meta_path = OUT / 'reports.json'
meta = json.loads(meta_path.read_text(encoding='utf-8'))
assert meta['collection_phase'] == 'partial_closed_reports'
sha = lambda data: hashlib.sha256(data).hexdigest()


def retain(source, relative):
    assert source.is_file() and 'private' not in source.name.lower()
    assert source.suffix.lower() not in ('.db', '.whl', '.key')
    data = source.read_bytes()
    assert not re.search(rb'nxobs_[0-9a-f]{64}|nxs_[0-9a-f]{48}', data), source.name
    target = OUT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == data, relative
    else:
        target.write_bytes(data)
    path = target.relative_to(REPO).as_posix()
    if not any(row['path'] == path for row in meta['retained_inputs']):
        meta['retained_inputs'].append(dict(path=path, original_path=str(source), bytes=len(data),
            sha256=sha(data), original_sha256=sha(data), exact_original_bytes=True, credential_pattern_matches=0))
    return path


def report(source, relative, scope):
    path = retain(source, relative)
    cases = list(ET.parse(source).getroot().iter('testcase'))
    counts = {tag: sum(len(case.findall(tag)) for case in cases) for tag in ('failure', 'error', 'skipped')}
    if not any(row['path'] == path for row in meta['reports']):
        meta['reports'].append(dict(path=path, scope=scope, cases=len(cases),
            unique_identities=len({(c.get('classname', '').removeprefix('tests.'), c.get('name')) for c in cases}),
            passed=sum(not any(c.find(t) is not None for t in ('failure', 'error', 'skipped')) for c in cases),
            **counts, sha256=sha(source.read_bytes())))


candidate = ROOT / 'candidate-v2'
proof = json.loads((candidate / 'package-proof.json').read_text(encoding='utf-8'))
delta = json.loads((candidate / 'package-delta.json').read_text(encoding='utf-8'))
assert len(delta['changed_package_paths']) == 2 and delta['unchanged_package_files'] == 679
for name, row in proof['files'].items():
    assert sha((REPO / 'src/okto_nexus' / name).read_bytes()) == row['source_sha256'], name
    assert sha((Path(proof['installed_package']) / name).read_bytes()) == row['installed_sha256'], name
for name in ('package-proof.json', 'package-delta.json', 'wheel-build.log', 'venv-create.log', 'wheel-install.log'):
    retain(candidate / name, 'candidate-v2/' + name)
for name in ('prepare_v2.py', 'build_release_v2.py', 'qualify_installed_v2.py'):
    retain(ROOT / name, 'drivers/' + name)
for suffix in ('initial', 'retest'):
    name = 'pr10b-attention-correlation-policy-' + suffix + '.xml'
    report(ROOT.parent / name, 'followup/source/' + name, 'source_attention_followup_' + suffix)
retain(ROOT.parent / 'pr10b-attention-policy-review-ibgwl18f/review.json', 'followup/review.json')
closed = candidate / 'tests-attention-followup/installed-qualification.json'
if closed.exists():
    qualification = json.loads(closed.read_text(encoding='utf-8'))
    xml = closed.parent / 'installed.xml'
    assert qualification['xml_sha256'] == sha(xml.read_bytes())
    report(xml, 'candidate-v2/installed.xml', 'installed_attention_followup_v2')
    retain(closed, 'candidate-v2/qualification.json')
meta['candidate_v2'] = dict(wheel_sha256=proof['wheel_sha256'], package_delta=delta,
    installed_followup_closed=closed.exists(), measurement_followup='pending')
meta_path.write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(artifacts=len(meta['retained_inputs']), reports=len(meta['reports']),
    installed_followup_closed=closed.exists(), final_wheel=proof['wheel_sha256']), indent=2))
