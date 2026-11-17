"""Curate five actual empty-Home checks; preserve prior cut qualifications."""
import hashlib
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
source=ROOT/'output/playwright/ui04-empty'
target=HERE/'empty-CIXUIG91'
target.mkdir(exist_ok=True)
text=(source/'output.txt').read_text(encoding='utf-8')
result=json.loads(text.split('### Result\n',1)[1].split('\n### Ran',1)[0])
ready=json.loads((source/'ready.json').read_text())
assert result['status']=='PASS' and not result['errors'] and not result['consoleErrors']
(target/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
for name in ['ready.json','output.txt','canonical-empty-first-harness.png','filtered-empty-existing-connections.png',
    'antecedent-datalist-role-output.txt','antecedent-aboutblank-init-output.txt']:shutil.copy2(source/name,target/name)
for name in ['empty-fixture.py','empty-probe.js']:shutil.copy2(HERE/name,target/name)
report=dict(status='PASS_FIVE_EMPTY_HOME_CHECKS_ONLY',scenario='T-HOME-03',checks_passed=5,
    bundle='index-CIXUIG91.js',js_sha256='0de41929962e2b23b65a30920d607ea2fc853db62bba859b40c78add287cafc1',
    canonical_empty='Own authorized ui04-empty workspace; actual ready exact entries0 and pre-filter connections0; seven sources ready',
    negative_case='Existing ws connections2 remains2 after harness filter yields entries0; no onboarding and New request enabled',
    mutation_requests=[r for r in result['requests'] if r['method'] not in ['GET','HEAD','OPTIONS']],
    page_errors=result['errors'],console_errors=result['consoleErrors'],
    source_pin_drift=[p for p,h in ready['source_sha256'].items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h],
    antecedents='Harness list input has combobox semantics; then own initScript access to aboutblank localStorage raised during cleanup. Fixed selectors/protocol guard and used a fresh own browser; final raw result has no exceptions. Product unchanged during these runner fixes.',
    limits=['Does not requalify the previous27 browser checks on this cut','Partial/stale/unknown inventory exclusion is Node/source evidence, not additional browser cases',
        'Live-viewer403 with active draft remains NOT_RUN; no404 was presented as403; no new fixture opened for that case','No provider/native/AT/200percent zoom qualification'],
    cleanup=dict(browser_pid=59000,browser_close_exit=0,fixture_exit=0,pid_absent=True,port=55059,port_absent=True,
        shared_context='WSS/lifespan generator and factory closed normally',tools=['9986e7','0f96c8','49eeab']),
    sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in target.iterdir() if p.is_file() and p.name!='qualification.json'})
(target/'qualification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'drift':report['source_pin_drift'],'sha256':hashlib.sha256((target/'qualification.json').read_bytes()).hexdigest()}))
