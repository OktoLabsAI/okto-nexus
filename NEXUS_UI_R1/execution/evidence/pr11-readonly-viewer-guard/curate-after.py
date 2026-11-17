from pathlib import Path
import json,shutil,hashlib
root=Path(__file__).resolve().parents[4];dest=Path(__file__).parent;out=root/'output/playwright/ui11-viewer-guard'
ctl=json.loads((out/'control.json').read_text())
shutil.copy2(Path(ctl['control'])/'ready.json',dest/'after-ready.json')
for name in ('after-auto-scroll-passive.png','after-canonical-form-guard.png','after-probe.js'):shutil.copy2(out/name,dest/name)
raw=(dest/'after-cli.txt').read_text();result=json.loads(raw.split('### Result\n',1)[1].split('\n### Ran',1)[0])
result['scope']='Only Auto-scroll read-only Close guard regression and unsent canonical composer guard; not provider, campaign, AT or full Home requalification.'
result['cleanup']={'browser_pid':53208,'close_exit':0,'fixture_session':6152,'fixture_exit':0,'pid_absent':True,'listener50898_absent':True,'shared_wss_lifespan_factory':'CLOSED'}
result['current_source_sha256']={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ('frontend/src/components/SessionExecutionPanel.tsx','frontend/src/components/RuntimeEventStream.tsx','frontend/src/components/AgentActionModal.tsx','frontend/tests/uiSessionInspection.test.mjs')}
(dest/'qualification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
pins={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir() if p.is_file() and p.name!='manifest.json'}
(dest/'manifest.json').write_text(json.dumps(pins,indent=2),encoding='utf-8')
print(json.dumps({'qualification_sha256':pins['qualification.json'],'files':len(pins),'bundle_sha256':json.loads((dest/'after-ready.json').read_text())['source_sha256']['src/okto_nexus/adapters/inbound/http/static/assets/index-BGONNtiX.js']}))
