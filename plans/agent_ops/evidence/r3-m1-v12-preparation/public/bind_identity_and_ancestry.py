from pathlib import Path
import ast,ctypes,hashlib,json,os,re,shutil
from ctypes import wintypes
from datetime import datetime,timezone
R=Path(__file__).resolve().parent;D=R/'draft';I=D/'installation'
OLD=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v11-bundle-racan37z')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def write(p,v):p.write_bytes((json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode())
p=read(D/'m1-codex-campaign-proposal-v12.json');old=read(OLD/'draft/m1-codex-campaign-proposal-v11.json')
closure=OLD/'campaign/public/closure.json';assert sha(closure)=='849f63e4d4710588a10db379e63f2401a4fb2789db978addb06ecd22a23f2883'
c=read(closure)
assert c['controller_checkpoint_sha256']=='5031daa866e98e35ea4172bac8f90e09db3bf6be6db0b68727a7fbf6e2d8e78c'
assert c['cumulative_reserved_admissions']==7
A={'closure_sha256':sha(closure),'checkpoint_sha256':c['controller_checkpoint_sha256'],
   'predecessor_faults':['OBSERVATION_UNKNOWN','DEADLINE120'],'prior_ancestry':old['controller_preparation']['ancestry']}
H=D/'preparation-history/v11'
for name in ('closure.json','final-presence-reconciled.json'):
 f=OLD/'campaign/public'/name;shutil.copyfile(f,H/name)
p['controller_preparation']['ancestry']=A
p['predecessor'].update(status=c['status'],closure_path=str(closure),closure_sha256=sha(closure),
 checkpoint_sha256=A['checkpoint_sha256'],faults_preserved=A['predecessor_faults'],unsettled_reservations_preserved=1,
 carry_in_admissions=7,carry_in_minimum_observed_tokens=89473)
for f in (D/'controller/controller.py',D/'controller/legacy_controller.py',I/'timed_install.py'):
 s=f.read_text();s=re.sub(r'^ANCESTRY = .*$', 'ANCESTRY = '+repr(A),s,flags=re.M);f.write_bytes(s.encode())
identity=Path('D:/Projetos/Techridy/okto-nexus-connector/src/okto_nexus_connector/platform/service_identity.py')
assert sha(identity)=='f61f0d437fa6b0b2ffce1cb7d76e256ae096c21cb9ee28661f3bf85b06ce25d5'
node=next(n for n in ast.parse(identity.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='effective_principal')
ns={'ctypes':ctypes,'wintypes':wintypes,'os':os};exec(compile(ast.Module(body=[node],type_ignores=[]),str(identity),'exec'),ns)
principal=ns['effective_principal']();assert principal.startswith('sid:')
def names(paths):
 h=lambda v:hashlib.sha256(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
 home=os.path.normcase(str(Path(paths['server_home']).resolve()));db=os.path.normcase(str((Path(paths['server_home'])/'nexus.db').resolve()))
 state=os.path.normcase(str(Path(paths['connector_state']).resolve()))
 pairs={'nexus':('OktoNexus-server-',h(['server',home,db,principal[4:]])), 'connector':('OktoNexus-connector-',h(['connector',state,principal]))}
 return {k:{'name':prefix+x,'instance_id':'svc_'+x,'exists':None,'absence_observed':False} for k,(prefix,x) in pairs.items()}
assert names(old['paths'])==old['topology']['task_names']
tasks=names(p['paths']);assert all(tasks[k]['name']!=old['topology']['task_names'][k]['name'] for k in tasks)
PORT=58631
def port(v):
 if isinstance(v,str):return v.replace('57589',str(PORT))
 if isinstance(v,list):return [port(x) for x in v]
 if isinstance(v,dict):return {k:port(x) for k,x in v.items()}
 return v
p=port(p);p['prepared_at_utc']=datetime.now(timezone.utc).isoformat()
p['topology'].update(task_names=tasks,port_availability_observed=False,fresh_home_reason='Preserve v11 and all earlier faults, unresolved reservations and receipts; no prior root reset or replay.')
p['counting'].update(conservative_carry_in_reservations=7,new_reservations_maximum=5,cumulative_reservations_maximum=12,
 observed_token_minimum_carry_in=89473,v11_new_observed_tokens=0,v11_new_reservations=1,v11_setup_test_submitted=False,v11_unsettled_reservations_preserved=1)
p['token_accounting'].update(admissions_carry_in=7,new_admissions_maximum=5,cumulative_admissions_maximum=12,observed_tokens_carry_in=89473)
p['authorization'].pop('technical_v11_binding_created',None)
p['blocking_preconditions']=['Validated strict local-only cleanup successor branch','Final dependency/source/metadata/entry checks and root technical binding']
for name in ('proposed-commands.json','planning-commands.json','remote-canonical-recipe.json'):
 q=port(read(D/name));q['status']='DRAFT_V12_COMPOSITION_PENDING'
 if name=='proposed-commands.json':
  q['tasks']=tasks
  for step in q['steps']:step['task_name']=tasks[step['component']]['name']
  q['counts'].update(provider_new_admissions_max=5,provider_cumulative_admissions_max=12,conservative_cumulative_reservations_max=12)
 if name=='planning-commands.json':q['cleanup']='Canonical normal component stop/drain, physical owner exit and task proof, then one uninstall bound to cleanup proof; no separate work-close dispatch or force.'
 if name=='remote-canonical-recipe.json':
  q['source_ancestry']={'recipe':str(OLD/'draft/remote-canonical-recipe.json'),'sha256':sha(OLD/'draft/remote-canonical-recipe.json'),'change':'V12 identity and explicit carry7/new5/cumulative12 only; no token budget increase.'}
 write(D/name,q)
write(D/'identity-preparation.json',{'source':str(identity),'source_sha256':sha(identity),
 'principal_sha256':hashlib.sha256(principal.encode()).hexdigest(),'prior_v11_names_reproduced':True,'tasks':tasks,
 'new_names_distinct':True,'process_sid_only':True,'scheduler_queries':0,'scheduler_mutations':0,'port_checks':0,'campaign_directory_created':False})
p['execution_bundle']['commands']={'path':str(D/'proposed-commands.json'),'sha256':sha(D/'proposed-commands.json')}
write(D/'m1-codex-campaign-proposal-v12.json',p)
state=read(R/'preparation-state.json');state.update(status='DRAFT_CLEANUP_AND_QUALIFICATION_PENDING',ancestry=A)
state['pending']=['cleanup branch','dependency-only preparation','affected checks/final pins'];write(R/'preparation-state.json',state)
print(json.dumps({'root':str(R),'closure_sha256':sha(closure),'task_names':tasks,'port':PORT,'campaign_absent':not (R/'campaign').exists()}))
