"""Read-only companion, never edits or upgrades the frozen after receipt."""
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import sys

PROVIDER = 'Microsoft-Windows-Kernel-Power'
NAMES = {42:'PreSleepNotification',107:'PostSleepNotification',506:'CsEnterReason',507:'CsExitReason'}
ANCESTOR = Path('C:/Users/jpamb/AppData/Local/Temp/r3-windows-attempt-bound-cqbln3b4')
PINS = {'attempt_contract.py':'c832c9e09bcf1b3e1683da75be5ebe104b33ee92f837d9799d0c78bebf214b7a',
        'automation_contract.py':'98ff23b98e32f679834fb34227a0df7196f776bf95a798baf92d41588bc1791c'}

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def utc(value):
    dt = datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None: raise ValueError('AWARE_TIME_REQUIRED')
    return dt
def require(value, code):
    if not value: raise ValueError(code)

def evaluate(before, after, issued, window_end):
    """Strict complete ordered pair; unavailable/ambiguous observations stay unknown."""
    result={'status':'EVENT_UNCONFIRMED','os_transition_observed':False,
            'deep_power_residency_proven':False,'api_causation_proven':False}
    try:
        for snap in (before,after):
            require(snap['status']=='READ_ONLY_CAPTURED' and snap['truncated'] is False,'INCOMPLETE_CAPTURE')
            require(snap['event_generated'] is False,'READ_ONLY_REQUIRED')
        require(before['boot_utc']==after['boot_utc'],'BOOT_CHANGED')
        begin,end=utc(issued),utc(window_end)
        require(utc(before['finished_utc'])<=begin<=end,'BASELINE_AFTER_ATTEMPT')
        require(utc(after['query_start_utc'])<=utc(before['started_utc']),'QUERY_GAP')
        require(begin<=utc(after['query_end_utc'])<=end+timedelta(seconds=180),'AFTER_WINDOW_INVALID')
        anchor=before['latest']
        require(anchor is not None and after['anchor']==anchor,'ANCHOR_MISSING_OR_CHANGED')
        require(utc(anchor['utc'])<=utc(before['started_utc']),'ANCHOR_TIME_INVALID')
        manifest={(r['event_id'],r['version']):r for r in after['manifest']}
        rows=[]
        for row in after['events']:
            require(row['provider']==PROVIDER and row['event_id'] in NAMES,'FOREIGN_EVENT')
            md=manifest.get((row['event_id'],row['version']))
            require(md and md['provider']==PROVIDER and md['log']=='System'
                    and md['transition']==row['transition']==NAMES[row['event_id']],'MANIFEST_MISMATCH')
            if row['record_id']>anchor['record_id']:
                require(begin<=utc(row['utc'])<=end,'UNRELATED_NEW_TRANSITION')
                rows.append(row)
        ids=[r['record_id'] for r in rows]
        require(ids==sorted(set(ids)),'RECORD_ORDER_INVALID')
        require(all(utc(a['utc'])<=utc(b['utc']) for a,b in zip(rows,rows[1:])),'CLOCK_ORDER_INVALID')
        pairs=[]
        for enter,leave,mode in ((506,507,'MODERN_STANDBY_SESSION'),(42,107,'SLEEP_NOTIFICATION')):
            subset=[r for r in rows if r['event_id'] in (enter,leave)]
            if not subset: continue
            require([r['event_id'] for r in subset]==[enter,leave],'AMBIGUOUS_OR_INCOMPLETE_PAIR')
            pairs.append({'mode':mode,'entry':subset[0],'exit':subset[1]})
        require(pairs,'NO_COMPLETE_TRANSITION')
        result.update(status='OS_TRANSITION_OBSERVED',os_transition_observed=True,pairs=pairs)
    except (KeyError,TypeError,ValueError) as exc:
        result['reason']=str(exc) if isinstance(exc,ValueError) else 'INVALID_CAPTURE_SHAPE'
    return result

def companion(plan_path,plan_sha,before_path,after_path,attempt_path,power_before_path,power_after_path):
    for name,sha in PINS.items(): require(digest(ANCESTOR/name)==sha,'ANCESTOR_CHANGED')
    sys.path.insert(0,str(ANCESTOR))
    from attempt_contract import validate_attempt
    from automation_contract import classify_event
    paths=[Path(p) for p in (plan_path,before_path,after_path,attempt_path,power_before_path,power_after_path)]
    plan,before,after,attempt,pb,pa=[json.loads(p.read_bytes()) for p in paths]
    require(digest(paths[0])==plan_sha,'SELECTED_PLAN_CHANGED')
    require(plan['selected_event']=='01-suspend-resume','SUSPEND_ONLY')
    validate_attempt(plan,before,digest(paths[1]),digest(paths[0]),attempt)
    require(after['plan_sha256']==plan_sha and after['before_sha256']==digest(paths[1])
            and after['event_id']==plan['selected_event']
            and after['event_attempt_pin']['sha256']==digest(paths[3]),'AFTER_SCOPE_CHANGED')
    require(utc(pb['started_utc'])>=utc(before['utc']),'POWER_BASELINE_STALE')
    result=evaluate(pb,pa,attempt['issued_utc'],plan['window']['expires_utc'])
    result['correlated_assessment']=classify_event(plan['selected_event'],before['own_session'],
        after['current']['own_session'],os_transition_observed=result['os_transition_observed'])
    result['source_pins']=[{'path':str(p),'sha256':digest(p)} for p in paths]
    result['original_receipts_modified']=False
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    for key in ('plan','plan_sha','before','after','attempt','power_before','power_after','output'):p.add_argument('--'+key.replace('_','-'),required=True)
    a=p.parse_args()
    result=companion(a.plan,a.plan_sha,a.before,a.after,a.attempt,a.power_before,a.power_after)
    with open(a.output,'x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(result['status'])
