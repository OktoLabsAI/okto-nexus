from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parent;D=R/'draft';P=D/'m1-codex-campaign-proposal-v12.json'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def write(p,v):p.write_bytes((json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode())
o=read(R/'final-origins/result.json');assert o['exit_code']==0 and o['source_unchanged'] and o['campaign_root_absent']
p=read(P);assert all(sha(v['path'])==v['sha256'] for v in p['execution_bundle']['files'].values())
p.update(status='FINAL_ARTIFACTS_READY_FOR_ROOT_REVIEW_TECHNICAL_BINDING_PENDING',final_proposal=True,execution_authorized=False,qualification_status='COMPONENTS_AND_ORIGINS_PASS_FINAL_ENTRY_REPORT_SEPARATE')
p['controller_preparation'].update(status='V12_COMPOSITION_OFFLINE_QUALIFIED',qualification_status='RETAINED_SOURCE73_AND_AFFECTED_V12_76_PASS',composed_module_origins={'path':str(R/'final-origins/module-origins.json'),'sha256':sha(R/'final-origins/module-origins.json')})
p['scope_qualification']['status']='OFFLINE_INSTALLED_CLI_PARSER_HANDLERS_V12_COMPOSITION_QUALIFIED_REAL_M1_PENDING'
p['execution_bundle']['status']='FROZEN_QUALIFIED'
p['execution_bundle']['qualification_scope']='Retained source discovery73PASS/1historical private DB deselected; V12 affected composition76PASS; drivers121PASS; isolated origins46PASS. Final20 entry refusals and real wheel/dependency/LF verification are recorded separately against this frozen proposal. Historical source64 and earlier failures are retained, not summed or repeated.'
p['operator_bootstrap']['implementation_status']='FROZEN_V12_DRIVER_BOUND_OFFLINE_QUALIFIED'
p['blocking_preconditions']=['Final entry/wheel/dependency reports must pass for these exact bytes','Root retention/review and truthful technical binding to existing user authorization','Fresh exact task/home/port runtime preflight; no current availability assertion']
write(P,p)
q=read(D/'offline-finalization.json');q.update(status='FROZEN_ORIGINS_PASS_ENTRY_CHECKS_PENDING',proposal_sha256=sha(P));write(D/'offline-finalization.json',q)
print(json.dumps({'proposal_sha256':sha(P),'runtime_pins':len(p['execution_bundle']['files']),'policy':p['controller_preparation']['policy']}))
