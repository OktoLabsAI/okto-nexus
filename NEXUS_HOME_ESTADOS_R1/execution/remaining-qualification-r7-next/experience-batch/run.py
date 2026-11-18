"""Prepared finite experience cuts. No allocation/import of product before explicit window.

Host Python -B only. Product child is READY interpreter -I -B via existing
birth-fenced supervisor. No provider, installation, source or prefix mutation.
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
BASE=HERE.parents[1]/'browser-hst'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def parse(text):
    text=text.replace('\r\n','\n')
    if '### Result\n'not in text:return None
    raw=text.split('### Result\n',1)[1].split('\n###',1)[0].strip()
    return json.loads(raw)if raw.startswith('{')else None
def main():
    p=argparse.ArgumentParser();p.add_argument('--ready',required=True,type=Path);p.add_argument('--source',required=True)
    p.add_argument('--window',required=True,choices=['EXPERIENCE_FUNCTIONAL_WINDOW_OPEN'])
    p.add_argument('--cut',required=True,choices=['naming','experience']);p.add_argument('--session',required=True)
    a=p.parse_args();assert a.session.startswith('hst-experience-')
    ready=json.loads(a.ready.read_text());assert ready['ready']and ready['prefix_frozen']and ready['source_commit']==a.source
    assert sha(Path(ready['wheel']))==ready['wheel_sha256']
    manifest=json.loads((a.ready.parent/'evidence/payload-manifest.json').read_text())
    installed=Path(ready['python']).parent.parent/'Lib/site-packages'
    def payload():
        count=sum(map(len,manifest.values()));bad=[n for group in manifest.values()for n,h in group.items()if not(installed/n).is_file()or sha(installed/n)!=h]
        assert count==ready['payload_files']and not bad
        return dict(files=count,mismatches=bad,wheel_sha256=ready['wheel_sha256'])
    initial_payload=payload()
    prepared=subprocess.run([sys.executable,'-B',str(BASE/'prepare_runtime.py'),'--package-ready',str(a.ready.resolve()),'--expected-source',a.source,'--mode','scope_two','--browser-window-open'],capture_output=True,text=True,encoding='utf-8',timeout=25,check=True)
    root=Path(json.loads(prepared.stdout)['root']);proof=module('experience_builder',HERE/'builder.py').build(root,naming_only=a.cut=='naming')
    runtime=json.loads((root/'runtime-ready.json').read_text());runtime['fixture_sha256']=sha(root/'fixture.py');(root/'runtime-ready.json').write_text(json.dumps(runtime,indent=2)+'\n')
    (root/'experience-builder-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    own=module('experience_containment',BASE/'containment.py').Owned(root);opened=False;steps=[];failure=None
    print(json.dumps(dict(event='ALLOCATED',root=str(root))),flush=True)
    def cli(step,*args,timeout=60):
        nonlocal opened
        out=root/('cli-experience-'+step+'.txt');assert not out.exists()
        with out.open('w',encoding='utf-8')as stream:
            child=subprocess.run([r'C:/Program Files/nodejs/npx.cmd','--yes','--package','@playwright/cli','playwright-cli','--session='+a.session,*args],stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
        if args[0]=='open'and child.returncode==0:opened=True
        observed=parse(out.read_text(encoding='utf-8'));steps.append(dict(step=step,exit_code=child.returncode,status=observed.get('status')if observed else None));own.sample()
        print(json.dumps(steps[-1]),flush=True);assert child.returncode==0,'CLI control failed: '+step
        return observed
    def control(name):
        (root/'control'/name).touch();end=time.monotonic()+35
        while time.monotonic()<end:
            path=root/'control/controls.json'
            if path.exists()and name in json.loads(path.read_text()).get('done',[]):return
            assert own.process.poll()is None,'Fixture exited in '+name
            own.sample();time.sleep(.1)
        raise RuntimeError('Control deadline '+name)
    def read(name):return json.loads((root/'control'/('exp-'+name+'.json')).read_text())
    def run(phase,**extra):
        cfg=dict(window=a.window,phase=phase,url=public['url'],screenshotPrefix=str(root/'experience-mobile'),**extra)
        script=root/('experience-'+phase+'.js');script.write_text((HERE/'browser.js').read_text().replace('__CONFIG__',json.dumps(cfg)),encoding='utf-8')
        data=cli(phase,'run-code','--filename='+str(script),timeout=75)
        assert data and data['status']in ['PASS_NAMING_PREFLIGHT','PASS_EXECUTED_SUBSET'],'Browser check incomplete/product defect: '+phase
        return data
    def cards(snapshot):return [i for column in snapshot['board']['columns'].values()for i in column['items']if i['kind']=='harness']
    def card(snapshot,ref):
        matches=[i for i in cards(snapshot)if all(i['connection'][k]==ref[k]for k in ['server_id','executor_id','binding_id','workspace_id','workspace_binding_id','agent_id'])]
        assert len(matches)==1,'Canonical binding card not unique';return matches[0]
    try:
        own.start(root/'runtime-ready.json',root/'fixture.py');end=time.monotonic()+120
        while not(root/'control/ready.json').exists():
            assert own.process.poll()is None,'Canonical preflight failed; preserve failure.json'
            assert time.monotonic()<end,'Preflight deadline';own.sample();time.sleep(.1)
        public=json.loads((root/'control/ready.json').read_text());baseline=read('base');refs=public['references']
        assert len(refs)==2 and len({r['workspace_id']for r in refs})==2
        cli('open','open','about:blank','--browser=chrome','--profile='+str(root/'browser-profile'));cli('storage','state-load',public['storage'])
        # Product AX failure is a deliberate hard stop, not an omitted keyboard element.
        run('naming')
        if a.cut=='experience':
            a_card=card(baseline,refs[0]);b_card=card(baseline,refs[1]);assert a_card['sessions_total']==0 and b_card['sessions_total']==1
            b1=baseline['sessions'][0]
            run('base',aCard=a_card['id'],bCard=b_card['id'],b1=b1,policies=baseline['policies'])
            control('exp-base-after');after=read('base-after')
            assert baseline['operations']==after['operations']and baseline['grant_digest']==after['grant_digest'],'Read UI changed runtime authority/operations'
            control('exp-b-history');history=read('history');b2=next(s for s in history['sessions']if s['scope']['session_id']!=b1['scope']['session_id'])
            run('history',bCard=b_card['id'],sessions=history['sessions'],projectLabel='Beta project')
            control('exp-external-fail')
            try:
                failed=read('external-failed');assert failed['board']['source_status']['external']=='unavailable'
                run('external',bCard=b_card['id'],b2=b2)
            finally:control('exp-external-restore')
            run('themes-mobile')
            # Questions are published only after all slow base/theme/cursor preparation.
            control('exp-start-active');active=read('active');identity=json.loads((root/'control/exp-active-identities.json').read_text())
            a1=next(s for s in active['sessions']if s['scope']['session_id']==identity['a1']['session_id']);a2=next(s for s in active['sessions']if s['scope']['session_id']==identity['a2']['session_id'])
            actual_a=card(active,refs[0]);assert actual_a['operational_status']['activity']=='working'
            run('active',aCard=a_card['id'],bCard=b_card['id'],a2=a2,projectA='Alpha project',projectB='Beta project',stateSince=actual_a['operational_status']['state_since'])
            control('exp-close-b');run('panel-after',expectedRevision=read('b-closed')['board']['revision'])
            control('exp-terminal-a1');terminal=read('a-terminal')
            moved=next(i for i in terminal['board']['columns']['needs_you']['items']if i.get('id')==a_card['id']);assert moved['kind']=='harness'
            run('moved-close',aCard=a_card['id'],expectedRevision=terminal['board']['revision'])
        (root/'experience-payload.json').write_text(json.dumps(dict(before=initial_payload,after=payload()),indent=2)+'\n')
    except BaseException as error:
        failure=dict(type=type(error).__name__,message=str(error));(root/'experience-failure.json').write_text(json.dumps(failure,indent=2)+'\n');print(json.dumps(dict(event='INCOMPLETE',root=str(root),failure=failure)),flush=True)
    finally:
        if opened:
            try:cli('close','close',timeout=25)
            except BaseException as error:steps.append(dict(step='close',error=type(error).__name__))
        (root/'control/stop').touch();end=time.monotonic()+180
        while own.process and own.process.poll()is None and time.monotonic()<end:own.sample();time.sleep(.25)
        cleanup=own.stop(force=bool(own.process and own.process.poll()is None));(root/'control/supervisor-cleanup.json').write_text(json.dumps(cleanup,indent=2)+'\n')
        (root/'experience-steps.json').write_text(json.dumps(dict(steps=steps,failure=failure,cleanup=cleanup),indent=2)+'\n');print(json.dumps(dict(event='CLOSED',root=str(root),cleanup=cleanup)),flush=True)
    return int(failure is not None)
if __name__=='__main__':raise SystemExit(main())
