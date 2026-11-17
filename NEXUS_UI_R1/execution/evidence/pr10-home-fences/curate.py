from pathlib import Path
import hashlib,json,shutil
root=Path(__file__).resolve().parents[4];dest=Path(__file__).parent;out=root/'output/playwright/ui10-home-fences'
control=json.loads((out/'control.json').read_text());ctl=Path(control['control'])
for name in ('ready.json','controlled-events.json','fixture-requests.json'):shutil.copy2(ctl/name,dest/name)
for name in ('B-empty-after-late-A.png','partial-results-source.png','probe.js'):shutil.copy2(out/name,dest/name)
raw=(dest/'browser-cli.txt').read_text();result=json.loads(raw.split('### Result\n',1)[1].split('\n### Ran',1)[0])
result['qualification']={'T-HOME-08':'real delayed response release after B; A request aborted, scope B preserved','T-HOME-07':'SUBSET: source-failure scope read, not literal same-scope Refresh','T-HOME-10':'scoped zero-occurrence/Server-zero rendering; other-project global bell3 remains','reporting_collision':'Raw T-HOME-07 check status partial is diagnostic envelope status overwriting PASS; assertion did not throw and overall PASS.'}
result['cleanup']={'browser_pid':28628,'first_close_exit':1,'second_close_exit':0,'pid_absent':True,'fixture_session':43918,'fixture_exit':0,'port':57433,'listener_absent':True,'wss_lifespan_factory_closed':True,'teardown_limit':'Uvicorn3s grace cancelled2open stream tasks; ASGI CancelledError logs, no forced kill.'}
(dest/'qualification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
pins={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir() if p.is_file() and p.name!='manifest.json'}
(dest/'manifest.json').write_text(json.dumps(pins,indent=2),encoding='utf-8')
print(json.dumps({'qualification_sha256':pins['qualification.json'],'files':len(pins)}))
