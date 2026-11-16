"""Curate actual CLI results; no browser/fixture/provider invocation."""
import hashlib
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
source=ROOT/'output/playwright/ui04-final'
target=HERE/'final-dfy1_5aT'
target.mkdir(exist_ok=True)

def parse(filename):
    text=(source/filename).read_text(encoding='utf-8')
    return json.loads(text.split('### Result\n',1)[1].split('\n### Ran',1)[0])

main=parse('output.txt')
fences=parse('fences-output.txt')
ready=json.loads((source/'ready.json').read_text(encoding='utf-8'))
assert main['status']==fences['status']=='PASS'
for name,value in [('results.json',main),('fences-results.json',fences),('ready.json',ready)]:
    (target/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
for name in ['desktop-home.png','desktop-exact-session-history.png','no-turn-session.png',
    'mobile-exact-session.png','composer-dirty-guard.png','real403-home-cleared.png','output.txt','fences-output.txt']:
    shutil.copy2(source/name,target/name)
shutil.copy2(ROOT/'src/okto_nexus/adapters/inbound/http/static/index.html',target/'index.html')
drift=[path for path,sha in ready['source_sha256'].items() if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=sha]
checks=main['checks']+fences['checks']
report=dict(status='PASS_WITH_EXPLICIT_UNQUALIFIED_CASES',bundle='index-dfy1_5aT.js',
    js_sha256='d4361240c4405978aefb39034e3c07e549766d338d290b313f719e282de62409',
    pass_checks=sum(x['status']=='PASS' for x in checks),not_run_checks=[x for x in checks if x['status']=='NOT_RUN'],
    source_pin_drift=drift,primary_console_errors=main['consoleErrors'],page_errors=main['pageErrors']+fences['errors'],
    mutations=[x for x in main['requests']+fences['requests'] if x['method'] not in ['GET','HEAD','OPTIONS']],
    expected_fence_statuses=[x for x in fences['responses'] if x['status']>=400],
    scope=['single Follow-up desktop and360px','exact2sessions no latest heuristic','one root dialog and one embedded viewer',
        'passive no-turn context','Home display pause and focus return','real unsent composer Escape/close/Back guards',
        'actual agent-key Home403 removes protected entries'],
    limits=['DOM/HTTP only, no AT speech or provider/native campaign',
        'Synthetic clone streams have explicit empty watermarks; does not qualify nonempty captured output in those clones',
        'Original admitted session has canonical captured input-request history',
        'Dirty Back test seeds one same-origin history entry with history.pushState; actual popstate guard, not cross-document beforeunload proof',
        'Other-agent Home403 is tested after passive panel closes; live panel/viewer403 not qualified',
        'Agent-origin question remains correctly addressed to subject; no human responder fabricated',
        'Agent-admin entry transition, result-specific panel, further cursor/CAS and native200percent zoom remain separately unqualified'],
    cleanup=dict(browser_pid=57896,browser_close_exit=0,fixture_exit=0,normal_stop_file=True,
        browser_pid_absent=True,port=63560,port_absent=True,
        evidence_tools=['051eed','088f91','519469'],fixture_context='WSS/lifespan generator and factory closed normally'),
    sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in target.iterdir() if p.is_file() and p.name!='qualification.json'})
(target/'qualification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(passed=report['pass_checks'],not_run=len(report['not_run_checks']),source_drift=drift,
    mutations=len(report['mutations']),sha256=hashlib.sha256((target/'qualification.json').read_bytes()).hexdigest())))
