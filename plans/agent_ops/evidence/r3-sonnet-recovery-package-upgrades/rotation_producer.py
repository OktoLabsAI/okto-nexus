"""One-shot canonical rotation producer. Only protected PTY receives material."""
from pathlib import Path
import sys,json,time
sys.path.insert(0,str(Path(__file__).resolve().parent))
def produce(X,post,deliver):
    X.preflight('producer')
    X.save('rotation-post-reserved.json',{'status':'RESERVED_BEFORE_POST','method':'POST',
        'path':'/api/v1/agents/m1-sonnet-remote/regenerate-key','agent_id':'m1-sonnet-remote',
        'expected_pre_rotation_epoch':1,'max_attempts':1,'atomic_compare_and_swap':False})
    X.preflight('producer')
    # Installed HTTP transport performs one opener.open; no retries.
    response=post('POST','/api/v1/agents/m1-sonnet-remote/regenerate-key',None)
    data=response.get('data') if isinstance(response,dict) else None
    if not (response.get('ok') is True and isinstance(data,dict)
            and data.get('agent_id')=='m1-sonnet-remote'):
        raise RuntimeError('ROTATION_RESPONSE_UNCONFIRMED')
    key=data.get('api_key')
    from okto_nexus.domain.keys import is_well_formed_api_key
    if not is_well_formed_api_key(key):raise RuntimeError('ROTATION_MATERIAL_UNCONFIRMED')
    deliver(key)
    key=None;data=None;response=None
    X.save('rotation-material-emitted.json',{'status':'EMITTED_ONCE_TO_PROTECTED_PTY',
        'agent_id':'m1-sonnet-remote','plaintext_written_to_artifacts':False,'post_attempts':1,'time':time.time()})

def main():
    from rotation_executor import load_context
    X=load_context(producer=True)
    from okto_nexus.adapters.inbound.cli.remote_setup_io import material_sink
    from okto_nexus.adapters.outbound.operator_client import OperatorProfile
    sink=material_sink(False)
    if sink is None:raise RuntimeError('PROTECTED_TTY_REQUIRED_BEFORE_POST')
    profile=OperatorProfile(X.P['paths']['operator_home'],'m1-sonnet-human')
    info=profile.read()
    if info['origin']!=X.P['origin'] or info['server_id']!=X.P['server_id']:
        raise RuntimeError('OPERATOR_PROFILE_SCOPE_CHANGED')
    produce(X,profile.client(),sink)
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        # Never serialize response bodies, exception messages, or local variables.
        print(json.dumps({'status':'ROTATION_PRODUCER_UNCONFIRMED','error_type':type(error).__name__}))
        raise SystemExit(3) from None
