"""Freeze offline reviewed bytes. Never invokes a service/task/provider."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as out:json.dump(value,out,indent=2);out.write('\n')
def totals(name):
    suites=ET.parse(ROOT/name).getroot().findall('testsuite')
    return {key:sum(int(s.get(key,'0')) for s in suites) for key in ('tests','failures','errors','skipped')}
for name,count in [('runner-final-reviewed.xml',53),('installed-supervisor-fixture-fixed.xml',81)]:
    total=totals(name);assert total==dict(tests=count,failures=0,errors=0,skipped=0),total
old=(ROOT/'plan.json').read_bytes()
with (ROOT/'plan-prepared-before-review.json').open('xb') as out:out.write(old)
plan=json.loads(old)
plan['status']='FROZEN_QUALIFIED_OFFLINE'
plan['root_review_pending']=True
plan['scope']['timeouts']={'readiness_seconds':180,'lifecycle_command_timeout_seconds':45,
    'cli_wrapper_wait_seconds':180,'physical_exit_seconds':30,'quiet_seconds':190,
    'failure_handle_observer_seconds':7200}
plan['scope']['failure_handoff']='On failure publish unconfirmed progression, retain own runtime/launcher/parent/Popen handles in the same runner, observe up to7200s for root-selected normal cleanup. No automatic effect. Observer expiry UNKNOWN, never PASS; handles close only after observation.'
plan['scope']['backoff_evidence']='FILETIME wall birth minus crash wall time, tolerance1s. Also compare endpoint wall vs monotonic elapsed with maximum1s drift; reject excess. Cancelling clock adjustments are not detected. Pure policy tests prove monotonic60s; actual stop during backoff is not exercised by this campaign.'
for phases in plan['commands'].values():
    for name,step in phases.items():
        argv=step['argv']
        if '--timeout' in argv:assert argv[argv.index('--timeout')+1]=='45',(name,argv)
for pin in plan['pins']:
    if Path(pin['path']).name in ('run.py','runtime_support.py'):pin['sha256']=sha(pin['path'])
    else:assert sha(pin['path'])==pin['sha256'],pin['path']
with (ROOT/'plan.json').open('w',encoding='utf-8',newline='\n') as out:json.dump(plan,out,indent=2);out.write('\n')
installation=json.loads((ROOT/'final-build/installation.json').read_bytes())
qualification={
 'status':'OFFLINE_QUALIFIED_NOT_EXECUTED','product_commits':plan['scope']['product_commits'],
 'wheels':{name:value['wheel_sha256'] for name,value in installation['products'].items()},
 'installation_sha256':sha(ROOT/'final-build/installation.json'),
 'installed_tests':{'passed':81,'deselected':2,'xml':'installed-supervisor-fixture-fixed.xml',
    'scope':'Pure policy, fake native tasks/Popen and readonly own-process identity. Two real benign redirector child-spawn cases excluded; source evidence already retained separately. No installed actual service/crash acceptance.'},
 'runner_tests':{'passed':53,'xml':'runner-final-reviewed.xml','scope':'All final runner cases with fake native/process/network interfaces, including partial-handle failure, unknown waits, wrapper timeout, drift, parent/counter/ACK changes and all three retained exits.'},
 'history':[
    {'artifact':'runner-final.xml','outcome':'43PASS before review deltas'},
    {'artifact':'runner-handoff-final.xml','outcome':'47PASS before partial-handle/drift delta'},
    {'artifact':'installed-supervisor-final.xml','outcome':'CollectionERROR missing test_service_start helper; no test executed; corrected by exact committed fixture copy.'},
    {'artifact':'installation.json','outcome':'Provisional pins341a/02a/e612 build/install success; superseded by separate final-build after new Core/Nexus commits. Provisional wheel bytes preserved; own venv now final products.'},
    {'artifact':'archive-core.stderr','outcome':'Initial build attempt failed before archive because isolated PATH had no git. Fixed to resolved absolute git; no source or service effect.'},
    {'tool_chunk':'a12181','outcome':'Preparation command PowerShell parser error before any file write; replaced with exact Python preparation file.'}],
 'live_calls':{'services':0,'native_tasks':0,'crashes':0,'provider':0},
 'limits':plan['scope']['limits']+[plan['scope']['backoff_evidence']],
 'plan_sha256':sha(ROOT/'plan.json'),'runner_sha256':sha(ROOT/'run.py'),
 'runtime_support_sha256':sha(ROOT/'runtime_support.py'),'pins_verified':len(plan['pins'])}
save(ROOT/'qualification.json',qualification)
command=[plan['python'],'-I','-B','-X','utf8',str(ROOT/'run.py'),'execute',
    '--expected-plan-sha256',sha(ROOT/'plan.json'),'--expected-runner-sha256',sha(ROOT/'run.py')]
save(ROOT/'review-command.json',{'status':'FROZEN_OFFLINE_ROOT_EXECUTION_REVIEW_PENDING',
    'argv':command,'cwd':str(ROOT),'environment':plan['environments']['A'],
    'plan_sha256':sha(ROOT/'plan.json'),'runner_sha256':sha(ROOT/'run.py'),
    'runtime_support_sha256':sha(ROOT/'runtime_support.py'),'tasks':plan['tasks'],'port':plan['port']})
paths=['run.py','runtime_support.py','test_runner.py','prepare_plan.py','freeze.py','qualify_runner.py',
 'qualify_installed.py','prepare_installed_tests.py','add_installed_fixture.py','installed-test-pins.json',
 'installed-fixture-added.json','runner-final.xml','runner-handoff-final.xml','runner-final-reviewed.xml',
 'installed-supervisor-final.xml','installed-supervisor-fixture-fixed.xml','plan.json',
 'plan-prepared-before-review.json','review-command.json','qualification.json','final-build/installation.json',
 'installation.json','build_install.py','build_final.py','prepare_final_build.py','archive-core.stderr']
paths += [str(p.relative_to(ROOT)).replace('\\','/') for p in sorted((ROOT/'installed-tests').glob('*.py'))]
save(ROOT/'public-allowlist.json',{'source_root':str(ROOT),'files':[{'path':name,'sha256':sha(ROOT/name),
    'bytes':(ROOT/name).stat().st_size} for name in paths]})
print(json.dumps({k:qualification[k] for k in ('plan_sha256','runner_sha256','runtime_support_sha256','pins_verified')}))
