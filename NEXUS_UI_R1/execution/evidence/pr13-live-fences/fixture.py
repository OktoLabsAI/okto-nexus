"""Many exact retained sessions plus canonical own ObservationService pulses."""
import importlib.util,json
from pathlib import Path
from fastapi.responses import JSONResponse
ROOT=Path(__file__).resolve().parents[4]
spec=importlib.util.spec_from_file_location('ui13base',ROOT/'NEXUS_UI_R1/execution/evidence/pr04-browser/fixture.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
original_seed,original_serve=base.seed,base.serve
def seed(s):
    ids=original_seed(s)
    with s.factory.unit_of_work() as uow:
        c=uow.connection;original=c.execute('SELECT * FROM execution_sessions WHERE session_id=?',(s.sessions[0],)).fetchone()
        for i in range(20):
            sid=f'ui13-passive-{i:02}';base.copy_session(c,original,sid)
            c.execute("INSERT INTO execution_event_watermarks VALUES(?,?,?,?,0,0,'none')",(original['server_id'],original['executor_id'],sid,original['stream_epoch']))
    return dict(ids,additional_passive_sessions=20)
async def serve(s,args,home,identities):
    app=s.app;observations=app.state.home.observations
    from okto_nexus.domain.runtime_context import RuntimeRequestContext
    context=RuntimeRequestContext('operator','http_loopback',trusted_local_operator=True)
    with s.factory.unit_of_work(write=False) as uow:
        source=dict(uow.connection.execute('SELECT * FROM observation_sources WHERE source_id=?',(s.external['source_id'],)).fetchone())
        instance=dict(uow.connection.execute('SELECT * FROM observation_instances WHERE observed_instance_id=?',(s.external['observed_instance_id'],)).fetchone())
    token=observations.issue_token(context=context,source_id=source['source_id'],body=dict(expected_revision=source['revision'],instance_grants=[dict(observed_instance_id=instance['observed_instance_id'],generation=instance['generation'])]))['token']
    pulses=[]
    class Controlled:
        def __getattr__(self,name):return getattr(app,name)
        async def __call__(self,scope,receive,send):
            if scope.get('path') in {'/__ui13/priority','/__ui13/progress','/__ui13/status'}:
                if scope['path']!=' /__ui13/status'.strip():
                    seq=len(pulses)+2;state='blocked' if scope['path'].endswith('priority') else 'working'
                    payload=dict(schema_version=1,source_id=source['source_id'],observed_instance_id=instance['observed_instance_id'],generation=instance['generation'],sequence=seq,state=state,evidence='reported',observed_at=s.clock.now_iso())
                    if state=='blocked':payload['reason_code']='external_input_required'
                    result=observations.publish(token=token,payload=payload);pulses.append({'sequence':seq,'state':state,'result':result})
                return await JSONResponse({'pulses':pulses})(scope,receive,send)
            return await app(scope,receive,send)
    s.app=Controlled()
    try:await original_serve(s,args,home,identities)
    finally:args.ready_file.with_name('pulses.json').write_text(json.dumps(pulses,indent=2),encoding='utf-8')
base.seed=seed;base.serve=serve
if __name__=='__main__':base.main()
