"""Own inert human fixture; two explicitly triggered canonical new questions."""
from pathlib import Path
import json
import tempfile

root=Path(__file__).resolve().parents[2]
evidence=root/'NEXUS_UI_R1/execution/evidence/pr07-navigation-arrival'
evidence.mkdir(exist_ok=True)
own=Path(tempfile.mkdtemp(prefix='nexus-ui-nav-arrival-runner-'))
source=root/'NEXUS_UI_R1/execution/evidence/pr04-browser/human-vmhGy86G'
base=(source.parent/'fixture.py').read_text(encoding='utf8').replace('ROOT = Path(__file__).resolve().parents[4]',f'ROOT = Path({str(root)!r})')
(own/'fixture.py').write_text(base,encoding='utf8')
human=(source/'human-fixture.py').read_text(encoding='utf8').replace('ROOT=HERE.parents[3]',f'ROOT=Path({str(root)!r})')
human=human.replace('p.relative_to(ROOT).as_posix()','str(p)')
(own/'human-fixture.py').write_text(human,encoding='utf8')
live=(source/'human-live-fixture.py').read_text(encoding='utf8').replace("grant['valid_until_server']","grant.get('valid_until_server')")
live=live.replace("state=captured['opening'];channel=state[5]", "s.deps.config.feature_memory=False\n            state=captured['opening'];channel=state[5]")
live=live.replace("end=time.monotonic()+180;last_renew=time.monotonic()", "end=time.monotonic()+300;last_renew=time.monotonic();published=set()")
live=live.replace("ws.send_text(encode_r4_frame(frame).decode())", '''ws.send_text(encode_r4_frame(frame).decode())
                        for index,view in enumerate(('Graph','Artifacts'),start=1):
                            trigger=args.ready_file.with_name('trigger-'+view)
                            if trigger.exists() and view not in published:
                                publish_question(s,state,index,view)
                                published.add(view)
                                diagnostics.append(dict(kind='canonical_new_question',view=view))''')
helper='''
def publish_question(s,state,index,view):
    from okto_nexus.application.execution_events import commit_execution_events
    channel=state[5];scope=state[6]['scope']
    with s.factory.unit_of_work(write=False) as uow:
        operation=uow.connection.execute("SELECT operation_id FROM execution_operations WHERE action='turn.submit' ORDER BY created_at LIMIT 1").fetchone()[0]
        before=uow.connection.execute("SELECT COUNT(*) FROM approvals WHERE action='execution.native.respond'").fetchone()[0]
    proposal=dict(schema_version=1,request_id=7+index,request_hash=str(index)*64,
        method='item/tool/requestUserInput',params=dict(turnId='native-turn',itemId='nav-'+view,
        isBlocking=True,questions=[dict(id='nav-question-'+view,header='New '+view,
        question='New question while viewing '+view,isOther=True,
        options=[dict(label='Continue',description='Synthetic inert choice'),dict(label='Stop',description='Synthetic stop')])]))
    event=dict(server_id=channel.server_id,executor_id=channel.executor_id,session_id=scope['session_id'],
        stream_epoch='native-epoch',sequence=index+1,category='input_request',operation_id=operation,
        payload=dict(native_approval=proposal,native_approval_display=proposal))
    frame={key:scope[key] for key in ('server_id','executor_id','binding_id','agent_id','session_id')}
    frame.update(protocol_major=1,contract_revision=R4_PREVIEW_REVISION,type='event.batch',
        connection_id=channel.connection_id,connection_generation=channel.connection_generation,
        stream_epoch='native-epoch',events=[event])
    commit_execution_events(s.factory,channel=channel,frame=frame,approvals=s.deps.approvals)
    with s.factory.unit_of_work(write=False) as uow:
        rows=uow.connection.execute("SELECT approval_id,request_payload FROM approvals WHERE action='execution.native.respond'").fetchall()
        found=[dict(approval_id=row['approval_id']) for row in rows if 'New question while viewing '+view in row['request_payload']]
    assert len(rows)==before+1 and len(found)==1
    # Publish only canonical public identity; no nonce, bearer or request payload.
    question_publication[view]=dict(before=before,after=len(rows),**found[0])

question_publication={}
'''
live=live.replace("def main():",helper+"\ndef main():")
live=live.replace("                                publish_question(s,state,index,view)","                                publish_question(s,state,index,view)\n                                args.ready_file.with_name('arrival-'+view+'.json').write_text(json.dumps(question_publication[view]),encoding='utf8')",1)
(own/'human-live-fixture.py').write_text(live,encoding='utf8')
(evidence/'allocation.json').write_text(json.dumps({'runner_root':str(own)},indent=2),encoding='utf8')
print(own)
