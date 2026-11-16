from pathlib import Path
import json, shutil, hashlib
root=Path(__file__).resolve().parents[4]
dest=Path(__file__).parent
out=root/'output/playwright/ui09-native-zoom'
control=json.loads((out/'control.json').read_text())
ctl=Path(control['control'])
for name in ('native200-home.png','native200-exact-panel.png','probe.js'):
    shutil.copy2(out/name,dest/name)
for name in ('ready.json','config.json'):
    shutil.copy2(ctl/name,dest/name)
for name in ('manifest.json','worker.js'):
    shutil.copy2(ctl/'extension'/name,dest/('extension-'+name))
raw=(dest/'browser-cli.txt').read_text()
result=json.loads(raw.split('### Result\n',1)[1].split('\n### Ran',1)[0])
result.update(scope='Focal native Chromium zoom200 Home and one exact session panel; not AT or full accessibility qualification',
              screenshot_limit='CLI screenshots remain 712x503 physical pixels at native200 and visibly crop the physical viewport; neither viewport nor fullPage capture is a complete visual layout oracle. DOM width, native API geometry, real selector interaction, and Close hit-test are independently captured. No full screenshot visual PASS claimed.',
              cleanup=dict(first_browser_pid=47660,first_browser_close_exit=0,first_fixture_session=15441,first_fixture_exit=0,first_port=58588,first_browser_pid_absent=True,first_port_listener_absent=True,final_browser_pid=42212,final_browser_close_exit=0,final_fixture_session=48108,final_fixture_exit=0,final_port=53859,final_browser_pid_absent=True,final_port_listener_absent=True))
(dest/'qualification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
pins={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir() if p.is_file() and p.name!='manifest.json'}
(dest/'manifest.json').write_text(json.dumps(pins,indent=2),encoding='utf-8')
print(json.dumps({'qualification_sha256':pins['qualification.json'],'files':len(pins)}))
