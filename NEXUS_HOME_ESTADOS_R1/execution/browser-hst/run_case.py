"""Finite prepared fixture + CLI sequence; no idle gap between READY and actions."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import importlib.util

HERE=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--ready',type=Path,required=True)
    p.add_argument('--source',required=True)
    p.add_argument('--case',choices=['scope','negative','info','pause','smoke','visual','r7'],required=True)
    p.add_argument('--session',required=True)
    a=p.parse_args();assert a.session.startswith('hst-')
    mode={'scope':'scope_two','negative':'failed_cancelled','info':'delayed_info','pause':'delayed_info','smoke':'question','visual':'baseline','r7':'question'}[a.case]
    prepared=subprocess.run([sys.executable,'-B',str(HERE/'prepare_runtime.py'),'--package-ready',str(a.ready.resolve()),
        '--expected-source',a.source,'--mode',mode,'--browser-window-open'],capture_output=True,text=True,encoding='utf-8',check=True)
    allocation=json.loads(prepared.stdout);root=Path(allocation['root'])
    spec=importlib.util.spec_from_file_location('hst_case_containment',HERE/'containment.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    owner=m.Owned(root);outcomes=[];opened=False
    print(json.dumps(dict(event='ALLOCATED',root=str(root),case=a.case)),flush=True)
    def cli(name,*command,timeout=65):
        nonlocal opened
        path=root/('cli-'+name+'.txt');assert not path.exists()
        with path.open('w',encoding='utf-8')as f:
            child=subprocess.run([r'C:/Program Files/nodejs/npx.cmd','--yes','--package','@playwright/cli','playwright-cli',
                 '--session='+a.session,*command],stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
        if command[0]=='open'and child.returncode==0:opened=True
        text=path.read_text(encoding='utf-8').replace('\r\n','\n');result=None
        if '### Result\n'in text:
            body=text.split('### Result\n',1)[1].split('\n###',1)[0].strip()
            if body.startswith('{'):result=json.loads(body)
        item=dict(step=name,exit_code=child.returncode,status=result.get('status')if result else None,
                  failed_checks=[x['id']for x in result.get('checks',[])if x.get('ok')is False]if result else [])
        outcomes.append(item);owner.sample();print(json.dumps(item),flush=True)
        if child.returncode:raise RuntimeError('CLI failed at '+name)
        return result
    def script(template,name,value):
        path=root/name;path.write_text((HERE/template).read_text(encoding='utf-8').replace('__CONFIG__',json.dumps(value)),encoding='utf-8');return str(path)
    try:
        pid=owner.start(root/'runtime-ready.json',root/'fixture.py');print(json.dumps(dict(event='STARTED',pid=pid)),flush=True)
        deadline=time.monotonic()+75
        while not(root/'control/ready.json').exists():
            owner.sample()
            if owner.process.poll()is not None:raise RuntimeError('Canonical preflight failed; raw data retained')
            assert time.monotonic()<deadline,'Canonical preflight timeout';time.sleep(.1)
        cfg=json.loads((root/'control/ready.json').read_text());print(json.dumps(dict(event='READY',url=cfg['url'])),flush=True)
        initialize=dict(url=cfg['url'],workspace_id='all'if a.case=='scope'else cfg['workspace_id'])
        init=script('initialize-template.js','initialize.js',initialize)
        if a.case=='scope':
            first,second=cfg['references'];sa=next(x for x in cfg['sessions']if x['reference']['workspace_id']==first['workspace_id']);sb=next(x for x in cfg['sessions']if x['reference']['workspace_id']==second['workspace_id'])
            case_cfg=dict(url=cfg['url'],a={**first,**{k:sa[k]for k in ['session_id','text']}},b={**second,**{k:sb[k]for k in ['session_id','text']}},screenshot=str((HERE.parents[2]/'output/playwright/home-states/r5-scope-late.png').resolve()))
            (root/'scope-config.json').write_text(json.dumps(case_cfg,indent=2)+'\n')
            test=script('scope-race-template.js','scope-race.js',case_cfg)
        elif a.case=='negative':
            case_cfg=dict(url=cfg['url'],workspace_id=cfg['workspace_id'],negative=json.loads((root/'control/negative-preflight.json').read_text()),screenshot=str((HERE.parents[2]/'output/playwright/home-states/r5-negative.png').resolve()))
            test=script('negative-template.js','negative.js',case_cfg)
        elif a.case in ['info','pause']:
            case_cfg=dict(url=cfg['url'],workspace_id=cfg['workspace_id'],screenshot=str((HERE.parents[2]/'output/playwright/home-states/r6-info-draft.png').resolve()))
            test=script('info-r6-template.js'if a.case=='info'else 'pause-info-template.js','info-upgrade.js',case_cfg)
        elif a.case=='r7':
            request=json.loads((root/'control/question-preflight.json').read_text())['requests'][0]
            request_id=request.get('request_id')or request['approval_id']
            case_cfg=dict(url=cfg['url'],workspace_id=cfg['workspace_id'],card_id=cfg['card_id'],request_id=request_id,stage='parallel',activity='working',apiOnly=False)
            test=script('question-state-template.js','question-parallel.js',case_cfg)
        elif a.case=='smoke':
            case_cfg=dict(url=cfg['url'],workspace_id=cfg['workspace_id'],screenshot=str((HERE.parents[2]/'output/playwright/home-states/r6-final-mobile.png').resolve()))
            test=script('final-smoke-template.js','final-smoke.js',case_cfg)
        else:
            image=HERE.parents[2]/'output/playwright/home-states'
            case_cfg=dict(url=cfg['url'],workspace_id=cfg['workspace_id'],desktop=str((image/'r6-visual-desktop.png').resolve()),mobile=str((image/'r6-visual-mobile.png').resolve()))
            test=script('mobile-intents-template.js','mobile-intents.js',case_cfg)
        cli('open','open','about:blank','--browser=chrome','--profile='+str(root/'browser-profile'))
        cli('state','state-load',cfg['storage'])
        if a.case not in ['info','pause']:cli('initialize','run-code','--filename='+init)
        cli(a.case,'run-code','--filename='+test)
        if a.case=='r7':
            (root/'control/release-1').touch()
            blocked=script('question-state-template.js','question-blocked.js',dict(case_cfg,stage='blocked',activity='waiting_user'))
            cli('blocked','run-code','--filename='+blocked)
            context=script('r7-context-template.js','r7-context.js',dict(case_cfg,reference=cfg['references'][0],session_a=cfg['sessions'][0]['session_id'],session_b=cfg['sessions'][1]['session_id']))
            cli('context','run-code','--filename='+context)
            (root/'control/partial-results').touch();time.sleep(.5)
            partial=script('partial-logout-template.js','partial.js',dict(url=cfg['url'],workspace_id=cfg['workspace_id']))
            cli('partial','run-code','--filename='+partial)
            (root/'control/restore-results').touch();time.sleep(.3)
            (root/'control/revoke-reader').touch();time.sleep(.5)
            logout=script('logout-template.js','logout.js',dict(url=cfg['url'],workspace_id=cfg['workspace_id']))
            cli('logout','run-code','--filename='+logout)
        if a.case=='pause':
            (root/'control/revoke-reader').touch()
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                controls=root/'control/controls.json'
                if controls.exists()and'revoke-reader'in json.loads(controls.read_text()).get('done',[]):break
                time.sleep(.1)
            logout=script('logout-template.js','logout.js',dict(url=cfg['url'],workspace_id=cfg['workspace_id']))
            cli('logout','run-code','--filename='+logout)
    finally:
        if opened:
            try:cli('close','close',timeout=25)
            except Exception as error:outcomes.append(dict(step='close',error=type(error).__name__))
        (root/'control/stop').touch()
        end=time.monotonic()+100
        while owner.process and owner.process.poll()is None and time.monotonic()<end:
            owner.sample();time.sleep(.25)
        cleanup=owner.stop(force=bool(owner.process and owner.process.poll()is None))
        (root/'control/supervisor-cleanup.json').write_text(json.dumps(cleanup,indent=2)+'\n')
        (root/'case-steps.json').write_text(json.dumps(dict(case=a.case,steps=outcomes,cleanup=cleanup),indent=2)+'\n')
        print(json.dumps(dict(event='CLOSED',root=str(root),cleanup=cleanup)),flush=True)


if __name__=='__main__':main()
