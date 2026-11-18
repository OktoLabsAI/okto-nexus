"""Finite installed browser cuts; allocation is forbidden before explicit gate.

Run from host Python-B. Child product interpreter is the READY prefix-I-B.
No source/product imports, installation, provider discovery or personal state.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def result(text):
    text=text.replace('\r\n','\n')
    if '### Result\n'not in text:return None
    raw=text.split('### Result\n',1)[1].split('\n###',1)[0].strip()
    return json.loads(raw)if raw.startswith('{')else None
def main():
    p=argparse.ArgumentParser();p.add_argument('--ready',type=Path,required=True);p.add_argument('--source',required=True)
    p.add_argument('--window',choices=['POST_PERF_BROWSER_WINDOW_OPEN'],required=True)
    p.add_argument('--cut',choices=['decision','context'],required=True);p.add_argument('--session',required=True)
    a=p.parse_args();assert a.session.startswith('hst-next-')
    ready=json.loads(a.ready.read_text(encoding='utf-8'));assert ready['source_commit']==a.source and ready['prefix_frozen']and ready['ready']
    assert sha(Path(ready['wheel']))==ready['wheel_sha256']
    payload=json.loads((a.ready.parent/'evidence/payload-manifest.json').read_text())
    base=Path(ready['python']).parent.parent/'Lib/site-packages'
    def payload_proof():
        mismatches=[name for group in payload.values()for name,digest in group.items()if not(base/name).exists()or sha(base/name)!=digest]
        count=sum(map(len,payload.values()));assert count==ready['payload_files']and not mismatches
        return dict(files=count,mismatches=mismatches,wheel_sha256=ready['wheel_sha256'])
    start_payload=payload_proof()
    command=[sys.executable,'-B',str(HERE/'prepare_runtime.py'),'--package-ready',str(a.ready.resolve()),'--expected-source',a.source,'--mode','question','--browser-window-open']
    if a.cut=='decision':command+=['--allow-native-decision']
    prepared=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',check=True,timeout=20)
    root=Path(json.loads(prepared.stdout)['root']);builder=load_module('next_owned_builder',HERE/'nextcuts_fixture_builder.py');derivative=builder.build(root,a.cut)
    config=json.loads((root/'runtime-ready.json').read_text());config['fixture_sha256']=sha(root/'fixture.py');(root/'runtime-ready.json').write_text(json.dumps(config,indent=2)+'\n')
    (root/'next-builder-proof.json').write_text(json.dumps(derivative,indent=2)+'\n')
    own=load_module('next_owned_containment',HERE/'containment.py').Owned(root);opened=False;steps=[];failure=None
    print(json.dumps(dict(event='ALLOCATED',cut=a.cut,root=str(root))),flush=True)
    def cli(step,*args,timeout=75):
        nonlocal opened
        out=root/('cli-'+step+'.txt');assert not out.exists()
        with out.open('w',encoding='utf-8')as f:
            child=subprocess.run([r'C:/Program Files/nodejs/npx.cmd','--yes','--package','@playwright/cli','playwright-cli','--session='+a.session,*args],stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
        if args[0]=='open'and child.returncode==0:opened=True
        data=result(out.read_text(encoding='utf-8'));item=dict(step=step,exit_code=child.returncode,status=data.get('status')if data else None)
        steps.append(item);print(json.dumps(item),flush=True);own.sample()
        if child.returncode:raise RuntimeError('CLI exit at '+step)
        return data
    def script(source,name,cfg):
        target=root/name;target.write_text((HERE/source).read_text(encoding='utf-8').replace('__CONFIG__',json.dumps(cfg)),encoding='utf-8');return str(target)
    def control(name,timeout=25):
        (root/'control'/name).touch();end=time.monotonic()+timeout
        while time.monotonic()<end:
            marker=root/'control/controls.json'
            if marker.exists()and name in json.loads(marker.read_text()).get('done',[]):return
            if own.process.poll()is not None:raise RuntimeError('Fixture exited during '+name)
            own.sample();time.sleep(.1)
        raise RuntimeError('Canonical control deadline: '+name)
    try:
        pid=own.start(root/'runtime-ready.json',root/'fixture.py');print(json.dumps(dict(event='STARTED',pid=pid)),flush=True)
        end=time.monotonic()+120
        while not(root/'control/ready.json').exists():
            if own.process.poll()is not None:raise RuntimeError('Canonical preflight refused; preserve raw failure')
            if time.monotonic()>end:raise RuntimeError('Canonical preflight deadline')
            own.sample();time.sleep(.1)
        cfg=json.loads((root/'control/ready.json').read_text());proof=json.loads((root/'control/next-before.json').read_text())
        request=next(x for x in proof['requests']if x['approval_key']['workspace_id']==cfg['workspace_id'])
        public_cfg=dict(window=a.window,url=cfg['url'],workspace_id=cfg['workspace_id'],request_id=request['request_id'],session_id=request['approval_key']['session_id'],question_expires_at=request['expires_at'],storage=cfg['storage'])
        print(json.dumps(dict(event='READY',url=cfg['url'],expires_at=request['expires_at'])),flush=True)
        cli('open','open','about:blank','--browser=chrome','--profile='+str(root/'browser-profile'))
        cli('state','state-load',cfg['storage'])
        if a.cut=='decision':
            browser=script('nextcuts-decision-browser.js','next-decision.js',public_cfg)
            observed=cli('decision','run-code','--filename='+browser,timeout=90)
            control('next-snapshot-after')
            after=json.loads((root/'control/next-after.json').read_text())
            assert observed and observed['status']=='PASS_BROWSER_SUBSET','Browser prerequisite/assertion incomplete; inspect original result before host effects'
            target=request['request_id'];before_rows=[x for x in proof['decisions']if x['canonical_request_id']==target];rows=[x for x in after['decisions']if x['canonical_request_id']==target]
            assert not before_rows and len(rows)==1,'Durable decision count is not exactly one'
            row=rows[0];writes=[x for x in after['native_writes']if x['operation_id']==row['native_operation_id']]
            assert len(writes)==1 and len(after['native_writes'])-len(proof['native_writes'])==1,'Native write count differs from one'
            assert row['actor_agent_id']=='operator'and row['session_id']==public_cfg['session_id']and row['workspace_id']==public_cfg['workspace_id'],'Decision authority tuple changed'
            assert proof['productive_operations']==after['productive_operations'],'Recovery created productive operation'
            receipts=after['receipts'][row['native_operation_id']];assert receipts,'No canonical receipt observed'
            assert observed and observed['status']=='PASS_BROWSER_SUBSET'and len(observed['posts'])==2
            assert row['client_intent_id']==observed['receipt']['client_intent_id']and row['decision_id']==observed['receipt']['decision_id'],'Recovered a different intent or receipt'
            host=dict(status='PASS_HOST_CANONICAL_INVARIANTS',decision_count=1,native_write_count=1,post_count=2,receipt_count=len(receipts),receipt_revisions=[x['receipt_revision']for x in receipts],receipt_stages=[x['stage']for x in receipts],decision_id=row['decision_id'],native_operation_id=row['native_operation_id'],client_intent_id=row['client_intent_id'],same_productive_operations=True,operator_identity_preserved=True)
            (root/'next-host-invariants.json').write_text(json.dumps(host,indent=2)+'\n')
        else:
            browser=script('nextcuts-context-browser.js','next-context.js',dict(public_cfg,reference=cfg['references'][0],workspace_b=cfg['references'][1]['workspace_id'],card_id=cfg['card_id']))
            first=cli('context-first','run-code','--filename='+browser,timeout=60)
            if not first or first['status']!='READY_CANONICAL_ARRIVAL':raise RuntimeError('Paginated UI precondition not ready')
            control('next-arrive-session',timeout=45)
            phase_cfg=dict(public_cfg,selected=first['selected'],relation_path=first['relation_path'],workspace_b=cfg['references'][1]['workspace_id'])
            follow=script('nextcuts-context-page.js','next-context-page.js',phase_cfg)
            observed=cli('context-finish','run-code','--filename='+follow,timeout=90)
            if not observed or observed['status']!='PASS_F05_HISTORY_READY':raise RuntimeError('Context functional check failed or incomplete')
            for step,command,phase in [('history-reload','reload','reload'),('history-back','go-back','closed'),('history-forward','go-forward','forward')]:
                cli(step,command)
                if 'beforeunload'in(root/('cli-'+step+'.txt')).read_text(encoding='utf-8'):cli(step+'-accept','dialog-accept')
                verify=script('nextcuts-history.js',step+'.js',dict(phase_cfg,phase=phase))
                checked=cli(step+'-verify','run-code','--filename='+verify)
                if not checked or checked['status']!='PASS_BROWSER_SUBSET':raise RuntimeError('History phase incomplete at '+step)
            invalid=script('nextcuts-invalid.js','next-invalid.js',phase_cfg);checked=cli('invalid','run-code','--filename='+invalid)
            if not checked or checked['status']!='PASS_BROWSER_SUBSET':raise RuntimeError('Invalid target phase incomplete')
            dirty=script('nextcuts-dirty.js','next-dirty.js',phase_cfg);checked=cli('dirty','run-code','--filename='+dirty)
            if not checked or checked['status']!='PASS_BROWSER_SUBSET':raise RuntimeError('Dirty guard phase incomplete')
            control('next-snapshot-after')
            after=json.loads((root/'control/next-after.json').read_text());arrival=json.loads((root/'control/next-arrival.json').read_text())
            assert after['decisions']==proof['decisions']and after['native_writes']==proof['native_writes'],'Read-only context changed decision/native-write rows'
            old_ids={x['operation_id']for x in proof['productive_operations']};new_ops=[x for x in after['productive_operations']if x['operation_id']not in old_ids]
            assert {x['operation_id']for x in new_ops}=={arrival['open_operation_id'],arrival['turn_operation_id']},'Unexpected productive operation beyond explicit canonical arrival'
            (root/'next-host-invariants.json').write_text(json.dumps(dict(status='PASS_HOST_CANONICAL_INVARIANTS',browser_post_count=len(observed['posts']),decision_rows_unchanged=True,native_writes_unchanged=True,explicit_facilitator_arrival=arrival,other_productive_operations_created=0),indent=2)+'\n')
            control('revoke-reader');logout=script('logout-template.js','logout.js',dict(url=cfg['url'],workspace_id=cfg['references'][1]['workspace_id']))
            revoked=cli('logout','run-code','--filename='+logout)
            assert revoked and revoked['status']=='PASS_SUBSET','Own logout cleanup not proved'
        (root/'next-payload-proof.json').write_text(json.dumps(dict(before=start_payload,after=payload_proof()),indent=2)+'\n')
    except BaseException as error:
        failure=dict(type=type(error).__name__,message=str(error));(root/'next-run-failure.json').write_text(json.dumps(failure,indent=2)+'\n');print(json.dumps(dict(event='INCOMPLETE',type=type(error).__name__,root=str(root))),flush=True)
    finally:
        if opened:
            try:cli('close','close',timeout=25)
            except BaseException as error:steps.append(dict(step='close',error=type(error).__name__))
        (root/'control/stop').touch();end=time.monotonic()+(180 if a.cut=='context'else 100)
        while own.process and own.process.poll()is None and time.monotonic()<end:own.sample();time.sleep(.25)
        cleanup=own.stop(force=bool(own.process and own.process.poll()is None));(root/'control/supervisor-cleanup.json').write_text(json.dumps(cleanup,indent=2)+'\n')
        (root/'next-steps.json').write_text(json.dumps(dict(cut=a.cut,steps=steps,failure=failure,cleanup=cleanup),indent=2)+'\n');print(json.dumps(dict(event='CLOSED',root=str(root),cleanup=cleanup)),flush=True)
    return 1 if failure else 0
if __name__=='__main__':raise SystemExit(main())
