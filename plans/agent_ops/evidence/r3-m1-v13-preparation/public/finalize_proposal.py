"""Integrate only the peer's frozen offline drivers; bind exact final sources."""
from pathlib import Path
import hashlib,json,shutil,sys
S=Path(__file__).resolve().parent;D=S/'draft';candidate=Path(sys.argv[1]);freeze=candidate/'qualification/runtime-pins.json'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest=json.loads(freeze.read_bytes());target=S/'root-drivers';target.mkdir(exist_ok=True)
runtime=manifest['files']
for name,entry in runtime.items():
    source=Path(entry['path']);assert sha(source)==entry['sha256']
    dest=target/source.name
    if dest.exists():assert dest.read_bytes()==source.read_bytes()
    else:shutil.copyfile(source,dest)
    assert sha(dest)==entry['sha256']
pfile=D/'m1-codex-campaign-proposal-v13.json';p=json.loads(pfile.read_bytes())
drivers={'common':'driver_common.py','invoke':'invoke.py','prepare_observation':'prepare_observation.py','observation':'m1_v13_observation.py','confirm_cleanup':'m1_v13_confirm_cleanup.py','confirm_final_presence':'confirm_final_presence.py','close_campaign':'close_campaign.py','operator_bootstrap':'operator_bootstrap.py','adopt_local':'adopt_local.py','authorize_local':'authorize_local.py'}
for key,name in drivers.items():p['execution_bundle']['files']['root_driver_'+key]={'path':str(target/name),'sha256':sha(target/name)}
recipefile=D/'remote-canonical-recipe.json';recipe=json.loads(recipefile.read_bytes())
recipe['status']='FROZEN_QUALIFIED';recipe['proposal_revision']=13
recipe['operator_bootstrap']['implementation_status']='FROZEN_V13_DRIVER_QUALIFIED'
recipe['operator_bootstrap']['executor'].update(p['execution_bundle']['files']['root_driver_operator_bootstrap'])
recipefile.write_text(json.dumps(recipe,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
planning=D/'planning-commands.json';plan=json.loads(planning.read_bytes());plan['status']='FROZEN_QUALIFIED'
planning.write_text(json.dumps(plan,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
for entry in p['execution_bundle']['files'].values():entry['sha256']=sha(entry['path'])
assert len(p['execution_bundle']['files'])==47
e=p['execution_bundle'];e['status']='FROZEN_QUALIFIED';e['commands']['sha256']=sha(e['commands']['path'])
e['qualification_scope']='69 affected composition cases PASS before the explicit preventive threshold delta;8 focused threshold cases PASS afterward. Final root-driver qualification is independently pinned. Final47-source origins/984-installed-payload hash check and21 negative entry gates run once against these bytes; reports accompany this proposal.'
p['status']='FROZEN_QUALIFIED_OFFLINE_WORK_SUCCESSOR';p['final_proposal']=True;p['qualification_status']='OFFLINE_COMPOSITION_QUALIFIED_REAL_WORK_PENDING'
p['blocking_preconditions']=['Root retention/review and truthful technical binding to standing user authorization','Fresh exact owned task/port runtime preflight and immutable predecessor/adopted-payload verification','Adopt existing DONE profile and current canonical binding; one read-only authorization review, conditional explicit issuance only under expired0/20 same-scope CAS gate']
p['base06_installation']['direct_interpreter_qualification']='ADOPTED_INSTALLED_V12_INTERPRETER_AND983_PAYLOADS_PINNED; final fresh origins report bound by outer artifact manifest.'
p['operator_bootstrap']['implementation_status']='FROZEN_V13_DRIVER_BOUND_OFFLINE_QUALIFIED'
p['scope_qualification']['status']='OFFLINE_INSTALLED_CLI_PARSER_HANDLERS_V13_COMPOSITION_QUALIFIED_REAL_WORK_PENDING'
c=p['controller_preparation'];c['status']='OFFLINE_WORK_SUCCESSOR_QUALIFIED';c['qualification_status']='AFFECTED69_PASS_PLUS_THRESHOLD8_PASS'
c['controller_sha256']=sha(D/'controller/controller.py');c['collector_sha256']=sha(D/'controller/token_collector.py');c['observer_sha256']=sha(D/'controller/independent_controller.py')
c['historical_v12_affected_composition']=c.pop('affected_composition')
c['affected_composition']={'xml':str(S/'affected-final/results.xml'),'sha256':sha(S/'affected-final/results.xml'),'tests':69,'scope':'Synthetic independent controller/policy/work/remote/lifecycle/adoption dual-root cases; pre-threshold-delta. Attempt00158PASS2obsolete-fixture-expectationFAIL retained.'}
c['threshold_delta']={'xml':str(S/'threshold-delta/results.xml'),'sha256':sha(S/'threshold-delta/results.xml'),'tests':8,'scope':'3 allocation+threshold before latePOST+before durableIO+2 postGETclock+four-work wrapper. Outer qualification deduplicates exact names across the69-case composition.'}
p['root_driver_preparation']={'status':'OFFLINE_V13_DRIVERS_QUALIFIED','source_freeze':{'path':str(freeze),'sha256':sha(freeze)},'qualification':{'path':str(candidate/'qualification/qualification.json'),'sha256':sha(candidate/'qualification/qualification.json')},'tests':119,'files':10,'scope':'Dual roots, configured adoption, read-only review/conditional expired0/20 grant issuance, local-only cleanup with Connector never selected. Exact peer qualification retained.'}
for step in p['steps']:
    if step['id']=='02-adopt-configured-local-and-review-grant':step['commands'][-1]='<PINNED_ROOT_INVOKE> <technical binding selectors> authorize_local apply'
p['local_authorization_maintenance']['root_review_selection']={'path':str(S/'private/authorize-local-reviewed.json'),'fields':{'decision':'issue','review_sha256':'<SHA of exact public authorize-local-review.json>','review_revision':'<canonical review_revision>','proposal_sha256':'<final proposalSHA>','approval_sha256':'<technical bindingSHA>','campaign_revision':13,'campaign_root':str(S.parent),'control_root':str(S)},'condition':'Root writes only after reviewing one expired unused grant and exact same scope/actions60min20actions. No issuance for available/exhausted/revoked/superseded/ambiguous.'}
pfile.write_text(json.dumps(p,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({'proposal':str(pfile),'sha256':sha(pfile),'pins':47,'runtime_drivers':len(runtime)}))
