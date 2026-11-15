"""Opt-in adapter for a FUTURE selected paid context; no effect at import."""
from datetime import datetime,timezone
from pathlib import Path
from fast_approval import present,read,stamp,exception_metadata,exclusive

def publish_before_slow_hooks(X,items,session,atomic):
    """Call first in publish_pending, before console/dashboard coordination."""
    request=X._last_request
    admission=read(Path(X.PRIVATE)/(request+'-admission.json'))
    operation=admission['operation_id']
    # Native approval_key intentionally omits workspace_binding_id. Its exact
    # six-field authority scope is checked here; the parent context separately
    # pins the full runtime binding, including workspace_binding_id.
    scope={k:X.expected_scope[k] for k in ('server_id','executor_id','binding_id','agent_id','workspace_id')}
    scope['session_id']=session
    ready_path=Path(X.PRIVATE)/'root-manually-ready.json'
    ready=read(ready_path) if ready_path.exists() else {}
    now=datetime.now(timezone.utc)
    ready_matches=(ready.get('manually_ready') is True and ready.get('model_pending') is False
        and ready.get('request_id')==request and ready.get('operation_id')==operation
        and ready.get('session_id')==session and isinstance(ready.get('expires_at'),str)
        and stamp(ready['expires_at'])>=now)
    if len(items)!=1:
        atomic(Path(X.PUBLIC)/'fast-native-question.json',{'native_pending_count':len(items),
            'fresh_for_manual_selection':False,'root_model_pending':not ready_matches,'observed_utc':now.isoformat()})
        return
    from okto_nexus.application.terminal_connection import document_revision
    item=items[0];proposal=item['request_payload']['kwargs']
    question={'approval_id':item['approval_id'],'review_revision':document_revision(proposal),'proposal':proposal}
    public,private=present(question,scope,operation_id=operation,request_id=request,now=now,root_model_pending=not ready_matches)
    atomic(Path(X.PRIVATE)/'native-command-root-view.json',private)
    atomic(Path(X.PUBLIC)/'fast-native-question.json',public)

def error_sink(X,request):
    def retain(metadata):
        # First fault is enough. Caller catches evidence IO failures while
        # preserving the original exception and conservative containment.
        path=Path(X.PRIVATE)/(request+'-observation-exception.json')
        if not path.exists():exclusive(path,metadata)
    return retain
