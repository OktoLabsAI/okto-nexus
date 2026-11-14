"""Build only a fresh, unauthorized v11 base; no campaign effects or product install."""
from pathlib import Path
import ast,copy,ctypes,difflib,hashlib,importlib.util,json,os,zipfile
from ctypes import wintypes
from datetime import datetime,timezone

R=Path(__file__).resolve().parent;D=R/'draft';I=D/'installation'
OLD=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v10-bundle-pscf18t5');O=OLD/'draft'
PORT=57589  # Proposed only, no listener/Scheduler operation in preparation.
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def text(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(value.encode())
def write(p,value):text(p,json.dumps(value,indent=2,ensure_ascii=False)+'\n')
def rebase(value):
    if isinstance(value,dict):return {k:rebase(v) for k,v in value.items()}
    if isinstance(value,list):return [rebase(v) for v in value]
    if isinstance(value,str):
        value=value.replace(str(OLD),str(R)).replace(OLD.as_posix(),R.as_posix())
        value=value.replace('m1v10-','m1v11-').replace('m1_v10_','m1_v11_').replace('proposal-v10.json','proposal-v11.json')
        value=value.replace('http://127.0.0.1:56237',f'http://127.0.0.1:{PORT}')
        return str(PORT) if value=='56237' else value
    return value
def assignments(source,values):
    lines=source.splitlines(True);found=set()
    for node in reversed(ast.parse(source).body):
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            name=node.targets[0].id
            if name in values:lines[node.lineno-1:node.end_lineno]=[name+' = '+values[name]+'\n'];found.add(name)
    assert found==set(values)
    return ''.join(lines)
def names(paths,principal):
    home=os.path.normcase(str(Path(paths['server_home']).resolve()))
    db=os.path.normcase(str((Path(paths['server_home'])/'nexus.db').resolve()))
    state=os.path.normcase(str(Path(paths['connector_state']).resolve()))
    h=lambda v:hashlib.sha256(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    values={'nexus':('OktoNexus-server-',h(['server',home,db,principal[4:]])),
            'connector':('OktoNexus-connector-',h(['connector',state,principal]))}
    return {k:{'name':prefix+digest,'instance_id':'svc_'+digest,'exists':None,'absence_observed':False} for k,(prefix,digest) in values.items()}

assert not D.exists() and not (R/'campaign').exists()
assert sha(O/'m1-codex-campaign-proposal-v10.json')=='90c2ed2ca18e7fd86380c614e516a5f8975af2a2052b56a3609004be4814405a'
closure_path=OLD/'campaign/public/closure.json';closure=read(closure_path)
assert sha(closure_path)=='c3d3e5f5b5b8fbec2c86ea711350ba1a7de44022e568b1c6cfc4fe2e93ff6db0'
assert closure['controller_checkpoint_sha256']=='8edf98687a374e607a662f00a21cc05e6461e87e4fd8118bf6fc6ecb52948f3e'
assert closure['cumulative_reserved_admissions']==6 and closure['carry_in_minimum_observed_tokens']==89473
assert closure['new_confirmed_productive_admissions']==1 and not closure['replay_allowed'] and not closure['billing_final']
old=read(O/'m1-codex-campaign-proposal-v10.json');p=rebase(old)
policy={'revision':11,'carry_in_admissions':6,'carry_in_tokens':89473,'max_cumulative_admissions':11,
        'max_new_admissions':5,'preventive_cumulative_tokens':200000,'operational_tolerance':700000,'deadline_seconds':120}
ancestry={'closure_sha256':sha(closure_path),'checkpoint_sha256':closure['controller_checkpoint_sha256'],
          'predecessor_faults':closure['faults_preserved'],'prior_ancestry':copy.deepcopy(old['controller_preparation']['ancestry'])}
identity=Path(r'D:/Projetos/Techridy/okto-nexus-connector/src/okto_nexus_connector/platform/service_identity.py')
assert sha(identity)=='f61f0d437fa6b0b2ffce1cb7d76e256ae096c21cb9ee28661f3bf85b06ce25d5'
node=next(n for n in ast.parse(identity.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='effective_principal')
namespace={'ctypes':ctypes,'wintypes':wintypes,'os':os}
exec(compile(ast.Module(body=[node],type_ignores=[]),str(identity),'exec'),namespace)
principal=namespace['effective_principal']();assert principal.startswith('sid:')
assert all(names(old['paths'],principal)[k]['name']==old['topology']['task_names'][k]['name'] for k in ('nexus','connector'))
tasks=names(p['paths'],principal)
assert all(tasks[k]['name']!=old['topology']['task_names'][k]['name'] for k in tasks)
D.mkdir();I.mkdir()
sources={};files={}
for key,item in old['execution_bundle']['files'].items():
    source=Path(item['path']);assert sha(source)==item['sha256']
    if key.startswith('controller_') or key=='work':continue  # Await independently qualified cache/publication candidate.
    if not source.is_relative_to(O):files[key]=copy.deepcopy(item);continue
    if source.suffix!='.py':continue
    relative=Path(str(source.relative_to(O)).replace('m1_v10_','m1_v11_'))
    target=D/relative;original=source.read_text();changed=original.replace('m1_v10_','m1_v11_').replace('m1v10-','m1v11-')
    if key=='context':
        changed=changed.replace("get('revision')==10","get('revision')==11").replace("get('proposal_revision')==10","get('proposal_revision')==11")
    text(target,changed)
    files[key]={'path':str(target),'sha256':sha(target)}
    sources[relative.as_posix()]={'source_path':str(source),'source_sha256':sha(source),'sha256':sha(target),
        'change':'byte-identical' if original==changed else 'revision/module/request labels only'}
    if changed!=original:text(D/'diffs'/(target.name+'.diff'),''.join(difflib.unified_diff(original.splitlines(True),changed.splitlines(True),fromfile='v10/'+source.name,tofile='v11/'+target.name)))

commands=rebase(read(O/'proposed-commands.json'))
commands.update(status='PREPARED_BASE_PENDING_OBSERVER_NOT_AUTHORIZED',tasks=tasks,execution_authorized=False,
    authorization_received=False,execution_blocked=True,baseline_preflight=None,port_availability_observed=False,
    package_pin_status='SAME_QUALIFIED_WHEELS_NEW_DEPENDENCY_TARGET_PENDING')
for s in commands['steps']:s['task_name']=tasks[s['component']]['name']
commands['counts'].update(provider_new_admissions_max=5,provider_cumulative_admissions_max=11,
    conservative_cumulative_reservations_max=11,historical_confirmed_productive=4,
    maximum_confirmed_productive_if_all_new_confirm=9)
write(D/'proposed-commands.json',commands)
planning=rebase(read(O/'planning-commands.json'))
planning.update(status='PREPARED_BASE_PENDING_OBSERVER_NOT_AUTHORIZED',execution_authorized=False,execution_blocked=True,commands_executed=0)
recipe=rebase(read(O/'remote-canonical-recipe.json'))
recipe['source_ancestry']={'recipe':str(O/'remote-canonical-recipe.json'),'sha256':sha(O/'remote-canonical-recipe.json'),
    'change':'Fresh v11 root/origin/labels only; canonical API/credential/cleanup semantics unchanged.'}
write(D/'remote-canonical-recipe.json',recipe)
planning['remote_recipe']={'path':str(D/'remote-canonical-recipe.json'),'sha256':sha(D/'remote-canonical-recipe.json')}
write(D/'planning-commands.json',planning)
for key,name in [('planning_commands','planning-commands.json'),('remote_canonical_recipe','remote-canonical-recipe.json')]:files[key]={'path':str(D/name),'sha256':sha(D/name)}

pins={};payloads=[]
for name,previous in old['package_pins']['packages'].items():
    wheel=Path(previous['wheel']);assert sha(wheel)==previous['sha256']
    with zipfile.ZipFile(wheel) as z:
        members=[n for n in z.namelist() if n.startswith(name+'/') and not n.endswith('/')]
        assert len(members)==len(set(members)) and all('..' not in n.split('/') for n in members)
        values={n:hashlib.sha256(z.read(n)).hexdigest() for n in members}
    pins[name]={'wheel':str(wheel),'sha256':sha(wheel),'files':len(values)}
    payloads.extend({'path':str(I/'venv/Lib/site-packages'/n),'sha256':h} for n,h in sorted(values.items()))
assert len(payloads)==sum(v['files'] for v in pins.values())==983
installer=(O/'installation/timed_install.py').read_text()
installer=assignments(installer,{'ROOT':f'Path({str(I)!r})','CAMPAIGN':f'Path({str(R/"campaign")!r})',
    'POLICY':repr(policy),'ANCESTRY':repr(ancestry),'WHEELS':repr(pins),
    'FINAL_PINS_BOUND':'False  # Dependency-only target verification pending; no real approval.',
    'EXPECTED_PAYLOAD_COUNT':'983'})
for a,b in [('M1 v10','M1 v11'),('current v10','current v11'),('V10_FINAL_PINS_REQUIRED','V11_FINAL_PINS_REQUIRED'),
            ("proposal['revision'] == 10","proposal['revision'] == 11"),("approval['proposal_revision'] == 10","approval['proposal_revision'] == 11"),
            ("'proposal_revision': 10","'proposal_revision': 11")]:installer=installer.replace(a,b)
text(I/'timed_install.py',installer)
for name in ('prepare_dependencies.py','probe_direct_interpreter.py','test_timed_install.py'):
    value=(O/'installation'/name).read_text()
    if name=='prepare_dependencies.py':
        value=value.replace("m1-v9-preparation-t4xaqhca/draft/installation/dependency-manifest.json",'m1-v10-bundle-pscf18t5/draft/installation/dependency-manifest.json')
        value=value.replace('6520870894d0b01e7205569816ddc6aae22b5c6e6a9474fc031fd7712d228b96','b5f9b58b99e4948e5bf53a152fa5ec8344b897cc4ec1d037f39945efdb668906')
    if name=='test_timed_install.py':
        value=value.replace("'revision': 10","'revision': 11").replace("'proposal_revision': 10","'proposal_revision': 11").replace('test_exact_v10_receipt','test_exact_v11_receipt')
    text(I/name,value)
text(R/'requirements_lf.py',(OLD/'requirements_lf.py').read_text())
spec=importlib.util.spec_from_file_location('requirements_lf_v11',R/'requirements_lf.py')
renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
renderer.write_new_requirements(I/'products-requirements.txt',{n:{'wheel':v['wheel'],'sha256':v['sha256']} for n,v in pins.items()})
assert b'\r' not in (I/'products-requirements.txt').read_bytes()

semantics='Six prior reservations remain charged, including four confirmed productive admissions, one v8 unconfirmed reservation and one v9 reserved work with no native admission. V10 added only its local setup reservation; its useful work never reserved. At most five new reservations keep the cumulative ceiling at eleven. No refunds, unused-slot reassignment or hidden retry.'
p.update(revision=11,status='PREPARED_BASE_PENDING_OBSERVER_AND_DEPENDENCIES_NOT_AUTHORIZED',
    prepared_at_utc=datetime.now(timezone.utc).isoformat(),final_proposal=False,execution_authorized=False,
    qualification_status='PENDING_V11_COMPOSITION',blocking_preconditions=[
        'Qualified cache/warmup observer and final-publication handling candidate, then actual v11 composition tests.',
        'New dependency-only environment, actual LF/wheel/entry verification and frozen root review.',
        'Explicit new approval bound to final v11 proposal before any product install or campaign effect.',
        'Fresh task/home/port preflight after approval; no current availability claim.'])
p.pop('readonly_preflight',None)
p['authorization']={k:False for k in ('execution_authorized','provider_use_authorized_for_successor','service_actions_authorized_for_successor','installation_authorized','approval_receipt_created','direct_user_approval_received')}
p['authorization']['scope']='Preparation only. Closed v10 and earlier approvals confer no execution authority on v11.'
p['counting'].update(conservative_carry_in_reservations=6,historical_confirmed_productive=4,new_reservations_maximum=5,
    cumulative_reservations_maximum=11,maximum_confirmed_productive_if_all_new_confirm=9,observed_token_minimum_carry_in=89473,
    v10_new_observed_tokens=21815,v10_useful_work_reserved=False)
p['finite_work'].update(maximum_productive_admissions=5,maximum_cumulative_admissions=11,counter_semantics=semantics,
    maximum_confirmed_productive_including_history=9,
    allocation='Exactly the finite selected allocation permits at most five new reservations: one local setup test and four work requests (useful plus continuation in each lane). Remote bootstrap/key transfer has zero productive model turns. No unused-slot reassignment, hidden retry or extra setup inference.')
p['request_ids']['productive_setup']=['m1v11-local-setup']
p['request_ids']['connector_setup_reservation_condition']='The selected remote setup path is nonproductive. Unexpected model consumption stops the campaign; no sixth reservation or inferred extra turn is allowed.'
p['controller_preparation']={'status':'PENDING_QUALIFIED_CACHE_OBSERVER_COMPOSITION','policy':policy,'ancestry':ancestry,
    'public_directory':str(D/'controller'),'execution_blocked':True,'approval_receipt_created':False,
    'controller_sha256':None,'collector_sha256':None,'observer_sha256':None}
p['topology'].update(origin=commands['origin'],task_names=tasks,port_availability_observed=False,
    fresh_home_reason='Preserve all v10 and earlier faults/receipts; never reset or replay their roots.')
p['token_accounting'].update(observed_tokens_carry_in=89473,admissions_carry_in=6,new_admissions_maximum=5,
    cumulative_admissions_maximum=11,proposed_remaining_observed_headroom=110527,counter_semantics=semantics)
p['token_accounting']['required_invariants']=[s.replace('67658','89473') for s in p['token_accounting']['required_invariants']]
p['package_pins'].update(status='QUALIFIED_WHEELS_DEPENDENCY_TARGET_PENDING',files=payloads,
    expected_product_payload_count=983,expected_total_pin_count=None,
    python=str(I/'venv/Scripts/python.exe'),python_prefix=str(I/'venv'))
p['package_pins'].pop('pin_count_semantics',None)
for name,pin in pins.items():
    p['package_pins']['packages'][name].update(pin,package=str(I/'venv/Lib/site-packages'/name),installed_at_preparation=False)
p['base06_installation'].update(status='DEPENDENCY_TARGET_PENDING_NOT_AUTHORIZED',dependencies_prepared=False,
    products_installed=False,installer_enabled=False,script=str(I/'timed_install.py'),script_sha256=sha(I/'timed_install.py'),
    requirements=str(I/'products-requirements.txt'),requirements_sha256=sha(I/'products-requirements.txt'),effects_executed=0,
    guard='No product install has executed. Final pins gate remains false until dependency proof; real exact v11 approval remains mandatory before reservation.')
for key in ('dependency_manifest_sha256','dependency_preparation_sha256','direct_interpreter_qualification'):p['base06_installation'].pop(key,None)
p['base06_installation']['invocation']=[str(I/'venv/Scripts/python.exe'),'-I','-B',str(I/'timed_install.py'),
    '--proposal',str(D/'m1-codex-campaign-proposal-v11.json'),'--expected-proposal-sha256','<FINAL_V11_PROPOSAL_SHA256>',
    '--approval-path','<REAL_V11_USER_RECEIPT>','--approval-sha256','<REAL_RECEIPT_SHA256>','--execute']
bundle=p['execution_bundle'];bundle.update(status='PENDING_OBSERVER_AND_V11_QUALIFICATION',directory=str(D),files=files,
    commands={'path':str(D/'proposed-commands.json'),'sha256':sha(D/'proposed-commands.json')},
    qualification_scope='Base rebased only. Prior v10/component proofs remain historical; v11 cache/controller/limit5 composition not yet qualified.',
    gate='Exact new v11 approval and completed installation proof remain mandatory; incomplete bundle also blocks every runtime entry.')
bundle.pop('final_gate_reports',None)
bundle['remote_transfer_order']['stop_order_module']=files['remote_stop_order']
bundle['final_pin_schema']['python']=str(I/'venv/Scripts/python.exe');bundle['final_pin_schema']['python_prefix']=str(I/'venv')
p['steps'][0]['gate']='Same qualified product wheels; new dependency target and cache/warmup observer composition must pass before final freeze.'
p['predecessor']={'closure':str(closure_path),'closure_sha256':sha(closure_path),'checkpoint_sha256':closure['controller_checkpoint_sha256'],
    'original_approved_v10_proposal_sha256':sha(O/'m1-codex-campaign-proposal-v10.json'),'historical_evidence_unchanged':True,'new_execution_authority_inherited':False}
p['acceptance']={'promoted':False,'m1_complete':False,'base06_measured':False,'scope':'Offline preparation only; no product install/provider/service effect.'}
write(D/'m1-codex-campaign-proposal-v11.json',p)
write(D/'entrypoint-source-map.json',sources)
write(D/'wheel-payload-pins.json',{'status':'SAME_QUALIFIED_WHEEL_BYTES_VERIFIED_NEW_TARGET_EMPTY','packages':pins,'files':payloads,
    'product_payload_count':983,'interpreter_pin_pending':True,'products_installed_in_target':False})
write(D/'identity-preparation.json',{'source':str(identity),'source_sha256':sha(identity),'principal_sha256':hashlib.sha256(principal.encode()).hexdigest(),
    'prior_v10_names_reproduced':True,'tasks':tasks,'new_names_distinct':True,'process_sid_only':True,'scheduler_queries':0,
    'scheduler_mutations':0,'port_checks':0,'campaign_directory_created':False})
write(D/'scope-delta.json',{'from_revision':10,'to_revision':11,'carry_reservations':[5,6],'carry_minimum_observed_tokens':[67658,89473],
    'maximum_new_reservations':[6,5],'maximum_cumulative_reservations':[11,11],'nominal_productive_allocation':5,
    'remote_setup_productive_turns':0,'unchanged':['three product wheels','Codex build/path/provider-home selection','200000 preventive','700000 tolerance','120 seconds','2 tasks/8 lifecycle actions/at most1 implicit Connector start','no forced service stop/replay'],
    'new':['fresh roots/task names/port/dependency-only target','pending qualified schema warmup/cache observer','pending final-publication error handling'],
    'allocation_rebase_required':['token_collector initial max_requests6→5','token_collector checkpoint validation6→5','legacy_controller len(requests)>6→5','legacy_controller summary>=6→5','POLICY max_new6→5'],
    'authorization_inferred':False,'product_install_executed':False})
for path in D.rglob('*.py'):compile(path.read_bytes(),str(path),'exec')
print(json.dumps({'root':str(R),'status':p['status'],'proposal_sha256':sha(D/'m1-codex-campaign-proposal-v11.json'),
    'port_proposed_not_checked':PORT,'tasks':tasks,'payloads_verified':983,'requirements_lf_only':True}))
