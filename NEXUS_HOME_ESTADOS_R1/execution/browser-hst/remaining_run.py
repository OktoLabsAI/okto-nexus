"""Reviewed, small F14 or I06 fixture; one bounded run per own allocation."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
def main():
    p=argparse.ArgumentParser();p.add_argument('--ready',type=Path,required=True);p.add_argument('--source',required=True);p.add_argument('--case',choices=['history','dirty'],required=True);p.add_argument('--session',required=True);p.add_argument('--window',choices=['REMAINING_FUNCTIONAL_WINDOW_OPEN'],required=True);a=p.parse_args()
    assert a.session.startswith('hst-rem-');common=module('remaining_common',HERE/'nextcuts_run.py');ready=json.loads(a.ready.read_text());assert ready['ready']and ready['prefix_frozen']and ready['source_commit']==a.source and common.sha(Path(ready['wheel']))==ready['wheel_sha256']
    payload=json.loads((a.ready.parent/'evidence/payload-manifest.json').read_text());site=Path(ready['python']).parent.parent/'Lib/site-packages'
    def verify_payload():
        count=sum(len(x)for x in payload.values());bad=[name for items in payload.values()for name,sha in items.items()if not(site/name).exists()or common.sha(site/name)!=sha];assert count==ready['payload_files']and not bad;return dict(files=count,mismatches=bad)
    payload_before=verify_payload()
    prepared=subprocess.run([sys.executable,'-B',str(HERE/'prepare_runtime.py'),'--package-ready',str(a.ready.resolve()),'--expected-source',a.source,'--mode','baseline'if a.case=='history'else'scope_two','--browser-window-open'],capture_output=True,text=True,encoding='utf-8',timeout=20,check=True)
    root=Path(json.loads(prepared.stdout)['root']);builder=module('remaining_builder',HERE/'remaining_fixture_builder.py');proof=builder.build(root,a.case)
    config=json.loads((root/'runtime-ready.json').read_text());config['fixture_sha256']=common.sha(root/'fixture.py');(root/'runtime-ready.json').write_text(json.dumps(config,indent=2)+'\n');(root/'remaining-builder-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    owner=module('remaining_containment',HERE/'containment.py').Owned(root);opened=False;failure=None;steps=[]
    print(json.dumps(dict(event='ALLOCATED',case=a.case,root=str(root))),flush=True)
    def cli(name,*args,timeout=65):
        nonlocal opened
        out=root/('cli-'+name+'.txt');assert not out.exists()
        with out.open('w',encoding='utf-8')as f:r=subprocess.run([r'C:/Program Files/nodejs/npx.cmd','--yes','--package','@playwright/cli','playwright-cli','--session='+a.session,*args],stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
        if args[0]=='open'and r.returncode==0:opened=True
        data=common.result(out.read_text(encoding='utf-8'));step=dict(name=name,exit_code=r.returncode,status=data.get('status')if data else None);steps.append(step);owner.sample();print(json.dumps(step),flush=True)
        if r.returncode:raise RuntimeError('CLI exit at '+name)
        return data
    def script(source,name,cfg):
        target=root/name;target.write_text((HERE/source).read_text(encoding='utf-8').replace('__CONFIG__',json.dumps(cfg)),encoding='utf-8');return str(target)
    def checked(name,source,cfg,status='PASS_SUBSET'):
        result=cli(name,'run-code','--filename='+script(source,name+'.js',cfg));assert result and result['status']==status,'Browser assertion incomplete at '+name;return result
    def control(name,timeout=40):
        (root/'control'/name).touch();end=time.monotonic()+timeout
        while time.monotonic()<end:
            marker=root/'control/controls.json'
            if marker.exists()and name in json.loads(marker.read_text()).get('done',[]):return
            if owner.process.poll()is not None:raise RuntimeError('Fixture exited during '+name)
            owner.sample();time.sleep(.1)
        raise RuntimeError('Canonical control deadline: '+name)
    try:
        pid=owner.start(root/'runtime-ready.json',root/'fixture.py');print(json.dumps(dict(event='STARTED',pid=pid)),flush=True);end=time.monotonic()+75
        while not(root/'control/ready.json').exists():
            if owner.process.poll()is not None:raise RuntimeError('Canonical preflight failed; preserve data')
            assert time.monotonic()<end,'Canonical preflight deadline';owner.sample();time.sleep(.1)
        cfg=json.loads((root/'control/ready.json').read_text());metadata=json.loads((root/'control/remaining-session-metadata.json').read_text());assert len(metadata)==2 and len({x['scope']['session_id']for x in metadata})==2
        base=dict(window=a.window,url=cfg['url'],workspace_id=cfg['workspace_id']);print(json.dumps(dict(event='READY',url=cfg['url'],questions_published=0)),flush=True)
        cli('open','open','about:blank','--browser=chrome','--profile='+str(root/'browser-profile'));cli('state','state-load',cfg['storage'])
        if a.case=='history':
            retained=next(x for x in metadata if x['lifecycle_state']=='CLOSED');sid=retained['scope']['session_id'];board=json.loads((root/'control/initial-board.json').read_text());delivery=next(x for x in board['columns']['results']['items']if x['kind']=='delivery'and x.get('result',{}).get('detail_target',{}).get('session_id')==sid)
            case=dict(base,session_id=sid,expected_scope=retained['scope'],target=delivery['result']['detail_target'],delivery_id=delivery['id'])
            checked('history-open','remaining_history_open.js',case)
            for step,command,phase in [('reload','reload','reload'),('back','go-back','back'),('forward','go-forward','forward')]:
                cli(step,command)
                if 'beforeunload'in(root/('cli-'+step+'.txt')).read_text(encoding='utf-8'):cli(step+'-accept','dialog-accept')
                checked(step+'-verify','remaining_history_verify.js',dict(case,phase=phase))
            # Reuse the already reviewed invalid-reference phase; its selected
            # tuple is supplied from actual preflight metadata, not guessed.
            scope=retained['scope'];selected=json.dumps([scope[k]for k in ['server_id','executor_id','workspace_id','session_id']])
            checked('invalid','nextcuts-invalid.js',dict(case,selected=selected))
        else:
            init=cli('initialize','run-code','--filename='+script('initialize-template.js','initialize.js',base));assert init is not None,'Initial actual Home not observed'
            checked('ready-for-questions','remaining_dirty_ready.js',dict(base,card_id=cfg['card_id']),status='READY_FOR_FRESH_QUESTIONS')
            control('remaining-publish-questions')
            fresh=json.loads((root/'control/remaining-fresh-questions.json').read_text());qa=next(x for x in fresh['requests']if x['approval_key']['workspace_id']==cfg['references'][0]['workspace_id']);qb=next(x for x in fresh['requests']if x['approval_key']['workspace_id']==cfg['references'][1]['workspace_id'])
            case=dict(base,a=qa,b=qb);checked('dirty','remaining_dirty.js',case,status='READY_REAL_LOGOUT');control('revoke-reader');checked('auth','remaining_auth.js',dict(case,workspace_id=qb['approval_key']['workspace_id']))
        (root/'remaining-payload-proof.json').write_text(json.dumps(dict(before=payload_before,after=verify_payload()),indent=2)+'\n')
    except BaseException as error:
        failure=dict(type=type(error).__name__,message=str(error));(root/'remaining-failure.json').write_text(json.dumps(failure,indent=2)+'\n');print(json.dumps(dict(event='INCOMPLETE',root=str(root),type=type(error).__name__)),flush=True)
    finally:
        if opened:
            try:cli('close','close',timeout=25)
            except BaseException as error:steps.append(dict(name='close',error=type(error).__name__))
        (root/'control/stop').touch();end=time.monotonic()+180
        while owner.process and owner.process.poll()is None and time.monotonic()<end:owner.sample();time.sleep(.25)
        cleanup=owner.stop(force=bool(owner.process and owner.process.poll()is None));(root/'control/supervisor-cleanup.json').write_text(json.dumps(cleanup,indent=2)+'\n');(root/'remaining-steps.json').write_text(json.dumps(dict(case=a.case,failure=failure,steps=steps,cleanup=cleanup),indent=2)+'\n');print(json.dumps(dict(event='CLOSED',root=str(root),cleanup=cleanup)),flush=True)
    return 1 if failure else 0
if __name__=='__main__':raise SystemExit(main())
