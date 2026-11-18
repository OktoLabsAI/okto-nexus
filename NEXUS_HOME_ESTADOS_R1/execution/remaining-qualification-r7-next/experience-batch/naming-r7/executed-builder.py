"""Private derivative preparation only; no allocation or product import here."""
import hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=HERE.parents[1]/'browser-hst'

FUNCTIONS=r'''
        exp={}
        def exp_snapshot(name):
            board=call('GET','/api/v1/home/harness-board?presentation_version=2',headers=controls.operator_headers())
            metadata=[]
            for known in sessions:
                value=call('GET','/api/v1/runtime-management/runtime/sessions/'+known['session_id']+'?executor_id='+known['reference']['executor_id'],headers=controls.operator_headers())
                assert value['scope']['session_id']==known['session_id']
                assert all(value['scope'][k]==known['reference'][k] for k in ['server_id','executor_id','binding_id','workspace_id','workspace_binding_id','agent_id'])
                metadata.append(dict(scope=value['scope'],lifecycle_state=value['lifecycle_state'],marker=known['text']))
            policies={r['agent_id']:call('GET','/api/v1/agents/'+r['agent_id']+'/runtime-policy',headers=controls.operator_headers())for r in refs}
            with deps.connection_factory.unit_of_work(write=False) as uow:
                operations=[dict(operation_id=r['operation_id'],intent=r['intent'],scope=r['scope'])for r in operations_record]
                grants=[dict(r)for r in uow.connection.execute('SELECT * FROM runtime_execution_grants ORDER BY grant_id')]
                grant_digest=hashlib.sha256(json.dumps(grants,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            value=dict(at=deps.clock.now_iso(),board=board,sessions=metadata,policies=policies,operations=operations,grant_digest=grant_digest,grant_count=len(grants))
            write('exp-'+name+'.json',value);return value
'''

CONTROLS=r'''
                    if name=='exp-base-after':exp_snapshot('base-after')
                    if name=='exp-b-history':
                        ref=refs[1];prior=next(s for s in sessions if s['reference']['binding_id']==ref['binding_id']and not s['closed'])
                        admit(ref,'runtime.close',session_id=prior['session_id']);prior['closed']=True
                        opened=admit(ref,'runtime.start',new_session=True);sid=opened['scope']['session_id']
                        current=dict(session_id=sid,reference=ref,text='HST synthetic output '+sid,closed=False);sessions.append(current);exp['b2']=current
                        admit(ref,'turn.submit',session_id=sid,text='HST safe B response')
                        (ROOT/'control/exp-failed').touch()
                        admit(ref,'turn.submit',session_id=sid,text='HST:'+json.dumps(dict(gate='exp-failed',question=False,terminal_status='failed')),expected='FAILED')
                        exp_snapshot('history')
                    if name=='exp-external-fail':
                        assert app.state.home_entries.home.config.feature_observations
                        exp['external_original']=app.state.home_entries.queries.external
                        def missing_external(*args,**kwargs):
                            import sqlite3
                            raise sqlite3.OperationalError('Own fixture external read source unavailable')
                        patch.setattr(app.state.home_entries.queries,'external',missing_external)
                        exp_snapshot('external-failed')
                    if name=='exp-external-restore':
                        patch.setattr(app.state.home_entries.queries,'external',exp.pop('external_original'))
                        exp_snapshot('external-restored')
                    if name=='exp-start-active':
                        ref=refs[0]
                        for index,question in enumerate([False,True]):
                            opened=admit(ref,'runtime.start',new_session=True);sid=opened['scope']['session_id']
                            item=dict(session_id=sid,reference=ref,text='HST synthetic output '+sid,closed=False);sessions.append(item)
                            turn=admit(ref,'turn.submit',session_id=sid,text='HST:'+json.dumps(dict(gate='exp-a-'+str(index),question=question,blocking=True)),operator=question,wait=False)
                            exp['a'+str(index+1)]=dict(session_id=sid,operation_id=turn['operation_id'],reference=ref)
                        deadline=time.monotonic()+20
                        while True:
                            data=call('GET','/api/v1/runtime-management/runtime/input-requests',headers=controls.operator_headers());data=data if isinstance(data,list)else data.get('items',[])
                            rows=[r for r in data if r.get('request_payload',{}).get('kwargs',{}).get('approval_key',{}).get('session_id')==exp['a2']['session_id']]
                            if len(rows)==1:break
                            assert time.monotonic()<deadline,'Fresh canonical operator request not observed';time.sleep(.05)
                        write('question-preflight.json',dict(requests=rows));proposal=rows[0]['request_payload']['kwargs']
                        exp['question']=dict(request_id=rows[0].get('approval_id')or rows[0].get('request_id'),approval_key=proposal['approval_key'],expires_at=proposal['expires_at'])
                        write('exp-active-identities.json',dict(a1=exp['a1'],a2=exp['a2'],question=exp['question']))
                        exp_snapshot('active')
                    if name=='exp-close-b':
                        item=exp['b2'];admit(item['reference'],'runtime.close',session_id=item['session_id']);item['closed']=True
                        exp_snapshot('b-closed')
                    if name=='exp-terminal-a1':
                        (ROOT/'control/exp-a-0').touch();deadline=time.monotonic()+20
                        item=exp['a1']
                        while True:
                            state=call('GET','/v1/runtime/operations/'+item['operation_id'],headers={'Authorization':'Bearer '+keys[item['reference']['agent_id']],'Cookie':''})
                            if state['executor_stage']=='SUCCEEDED':break
                            assert time.monotonic()<deadline,'Canonical A1 terminal missing';time.sleep(.05)
                        exp_snapshot('a-terminal')
'''

def render(original:bytes,*,naming_only=False):
    text=original.decode('utf-8').replace('\r\n','\n')
    text=text.replace("'--feature-hitl','true',","'--feature-hitl','true','--feature-observations','true',")
    text=text.replace("        browser_ready=False\n", "        operations_record=operations\n        browser_ready=False\n")
    text=text.replace("'HST Second Project'","'Beta project for readable authorized collaborator activity and delivery'").replace("'HST Demo Project'","'Alpha project for readable authorized collaborator activity and questions'")
    anchor="        browser_ready=False\n";assert text.count(anchor)==1;text=text.replace(anchor,FUNCTIONS+'\n'+anchor)
    anchor="          for ref in refs:\n";assert text.count(anchor)==1
    text=text.replace(anchor,anchor+("            continue\n"if naming_only else"            if ref is refs[0]:continue\n"))
    anchor="          write('initial-board.json',public)";assert text.count(anchor)==1;text=text.replace(anchor,anchor+"\n          exp_snapshot('base')")
    old="['complete','verify','revoke-reader','partial-results','restore-results']:"
    new="['complete','verify','revoke-reader','partial-results','restore-results','exp-base-after','exp-b-history','exp-external-fail','exp-external-restore','exp-start-active','exp-close-b','exp-terminal-a1']:"
    assert old in text;text=text.replace(old,new)
    anchor="                    done.add(name);write('controls.json',dict(done=sorted(done)))";assert text.count(anchor)==1;text=text.replace(anchor,CONTROLS+anchor)
    return text

def build(root:Path,*,naming_only=False):
    assert root.name.startswith('nexus-hst-browser-')
    original=(BASE/'fixture.py').read_bytes();text=render(original,naming_only=naming_only)
    (root/'fixture.py').write_text(text,encoding='utf-8')
    return dict(original_sha256=hashlib.sha256(original).hexdigest(),derivative_sha256=hashlib.sha256((root/'fixture.py').read_bytes()).hexdigest(),naming_only=naming_only,max_sessions=0 if naming_only else 4,question_published_after_base=True,question_ttl='Original120s, never renewed',authority_sql_mutations=False,provider_invocations=0)
