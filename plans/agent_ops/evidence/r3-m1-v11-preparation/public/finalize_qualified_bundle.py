"""Freeze the reviewed offline v11 sources and honest coverage; never grant campaign authority."""
from pathlib import Path
import hashlib,json,xml.etree.ElementTree as E
R=Path(__file__).resolve().parent;D=R/'draft';I=D/'installation'
S=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v11-read250-candidate-q537zfyi')
DR=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v11-driver-candidate-r3pnub4c')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def write(p,v):p.write_bytes((json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode())
assert not (R/'campaign').exists()
assert not any((I/n).exists() for n in ('installation-reserved.json','installation-result.json','installation-unknown.json'))
assert sha(S/'qualification/qualification.json')=='4b04b0a1b73d763d1e778a4f42811dea64825f437af80cb42901e79d678fe903'
assert read(S/'qualification/qualification.json')['final_suite']['passed']==64
assert read(R/'final-composed-origins/result.json')['exit_code']==0
groups={}
for name,xml in [('installed-controller-cli-component',S/'qualification/final.xml'),
    ('root-driver-component',DR/'pure-tests-004.xml'),('installer-checks',R/'installer-checks/results.xml'),
    ('remote-composition-final',R/'remote-composition-final/results.xml'),('lifecycle-cleanup-checks',R/'lifecycle-cleanup-checks/results.xml')]:
    cases=E.parse(xml).getroot().findall('.//testcase')
    assert cases and all(c.find(t) is None for c in cases for t in ('failure','error','skipped'))
    groups[name]={'tests':len(cases),'xml':str(xml),'xml_sha256':sha(xml)}
assert {k:v['tests'] for k,v in groups.items()}=={'installed-controller-cli-component':64,'root-driver-component':51,'installer-checks':30,'remote-composition-final':22,'lifecycle-cleanup-checks':7}
P=D/'m1-codex-campaign-proposal-v11.json';p=read(P)
with (D/'preparation-history/pre-final-qualified-proposal.json').open('xb') as f:f.write(P.read_bytes())
for name in ('proposed-commands.json','planning-commands.json'):
    doc=read(D/name);doc['status']='FROZEN_REFERENCE_REQUIRING_EXACT_V11_APPROVAL';doc['execution_authorized']=False
    if name=='proposed-commands.json':doc['package_pin_status']='QUALIFIED_ARTIFACTS_INSTALL_REQUIRED'
    write(D/name,doc)
for pin in p['execution_bundle']['files'].values():
    if Path(pin['path']).is_relative_to(D):pin['sha256']=sha(pin['path'])
    else:assert sha(pin['path'])==pin['sha256']
assert len(p['execution_bundle']['files'])==45
p['execution_bundle']['commands']={'path':str(D/'proposed-commands.json'),'sha256':sha(D/'proposed-commands.json')}
p['status']='OFFLINE_QUALIFIED_FOR_ROOT_FINAL_REVIEW_NOT_AUTHORIZED'
p['qualification_status']='SOURCE_COMPONENT64_PASS_BYTE_EXACT_FINAL_IMPORTS_PASS_ENTRY_GATES_RECORDED_SEPARATELY'
p['execution_authorized']=False;p['final_proposal']=False
p['blocking_preconditions']=['Independent root final review of scope, frozen bytes, exact commands and retained evidence.',
    'Exact v11 authorization and successful one-shot installation proof before any campaign effect.',
    'Fresh own task/home/port/native preflight; no current availability or successful real M1 execution is inferred.']
p['controller_preparation'].update(status='FINAL_V11_INSTALLED_CLI_OBSERVER_OFFLINE_QUALIFIED',qualification_status='64_FINAL_COMPONENT_CASES_PASS_NO_REAL_CAMPAIGN',
    composed_module_origins={'path':str(R/'final-composed-origins/module-origins.json'),'sha256':sha(R/'final-composed-origins/module-origins.json')},
    qualification_groups=groups,
    operational_limit='No hard real-time OS or statistical availability guarantee. Earlier timing failures remain retained; the source64 final suite ran once after the reviewed local read cap change. Aggregate acceptance/freshness limits remain600ms/1s.')
p['controller_preparation']['observation_contract']={'schema_initialization_ms':250,'snapshot_read_ms':250,'read_budget_ms':250,
    'aggregate_poll_ms':600,'freshness_ms':1000,'productive_deadline_seconds':120,
    'freshness_basis':'Only a complete successful poll renews freshness, expiring one second after that poll began.',
    'effect_boundary':'The serialized worker independently checks freshness, aggregate deadline, productive deadline and observed token threshold at POST boundaries.',
    'failure':'Fence before fault/threshold persistence; retain reservations/primary error and select existing normal stop once. No replay or forced service stop.'}
p['execution_bundle'].update(status='FROZEN_QUALIFIED',
    gate='Exact successor approval, unchanged source/product/native pins and one-shot installation proof precede every campaign effect.',
    qualification_scope='64 final frozen controller/installed-CLI component cases,51 pure root-driver cases,30 fake installer cases,22 remote fake-effect cases and7 actual lifecycle wrapper fake-effect cases. Byte-identical source composition verified in fresh isolated Python; final entry denials reported separately.',
    final_gate_reports=[str(R/'reviewed-final-entry-gates/results.xml'),str(R/'reviewed-final-entry-gates/result.json')])
p['base06_installation']['status']='DEPENDENCIES_ONLY_PREPARED_PRODUCTS_REQUIRE_EXACT_APPROVAL'
p['package_pins']['count_rule']='983 exact qualified wheel payloads plus one verified interpreter pin; no campaign product install during preparation.'
p['package_pins']['build_scope']='Unchanged prior qualified wheels07b7ed53/73f1a3ba/609e0fbb. Later SVC-T19/SUPERVISOR_PENDING diagnostic patches in current repositories are not present in these campaign wheels.'
p['steps'][0]['gate']='Exact qualified wheel/dependency/source bytes bound; authorization and fresh runtime preflight remain required.'
p['finite_work']['remote_return_scope']='A fresh wrapper invocation re-enters installed run_work parser/handlers and reloads the same canonical checkpoint. No Connector identity re-registration, physical host reconnection, console-window closure or dashboard event is inferred.'
p['scope_qualification']={'status':'OFFLINE_INSTALLED_CLI_PARSER_HANDLERS_QUALIFIED_REAL_M1_PENDING',
    'work_path':'CLIFlow -> installed run_work parser/handlers -> original open_work/TerminalWork under installed profile guard -> existing serialized/fenced canonical HTTP.',
    'offline_installed_parser_exercised':True,'real_campaign_cli_executed':False,'console_subprocess_exit_proven':False,'dashboard_open_close_exercised':False,
    'factory_instrumentation':'Observes original factory methods and transport; parser/readiness/lock/checkpoint/display remain installed code. No stdout redirect or duplicate POST authority.',
    'recovery':'GET-only installed status/events/answer review and existing receipt GETs. work resume is not used as a GET-only recovery operation.',
    'acceptance':'DX-T39/DX-T40/AC11 and M1 remain pending actual approved harness/provider work; SVC-T09 terminal/dashboard closure is not proved by invoking a parser function.',
    'allocation_test_clock':'Only test_actual_five_requests_roundtrip_sixth_refused fixes controller/reader clocks to isolate five-new/eleven-cumulative reservation logic; actual SQLite/persistence/reopen remain. Other fixtures retain their documented clocks.',
    'historical_failures':'Initial local52suite50PASS2FAIL preserved (inherited six-turn fixture and105.287ms snapshot); predecessorCLI63suite61PASS2timingFAIL at211.2865/153.5869ms preserved. Subsequent reviewed read250 suite64PASS ran once; no earlier failure relabeled.',
    'old_740ms_poll':'Retained failed poll includes fault/containment; not an accepted cycle. Cleanup duration was not separately measured, so the entire excess is not attributed to cleanup.'}
for step in p['steps']:
    if any('<NEXUS> work ' in command for command in step.get('commands',[])):
        step['coverage_limit']='CLI argv are reference strings. The wrapper executes installed run_work parser/handlers in its API worker; it does not launch a separate interactive console for each command.'
for row in p['fixed_plan_map']:
    if row['requirement'] in ('M1 / DX-T39','M1 / DX-T40','DX-T47 / DX-T50'):
        row['proof']='Planned real installed run_work parser/handler cycle with canonical checkpoint recovery. Offline synthetic parser qualification is complete; actual campaign result/continuity remains pending, and no console-window/dashboard closure is inferred.'
assert all(not v for k,v in p['authorization'].items() if k!='scope')
write(P,p)
scope=read(D/'scope-delta.json');scope.update(observer_source_freeze=p['controller_preparation']['source_freeze'],
    new=['fresh roots/task names/port/dependency-only target','installed CLI parser/handler observer with250ms read/init and600ms aggregate/1s freshness','root drivers and independently revalidated never-started cleanup path'],
    allocation_rebase_verified_by=str(S/'qualification/final.xml'))
write(D/'scope-delta.json',scope)
payloads=read(D/'wheel-payload-pins.json');payloads['interpreter_pin_pending']=False
payloads['interpreter_pin']=next(v for v in p['package_pins']['files'] if v['path']==p['package_pins']['python']);payloads['expected_total_pin_count']=984
write(D/'wheel-payload-pins.json',payloads)
write(D/'offline-finalization.json',{'status':p['status'],'proposal_sha256':sha(P),'groups':groups,
    'source_freeze':p['controller_preparation']['source_freeze'],'runtime_pins':45,'package_pins':984,
    'campaign_absent':True,'products_not_installed':True,'real_approval_absent':True})
print(json.dumps({'status':p['status'],'proposal_sha256':sha(P),'runtime_pins':45,'qualified_cases_before_entry_checks':sum(v['tests'] for v in groups.values())}))
