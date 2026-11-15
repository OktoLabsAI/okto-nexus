"""All new09/10 attempts count Native-or-uncertain; old05 remains the sole exception."""
from pathlib import Path
from request_context import require,read_json,pin,reserve,sha
from successor_policy import HERE,IDS
def validate_receipt(plan):
    candidate=read_json(pin(plan['successor_candidate']))
    previous=read_json(pin(candidate['previous_plan']))
    from denial_reconciliation import validate_receipt as validate_original05
    validate_original05(previous)
    reconciliation=read_json(pin(candidate['reconciliation']))
    require(reconciliation['campaign_tokens']==180426 and reconciliation['native_charges']==3
        and reconciliation['server_admissions']==4 and reconciliation['native07_outcome']=='interrupted'
        and reconciliation['prefix_hashes_equal'] is True and reconciliation['closed_stream_cursor']==110,'RECONCILIATION_CHANGED')
    original=read_json(pin(previous['server_admission_history']))
    history=read_json(pin(candidate['current_server_history']))
    require(history['rows']==original['rows']+[{'request_id':'m1-sonnet-remote-useful-07',
        'server_admission_consumed':True,'native_forwarded_or_uncertain':True}]
        and history['server_admissions_consumed']==4 and history['native_forwarded_or_uncertain']==3,'SERVER_HISTORY_CHANGED')
    return history
def counts(private,request=None):
    seen=set()
    for path in Path(private).glob('server-attempt-*.json'):
        row=read_json(path);rid=row.get('request_id');ordinal=5 if rid==IDS['useful'] else 6
        require(rid in IDS.values() and rid not in seen and path.name=='server-attempt-'+rid+'.json'
            and row.get('state')=='NEW_NATIVE_FORWARDED_OR_UNCERTAIN' and row.get('native_charge_upper_bound')==1
            and row.get('server_admission_consumed') is True and row.get('server_ordinal')==ordinal
            and row.get('native_upper_bound')==ordinal-1 and row.get('refund_allowed') is False,'NEW_ATTEMPT_CHANGED')
        seen.add(rid)
    require(IDS['continuation'] not in seen or IDS['useful'] in seen,'CONTINUATION_WITHOUT_USEFUL')
    require(len(seen)<=2 and 4+len(seen)<=6 and 3+len(seen)<=5,'DUAL_COUNTER_LIMIT')
    if request is not None:
        require(request in IDS.values() and request not in seen and len(seen)<2,'NEW_ATTEMPT_REPLAY_OR_EXHAUSTED')
        require(request!=IDS['continuation'] or IDS['useful'] in seen,'CONTINUATION_WITHOUT_USEFUL')
    return {'server_admissions':4+len(seen),'native_forwarded_or_uncertain':3+len(seen),'new_attempts':len(seen)}
def reserve_attempt(plan,private,request,budget):
    validate_receipt(plan);before=counts(private,request)
    require((budget.limit,budget.preventive,budget.max_requests)==(500000,480000,5),'ACTIVE_POLICY_CHANGED')
    value={'request_id':request,'state':'NEW_NATIVE_FORWARDED_OR_UNCERTAIN','native_charge_upper_bound':1,
        'server_admission_consumed':True,'refund_allowed':False,'server_ordinal':before['server_admissions']+1,
        'native_upper_bound':before['native_forwarded_or_uncertain']+1}
    reserve(Path(private)/('server-attempt-'+request+'.json'),value);return value
