"""Pin offline candidate for root review; does not execute its commands."""
from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as out:json.dump(value,out,indent=2);out.write('\n')
suite=ET.parse(ROOT/'offline-reviewed.xml').getroot().find('testsuite')
assert suite is not None and int(suite.get('tests'))==33 and suite.get('errors')==suite.get('failures')=='0'
assert not (ROOT/'case').exists() and not (ROOT/'public').exists() and not (ROOT/'private').exists()
original=(ROOT/'plan.json').read_bytes()
with (ROOT/'plan-before-review.json').open('xb') as out:out.write(original)
plan=json.loads(original)
plan['status']='OFFLINE_QUALIFIED_ROOT_REVIEW_PENDING'
plan['scope']['cleanup']+=' If readiness failed before complete cohort capture, handoff stays UNKNOWN and reads only the exact task/canonical owner. Empty handles, absent task or null PID never prove physical exit. Later READY may be captured once with exact scope, image/birth, single initial attempt and query-only handles; this never changes the failed campaign outcome.'
for pin in plan['pins'].values():
    if Path(pin['path']).name in ('run_case.py','connection_case.py','cohort.py','runtime_support.py'):pin['sha256']=sha(pin['path'])
    else:assert sha(pin['path'])==pin['sha256']
with (ROOT/'plan.json').open('w',encoding='utf-8',newline='\n') as out:json.dump(plan,out,indent=2);out.write('\n')
q={'status':'OFFLINE_QUALIFIED_NOT_EXECUTED','tests_passed':33,'xml':'offline-reviewed.xml',
   'prior_offline_cases':{'passed':27,'xml':'offline-final.xml','overlap':'All prior27 recur in33; six new edge cases, do not add counts.'},
   'coverage':['Real installed TerminalConnection.options and dashboard runtime-options route with fake IO.',
       'Pending/stale inventory and transient GET wait only; positive GET errors and all POST uncertainty are not retried.',
       'start45 then passive180 readiness; positive refusal/identity drift halt, no start replay.',
       'Runtime pythonw image path/hash bound before cohort/setup.',
       'Complete retained runtime/launcher/parent exits and nativeinactive required before uninstall.',
       'CLI still live forbids parallel cleanup; uncaptured cohort/task absent is UNKNOWN, not physical proof.',
       'Later READY handoff capture is query-only and keeps cleanup/campaign unconfirmed.',
       'Synthetic reference must diagnose failed PROVIDER_AUTH_REQUIRED; no success inferred.'],
   'warning':'One existing Starlette TestClient/httpx deprecation warning; no native network/process/service started by fixtures.',
   'installed_payloads':988,'installation_sha256':sha(ROOT/'installation.json'),
   'wheels':json.loads((ROOT/'installation.json').read_bytes())['wheels'],
   'plan_sha256':sha(ROOT/'plan.json'),'runtime_pins':plan['pins'],
   'effects':{'service_calls':0,'native_tasks':0,'provider_processes':0,'credential_resolution_probes':0,'model_turns':0},
   'prior_real_failures':'Three actual failed attempts retained in plans/agent_ops/evidence/r3-svc-t15-terminal-context; none superseded or promoted.',
   'new_case_runtime_directories_absent':True,'root_execution_review_pending':True}
save(ROOT/'qualification.json',q)
save(ROOT/'review-command.json',{'status':'ROOT_REVIEW_REQUIRED_BEFORE_EXECUTION','argv':[plan['python'],'-I','-B','-X','utf8',
    str(ROOT/'run_case.py'),'execute','--expected-plan-sha256',sha(ROOT/'plan.json')],
    'cwd':str(ROOT),'environment':json.loads((ROOT/'environment.json').read_bytes()),
    'port':plan['port'],'task_name':plan['tasks']['nexus'],'plan_sha256':sha(ROOT/'plan.json')})
names=['run_case.py','connection_case.py','cohort.py','runtime_support.py','plan.json','plan-before-review.json',
    'qualification.json','review-command.json','source-ancestry.json','test-ancestry.json','test_lifecycle.py',
    'test_connection_routes.py','offline-final.xml','offline-reviewed.xml','qualify.py','prepare_sources.py',
    'prepare_tests.py','prepare_plan.py','prepare_dependencies.py','install_products.py','installation.json',
    'dependency-preparation.json','freeze.py']
save(ROOT/'public-allowlist.json',{'source_root':str(ROOT),'files':[{'path':name,'sha256':sha(ROOT/name),
    'bytes':(ROOT/name).stat().st_size} for name in names]})
print(json.dumps({'plan_sha256':sha(ROOT/'plan.json'),'runner_sha256':sha(ROOT/'run_case.py'),
    'qualification_sha256':sha(ROOT/'qualification.json'),'public_allowlist_sha256':sha(ROOT/'public-allowlist.json')}))
