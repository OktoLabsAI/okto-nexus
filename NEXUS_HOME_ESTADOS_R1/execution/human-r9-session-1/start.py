"""Explicitly authorized own human session. No participant tasks automated."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2];NEXT=REPO/'NEXUS_HOME_ESTADOS_R1/execution/remaining-qualification-r7-next'
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    frozen=load('human_frozen_guard',NEXT/'keyboard-app-r9-prepared/run_v4.py')
    before,manifest,_,ready=frozen.check(NEXT/'keyboard-app-r9-prepared/ROOT-GATE-v4.json')
    browser=REPO/'NEXUS_HOME_ESTADOS_R1/execution/browser-hst'
    allocated=subprocess.run([sys.executable,'-B',str(browser/'prepare_runtime.py'),'--package-ready',str(REPO/manifest['ready']),'--expected-source',ready['source_commit'],'--mode','scope_two','--browser-window-open'],input=b'',capture_output=True,timeout=25,check=True)
    root=Path(json.loads(allocated.stdout)['root']);print(json.dumps(dict(event='ALLOCATED',root=str(root))),flush=True)
    builder=load('human_experience_builder',NEXT/'experience-batch/builder.py');builder.build(root)
    fixture=root/'fixture.py';text=fixture.read_text();assert text.count('end=time.monotonic()+300')==1
    text=text.replace('end=time.monotonic()+300','end=time.monotonic()+900')
    text=text.replace('Alpha project for readable authorized collaborator activity and questions','Site da loja').replace('Beta project for readable authorized collaborator activity and delivery','Relatório de vendas')
    text=text.replace("name.replace('-',' ').title()","{'hst-a':'Ana','hst-b':'Bruno'}.get(name,name.replace('-',' ').title())")
    fixture.write_text(text,encoding='utf-8');runtime=json.loads((root/'runtime-ready.json').read_text());runtime['fixture_sha256']=sha(fixture);write(root/'runtime-ready.json',runtime)
    config=json.loads((NEXT/'native-zoom-batch/playwright-cli.json').read_text());config['browser']['launchOptions']['headless']=False;write(root/'playwright-cli.json',config)
    life=load('human_lifecycle',browser/'containment.py');driver=load('human_browser_env',NEXT/'security-r9-batch/browser_driver.py');manager=load('human_commands',NEXT/'security-r9-batch/run.py')
    owner=life.Owned(root);commands=manager.Commands(root,driver.environment(root),time.monotonic()+1000)
    session='hst-human-r9-1';tool=manifest['tooling'];rtk=shutil.which('rtk');opened=False;failure=None
    def cli(name,*args,cleanup=False):return commands.run(name,[rtk,'proxy',tool['node'],tool['entry'],'--session='+session,*args],timeout=45,cleanup=cleanup)
    try:
        owner.start(root/'runtime-ready.json',fixture);end=time.monotonic()+65
        while not(root/'control/ready.json').exists():
            assert owner.process.poll()is None and time.monotonic()<end,'Human fixture failed before ready';owner.sample();time.sleep(.1)
        state=json.loads((root/'control/ready.json').read_text());assert state['provider_invocations']==0
        opened=True;cli('launch','open','about:blank','--browser=chrome','--profile='+str(root/'browser-profile'),'--config='+str(root/'playwright-cli.json'))
        cli('load-cookie','state-load',state['storage'])
        bootstrap='''async page=>{
          const url=__URL__;page.__humanHTTP=[];
          page.on('response',r=>page.__humanHTTP.push({at:new Date().toISOString(),method:r.request().method(),path:new URL(r.url()).pathname,status:r.status()}));
          await page.addInitScript(origin=>{if(location.origin!==origin)return;localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','all');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0',new Date().toISOString());window.__humanClicks=[];document.addEventListener('click',e=>{if(!e.isTrusted)return;const n=e.target.closest('button,a,summary');window.__humanClicks.push({at:new Date().toISOString(),trusted:true,tag:e.target.tagName,control:n?.tagName??null,label:n?(n.getAttribute('aria-label')||n.textContent||'').trim().slice(0,100):null});},true);},new URL(url).origin);
          await page.setViewportSize({width:1440,height:1000});await page.goto(url);await page.getByTestId('home-follow-up').waitFor({timeout:20000});
          return {status:'HUMAN_BOOTSTRAP_READY',url:page.url(),columns:await page.locator('[data-home-column]').count()};
        }'''.replace('__URL__',json.dumps(state['url']))
        (root/'bootstrap.js').write_text(bootstrap);boot=manager.cli_result(cli('bootstrap','run-code','--filename='+str(root/'bootstrap.js')));assert boot['columns']==3
        (root/'control/exp-start-active').touch();end=time.monotonic()+35
        while True:
            try:done=json.loads((root/'control/controls.json').read_text())['done']
            except (FileNotFoundError,json.JSONDecodeError):done=[]
            if 'exp-start-active'in done:break
            assert owner.process.poll()is None and time.monotonic()<end,'Fresh human active preflight failed';owner.sample();time.sleep(.1)
        active=json.loads((root/'control/exp-active.json').read_text());identity=json.loads((root/'control/exp-active-identities.json').read_text())
        cards=[i for c in active['board']['columns'].values()for i in c['items']if i['kind']=='harness'];assert any(i['operational_status']['activity']=='working'and i['operational_status']['freshness']=='current'for i in cards)
        show='''async page=>{await page.reload();await page.getByTestId('home-follow-up').waitFor();await page.locator('[data-home-badge="Working"]').waitFor({timeout:15000});return {url:page.url(),working:true,openDialogs:await page.locator('dialog[open]').count(),httpWrites:(page.__humanHTTP??[]).filter(r=>!['GET','HEAD','OPTIONS'].includes(r.method))};}'''
        (root/'show.js').write_text(show);visible=manager.cli_result(cli('show-ready','run-code','--filename='+str(root/'show.js')));assert visible['openDialogs']==0 and not visible['httpWrites']
        observation='''async page=>({at:new Date().toISOString(),clicks:await page.evaluate(()=>window.__humanClicks??[]),http:page.__humanHTTP??[],urlPath:new URL(page.url()).pathname,openDialogs:await page.locator('dialog[open]').count()})'''
        (root/'observe.js').write_text(observation)
        info=dict(status='READY_FOR_HUMAN_NOT_PASS',url=state['url'],ownroot=str(root),supervisor_pid=__import__('os').getpid(),fixture_launcher_pid=owner.process.pid,browser_session=session,read_window_seconds=900,authority='Original lease/question120s and peer150s; no renewal. Read window does not extend evidence currentness.',question_expires_at=identity['question']['expires_at'],active_observed_at=active['at'],source=ready['source_commit'],wheel_sha256=ready['wheel_sha256'],stop=str(root/'control/stop'),supervisor_stop=str(root/'control/human-supervisor-stop'),profile=str(root/'browser-profile'),public_observations=str(HERE/'observations.json'),provider_invocations=0,ready=visible)
        write(HERE/'session.json',info);print(json.dumps(dict(event='HUMAN_READY',**info)),flush=True)
        deadline=time.monotonic()+900;ordinal=0
        while time.monotonic()<deadline and owner.process.poll()is None and not(root/'control/human-supervisor-stop').exists()and not(root/'control/stop').exists():
            owner.sample();commands.sample();time.sleep(5);ordinal+=1
            if ordinal%2==0:
                value=manager.cli_result(cli('observe-'+str(ordinal),'run-code','--filename='+str(root/'observe.js')));write(root/'human-observations.private.json',value);write(HERE/'observations.json',value)
    except BaseException as e:
        failure=dict(type=type(e).__name__,message=str(e));write(root/'human-start-failure.private.json',failure);print(json.dumps(dict(event='FAILURE',**failure)),flush=True)
    finally:
        if opened:
            try:cli('shutdown-browser','close',cleanup=True)
            except BaseException as e:failure=failure or dict(type=type(e).__name__,message='Browser close failed')
        (root/'control/stop').touch();end=time.monotonic()+180
        while owner.process and owner.process.poll()is None and time.monotonic()<end:owner.sample();time.sleep(.2)
        cleanup=owner.stop(force=owner.process is not None and owner.process.poll()is None)
        commands.sample();remaining=commands.remaining();containment=commands.contain()if remaining else dict(forced_births=[],remaining=[])
        after=frozen.check(NEXT/'keyboard-app-r9-prepared/ROOT-GATE-v4.json')[0]
        write(HERE/'cleanup.json',dict(failure=failure,fixture_cleanup=cleanup,browser_containment=containment,before=before,after=after,known_births=list(commands.known.values()),root=str(root)))
        print(json.dumps(dict(event='HUMAN_SESSION_CLOSED',root=str(root),failure=failure,fixture=cleanup,remaining=len(containment['remaining']))),flush=True)
if __name__=='__main__':main()
