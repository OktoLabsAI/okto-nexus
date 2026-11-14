"""Freeze qualified offline candidate metadata for independent review; no authority."""
from pathlib import Path
import hashlib,json,xml.etree.ElementTree as E
R=Path(__file__).resolve().parent;D=R/'draft'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def write(p,v):p.write_bytes((json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode())
assert not (R/'campaign').exists()
assert not any((D/'installation'/n).exists() for n in ('installation-reserved.json','installation-result.json','installation-unknown.json'))
p=read(D/'m1-codex-campaign-proposal-v11.json')
groups={}
for name in ('installer-checks','remote-composition-final','observer-composition-final'):
    result=read(R/name/'result.json');assert result['exit_code']==0,(name,result)
    cases=E.parse(R/name/'results.xml').getroot().findall('.//testcase')
    assert cases and all(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in cases)
    groups[name]={'case_count':len(cases),'xml':str(R/name/'results.xml'),'xml_sha256':sha(R/name/'results.xml'),
        'result':str(R/name/'result.json'),'result_sha256':sha(R/name/'result.json')}
assert groups['installer-checks']['case_count']==30 and groups['remote-composition-final']['case_count']==22
history=D/'preparation-history'
with (history/'pre-final-proposal.json').open('xb') as f:f.write((D/'m1-codex-campaign-proposal-v11.json').read_bytes())
commands=read(D/'proposed-commands.json')
commands.update(status='FROZEN_EIGHT_ACTIONS_REQUIRING_EXACT_V11_APPROVAL',execution_authorized=False,
    package_pin_status='QUALIFIED_ARTIFACTS_INSTALL_REQUIRED')
write(D/'proposed-commands.json',commands)
planning=read(D/'planning-commands.json');planning['status']='FROZEN_REFERENCE_COMMANDS_REQUIRING_EXACT_V11_APPROVAL'
write(D/'planning-commands.json',planning)
for item in p['execution_bundle']['files'].values():
    path=Path(item['path'])
    if path.is_relative_to(D):item['sha256']=sha(path)
    else:assert sha(path)==item['sha256']
p['execution_bundle']['commands']={'path':str(D/'proposed-commands.json'),'sha256':sha(D/'proposed-commands.json')}
p['status']='PREPARED_FOR_ROOT_REVIEW_NOT_AUTHORIZED';p['final_proposal']=False
p['qualification_status']='OFFLINE_COMPOSITION_PASSED_FINAL_ENTRY_GATES_AND_ROOT_REVIEW_PENDING'
p['blocking_preconditions']=['Independent root review of final source freeze, proposal and preserved qualification attempts.',
    'The work wrapper invokes installed TerminalWork through open_work and the canonical HTTP transport; literal work CLI parser/re-entry coverage required by M1 remains unresolved.',
    'Exact successor approval receipt required before any installation or campaign effect.',
    'Fresh own task, home, port and native pin preflight after authorization; current availability not inferred.']
p['controller_preparation'].update(status='V11_COMPOSED_SYNTHETIC_QUALIFIED',qualification_status='OFFLINE_TESTS_PASS_NO_REAL_CAMPAIGN',
    composed_module_origins={'path':str(R/'observer-composition-final/module-origins.json'),'sha256':sha(R/'observer-composition-final/module-origins.json')},
    qualification_groups=groups,
    operational_limit='Bounded offline qualification does not guarantee real-time OS scheduling or campaign success. Every source attempt, including earlier timing failures, remains separate; token billing remains unconfirmed.')
p['controller_preparation']['observation_contract']={'schema_initialization_ms':250,'snapshot_read_ms':250,
    'aggregate_poll_ms':600,'freshness_ms':1000,'productive_deadline_seconds':120,
    'freshness_basis':'A complete successful poll alone renews freshness, expiring one second after that poll started.',
    'effect_boundary':'The serialized worker rechecks freshness, aggregate poll deadline, productive deadline and token threshold immediately before each POST.',
    'budget_failure':'Fail closed, preserve reservations and primary error, select existing normal-stop capability once; no automatic replay or service force.',
    'scope':'Preparation changes the observer contract only; unchanged product wheels and provider limits.'}
p['execution_bundle'].update(status='FROZEN_QUALIFIED',
    gate='Exact successor approval, unchanged source/product/native pins and one-shot installation proof precede every campaign effect.',
    qualification_scope='Actual rebased v11 modules with synthetic Core journals; fake installer and remote transfer effects. No campaign installation, real provider, credentials or native service.',
    final_gate_reports=[str(R/'reviewed-final-entry-gates/results.xml'),str(R/'reviewed-final-entry-gates/result.json')])
p['base06_installation']['status']='DEPENDENCIES_ONLY_PREPARED_PRODUCTS_REQUIRE_EXACT_APPROVAL'
p['package_pins']['count_rule']='Derive exact product payload pins from the unchanged qualified wheel bytes; add one independently verified interpreter pin.'
p['package_pins']['build_scope']='The three prior qualified wheels (07b7ed53,73f1a3ba,609e0fbb) are unchanged. This campaign candidate does not contain the later proposed SUPERVISOR_PENDING/SVC-T19 diagnostic patch.'
p['steps'][0]['gate']='The exact qualified wheel/dependency/source pins and offline composition are bound; real approval and fresh runtime preflight remain required.'
p['execution_authorized']=False
p['finite_work']['remote_return_scope']='Reopen the temporary wrapper and installed TerminalWork checkpoint for the same Connector work; this is not a literal human CLI parser restart, Connector identity re-registration or physical host reconnection.'
p['scope_qualification']={'status':'OFFLINE_PARTIAL_SCOPE_NOT_M1_APPROVAL_READY',
    'installed_product_path':'m1_v11_work.py -> adapters.inbound.cli.work.open_work -> application.terminal_work.TerminalWork -> canonical HTTP transport serialized by the existing controller.',
    'work_cli_parser_executed':False,
    'work_claim_limit':'Useful work, decision, observation, continuation and checkpoint recovery are application-flow/HTTP observables. They do not establish literal CLI parser, rendering or interactive re-entry behavior.',
    'actual_cli_scope':'Lifecycle, setup and remote bootstrap wrappers invoke real installed CLIs when authorized; no execution occurred during this preparation.',
    'reference_commands':'All work send/watch/status/resume/answer command strings remain illustrative only; the work wrapper does not execute those argv.',
    'unpromoted_requirements':['DX39','DX40','AC11','M1'],
    'test_clock_scope':'Only test_actual_five_requests_roundtrip_sixth_refused freezes controller/reader clocks to isolate the allocation5/11 contract. SQLite, persistence and installed modules remain real; other reader/nominal cases retain their own documented clocks.',
    'preserved_initial_composition':{'tests':52,'passed':50,'failed':2,'xml':str(R/'observer-composition-initial/results.xml'),
        'fixture_failure':'Inherited six-turn v10 fixture corrected to selected one-setup/four-work v11 allocation.',
        'timing_failure':'Core snapshot SQLITE_INTERRUPT at105.287ms against100ms; fail-closed reservation and normal-stop selection retained; later allocation-only clock isolation does not erase this availability observation.'}}
for step in p['steps']:
    if any('<NEXUS> work ' in command for command in step.get('commands',[])):
        step['coverage_limit']='Illustrative CLI argv only. Current wrapper uses installed TerminalWork through canonical HTTP, without executing the work CLI parser; literal CLI M1 coverage remains pending.'
assert all(not v for k,v in p['authorization'].items() if k!='scope')
write(D/'m1-codex-campaign-proposal-v11.json',p)
scope=read(D/'scope-delta.json');scope['observer_source_freeze']=p['controller_preparation']['source_freeze']
scope['new']=['fresh roots/task names/port/dependency-only target','selected qualified reader source freeze and explicit timing contract','final-publication error handling']
scope['allocation_rebase_verified_by']=str(R/'observer-composition-final/results.xml')
write(D/'scope-delta.json',scope)
payloads=read(D/'wheel-payload-pins.json');payloads['interpreter_pin_pending']=False
payloads['interpreter_pin']=next(v for v in p['package_pins']['files'] if v['path']==p['package_pins']['python'])
payloads['expected_total_pin_count']=984
write(D/'wheel-payload-pins.json',payloads)
write(D/'offline-finalization.json',{'status':p['status'],'proposal_sha256':sha(D/'m1-codex-campaign-proposal-v11.json'),
    'groups':groups,'runtime_pin_count':len(p['execution_bundle']['files']),'all_gate_entries':len(p['package_pins']['files']),
    'campaign_absent':True,'products_not_installed':True,'real_approval_absent':True})
print(json.dumps({'status':p['status'],'proposal_sha256':sha(D/'m1-codex-campaign-proposal-v11.json'),'groups':{k:v['case_count'] for k,v in groups.items()}}))
