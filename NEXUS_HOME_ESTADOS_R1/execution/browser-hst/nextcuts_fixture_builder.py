"""Build a private derivative only after the runner's explicit window gate.

No imports from product packages. Canonical admissions come from the qualified
fixture copied into the new Temp root. Added SQL is read-only proof collection.
"""
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent

PROOF=r'''
        def next_proof(label):
            pending=call('GET','/api/v1/runtime-management/runtime/input-requests',headers=controls.operator_headers())
            pending=pending if isinstance(pending,list) else pending.get('items',[])
            with deps.connection_factory.unit_of_work(write=False) as uow:
                db=uow.connection
                decisions=[dict(r) for r in db.execute('SELECT decision_id,server_id,executor_id,binding_id,agent_id,workspace_id,session_id,session_owner_generation,canonical_request_id,actor_agent_id,canonical_state,native_operation_id,client_intent_id FROM execution_decisions ORDER BY decision_id')]
                writes=[dict(r) for r in db.execute("SELECT operation_id,server_id,executor_id,binding_id,workspace_id,session_id,subject_agent_id,actor_agent_id,action FROM execution_operations WHERE action IN ('input.provide','approval.decide') ORDER BY operation_id")]
                productive=[dict(r) for r in db.execute("SELECT operation_id,server_id,executor_id,session_id,action FROM execution_operations WHERE action IN ('runtime.open','runtime.start','turn.submit') ORDER BY operation_id")]
                receipts={row['native_operation_id']:[dict(r) for r in db.execute('SELECT receipt_revision,stage FROM execution_receipts WHERE server_id=? AND executor_id=? AND operation_id=? ORDER BY receipt_revision',(row['server_id'],row['executor_id'],row['native_operation_id']))] for row in decisions}
            native=[]
            for item in pending:
                p=item.get('request_payload',{}).get('kwargs',{})
                native.append(dict(request_id=item.get('approval_id')or item.get('request_id'),approval_key=p.get('approval_key'),recipient_agent_id=p.get('recipient_agent_id'),expected_revision=p.get('expected_revision'),expires_at=p.get('expires_at')))
            write('next-'+label+'.json',dict(at=deps.clock.now_iso(),decisions=decisions,native_writes=writes,productive_operations=productive,receipts=receipts,requests=native))
'''

HISTORY=r'''
          # Complete retained sessions are created through their real owner,
          # before either live question begins its original120s expiry.
          for historic_index in range(10):
            ref=refs[0]
            opened=admit(ref,'runtime.start',new_session=True);sid=opened['scope']['session_id']
            sessions.append(dict(session_id=sid,reference=ref,text='HST synthetic output '+sid,closed=False,historical_fixture=True))
            admit(ref,'turn.submit',session_id=sid,text='HST safe historical fixture turn')
            admit(ref,'runtime.close',session_id=sid);sessions[-1]['closed']=True
'''

ARRIVAL=r'''
                    if name=='next-arrive-session':
                        ref=refs[0];opened=admit(ref,'runtime.start',new_session=True);sid=opened['scope']['session_id']
                        sessions.append(dict(session_id=sid,reference=ref,text='HST synthetic output '+sid,closed=False,historical_fixture=True))
                        turn=admit(ref,'turn.submit',session_id=sid,text='HST safe new related session')
                        closed=admit(ref,'runtime.close',session_id=sid);sessions[-1]['closed']=True
                        write('next-arrival.json',dict(session_id=sid,reference=ref,open_operation_id=opened['operation_id'],turn_operation_id=turn['operation_id'],close_operation_id=closed['operation_id']))
                    if name=='next-snapshot-after':next_proof('after')
'''

def build(root:Path,case:str):
    assert case in ('decision','context')and root.name.startswith('nexus-hst-browser-')
    original=(HERE/'fixture.py').read_text(encoding='utf-8')
    text=original
    anchor="        browser_ready=False\n"
    assert text.count(anchor)==1;text=text.replace(anchor,PROOF+'\n'+anchor)
    text=text.replace("          write('initial-board.json',public)","          write('initial-board.json',public)\n          next_proof('before')")
    text=text.replace("['complete','verify','revoke-reader','partial-results','restore-results']:","['complete','verify','revoke-reader','partial-results','restore-results','next-snapshot-after','next-arrive-session']:")
    text=text.replace("                    done.add(name);write('controls.json',dict(done=sorted(done)))",ARRIVAL+"                    done.add(name);write('controls.json',dict(done=sorted(done)))")
    if case=='context':
        old="        workers=['hst-a','hst-b'] if mode=='scope_two' else ['hst-worker'] if mode!='idle_three' else ['hst-one','hst-two','hst-three']"
        assert old in text;text=text.replace(old,"        workers=['hst-a','hst-b']")
        text=text.replace("'project-b' if mode=='scope_two' and index else 'project'","'project-b' if index else 'project'")
        text=text.replace("'HST Second Project' if mode=='scope_two' and index else 'HST Demo Project'","'HST Second Project' if index else 'HST Demo Project'")
        text=text.replace("workspace_id=refs[0]['workspace_id'] if refs and mode!='scope_two' else None","workspace_id=None")
        anchor="          for ref in refs:\n"
        assert text.count(anchor)==1;text=text.replace(anchor,HISTORY+anchor)
    assert text!=original
    destination=root/'fixture.py';destination.write_text(text,encoding='utf-8')
    return dict(original_sha256=hashlib.sha256(original.encode()).hexdigest(),derivative_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),case=case,sql_authority_mutations=False)
