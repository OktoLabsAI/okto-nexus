"""Offline composition only: pinned source copies and finite amendment metadata."""
from pathlib import Path
import hashlib,json,shutil,sys
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def pin(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def save(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
S=HERE.parent;B=S.parent;old=read(S/'work-request11/amendment.json')
P=read(old['original']['proposal'])
freeze=Path('C:/Users/jpamb/AppData/Local/Temp/m1-request12-controller-875t5rwb/runtime-freeze.json')
assert sha(freeze)=='704cab462343ed0773990917d1240d1fbe8aec95782f93a9183164c022fc1c56'
(HERE/'modules').mkdir(exist_ok=True)
for name,entry in read(freeze)['runtime'].items():
    assert sha(entry['path'])==entry['sha256']
    target=HERE/'modules'/name
    if not target.exists():shutil.copyfile(entry['path'],target)
    assert sha(target)==entry['sha256']
installed=read(HERE/'package/installation.json')
sys.path.insert(0,str(HERE))
from request_context import current_commands
C=current_commands(read(P['execution_bundle']['commands']['path']),installed['python'])
assert len(C['steps'])==4
save(HERE/'commands.json',C)
force=Path('C:/Users/jpamb/AppData/Local/Temp/m1-request11-authorized-force-vjlixwq8')
basis={'checkpoint':pin(S/'work-request11/private/controller.json'),
    'companion':pin(force/'closure-companion.json'),'accounting':pin(force/'accounting-derived.json'),
    'adoption':old['basis']['adoption'],'controller_freeze':pin(freeze)}
history=old['expected_historical_grants']+[
    {'grant_id':'grant_167e8f055e0f4444b9a429ca5a4ce686','expires_at':'2026-11-14T20:08:18.408235Z',
     'max_executions':3,'minimum_used_executions':0,'revision':1}]
save(HERE/'historical-grants.json',history)
basis['historical_grants']=pin(HERE/'historical-grants.json')
cp=read(basis['checkpoint']['path'])
policy={**cp['policy'],'carry_in_admissions':11,'carry_in_tokens':272648,'max_new_admissions':2}
names={'context':'request_context.py','entry':'request_entry.py','invoke':'invoke_request.py',
    'common':'driver_common.py','work':'local_work.py','cohort':'cohort.py','lifecycle':'lifecycle.py',
    'authorize':'authorize_local.py','upgrade':'upgrade_environment.py','adopt':'adopt_local.py','observation_helpers':'m1_v14_observation.py',
    'close':'close_campaign.py','final_presence':'confirm_final_presence.py'}
sources={key:pin(HERE/name) for key,name in names.items()}
sources.update({p.stem:pin(p) for p in (HERE/'modules').glob('*.py')})
overrides={'lifecycle':sources['lifecycle'],'work':sources['work'],
    'root_driver_authorize_local':sources['authorize'],'root_driver_adopt_local':sources['adopt'],
    'root_driver_common':sources['common'],'root_driver_observation':sources['cohort'],
    'root_driver_confirm_cleanup':sources['cohort'],'root_driver_confirm_final_presence':sources['final_presence'],
    'root_driver_close_campaign':sources['close'],'root_driver_upgrade_environment':sources['upgrade'],
    'controller_token_collector':sources['token_collector']}
checkpoint=Path(old['initial_work_checkpoint']['path'])
projection=read(checkpoint)
assert projection['session_id']=='ses_abdc7fd9ab15ccadc06fe7aec6b9f247'
assert projection['work']['client_intent_id']=='m1v14-local-work-11'
value={'format':'okto.m1.v14.work-request12','execution_status':'OFFLINE_PREPARATION_ROOT_REVIEW_REQUIRED',
    'authority':'Technical amendment binding standing user authorization; no new human hash approval is claimed.',
    'campaign_root':str(B),'control_root':str(S),'work_root':str(HERE),'original':old['original'],
    'source_authority':{k:old['original'][k] for k in ('proposal_sha256','approval_sha256')},
    'basis':basis,'sources':sources,'bundle_overrides':overrides,'commands':pin(HERE/'commands.json'),
    'installation':pin(HERE/'package/installation.json'),'wheels':installed['wheels'],
    'policy':policy,'controller_ancestry':cp['ancestry'],
    'request_ids':{'useful':'m1v14-local-work-12','continuation':'m1v14-local-work-13'},
    'initial_work_checkpoint':pin(checkpoint),'predecessor_session_id':projection['session_id'],
    'expected_historical_grants':history,'future_force_authorized':False,
    'scope':'New local useful12 and continuation13 only after useful success; request11 remains FAILED history, never replayed.',
    'remote_DX40':'PENDING_NOT_SELECTED','Claude_Sonnet':'NOT_SELECTED',
    'initial_minimum_observed_tokens':272648,'initial_cumulative_reservations':11,'remaining_tolerance_tokens':427352,
    'observation_bounds':{'snapshot_seconds':1,'initialization_seconds':2,'poll_seconds':11,
        'freshness_seconds':12,'cadence_seconds':16,'target_start_seconds':0.2,'max_observed_requests':4},
    'startup':{'cli_timeout_seconds':45,'passive_observation_seconds':180,'repeat_start':False,
        'qualification':'CLI3 remains CLI3; only later exact READY identity can permit next stage. No SLA claim.'},
    'cleanup':'All supervisor parent/launcher/runtime retained handle exits plus native inactive and canonical owner absence; no future force.',
    'native_decision_path':str(HERE/'private/native-decision.json'),
    'no_effects_during_preparation':True}
home=B/'campaign/nexus-home'
run=read(home/'service-run.json');shutdown=read(home/'service-shutdown.json')
assert run['state']=='drained' and shutdown['state']=='DRAINED' and run['generation']==shutdown['generation']
value['migration']={'run':pin(home/'service-run.json'),'shutdown':pin(home/'service-shutdown.json'),
    'source_context':pin(home/'service-context.json'),'generation':run['generation'],
    'target_python':installed['python'],'source_drain_observed':True,
    'scope':'Canonical upgrade-plan then exact reviewed upgrade-apply; no task exists, no implicit start or model admission.'}
value['migration']['source_context_revision']=hashlib.sha256(json.dumps(read(home/'service-context.json'),
    sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
save(HERE/'amendment.json',value)
print(json.dumps({'amendment_sha256':sha(HERE/'amendment.json'),'sources':len(sources),'steps':len(C['steps']),
    'package_sha256':value['installation']['sha256'],'initial_work_checkpoint_sha256':value['initial_work_checkpoint']['sha256']}))
