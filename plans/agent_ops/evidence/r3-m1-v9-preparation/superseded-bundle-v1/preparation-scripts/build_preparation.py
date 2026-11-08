"""Finite v9 draft builder. Writes preparation files only; never executes a campaign."""
import ast
from copy import deepcopy
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / 'draft'
OLD = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v8-handoff-ready-s4wcxb28')
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
CONNECTOR = Path('D:/Projetos/Techridy/okto-nexus-connector')
CLOSURE = Path('C:/Users/jpamb/AppData/Local/Temp/m1-fresh-v8-pg0b6zbf/campaign/public/closure.json')
OLD_INSTALLER = Path('C:/Users/jpamb/AppData/Local/Temp/m1-base06-install-g9ii2zhe/timed_install.py')
PORT = 54913  # Proposed only: no bind, reservation or network call in preparation.
CAMPAIGN = ROOT / 'campaign'
INSTALL = OUT / 'installation'
PYTHON = INSTALL / 'venv/Scripts/python.exe'
POLICY = {'revision':9, 'carry_in_admissions':3, 'carry_in_tokens':45843,
          'max_cumulative_admissions':9, 'max_new_admissions':6,
          'preventive_cumulative_tokens':200000, 'operational_tolerance':700000,
          'deadline_seconds':120}
sha = lambda raw: hashlib.sha256(raw).hexdigest()
def load(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def digest(path): return sha(Path(path).read_bytes())
def write(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def text(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value,encoding='utf-8')

assert not OUT.exists() and not CAMPAIGN.exists()
assert digest(OLD/'m1-codex-campaign-proposal-v8.json') == 'a41d1de0eef405f30dd8615019a1d3929e33910ce7106006162543bc2520eccb'
assert digest(OLD/'manifest.json') == 'c71f11d51edcf3f0e90ffe09b986a815cc8ffb95c7713a88b220f067ccbf4818'
assert digest(CLOSURE) == '678dd44b316496fc847fe3b3686a233a2fd40d7afe89fd6e5d1d3132ca04f03d'
old = load(OLD/'m1-codex-campaign-proposal-v8.json')
closure = load(CLOSURE)
assert closure['cumulative_reserved_admissions']==3 and closure['new_reserved_admissions']==1
assert closure['historical_confirmed_productive_admissions']==2 and closure['new_confirmed_productive_admissions']==0
assert closure['carry_in_minimum_observed_tokens']==45843 and closure['new_observed_tokens']==0
assert closure['faults_preserved']==['SETUP_CLI_RETURNED_WITHOUT_SETTLED_USAGE']
assert closure['controller_checkpoint_sha256']=='6e4ea14fe5a2e4317962ec329409b428c4845e0ed7627dd4c74879bb1904c361'
assert closure['closed_without_force'] and closure['all_temporary_tasks_absent']
ANCESTRY = {'closure_sha256':digest(CLOSURE), 'checkpoint_sha256':closure['controller_checkpoint_sha256'],
            'predecessor_faults':closure['faults_preserved'],
            'prior_ancestry':old['controller_preparation']['ancestry']}

# Read only the current process SID using the exact existing helper function.
# No credential API, token contents beyond TokenUser, Scheduler query or child.
identity_path = CONNECTOR/'src/okto_nexus_connector/platform/service_identity.py'
tree = ast.parse(identity_path.read_text(encoding='utf-8'))
node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='effective_principal')
namespace = {'ctypes':ctypes,'wintypes':wintypes,'os':os}
exec(compile(ast.Module(body=[node],type_ignores=[]),str(identity_path),'exec'),namespace)
principal = namespace['effective_principal']()
assert principal.startswith('sid:')
def identities(paths):
    home = os.path.normcase(str(Path(paths['server_home']).resolve()))
    database = os.path.normcase(str((Path(paths['server_home'])/'nexus.db').resolve()))
    state = os.path.normcase(str(Path(paths['connector_state']).resolve()))
    server = sha(json.dumps(['server',home,database,principal[4:]],ensure_ascii=False,separators=(',',':')).encode())
    connector = sha(json.dumps(['connector',state,principal],separators=(',',':')).encode())
    return {'nexus':{'name':'OktoNexus-server-'+server,'instance_id':'svc_'+server},
            'connector':{'name':'OktoNexus-connector-'+connector,'instance_id':'svc_'+connector}}
old_ids = identities(old['paths'])
assert all(old_ids[k]['name']==old['topology']['task_names'][k]['name'] for k in old_ids)

OUT.mkdir()
paths = {key:(str(CAMPAIGN/Path(value).relative_to(old['paths']['campaign_root']))
              if key!='codex_executable' else value) for key,value in old['paths'].items()}
ids = identities(paths)
assert all(ids[k]['name']!=old_ids[k]['name'] for k in ids)
for value in ids.values():
    value.update(exists=None,absence_observed=False)
replacements = [(old['paths']['campaign_root'],str(CAMPAIGN)),
                (old['package_pins']['python_prefix'],str(INSTALL/'venv')),
                (str(OLD),str(OUT)),('m1v8','m1v9'),('m1-v8','m1-v9'),('m1_v8','m1_v9'),
                ('m1-codex-campaign-proposal-v8.json','m1-codex-campaign-proposal-v9.json'),
                ('http://127.0.0.1:49807','http://127.0.0.1:'+str(PORT))]
def replace_string(value):
    for before,after in replacements:
        value=value.replace(before,after).replace(before.replace('\\','/'),after.replace('\\','/'))
    return value
def rebase(value):
    if isinstance(value,str): return replace_string(value)
    if isinstance(value,list): return [rebase(v) for v in value]
    if isinstance(value,dict): return {k:rebase(v) for k,v in value.items()}
    return value

sources = {}
for file in ('campaign_context.py','m1_v8_lifecycle.py','m1_v8_setup.py','m1_v8_work.py',
             'm1_v8_remote_setup.py','supervisor_check.py','publication.py','response_loss.py','test_entry_guards.py'):
    original = (OLD/file).read_text(encoding='utf-8')
    changed = replace_string(original)
    if file=='campaign_context.py':
        changed=changed.replace("proposal=json.loads(raw)","proposal=json.loads(raw)\n        require(proposal.get('revision')==9,'PROPOSAL_REVISION_MISMATCH')")
        changed=changed.replace("receipt.get('proposal_revision')==8","receipt.get('proposal_revision')==9")
        changed=changed.replace("installed.get('proposal_revision')==8","installed.get('proposal_revision')==9")
        changed=changed.replace("installed.get('payload_count')==982","installed.get('payload_count')==installation['expected_payload_count']")
    name=file.replace('m1_v8','m1_v9')
    text(name,changed)
    sources[name]={'source':str(OLD/file),'source_sha256':digest(OLD/file),
                   'sha256':digest(OUT/name),'reuse':'byte_identical' if original.encode()==changed.encode() else 'explicit_v9_delta'}

controller_source=Path(old['controller_preparation']['public_directory'])
for file in ('token_collector.py','setup_journal.py'):
    raw=(controller_source/file).read_bytes()
    (OUT/'controller').mkdir(exist_ok=True)
    (OUT/'controller'/file).write_bytes(raw)
    sources['controller/'+file]={'source':str(controller_source/file),'source_sha256':sha(raw),'sha256':sha(raw),'reuse':'byte_identical'}
controller=(controller_source/'controller.py').read_text(encoding='utf-8')
tree=ast.parse(controller)
lines=controller.splitlines(keepends=True)
for node in reversed(tree.body):
    if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('POLICY','ANCESTRY'):
        key=node.targets[0].id
        lines[node.lineno-1:node.end_lineno]=[key+' = '+repr(POLICY if key=='POLICY' else ANCESTRY)+'\n']
changed=''.join(lines).replace("'format':8","'format':9").replace("self.data['format'] != 8","self.data['format'] != 9")
changed=changed.replace("receipt.get('proposal_revision') == 8","receipt.get('proposal_revision') == 9").replace('V8_APPROVAL_REQUIRED','V9_APPROVAL_REQUIRED')
text('controller/controller.py',changed)
sources['controller/controller.py']={'source':str(controller_source/'controller.py'),'source_sha256':digest(controller_source/'controller.py'),
 'sha256':digest(OUT/'controller/controller.py'),'reuse':'policy_ancestry_format_approval_revision_only'}
text('controller/controller.diff',''.join(difflib.unified_diff(controller.splitlines(keepends=True),changed.splitlines(keepends=True),fromfile='v8/controller.py',tofile='v9/controller.py')))

commands=rebase(load(OLD/'proposed-commands.json'))
commands.update(status='DRAFT_NOT_AUTHORIZED_NOT_EXECUTED',tasks=ids,baseline_preflight=None,
    commands_executed=0,authorization_received=False,execution_blocked=True,
    package_pin_status='PENDING_NEW_NEXUS_QUALIFICATION_AND_FRESH_INSTALL_TARGET')
commands['service_selection_args']=[str(PORT) if v=='49807' else v for v in commands['service_selection_args']]
for step in commands['steps']:
    step['task_name']=ids[step['component']]['name']
    step['argv']=[str(PORT) if v=='49807' else v for v in step['argv']]
commands['counts'].update(provider_cumulative_admissions_max=9,
    conservative_cumulative_reservations_max=9,historical_confirmed_productive=2,
    prior_unconfirmed_reserved=1,maximum_confirmed_productive_if_all_new_confirm=8)
commands['guards']=[g.replace('8 cumulative admissions','9 cumulative reservations') for g in commands['guards']]
write('proposed-commands.json',commands)
planning=rebase(load(OLD/'planning-commands.json'))
for entry in planning.values():
    if isinstance(entry,dict) and 'argv' in entry:
        entry['argv']=[str(PORT) if v=='49807' else v for v in entry['argv']]
write('planning-commands.json',planning)

proposal=rebase(deepcopy(old))
proposal.update(revision=9,status='DRAFT_AWAITING_PIN_AND_QUALIFICATION',preparation_revision=1,
    prepared_at_utc=datetime.now(timezone.utc).isoformat(),paths=paths,execution_authorized=False)
proposal['authorization']={key:False for key in ('execution_authorized','provider_use_authorized_for_successor','service_actions_authorized_for_successor','proposed_limit_change_authorized')}
proposal['authorization']['scope']='Only a new explicit receipt for the final v9 snapshot can authorize this fresh successor. v7/v8 approvals do not carry over.'
proposal['predecessor']={'campaign_revision':8,'proposal':str(OLD/'m1-codex-campaign-proposal-v8.json'),
    'proposal_sha256':digest(OLD/'m1-codex-campaign-proposal-v8.json'),'closure':str(CLOSURE),'closure_sha256':digest(CLOSURE),
    'checkpoint_sha256':closure['controller_checkpoint_sha256'],'closure_commit':'6360d9e7',
    'faults_preserved':closure['faults_preserved'],'cumulative_reserved_carry_in':3,
    'historical_confirmed_productive':2,'v8_reserved_without_confirmed_productive':1,
    'observed_tokens_carry_in':45843,'billing_final':False,'no_reset_no_replay':True,
    'prior_ancestry':old['predecessor']}
proposal['topology'].update(origin=commands['origin'],task_names=ids,service_selection_args=commands['service_selection_args'],
    fresh_home_reason='Preserve the sealed v8 fault and request without replay. New IDs and homes require their own review; no old checkpoint is reset.')
proposal['finite_work']['maximum_cumulative_admissions']=9
proposal['finite_work']['counter_semantics']='Admission counters reserve before dispatch. Nine is a cumulative reservation allocation, not proof of nine inferences. Two historical productive admissions are confirmed; v8 retains one unconfirmed reserved slot; at most six new reservations are proposed.'
proposal['finite_work']['maximum_confirmed_productive_including_history']=8
proposal['token_accounting'].update(admissions_carry_in=3,cumulative_admissions_maximum=9,
    previous_preventive_threshold=200000,counter_semantics=proposal['finite_work']['counter_semantics'])
proposal['token_accounting']['algorithm'][0]='Carry in 3 conservative reservations and 45843 observed tokens once; preserve the v8 fault/checkpoint and earlier v7 ancestry. Reservation is not proof of inference.'
proposal['counting']={'conservative_carry_in_reservations':3,'historical_confirmed_productive':2,
    'v8_reserved_without_confirmed_productive':1,'new_reservations_maximum':6,'cumulative_reservations_maximum':9,
    'maximum_confirmed_productive_if_all_new_confirm':8,'observed_token_minimum_carry_in':45843,
    'v8_new_observed_tokens':0,'billing_final':False,'unused_slots_reassignable':False}
proposal['controller_preparation'].update(public_directory=str(OUT/'controller'),policy=POLICY,ancestry=ANCESTRY,
    controller_sha256=digest(OUT/'controller/controller.py'),collector_sha256=digest(OUT/'controller/token_collector.py'),
    status='DRAFT_V9_DELTA_NOT_YET_QUALIFIED')
for key in ('manifest','manifest_sha256','tests','qualified_cases','public_manifest'):
    proposal['controller_preparation'].pop(key,None)
proposal['controller_preparation']['approval_schema'].update(proposal_revision=9,policy=POLICY,ancestry=ANCESTRY)
proposal['controller_preparation']['approval_schema_is_template']=True
proposal['controller_preparation']['historical_v8_synthetic_cases']=proposal['controller_preparation'].pop('recorded_final_synthetic_tests',23)
proposal['controller_preparation'].pop('review',None)
proposal['controller_preparation']['v9_qualification']=None
proposal['transport_reuse'].update(status='DRAFT_COMPOSITION_REQUIRES_V9_QUALIFICATION',
    controller='V9 policy/ancestry/receipt/state-format delta from qualified v8 revision2; no v9 test result yet.')
proposal['publication_helper']['qualification_scope']='Historical qualification of the byte-identical helper, not a new v9 campaign result.'
for step in proposal['steps']:
    step['commands_are_reference_only']=True
    step['dispatch_rule']='Use only the frozen approved finite campaign wrappers; these CLI/API references are not standalone dispatch authority.'
proposal['steps'][0]['gate']='New Nexus GET check-recovery wheel and exact unchanged Core/Connector artifacts qualified and pinned; no personal configuration read.'
remote_step=next(s for s in proposal['steps'] if s['id']=='05-connector-root-review-finish')
remote_step['commands']=remote_step['commands'][:3]+['<QUALIFIED_PYTHON> -I -B m1_v9_remote_setup.py <exact proposal and approval selectors> transfer']
proposal['authorization_request_summary'].update(new_admissions_maximum=6,cumulative_admissions_maximum=9,
    conservative_cumulative_reservations_maximum=9,historical_confirmed_productive=2,
    prior_unconfirmed_reserved_slot=1,maximum_confirmed_productive_if_all_new_confirm=8,
    execution_authorized=False,product_install_prefix=str(INSTALL/'venv'))
proposal['authorization_request_summary']['counter_semantics']=proposal['finite_work']['counter_semantics']
proposal.pop('proposed_delta_from_v7',None)
proposal['proposed_delta_from_v8']={'new_fresh_cycle':True,'new_ids':True,'old_fault_and_reserved_slot_preserved':True,
    'carry_in_reservations':{'previous':2,'proposed':3},'cumulative_reservation_limit':{'previous':8,'proposed':9},
    'new_reservation_limit':6,'preventive_cumulative_tokens':200000,'operational_tolerance':700000,
    'reason':'v8 stopped before setup:test after a version-check response loss. New Nexus GET recovery must be installed and qualified. No old request replay or fault reset.',
    'approval_received':False,'same_service_scope':{'tasks':2,'explicit_actions':8,'implicit_scheduler_start_maximum':1}}
for key in ('previous_preparation','baseline_package_pins','baseline_preflight','package_proof_input'):
    proposal.pop(key,None)
proposal['historical_evidence']={'v8_manifest':{'path':str(OLD/'manifest.json'),'sha256':digest(OLD/'manifest.json')},
    'v8_closure':{'path':str(CLOSURE),'sha256':digest(CLOSURE)},
    'prior_evidence_references':old['evidence_references'],
    'scope':'Historical or unchanged-component evidence only; never a v9 runtime/test result.'}
proposal['evidence_references']={key:value for key,value in old['evidence_references'].items() if key in ('pty','fg_installed_branches')}
proposal['evidence_references']['scope']='Unchanged component references; v9 guards/controller/updated Nexus composition still require qualification.'
proposal['preflight_before_effects']=[v.replace('8 cumulative admissions','9 cumulative reservations').replace('for8 cumulative admissions','for9 cumulative reservations') for v in proposal['preflight_before_effects']]
proposal['package_pins'].update(status='PENDING_V9_NEXUS_QUALIFICATION',python=str(PYTHON),python_prefix=str(INSTALL/'venv'),files=[],qualified_reference_environment=None)
for module,pin in proposal['package_pins']['packages'].items():
    pin['package']=str(INSTALL/'venv/Lib/site-packages'/module)
    pin['installed_at_preparation']=False
    if module=='okto_nexus':
        pin.update(wheel=None,sha256=None,files=None,expected_payload_files=None,qualified_reference_package=None)
        pin['pending_reference_root']='C:/Users/jpamb/AppData/Local/Temp/m1-check-recovery-inopit5p'
proposal['package_pin_status']={'current':'PENDING_NEW_NEXUS_AND_FRESH_TARGET','required':'Qualified new Nexus wheel, exact package maps, fresh dependency target, finite guard qualification, then new explicit approval before offline product installation.'}

# Installer is a blocked draft: no pip/env/dependency preparation is run here.
installer=OLD_INSTALLER.read_text(encoding='utf-8')
tree=ast.parse(installer); lines=installer.splitlines(keepends=True)
wheels={m:{k:v for k,v in p.items() if k in ('wheel','sha256','files')} for m,p in proposal['package_pins']['packages'].items()}
for node in reversed(tree.body):
    if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name):
        name=node.targets[0].id
        if name in ('ROOT','CAMPAIGN','POLICY','ANCESTRY','WHEELS'):
            value=repr(str(INSTALL)) if name=='ROOT' else repr(str(CAMPAIGN)) if name=='CAMPAIGN' else repr({'POLICY':POLICY,'ANCESTRY':ANCESTRY,'WHEELS':wheels}[name])
            if name in ('ROOT','CAMPAIGN'):value='Path('+value+')'
            lines[node.lineno-1:node.end_lineno]=[name+' = '+value+'\n']
installer=''.join(lines).replace('M1 v8','M1 v9').replace('current v8 proposal','current v9 proposal').replace("proposal['revision'] == 8","proposal['revision'] == 9").replace("approval['proposal_revision'] == 8","approval['proposal_revision'] == 9").replace("'proposal_revision': 8","'proposal_revision': 9")
installer=installer.replace('def install(args):\n','FINAL_PINS_BOUND = False  # Root must bind qualified v9 pins and requalify before freeze.\nEXPECTED_PAYLOAD_COUNT = None\n\ndef install(args):\n    fail_unless(FINAL_PINS_BOUND, \'V9_FINAL_PINS_REQUIRED\')\n')
installer=installer.replace('total == 982','total == EXPECTED_PAYLOAD_COUNT').replace("'payload_count': 982","'payload_count': EXPECTED_PAYLOAD_COUNT")
text('installation/timed_install.py',installer)
proposal['base06_installation']={'status':'DRAFT_TARGET_NOT_PREPARED_NOT_AUTHORIZED','python':str(PYTHON),'python_prefix':str(INSTALL/'venv'),
    'script':str(INSTALL/'timed_install.py'),'script_sha256':digest(INSTALL/'timed_install.py'),
    'requirements_sha256':None,'dependency_manifest_sha256':None,'expected_payload_count':None,
    'result':str(INSTALL/'installation-result.json'),'reservation':str(INSTALL/'installation-reserved.json'),
    'products_installed':False,'dependencies_prepared':False,
    'invocation':[str(PYTHON),'-I','-B',str(INSTALL/'timed_install.py'),'--proposal','<FINAL_V9_PROPOSAL_PATH>',
        '--expected-proposal-sha256','<FINAL_V9_PROPOSAL_SHA256>','--approval-path','<ACTUAL_V9_APPROVAL_RECEIPT>',
        '--approval-sha256','<ACTUAL_V9_RECEIPT_SHA256>','--execute']}
bundle=proposal['execution_bundle']
bundle.update(status='DRAFT_NOT_QUALIFIED',directory=str(OUT),qualification_scope='Preparation copies and static compile only; no v9 gates or runtime qualification executed.')
for key,row in bundle['files'].items():
    old_path=Path(old['execution_bundle']['files'][key]['path'])
    if old_path.parent==OLD:
        path=OUT/old_path.name.replace('m1_v8','m1_v9')
    elif key=='setup_monitor':path=OUT/'controller/setup_journal.py'
    elif key=='timed_install':path=INSTALL/'timed_install.py'
    elif key in ('install_requirements','install_dependency_manifest'):
        row.update(path=str(INSTALL/old_path.name),sha256=None,status='PENDING_PREPARATION');continue
    else:
        # Reuse qualified immutable helpers/dependency payloads at original origins.
        path=old_path
    row.update(path=str(path),sha256=digest(path))
bundle['commands']={'path':str(OUT/'proposed-commands.json'),'sha256':digest(OUT/'proposed-commands.json')}
proposal['blocking_preconditions_before_execution_request']=[
    'Bind and qualify the new Nexus GET check-recovery wheel; never use the historical fdb8 wheel as the successor fix.',
    'Prepare a fresh dependency-only installation target and requalify its pinned timed installer; do not reuse the executed v8 installation.',
    'Qualify v9 controller carry-in/resume/approval guards and touched entry gates without provider/native effects.',
    'Review/qualify composition against the new exact installed product pins, preserving reusable component limitations.',
    'Observe exact new task absence, empty campaign paths and proposed port availability immediately before any future effect.',
    'Freeze final manifest/proposal hash and obtain one explicit v9 approval. v7/v8 approvals do not authorize this draft.']
proposal['preconditions_after_approval_before_effects']=[v.replace('verify982 payloads','verify the exact new payload set') for v in proposal['preconditions_after_approval_before_effects']]
write('m1-codex-campaign-proposal-v9.json',proposal)
write('source-map.json',sources)
write('identity-preparation.json',{'status':'DERIVED_ONLY_NOT_TASK_PREFLIGHT','source':str(identity_path),'source_sha256':digest(identity_path),
 'prior_v8_names_reproduced':True,'new_names_distinct':True,'tasks':ids,'principal_sha256':sha(principal.encode()),
 'process_identity_query_only':True,'scheduler_queries':0,'scheduler_mutations':0,'child_processes':0,
 'credential_api_calls':0,'port':PORT,'port_checked':False,'port_reserved':False,'campaign_root_created':CAMPAIGN.exists()})
for name,path in [('v8-proposal.json',OLD/'m1-codex-campaign-proposal-v8.json'),('v8-closure.json',CLOSURE),
                 ('v8-qualification.json',REPO/'plans/agent_ops/evidence/r3-m1-v8-execution/qualification.json')]:
    (OUT/'history').mkdir(exist_ok=True)
    (OUT/'history'/name).write_bytes(Path(path).read_bytes())
write('delta-map.json',{
 'status':'PREPARATION_ONLY_UNQUALIFIED','controller':'Only policy/ancestry/state format/receipt revision changed; new cap6 retained, carry-in3 and cumulative9 are reservations.',
 'changed_scripts':{k:v['reuse'] for k,v in sources.items() if v['reuse']!='byte_identical'},
 'byte_identical_reuse':[k for k,v in sources.items() if v['reuse']=='byte_identical'],
 'external_reuse':['PTY V5 + owned Job + pinned pywinpty at original origin','qualified Codex binary selection (not executed)','Connector/Core qualified wheel artifacts (not installed here)'],
 'must_qualify':['v9 controller refuses old receipt/state and preserves carry-in on resume','carry-in3 plus six reservations is9, seventh new refuses','cumulative tokens45843 plus setup/work guarded at200000','missing/wrong v9 receipt/proposal/pins refuse before effects','fresh timed-install guards with new Nexus pin and package count'],
 'no_status_inheritance':'Historical tests are references only. No v9 test/runtime result is claimed.'})
compiled=[]
for path in OUT.rglob('*.py'):
    compile(path.read_bytes(),str(path),'exec');compiled.append(path.relative_to(OUT).as_posix())
assert POLICY['carry_in_admissions']+POLICY['max_new_admissions']==POLICY['max_cumulative_admissions']==9
assert len(commands['steps'])==8 and not any('--force' in s['argv'] for s in commands['steps'])
assert len(ids)==2 and not CAMPAIGN.exists() and not (INSTALL/'venv').exists()
assert digest(CLOSURE)==ANCESTRY['closure_sha256'] and digest(OLD/'m1-codex-campaign-proposal-v8.json')==proposal['predecessor']['proposal_sha256']
write('preparation-checks.json',{'status':'STATIC_PREPARATION_ONLY','compiled_files':compiled,
 'native_cli_calls':0,'provider_calls':0,'service_calls':0,'credential_reads':0,'campaign_root_created':False,
 'products_installed':False,'environment_created':False,'originals_unchanged':True,
 'reserves_cumulative':9,'confirmed_productive_history':2,'new_maximum':6,'billing_final':False,
 'tests_executed':0,'live_task_or_port_preflight':False})
print(json.dumps({'draft':str(OUT),'campaign_root':str(CAMPAIGN),'port':PORT,'tasks':ids,
                  'proposal_sha256':digest(OUT/'m1-codex-campaign-proposal-v9.json'),'status':proposal['status']}))
