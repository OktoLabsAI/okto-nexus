"""One authorized Chrome/API/static-overlay focal; no installed mutation."""
import hashlib,importlib.util,json,re,shutil,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2];NEXT=REPO/'NEXUS_HOME_ESTADOS_R1/execution/remaining-qualification-r7-next';BROWSER=REPO/'NEXUS_HOME_ESTADOS_R1/execution/browser-hst'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
def guard():
 ready_path=REPO/'NEXUS_HOME_ESTADOS_R1/execution/package-hst-r9/READY.json';ready=json.loads(ready_path.read_text());assert ready['wheel_sha256']=='e870ea400435d5b736093990af9b56544661e205ad657bbff83f830421a3e628'and sha(ready['wheel'])==ready['wheel_sha256']
 payload=json.loads((ready_path.parent/'evidence/payload-manifest.json').read_text());site=Path(ready['python']).parent.parent/'Lib/site-packages';assert sum(map(len,payload.values()))==1031
 assert all(sha(site/p)==h for group in payload.values()for p,h in group.items())
 sources=json.loads((ready_path.parent/'evidence/source-pins-after.json').read_text());backend={p:h for p,h in sources.items()if p.startswith('src/okto_nexus/')and'/static/'not in p};exception='src/okto_nexus/adapters/outbound/sqlite/home.py';exception_sha='50835c0a009ba5b1d67dac8a01827aae57424c49d8812b2e6a3d1da287e42d25';assert sha(REPO/exception)==exception_sha
 assert all(sha(REPO/p)==h for p,h in backend.items()if p!=exception)
 static=REPO/'src/okto_nexus/adapters/inbound/http/static';html=(static/'index.html').read_text();js=re.search(r'src="(/assets/[^" ]+\.js)',html)[1];css=re.search(r'href="(/assets/[^" ]+\.css)',html)[1];assert js=='/assets/index-8qNwMfLq.js'
 assets={name:sha(static/name.lstrip('/'))for name in ['/index.html',js,css]};manifest=json.loads((NEXT/'native-zoom-batch/prepared-bound-v2.json').read_text());tool=manifest['tooling'];assert sha(tool['node'])==tool['node_sha256']and sha(tool['chrome'])==tool['chrome_sha256']
 return dict(wheel=ready['wheel_sha256'],payload1031=True,checkout_exception=dict(path=exception,sha256=exception_sha,runtime_uses_original_installed_home_py=True),backend_count=len(backend),backend_hash=hashlib.sha256(json.dumps(backend,sort_keys=True).encode()).hexdigest(),assets=assets),ready,tool,static
def main():
 before,ready,tool,static=guard();write(HERE/'pins-before-cut2.json',before)
 child=subprocess.run([sys.executable,'-B',str(BROWSER/'prepare_runtime.py'),'--package-ready',str(REPO/'NEXUS_HOME_ESTADOS_R1/execution/package-hst-r9/READY.json'),'--expected-source',ready['source_commit'],'--mode','scope_two','--browser-window-open'],input=b'',capture_output=True,timeout=25,check=True)
 root=Path(json.loads(child.stdout)['root']);print(json.dumps(dict(event='ALLOCATED',root=str(root))),flush=True)
 build=load('overlay_builder',NEXT/'experience-batch/builder.py');build.build(root);(root/'overlay/assets').mkdir(parents=True)
 for name in before['assets']:shutil.copyfile(static/name.lstrip('/'),root/'overlay'/name.lstrip('/'))
 fixture=root/'fixture.py';text=fixture.read_text();anchor="            server=uvicorn.Server(uvicorn.Config(surface,host='127.0.0.1'"
 assert text.count(anchor)==1
 wrap="""            real_surface=surface
            async def overlay(scope,receive,send):
                paths={__PATHS__}
                path=scope.get('path')
                if scope['type']=='http'and scope.get('method')in['GET','HEAD']and path in paths:
                    from starlette.responses import FileResponse
                    return await FileResponse(ROOT/'overlay'/paths[path])(scope,receive,send)
                return await real_surface(scope,receive,send)
            surface=overlay
""".replace('{__PATHS__}',repr({'/':'index.html',**{k:k.lstrip('/')for k in before['assets']if k!='/index.html'}}))
 text=text.replace(anchor,wrap+anchor);fixture.write_text(text);runtime=json.loads((root/'runtime-ready.json').read_text());runtime['fixture_sha256']=sha(fixture);write(root/'runtime-ready.json',runtime)
 shutil.copyfile(NEXT/'native-zoom-batch/playwright-cli.json',root/'playwright-cli.json');life=load('overlay_life',BROWSER/'containment.py');driver=load('overlay_env',NEXT/'security-r9-batch/browser_driver.py');manager=load('overlay_commands',NEXT/'security-r9-batch/run.py');owner=life.Owned(root);commands=manager.Commands(root,driver.environment(root),time.monotonic()+180);opened=False;failure=None;result=None
 def cli(name,*args,cleanup=False):return commands.run(name,[shutil.which('rtk'),'proxy',tool['node'],tool['entry'],'--session=hst-overlay-8qn',*args],timeout=60,cleanup=cleanup)
 try:
  owner.start(root/'runtime-ready.json',fixture);end=time.monotonic()+65
  while not(root/'control/ready.json').exists():
   assert owner.process.poll()is None and time.monotonic()<end;owner.sample();time.sleep(.1)
  state=json.loads((root/'control/ready.json').read_text());opened=True;cli('launch','open','about:blank','--browser=chrome','--profile='+str(root/'browser-profile'),'--config='+str(root/'playwright-cli.json'));cli('cookie','state-load',state['storage'])
  (root/'control/exp-start-active').touch();end=time.monotonic()+35
  while True:
   try:done=json.loads((root/'control/controls.json').read_text())['done']
   except(FileNotFoundError,json.JSONDecodeError):done=[]
   if'exp-start-active'in done:break
   assert owner.process.poll()is None and time.monotonic()<end;owner.sample();time.sleep(.1)
  active=json.loads((root/'control/exp-active.json').read_text());identity=json.loads((root/'control/exp-active-identities.json').read_text());cards=[v for c in active['board']['columns'].values()for v in c['items']if v['kind']=='harness'];card=next(c for c in cards if c['connection']['binding_id']==identity['a1']['reference']['binding_id']);events=[e for e in card['events_preview']if(e.get('target')or{}).get('operation_id')==identity['a1']['operation_id']];assert len(events)==1
  session=next(s for s in active['sessions']if s['scope']['session_id']==identity['a1']['session_id']);cfg=dict(url=state['url'],card=card['id'],event=events[0]['id'],target=events[0]['target'],scope=session['scope'],output=str(root/'overlay'))
  (root/'browser.js').write_text((HERE/'browser-cut2.js').read_text().replace('__CONFIG__',json.dumps(cfg)));result=manager.cli_result(cli('focal','run-code','--filename='+str(root/'browser.js')));write(root/'result.private.json',result);assert result['status']=='PASS_OVERLAY_BROWSER_FOCAL'
 except BaseException as e:failure=dict(type=type(e).__name__,message=str(e));print(json.dumps(dict(event='FAILURE',failure=failure)),flush=True)
 finally:
  if opened:
   try:cli('browser-close','close',cleanup=True)
   except BaseException as e:failure=failure or dict(type=type(e).__name__,message='Browser close failed')
  (root/'control/stop').touch();end=time.monotonic()+180
  while owner.process and owner.process.poll()is None and time.monotonic()<end:owner.sample();time.sleep(.2)
  cleanup=owner.stop(force=owner.process is not None and owner.process.poll()is None);commands.sample();containment=commands.contain()if commands.remaining()else dict(forced_births=[],remaining=[]);after=guard()[0];assert before==after
  write(root/'run.private.json',dict(before=before,after=after,result=result,failure=failure,cleanup=cleanup,containment=containment,known_births=list(commands.known.values()),commands=commands.commands,layer='Real Chrome + real installed R9 API + Vite static-only overlay; not new installed package'))
  write(HERE/'runtime-cut2.json',dict(root=str(root),result=result['status']if result else None,failure=failure,cleanup=cleanup,containment=containment));print(json.dumps(dict(event='FINISHED',root=str(root),failure=failure,result=result['status']if result else None)),flush=True)
 return int(bool(failure))
if __name__=='__main__':raise SystemExit(main())
