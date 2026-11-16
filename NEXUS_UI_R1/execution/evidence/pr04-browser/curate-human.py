"""Conservative curation of a live-authority-expired human probe, not a pass."""
from pathlib import Path
import hashlib
import json
import shutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
source=ROOT/'output/playwright/ui04-human'
target=HERE/'human-dfy1'
target.mkdir(exist_ok=True)
text=(source/'output.txt').read_text(encoding='utf-8')
result=json.loads(text.split('### Result\n',1)[1].split('\n### Ran',1)[0])
ready=json.loads((source/'ready.json').read_text(encoding='utf-8'))
(target/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
for name in ['output.txt','ready.json','human-failure.png']:
    shutil.copy2(source/name,target/name)
control=json.loads((source/'control.json').read_text())
shutil.copy2(Path(control['control'])/'final-db.json',target/'final-db.json')
shutil.copy2(source/'authority-compare.json',target/'authority-compare.json')
db=json.loads((target/'final-db.json').read_text())
report=dict(status='NOT_QUALIFIED_LIVE_AUTHORITY_BECAME_STALE',bundle=ready['bundle'],preflight=ready['preflight'],
    origin=ready['origin'],browser_form_available=False,completed_guard_checks=0,
    native_decision_posts=[r for r in db['requests'] if r['method']=='POST'],db_summary=db['summary'],
    two_tab_cas='NOT_RUN; no human answer form became available in this browser run',
    observed_pre_browser=dict(tool='b2bbb8',kind='native_question_pending',allowed_actions=['inspect_approval','respond_native']),
    observed_browser='Canonical approval inspection only; no current actionable occurrence; native-approval-input form absent',
    later_comparison='Both actual Attention and Home entries preview stale with inspect_approval only; no Home-only discrepancy established',
    diagnostic_limit='Exact require_live failing authority dependency was not captured; no inferred expiry cause or product bug asserted',
    source_pin_drift=[p for p,h in ready['source_sha256'].items() if (ROOT/p).exists() and hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h],
    source_pin_missing_after_new_build=[p for p in ready['source_sha256'] if not (ROOT/p).exists()],
    cleanup=dict(browser_close_exit=0,fixture_exit=0,own_browser_pid=35408,pid_absent=True,port=52649,port_absent=True,
        tools=['c60e5a','37f355','c17c73']),
    sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in target.iterdir() if p.is_file() and p.name!='qualification.json'})
assert not report['native_decision_posts'] and db['summary']['decisions']==db['summary']['decide_operations']==0
(target/'qualification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'source_drift':report['source_pin_drift'],'db':report['db_summary'],
    'sha256':hashlib.sha256((target/'qualification.json').read_bytes()).hexdigest()}))
