"""Small F14/I06 derivative; no allocation/import/product execution here."""
import hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent

CAPTURE=r'''
          metadata=[]
          for known in sessions:
            value=call('GET','/api/v1/runtime-management/runtime/sessions/'+known['session_id']+'?executor_id='+known['reference']['executor_id'],headers=controls.operator_headers())
            assert value['scope']['session_id']==known['session_id'],'RuntimeSession publishes scope.session_id'
            assert all(value['scope'][key]==known['reference'][key] for key in ['server_id','executor_id','workspace_id','binding_id','workspace_binding_id'])
            metadata.append(dict(scope=value['scope'],lifecycle_state=value['lifecycle_state'],top_level_keys=sorted(value)))
          write('remaining-session-metadata.json',metadata)
'''

PUBLISH=r'''
                    if name=='remaining-publish-questions':
                        created=[]
                        for qindex,ref in enumerate(refs):
                            opened=admit(ref,'runtime.start',new_session=True);sid=opened['scope']['session_id']
                            sessions.append(dict(session_id=sid,reference=ref,text='HST synthetic output '+sid,closed=False))
                            turn=admit(ref,'turn.submit',session_id=sid,text='HST:'+json.dumps(dict(gate='remaining-'+str(qindex),question=True,blocking=True,message='Synthetic output')),operator=True,wait=False)
                            created.append(dict(session_id=sid,reference=ref,operation_id=turn['operation_id']))
                        deadline=time.monotonic()+20
                        while True:
                            data=call('GET','/api/v1/runtime-management/runtime/input-requests',headers=controls.operator_headers())
                            data=data if isinstance(data,list) else data.get('items',[])
                            relevant=[item for item in data if item.get('request_payload',{}).get('kwargs',{}).get('approval_key',{}).get('session_id') in {q['session_id']for q in created}]
                            if len(relevant)==len(created):break
                            assert time.monotonic()<deadline,'Fresh canonical requests not observed';time.sleep(.05)
                        write('question-preflight.json',dict(requests=relevant))
                        public=[]
                        for item in relevant:
                            params=item['request_payload']['kwargs'];public.append(dict(request_id=item.get('approval_id')or item.get('request_id'),approval_key=params['approval_key'],expires_at=params['expires_at']))
                        write('remaining-fresh-questions.json',dict(created=created,requests=public,published_at=deps.clock.now_iso(),ttl_policy='Original native120s; no renewal'))
'''

def build(root,case):
    assert case in ('history','dirty')and root.name.startswith('nexus-hst-browser-')
    original=(HERE/'fixture.py').read_bytes();text=original.decode('utf-8').replace('\r\n','\n')
    anchor="          if not browser_ready:controls.configure_browser_session()\n";assert text.count(anchor)==1;text=text.replace(anchor,anchor+CAPTURE)
    if case=='dirty':
        text=text.replace("['complete','verify','revoke-reader','partial-results','restore-results']:","['complete','verify','revoke-reader','partial-results','restore-results','remaining-publish-questions']:")
        anchor="                    done.add(name);write('controls.json',dict(done=sorted(done)))";assert text.count(anchor)==1;text=text.replace(anchor,PUBLISH+anchor)
    (root/'fixture.py').write_text(text,encoding='utf-8')
    return dict(case=case,original_sha256=hashlib.sha256(original).hexdigest(),derivative_sha256=hashlib.sha256((root/'fixture.py').read_bytes()).hexdigest(),session_metadata_contract='RuntimeSession.scope.session_id; direct JSON, no top-level session_id',history_seed_sessions=2,questions_initially_published=0,authority_sql_mutations=False)
