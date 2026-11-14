"""Materialize reviewable commands; no service/task/native execution."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT));import connection_case as C
assert sys.flags.isolated and Path(sys.prefix).resolve()==(ROOT/'venv').resolve()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):return {'path':str(p),'sha256':sha(p)}
python=str(ROOT/'venv/Scripts/python.exe');home=ROOT/'case/nexus-home';case=ROOT/'case'
native=Path('C:/Users/jpamb/AppData/Local/Temp/m1-native-discovery-iyoo0rs3/codex-0.157.0/codex.exe')
assert sha(native)=='ed1c7b36e44536809c868864c833af8a857f56599a7a7fe23b908a1ba1093b1f'
from nexus_connector_core.installation import installation_ref
from okto_nexus.adapters.outbound.service_manager.identity import server_instance_id
candidate=installation_ref('codex_app_server',str(native));identity=server_instance_id(home,home/'nexus.db')
selection=['--home',str(home),'--host','127.0.0.1','--port','59107','--project-root',str(case/'project'),
    '--embedding-mode','off','--feature-harness-integrations','true','--metrics-mode','disabled','--harness-root',str(native.parent)]
base=[python,'-I','-B','-X','utf8']
connection=['connect','--plan','--client','codex','--project',str(case/'project'),'--profile',C.PROFILE,
    '--new-agent',C.PROFILE,'--provider-home',str(case/'profile/.codex'),'--candidate-ref',candidate,
    '--no-start-at-login','--no-chat','--json']
phases={'install':['service','install','--user','--start-at-login','--json'],
    'start':['service','start','--timeout','45','--json'],'plan':connection,
    'stop':['service','stop','--timeout','45','--json'],'uninstall':['service','uninstall','--user','--json']}
commands={name:{'argv':base+['-m','okto_nexus.adapters.inbound.cli.main']+args+selection,
    'cwd':str(case),'environment':'terminal'} for name,args in phases.items()}
commands['terminal-probe']={'argv':base+[str(ROOT/'run_case.py'),'probe'],'cwd':str(case),'environment':'terminal'}
pins={name:pin(ROOT/name) for name in ('run_case.py','connection_case.py','cohort.py','runtime_support.py','installation.json')}
pins.update(native=pin(native),nexus_wheel=pin(ROOT/'wheels/okto_nexus-0.3.3-py3-none-any.whl'),
    core_wheel=pin(ROOT/'wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'),
    connector_wheel=pin(ROOT/'wheels/okto_nexus_connector-0.0.12-py3-none-any.whl'))
images=[Path(python),Path(python).with_name('pythonw.exe'),Path(sys.base_prefix)/'python.exe',Path(sys.base_prefix)/'pythonw.exe']
plan={'format':'r3.svc-t15.terminal-only.fresh','status':'PREPARED_REVIEW_PENDING','root':str(ROOT),'python':python,
    'homes':{'nexus':str(home)},'port':59107,'tasks':{'nexus':'OktoNexus-server-'+identity.removeprefix('svc_')},
    'instance_ids':{'nexus':identity},'model_turn_limit':0,'reference':C.REFERENCE,'candidate_ref':candidate,
    'pins':pins,'python_images':{str(p.resolve()):sha(p) for p in images},'commands':{'nexus':commands},
    'connection_plan_arguments':connection,
    'scope':{'credential':'Random synthetic non-login value generated only during selected run; passed only to CLI children under SVC_T15_ONLY_CLI_KEY. Root/service environment excludes it. No personal vault/key/auth files read.',
        'products':'Final immutable Core7810f3/Nexus6714d695/Connectore612ff8 wheels copied to own venv; no working-tree imports.',
        'startup':'One canonical start45 then passive GET180 only pending/transport. Positive refusal or identity drift halts; no start replay. Parent/launcher/runtime query+sync handles retained before setup.',
        'inventory':'Installed TerminalConnection.options routes through agents/{id}/runtime-options?executor_id=...; explicit workspace_id=None. Only stale/PENDING waits, positive selection errors refuse. GET SERVER_UNREACHABLE only bounded retry, never POST replay.',
        'setup':'CLI connect --plan; own request differs only secret_bindings.OPENAI_API_KEY reference and unique client_intent_id. At most1 canonical version check and1 setup:test POST, no commit/binding/authorization or model turn. Expect PROVIDER_AUTH_REQUIRED before native open and journal0turn actions.',
        'cleanup':'One normal stop45 only after CLI wrappers exited. Require drained and physical runtime+launcher+parent exits plus nativeinactive before uninstall; preserve all data. No force/kill. Uncertainty retains handles for root handoff up to7200s, never claims PASS.',
        'limits':{'canonical_cli_max':6,'version_check_post_max':1,'setup_test_post_max':1,
            'start_deadline_seconds':45,'passive_ready_seconds':180,'inventory_seconds':120,'setup_test_seconds':120,
            'cli_wrapper_wait_seconds':180,'physical_exit_seconds':30,'failure_handle_observer_seconds':7200},
        'prior_failures':'Three attempts retained in r3-svc-t15-terminal-context; no prior acceptance or byte reuse of runtime homes. Startup150s observation is not a cause attribution.',
        'no_live_effects_during_preparation':True}}
with (ROOT/'plan.json').open('x',encoding='utf-8') as out:json.dump(plan,out,indent=2);out.write('\n')
print(json.dumps({'plan_sha256':sha(ROOT/'plan.json'),'task':plan['tasks']['nexus'],'candidate_ref':candidate}))
