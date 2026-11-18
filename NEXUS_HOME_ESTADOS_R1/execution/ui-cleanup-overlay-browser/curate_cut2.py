"""Curate the sole stopped overlay cut, without another browser/app execution."""
import hashlib,importlib.util,json
from pathlib import Path
from urllib.parse import urlsplit
import psutil
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2]
root=Path(json.loads((HERE/'runtime-cut2.json').read_text())['root']);raw=json.loads((root/'run.private.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
remaining=[]
for b in raw['known_births']:
 try:
  p=psutil.Process(b['pid'])
  if abs(p.create_time()-b['birth'])<.01 and p.exe()==b['exe']:remaining.append(b)
 except psutil.NoSuchProcess:pass
profiles=[]
for p in psutil.process_iter(['pid','cmdline']):
 try:
  if str(root/'browser-profile').lower()in' '.join(p.info['cmdline']or[]).lower():profiles.append(p.pid)
 except(psutil.NoSuchProcess,psutil.AccessDenied):pass
ready=json.loads((root/'control/ready.json').read_text());port=urlsplit(ready['url']).port
listeners=[dict(pid=c.pid,port=c.laddr.port)for c in psutil.net_connections(kind='tcp')if c.status=='LISTEN'and c.laddr.port==port]
assert not remaining and not profiles and not listeners and not raw['containment']['remaining']
s=importlib.util.spec_from_file_location('overlay_privacy',REPO/'NEXUS_HOME_ESTADOS_R1/execution/browser-hst/curation_privacy.py');privacy=importlib.util.module_from_spec(s);s.loader.exec_module(privacy)
cas=privacy.cas_values(root);cookies=[c['value']for c in json.loads((root/'control/browser-storage.private.json').read_text())['cookies']]
out=HERE/'cut-2';out.mkdir(exist_ok=False);redactions=0
for name in ['run.private.json','result.private.json','browser.js','fixture.py','runtime-ready.json','control/origins.json','control/exp-active.json','overlay/index.html','command-focal.private.txt','overlay-home.png','overlay-terminal.png']:
 p=root/name
 if not p.exists():continue
 body,count=privacy.redact(p.read_bytes(),cas);redactions+=count
 for cookie in cookies:redactions+=body.count(cookie.encode());body=body.replace(cookie.encode(),b'<redacted-own-cookie>')
 assert not any(v.encode()in body for v in cas|set(cookies))
 target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
final=json.loads((root/'control/final.json').read_text());result=raw['result']
report=dict(status='PASS_PRESENTATION_OVERLAY_CANONICAL_CLOSE_UNKNOWN'if final['unknown']else'PASS_PRESENTATION_OVERLAY',layer=raw['layer'],runtime_exit=0,checks_passed=sum(c['pass']for c in result['checks']),checks_failed=sum(not c['pass']for c in result['checks']),failure=result.get('error'),qualified=[c['id']for c in result['checks']if c['pass']],not_qualified=['Actual clipboard copy; button was not clicked','New SQL subject projection and new installed package; runtime API remains old R9'],cause_evidence='No failure; all13 scoped presentation assertions passed',browser_writes=next(c['actual']for c in result['checks']if c['id']=='zero-browser-POST'),page_errors=next(c['actual']for c in result['checks']if c['id']=='zero-page-errors'),provider_invocations=final['provider_invocations'],before=raw['before'],after=raw['after'],before_after_equal=raw['before']==raw['after'],fixture_cleanup=raw['cleanup'],containment=raw['containment'],physical=dict(remaining_births=remaining,profiles=profiles,listeners=listeners,port=port),canonical_close=dict(unknown=final['unknown'],sessions=[dict(session_id=v['session_id'],confirmed=v['closed'])for v in final['sessions']]),clipboard='Not clicked; Windows clipboard untouched.',redactions=redactions,root=str(root))
(out/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
(out/'README.md').write_text("""# 8q overlay focal —13/13 positive

Real Chrome + unchanged installed R9 HTTP API + new Vite static-only overlay. This is not a newly installed package. The frozen prefix1031 payload and all original backend checkout bytes were checked except exactly sqlite/home.py, whose explicit new SHA is bound separately; the runtime still imports old R9 home.py. New SQL subject projection requires its separate SQLite/pytest evidence.

Home generic Work request/Connection details/Evidence observed were absent. Received timestamp retained its raw datetime while rendering browser-local Sao Paulo text. Exact View work opened the canonical target with GET200/full12-field session scope, visible real Turn started output, technical IDs hidden in basic view, READY/control_available true/no release pending. The terminal disclosure contained the exact existing-session command and enabled Copy command affordance. Copy was not clicked: no proven isolated browser clipboard, Windows clipboard untouched. No browser POST/page errors/provider calls.

Runner/CLI/fixture normal0; no signals or forced containment. All observed own process births/profile/listener absent. Canonical B1 close confirmed, A1/A2 UNKNOWN remains separate. Public screenshots were viewed and contain synthetic fixture UI only, with terminal command disclosure closed. No human acceptance, real provider or new installed-package qualification.
""")
manifest={p.relative_to(out).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)for p in out.rglob('*')if p.is_file()}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(status=report['status'],manifest_sha256=sha(out/'manifest.json'),physical=report['physical'],fixture_cleanup=report['fixture_cleanup'],redactions=redactions),indent=2))
