"""Allowlisted public copy; no homes, databases, private process logs or keys."""
from pathlib import Path
import difflib,hashlib,json,re,shutil,subprocess,xml.etree.ElementTree as ET

ROOT=Path(__file__).parent
PUBLIC=ROOT/'public'
PUBLIC.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(name,value):(PUBLIC/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
entries=[]
def add(source,name):
    raw=source.read_bytes()
    text=raw.decode('utf-8')
    # Only recognizable synthetic credential literals could require redaction;
    # this campaign does not create or display agent credentials.
    counts={}
    for label,pattern in [('agent_key',r'nxs_[A-Za-z0-9_-]{20,}'),('observation_token',r'nxobs_[A-Za-z0-9_-]{20,}')]:
        text,n=re.subn(pattern,'[REDACTED_'+label.upper()+']',text)
        counts[label]=n
    payload=text.replace('\r\n','\n').encode('utf-8')
    destination=PUBLIC/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(payload)
    entries.append({'source_path':str(source),'path':name,'original_sha256':hashlib.sha256(raw).hexdigest(),
        'artifact_sha256':sha(destination),'redactions':counts,'normalization':'UTF-8; CRLF to LF; credential patterns only'})

attempts=[]
for folder,name,limitation in [
    ('initial','collection-initial.xml','Preparation only: psutil absent in qualified venv; no Server/test body started. Fixed helper to use native Windows read APIs without installing dependencies.'),
    ('execution-initial','execution-fixture-initial.xml','6 pass /1 fixture failure: replacing Windows os.environ by a plain dict lost canonical SystemRoot spelling before detached spawn; WinError10106 occurred before bind. Runner afterward compared preexisting __pycache__ only on its before side and raised; XML was already closed. No product qualification from this failed port case.'),
    ('final','execution-final.xml','6 pass /1 real product failure: occupied-port cause is absent from public service result and bounded logs. Product bytes match the qualified wheel; tests stayed unchanged during this final run.')]:
    source=ROOT/'reports'/folder/'tests.xml';tree=ET.parse(source)
    cases=[]
    for c in tree.iter('testcase'):
        state='failed' if c.find('failure') is not None else 'error' if c.find('error') is not None else 'skipped' if c.find('skipped') is not None else 'passed'
        cases.append({'classname':c.get('classname'),'name':c.get('name'),'status':state})
    add(source,'reports/'+name)
    attempts.append({'attempt':folder,'report':'reports/'+name,'cases':cases,'counts':{s:sum(c['status']==s for c in cases) for s in ['passed','failed','error','skipped']},'limitation':limitation})
add(ROOT/'reports/installed-inputs.json','proofs/installed-inputs.json')
add(ROOT/'reports/final/input-hashes.json','proofs/final-test-input-hashes.json')
add(ROOT/'reports/final/summary.json','proofs/final-run.json')
for name in ['occupied-port','startup-invalid_config','startup-future_migration','startup-unavailable_storage','connect-interruption']:
    add(ROOT/'reports/final'/(name+'.json'),'proofs/'+name+'.json')
test=ROOT/'candidate/tests/test_service_failure_boundaries.py'
add(test,'candidate/test_service_failure_boundaries.py')
patch=''.join(difflib.unified_diff([],test.read_text(encoding='utf-8').splitlines(keepends=True),fromfile='/dev/null',tofile='b/tests/test_service_failure_boundaries.py'))
(PUBLIC/'tests.patch').write_text(patch,encoding='utf-8',newline='\n')
for name in ['prepare.py','run_installed.py','curate.py']:
    add(ROOT/name,'scripts/'+name)
ruff=subprocess.run(['ruff','check',str(test)],capture_output=True,text=True)
assert ruff.returncode==0
(PUBLIC/'ruff.txt').write_text(ruff.stdout+ruff.stderr,encoding='utf-8',newline='\n')
dump('attempts.json',{'attempts':attempts,'distinct_execution_identities':7,'qualified_identities':6,'unresolved_product_failures':1,
    'collection_error_is_not_an_execution_identity':True,'repeat_counts_not_added_to_coverage':True})
final_inputs=json.loads((ROOT/'reports/final/input-hashes.json').read_text())
assert final_inputs['tests\\test_service_failure_boundaries.py']==sha(test)
assessment={'schema':'r3.svc.failure-boundaries.v1','scope':['SVC-T06','SVC-T12','SVC-T13'],
    'mode':'installed noneditable wheel, new tests only in Temp','wheel_sha256':'9b18dc0c69673bb730198ca461f2464c8ee4ae3fdc1226f22ffcb8140783412f',
    'package_files_verified':690,'mcp':'1.30.0','product_changed':False,'checkout_changed':False,
    'results':{'SVC-T06':{'status':'PARTIAL_PRODUCT_DEFECT','proved':['one actual spawn','occupied foreign loopback listener survives','configured port and database unchanged','no ready event','child exits and ownership lock releases'],
        'defect':'Public service start returns STARTUP_FAILED and asks to inspect diagnostics, but service logs have no bind/port cause. The canonical detached child stderr is discarded in production.',
        'product_refs':['src/okto_nexus/adapters/outbound/service_manager/local.py:225','src/okto_nexus/adapters/inbound/cli/service_process.py:44','src/okto_nexus/adapters/inbound/cli/serve.py:612'],
        'recommendation':'Preserve a sanitized typed startup bind failure from the actual bind attempt; do not replace ownership or add a racy preflight-only port probe. Parent owns any product change.'},
      'SVC-T12':{'status':'VERIFIED_SCOPED','proved':['invalid enum rejected before home/store creation','future migration ledger rejected with MIGRATION_ERROR; original rows and table set preserved','storage parent occupied by regular file yields explicit exclusion/storage diagnostic and preserves file','all three never listen or report readiness','existing failed-bootstrap lock release and injected lock-storage denial regressions pass'],
        'limits':'Disposable local config/SQLite/filesystem; not all possible OS permission or migration faults.'},
      'SVC-T13':{'status':'VERIFIED_SCOPED','proved':['real owner captured by PID plus Windows process birth/image and parent relationship','KeyboardInterrupt injected into one connect observer sleep','connect returns130 without launch/setup/shutdown receipts','same owner/generation subsequently reaches ready','canonical stop yields DRAINED and process exits0'],
        'limits':'Fault injection at the exact observer boundary, not physical keyboard/console signaling; no provider or admitted native turn was needed or claimed.'}},
    'cleanup':{'occupied_port_child':'exited1; foreign listener retained until test-owned context closes','interrupted_connect_owner':'canonical DRAINED then captured process exit0','global_console_signals':0,'registered_services':0,'providers':0},
    'isolation_limits':['No packages installed or source/config bytes changed in shared qualified venv. Wheel comparison covers payload files, not incidental Python bytecode caches.','Raw XML and raw process stderr remain in Temp; only curated allowlist goes to public.','A captured Popen stderr sink is the only instrumentation of port startup; the public-cause assertion deliberately excludes that private stream.','Parent repository source may evolve independently; these assertions import only the pinned installed package.']}
dump('assessment.json',assessment)
(PUBLIC/'README.md').write_text('''# SVC-T06 / T12 / T13 — finite installed qualification

Final: **6 passed, 1 real product failure**, seven distinct execution identities.
Five new cases plus two reused exclusion/bootstrap regressions. Repeated runs
are not added to coverage. Preparation failures are retained separately.

T06 proves no fallback and preserved ownership but exposes a missing public bind
diagnostic: `STARTUP_FAILED` plus generic action, while the real child stderr
contains the occupied-port cause and production discards it. This case stays red.
T12 covers real invalid config, future migration ledger and blocked storage;
T13 injects KeyboardInterrupt only in a connect wait while observing a real,
birth-verified disposable owner, then confirms the same generation ready and
canonical DRAINED cleanup. No global signals, personal state, provider, native
service registration, or source-product changes occurred.

`tests.patch` adds only the new test file. The existing two tests are selected
unchanged from `tests/test_serve_lock.py`; their final copied hash is in the
inputs proof. All runtime imports came from noneditable Nexus wheel `9b18…`
(690 matching payload files), Core 0.0.14 and MCP 1.30.0 in the qualified CI venv.

The first collection had a missing optional test dependency, replaced with
native Windows read APIs. The first executable run had a fixture-only SystemRoot
case issue and a runner-only bytecode inventory comparison issue. Both raw XMLs
are preserved; no earlier failure was overwritten or counted as final success.

See assessment.json for exact boundaries; attempts.json for nominal cases;
artifact-manifest.json for original/public hashes and redactions. This is not
M1/M2, registered Task Scheduler, actual login/logout, or provider qualification.
''',encoding='utf-8',newline='\n')
all_names=sorted(p.relative_to(PUBLIC).as_posix() for p in PUBLIC.rglob('*') if p.is_file())
files=[{'path':name,'bytes':(PUBLIC/name).stat().st_size,'sha256':sha(PUBLIC/name)} for name in all_names]
aggregate=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
dump('artifact-manifest.json',{'allowlist':files,'copies':entries,'aggregate_sha256':aggregate,
    'excluded':['homes','databases','credentials','raw process logs','venv','wheel binaries','pytest temporary state'],
    'redactions':sum(sum(x['redactions'].values()) for x in entries)})
print(json.dumps({'public':str(PUBLIC),'artifact_count':len(files),'manifest_sha256':sha(PUBLIC/'artifact-manifest.json'),
    'aggregate_sha256':aggregate,'redactions':sum(sum(x['redactions'].values()) for x in entries)},indent=2))
