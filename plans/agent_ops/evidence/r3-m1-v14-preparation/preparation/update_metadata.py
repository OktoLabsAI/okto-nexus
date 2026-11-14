from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
S=Path(__file__).parent;D=S/'draft';path=D/'m1-codex-campaign-proposal-v14.json'
p=json.loads(path.read_bytes());old=json.loads((S.parent/'successor13/draft/m1-codex-campaign-proposal-v13.json').read_bytes())
def pin(f):return {'path':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
def current_text(v):
    if isinstance(v,str):
        for a,b in [('v13','v14'),('V13','V14'),('111651','134199'),('eight historical','nine historical'),('Eight historical','Nine historical'),('maximum12 cumulative','maximum13 cumulative'),('cumulative12','cumulative13'),('maximum12','maximum13'),('120-second','600-second'),('120s','600s'),('--timeout 120','--timeout 600'),('m1v12-local-work-','m1v14-local-work-'),('m1v12-remote-work-','m1v14-remote-work-')]:v=v.replace(a,b)
        return v
    if isinstance(v,list):return [current_text(x) for x in v]
    if isinstance(v,dict):return {k:current_text(x) for k,x in v.items()}
    return v
for key in ('finite_work','steps','authorization','topology','token_accounting','base06_installation','base06_measurement','acceptance','scope_qualification','root_driver_preparation','evidence_policy'):
    p[key]=current_text(p[key])
p['prepared_at_utc']=datetime.now(timezone.utc).isoformat();p['preparation_revision']=14
p['authorization'].pop('technical_v13_binding_created',None);p['authorization']['technical_v14_binding_created']=False
p['finite_work']['maximum_cumulative_admissions']=13
p['finite_work']['maximum_native_decisions_per_lane']=3
p['finite_work']['request']+=' Use one noninteractive Python process through rtk proxy python -c to read the CSV, compute the values and hash, and write the JSON. Avoid nested PowerShell shells or shell-expanded variables. Compute the result yourself from the file; do not assume supplied expected values.'
p['finite_work']['native_decision']='At most three genuine, exact reviewed native permission decisions per lane across useful work and continuation. Each must bind the actual canonical approval ID, revision, actor/session and source/output command. No broad prefix/persistent approval or policy change; denied commands are never bypassed.'
p['finite_work']['resolved_requests']={lane:p['finite_work']['request'].replace('<project>',p['paths']['local_project' if lane=='local' else 'remote_project']).replace('<lane_deliverables>',p['paths']['local_deliverables' if lane=='local' else 'remote_deliverables']) for lane in ('local','connector')}
p['counting'].update(conservative_carry_in_reservations=9,historical_confirmed_productive=6,
 cumulative_reservations_maximum=13,maximum_confirmed_productive_if_all_new_confirm=10,observed_token_minimum_carry_in=134199,
 v13_new_observed_tokens=22548,v13_new_reservations=1,v13_work_cancelled_after_deadline=True,v13_unsettled_after_reconciliation=0)
p['token_accounting'].update(observed_tokens_carry_in=134199,admissions_carry_in=9,cumulative_admissions_maximum=13,
 proposed_remaining_observed_headroom=365801,serial_turn_deadline_seconds=600)
p['token_accounting']['counter_semantics']='All nine historical reservations and134199 minimum observed tokens remain charged. The v13 turn was canonically CANCELLED after normal interruption and its retained Core usage is settled in a separate derived checkpoint. Original DEADLINE120 and WORK_TERMINAL_FAILED remain ancestry. Four new work intents cover useful plus continuation in both topologies; maximum13 cumulative, no replay/refund/setup reset, no increase to500k preventive/700k tolerance.'
p['predecessor']={'revision':13,'status':'CLOSED_RECONCILED_SETTLED_ACCEPTANCE_NOT_INFERRED',
 'closure':p['adoption']['predecessor_closure_pin'],'companion':p['adoption']['predecessor_companion_pin'],
 'derived_checkpoint':p['adoption']['predecessor_checkpoint_pin'],'original_checkpoint':p['adoption']['predecessor_original_checkpoint_pin'],
 'carry_in_admissions':9,'carry_in_tokens':134199,'faults':['DEADLINE120','WORK_TERMINAL_FAILED']}
p['policy_delta']={'previous_revision':13,'next_revision':14,'previous_deadline_seconds':120,'next_deadline_seconds':600,
 'previous_cumulative_reservation_limit':12,'next_cumulative_reservation_limit':13,'carry_in_admissions':9,'new_admissions':4,
 'carry_in_tokens':134199,'preventive_cumulative_tokens':500000,'operational_tolerance':700000,
 'native_decisions_per_lane':3,'claude_selected':False,
 'reason':'Preserve the cancelled settled v13 attempt and let the finite useful work await exact native decisions within600 seconds. Ceiling13 is an explicit internal allocation delta, not a token budget increase. New local session after prior CLOSED; no setup replay.'}
A=p['adoption'];A['predecessor_session_state']='CLOSED'
A['expected_historical_grants']=[
 {'grant_id':'grant_89bbed009c65458fab96ff9d0a3ffc72','revision':1,'expires_at':'2026-11-14T16:22:02.541642Z','max_executions':20,'minimum_used_executions':0},
 {'grant_id':'grant_ac06e31629304e1fb2b34161918a73ef','revision':1,'expires_at':'2026-11-14T17:26:23.088231Z','max_executions':20,'minimum_used_executions':1}]
A['predecessor_authorization_apply_pin']=pin(S.parent/'successor13/public/authorize-local-apply.json')
A['old_work_history']='Adopt writes an exact immutable snapshot in control/private/predecessor-work-checkpoint.json. Canonical CLI may update its current checkpoint for authorization/new-session; old intent/session/receipt and snapshot remain history.'
maintenance=p['local_authorization_maintenance']
maintenance.update(maximum_new_grants=1,allowed_old_state='expired',required_old_used_executions=None,
 max_executions=3,minimum_available_actions=3,minimum_existing_grant_window_seconds=630,
 repeat_review_allowed=True,available_insufficient_window='Do not infer expiry. Preserve versioned read-only reviews; any later explicit selection must observe canonical expired before new issuance.',
 old_grant_preserved=True,consumption_reset=False)
maintenance['root_review_selection']['fields']['campaign_revision']=14
maintenance['root_review_selection']['condition']='Root explicitly selects the exact canonical expired review after all historical grants are unavailable by expiry; issue at most one new60min/3-action grant with same scope/actions. Preserve all prior grants/consumption. Never issue automatically for available, exhausted, revoked, superseded or ambiguous state.'
maintenance['counting_source']='Installed runtime_access: only send/steer/execute_work consume; open/interrupt/close do not. Three actions conservatively cover two sends plus one margin; this is not extra model allocation.'
for step in p['steps']:
    if step['id']=='02-adopt-configured-local-and-review-grant':
        step['required_evidence']='Pinned closed v13 original closure plus reconciled companion/checkpoint, retained v12 installed payloads and configured profile. Snapshot old current work, prove old session CLOSED. Review exact historical grants; available grant may have used actions if remaining>=3 and window>=630s.'
        step['proposed_effects']='New control evidence only, no setup. Explicit canonical read-only review; at most one root-selected60min/3-action grant only after canonical expiry, preserving historical consumption.'
    if step['id']=='03-local-work-decision-result':
        step['commands'][0]=step['commands'][0].replace('work send ','work send --new-session ')
        step['proposed_effects']='One newly identified useful turn in a new session after the old session CLOSED, at most3 exact reviewed native decisions per lane total, then one separately allocated continuation. Same source/output and no policy expansion.'
p['controller_preparation']['historical_v13_qualification']={k:v for k,v in old['controller_preparation'].items() if 'qualification' in k or 'composition' in k or 'threshold_delta'==k}
for key in list(p['controller_preparation']):
    if key in ('affected_composition','threshold_delta','qualification_status'):p['controller_preparation'].pop(key)
p['controller_preparation']['status']='PREPARING_V14_AFFECTED_DELTA'
p['controller_preparation']['qualification_status']='PENDING_AFFECTED_TESTS'
p['execution_bundle']['qualification_scope']='V14 affected delta is being qualified. Earlier v13 suites remain historical references; no claim they ran against changed v14 bytes.'
p['scope_qualification']['status']='PREPARING_V14_OFFLINE_DELTA_REAL_EXECUTION_PENDING'
path.write_text(json.dumps(p,indent=2)+'\n',encoding='utf-8',newline='\n')
recipefile=D/'remote-canonical-recipe.json';recipe=current_text(json.loads(recipefile.read_bytes()))
recipe['proposal_revision']=14;recipe['limits']['policy']=p['controller_preparation']['policy'];recipe['status']='PREPARING_OFFLINE'
recipefile.write_text(json.dumps(recipe,indent=2)+'\n',encoding='utf-8',newline='\n')
