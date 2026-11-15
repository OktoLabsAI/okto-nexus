"""Campaign-only presentation and explicit manual file selection. Never sends a decision."""
from datetime import datetime,timezone
from pathlib import Path
import argparse,hashlib,json,os,re

def require(ok,code):
    if not ok:raise ValueError(code)
def read(p):return json.loads(Path(p).read_bytes())
def digest(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()
def exclusive(path,value):
    with Path(path).open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def stamp(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    require(result.tzinfo is not None,'AWARE_TIME_REQUIRED');return result

def present(private_question,scope,*,operation_id,request_id,now,root_model_pending):
    from okto_nexus.application.terminal_connection import document_revision
    proposal=private_question['proposal'];key=proposal['approval_key']
    require(scope and all(key.get(k)==v for k,v in scope.items()),'EXACT_PENDING_SCOPE_REQUIRED')
    require(proposal.get('recipient_agent_id')=='operator','HUMAN_OPERATOR_RECIPIENT_REQUIRED')
    require(document_revision(proposal)==private_question['review_revision'],'NATIVE_REVIEW_CHANGED')
    params=proposal['display']['params'];command=params.get('input',{}).get('command');tool=params.get('tool_name')
    require(tool in ('PowerShell','Bash') and isinstance(command,str) and 0<len(command.encode('utf-8'))<=16384,'EXACT_SHELL_COMMAND_REQUIRED')
    remaining=(stamp(proposal['expires_at'])-now).total_seconds()
    public={'approval_id':private_question['approval_id'],'review_revision':private_question['review_revision'],
        'request_id':request_id,'operation_id':operation_id,'scope':scope,'tool_name':tool,'command_sha256':digest(command),
        'expires_at':proposal['expires_at'],'observed_utc':now.isoformat(),'remaining_seconds_at_observation':remaining,
        'fresh_for_manual_selection':remaining>=30,'native_pending_count':1,'root_model_pending':root_model_pending,
        'manual_selection_required':True,'native_ttl_changed':False,'decision_sent':False}
    return public,dict(public,command=command)

def select(public,root_view,*,scope,approval_id,revision,command_sha256,decision,root_ready,now,destination):
    require(decision in ('approve','deny'),'EXPLICIT_DECISION_REQUIRED')
    require(public.get('native_pending_count')==1 and public.get('root_model_pending') is False,'NATIVE_OR_ROOT_NOT_READY')
    require(public.get('scope')==scope and root_view.get('scope')==scope,'EXACT_SELECTION_SCOPE_REQUIRED')
    require(root_ready.get('manually_ready') is True and root_ready.get('model_pending') is False
        and root_ready.get('request_id')==public['request_id'] and root_ready.get('operation_id')==public['operation_id']
        and root_ready.get('session_id')==scope['session_id'] and stamp(root_ready['expires_at'])>=now,'ROOT_STILL_PENDING_OR_SCOPE_CHANGED')
    require(public['approval_id']==root_view['approval_id']==approval_id
        and public['review_revision']==root_view['review_revision']==revision,'MANUAL_ID_REVISION_CHANGED')
    require(public['command_sha256']==root_view['command_sha256']==command_sha256==digest(root_view['command']),
        'EXACT_REVIEWED_COMMAND_CHANGED')
    require(public['expires_at']==root_view['expires_at'] and (stamp(public['expires_at'])-now).total_seconds()>=30,
        'NATIVE_QUESTION_EXPIRED_OR_TOO_LATE')
    age=(now-stamp(public['observed_utc'])).total_seconds()
    require(0<=age<=20,'NATIVE_QUESTION_OBSERVATION_STALE')
    # File is the existing runner's input, not a network request. No overwrite or
    # retry; existing select_decision persists its own canonical-send reservation.
    choice={'approval_id':approval_id,'review_revision':revision,'decision':decision}
    exclusive(destination,choice)
    return {'status':'MANUAL_SELECTION_FILE_CREATED_NO_SEND','remaining_seconds':(stamp(public['expires_at'])-now).total_seconds(),
        'command_sha256':command_sha256,'decision_sent':False,'approval_id':approval_id,'decision':decision}

def exception_metadata(error,stage):
    name=type(error).__name__;code=getattr(error,'code',None);code=getattr(code,'value',code)
    return {'stage':stage if stage in ('events_wait','event_ingest','page_callback','publish') else 'unclassified',
        'exception_class':name if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}',name) else 'Unclassified',
        'code':code if isinstance(code,str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}',code) else None,
        'message_or_payload_retained':False,'admission_closed':True,'budget_uncertainty_preserved':True}

def main():
    parser=argparse.ArgumentParser()
    for key in ('public','root-view','scope','root-ready','destination','approval-id','review-revision','reviewed-command-sha256','decision'):
        parser.add_argument('--'+key,required=True)
    args=parser.parse_args()
    result=select(read(args.public),read(args.root_view),scope=read(args.scope),approval_id=args.approval_id,
        revision=args.review_revision,command_sha256=args.reviewed_command_sha256,decision=args.decision,
        root_ready=read(args.root_ready),now=datetime.now(timezone.utc),destination=args.destination)
    print(json.dumps(result))

if __name__=='__main__':main()
