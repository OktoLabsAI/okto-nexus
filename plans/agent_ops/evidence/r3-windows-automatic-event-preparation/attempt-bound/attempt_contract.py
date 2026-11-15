"""Exact prospective OS attempt correlation. No event effect on import."""
from datetime import datetime
import hashlib,json
from pathlib import Path
from automation_contract import event_command,validate_window,require

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def at(value):
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    require(parsed.tzinfo is not None,'AWARE_TIME_REQUIRED');return parsed

def validate_attempt(P,before,before_sha,plan_sha,attempt):
    require(isinstance(attempt,dict) and attempt.get('state')=='RESERVED_BEFORE_OS_CALL','EVENT_ATTEMPT_REQUIRED')
    require(attempt.get('plan_sha256')==plan_sha==before.get('plan_sha256'),'ATTEMPT_PLAN_CHANGED')
    require(attempt.get('before_sha256')==before_sha,'ATTEMPT_BEFORE_CHANGED')
    event=P['selected_event']
    require(attempt.get('event_id')==before.get('event_id')==event,'ATTEMPT_EVENT_CHANGED')
    principal=before['own_session']['principal_sha256']
    require(attempt.get('principal_sha256')==P['window']['principal_sha256']==principal,'ATTEMPT_PRINCIPAL_CHANGED')
    require(attempt.get('window')==P['window'],'ATTEMPT_WINDOW_CHANGED')
    issued=at(attempt['issued_utc'])
    require(issued>=at(before['utc']),'ATTEMPT_BEFORE_OBSERVATION')
    validate_window(P['window'],issued,principal)
    require(attempt.get('command')==event_command(event,r'C:\Windows\System32'),'ATTEMPT_COMMAND_CHANGED')
    require(attempt.get('automatic_next_event') is False and attempt.get('no_force_apps') is True
        and attempt.get('no_retry') is True,'ATTEMPT_POLICY_CHANGED')
    return attempt

def before_after_reserve(P,before,before_sha,plan_sha,directory):
    """A login without a selected OS attempt must not consume after.reserved."""
    path=Path(directory)/'event-attempt.json'
    if not path.is_file():return None
    value=json.loads(path.read_bytes())
    validate_attempt(P,before,before_sha,plan_sha,value)
    returned=Path(directory)/'event-command-returned.json'
    if returned.is_file():
        result=json.loads(returned.read_bytes())
        require(result.get('attempt_sha256')==digest(path),'RETURNED_ATTEMPT_CHANGED')
        if result.get('state')=='REFUSED_BEFORE_OS_CALL':return None
    return {'path':str(path),'sha256':digest(path),'issued_utc':value['issued_utc']}
