"""Export public QA facts only; raw homes/logs/SQLite/credentials stay Temp."""
from pathlib import Path
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
root = Path(json.loads((HERE/'allocation.json').read_text())['root'])
result = json.loads((root/'result.json').read_text())
assert result['mode'] == 'SOURCE_ONLY_NOT_NEW_INSTALLED_PACKAGE'
out = HERE/'final'
out.mkdir(exist_ok=False)
records = []
raw_refs = []
for case in result['cases']:
    folder = root/case['label']
    target = out/case['label']
    target.mkdir()
    for name in ('runner.json', 'origins-start.json', 'origins-finish.json'):
        shutil.copyfile(folder/name, target/name)
    xml = folder/'junit.xml'
    raw_refs.append(dict(path=str(xml), sha256=hashlib.sha256(xml.read_bytes()).hexdigest(), exported=False))
    document = ET.parse(xml)
    for parent in document.iter():
        for child in list(parent):
            if child.tag in ('system-out', 'system-err'):
                parent.remove(child)
    for test in document.iter('testcase'):
        records.append(dict(cut=case['label'], name=test.get('name'), classname=test.get('classname'),
            seconds=test.get('time'), status='FAIL' if test.find('failure') is not None or test.find('error') is not None
            else 'SKIP' if test.find('skipped') is not None else 'PASS'))
    document.write(target/'junit-sanitized.xml', encoding='utf-8', xml_declaration=True)
    log = folder/'raw.log'
    raw_refs.append(dict(path=str(log), sha256=hashlib.sha256(log.read_bytes()).hexdigest(), exported=False))
for name in ('source-pins-start.json', 'source-pins-end.json', 'payload-start.json', 'payload-end.json'):
    shutil.copyfile(root/name, out/name)
qualification = dict(status='PASS' if all(c['exit_code'] == 0 for c in result['cases'])
    and all(r['status'] == 'PASS' for r in records) and not result['payload_drift']
    and not result['repository_input_drift'] else 'NOT_GREEN',
    mode=result['mode'], nodes=records, passed=sum(r['status']=='PASS' for r in records),
    failed=sum(r['status']=='FAIL' for r in records), skipped=sum(r['status']=='SKIP' for r in records),
    cases=[dict(label=c['label'], argv=c['argv'], cwd=c['cwd'], deadline_seconds=c['deadline_seconds'],
        exit_code=c['exit_code'], processes_after=c['processes_after'], signals=c['signals'],
        rejected_nonowned_births=c['rejected_nonowned_births']) for c in result['cases']],
    payload_files=result['payload_files'], payload_drift=result['payload_drift'],
    repository_input_drift=result['repository_input_drift'], raw_refs=raw_refs,
    cleanup=dict(all_owned_processes_exited=all(not p['alive'] for c in result['cases'] for p in c['processes_after']),
                 signals=[s for c in result['cases'] for s in c['signals']], data_preserved_in_owned_temp=True),
    limits=['Nexus imports are repository src, not the PR27 installed Nexus or a new candidate wheel.',
        'Core/Connector and Python dependencies come from the qualified PR27 prefix. Payload files matched exact three wheels before and after.',
        'Setup/Test/version/lifecycle fixture peers are synthetic, no native/provider account or real credential backend.',
        'ID-choice file is filtered to cancel/resume/JSON; the other functions were not repeated.',
        'Initial preflight selected an antecedent PR27 wheel; it stopped before pytest and changed no prefix. Final-wheel comparison has zero drift.',
        'Raw fixture logs, SQLite, homes and vault contents stay in owned Temp. Sanitized XML omits stdout/stderr.'])
(HERE/'qualification.json').write_text(json.dumps(qualification, indent=2)+'\n', encoding='utf-8')
files = [p for p in HERE.rglob('*') if p.is_file() and p.name != 'manifest.json']
(HERE/'manifest.json').write_text(json.dumps([dict(path=p.relative_to(HERE).as_posix(),
    sha256=hashlib.sha256(p.read_bytes()).hexdigest(), bytes=p.stat().st_size) for p in files], indent=2)+'\n')
print(json.dumps(dict(status=qualification['status'], passed=qualification['passed'], failed=qualification['failed'],
    payload_files=result['payload_files'], payload_drift=result['payload_drift'], source_drift=result['repository_input_drift'],
    all_owned_processes_exited=qualification['cleanup']['all_owned_processes_exited'], manifest_entries=len(files))))
