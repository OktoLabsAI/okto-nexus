"""Curate the sole stopped overlay cut, without another browser/app execution."""
import hashlib,importlib.util,json
from pathlib import Path
from urllib.parse import urlsplit
import psutil
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2]
root=Path(json.loads((HERE/'runtime.json').read_text())['root']);raw=json.loads((root/'run.private.json').read_text())
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
out=HERE/'cut-1';out.mkdir(exist_ok=False);redactions=0
for name in ['run.private.json','result.private.json','browser.js','fixture.py','runtime-ready.json','control/origins.json','control/exp-active.json','overlay/index.html','command-focal.private.txt']:
 p=root/name
 if not p.exists():continue
 body,count=privacy.redact(p.read_bytes(),cas);redactions+=count
 for cookie in cookies:redactions+=body.count(cookie.encode());body=body.replace(cookie.encode(),b'<redacted-own-cookie>')
 assert not any(v.encode()in body for v in cas|set(cookies))
 target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
final=json.loads((root/'control/final.json').read_text());result=raw['result']
report=dict(status='FAIL_PRESENTATION_GENERIC_RESULT_EVENT_TITLE_FIRST_FAILURE_PRESERVED',layer=raw['layer'],runtime_exit=1,checks_passed=sum(c['pass']for c in result['checks']),checks_failed=sum(not c['pass']for c in result['checks']),failure=result['error'],qualified=['Real Chrome loaded exact index-Cp1x7DiS.js static overlay','Home no Connection details or Evidence observed'],not_qualified=['Local timestamp/datetime rendering','View work exact target/session terminal','No IDs outside disclosure','READY/control command and Copy command affordance'],cause_evidence='Captured AX shows idle card Activity preview paragraph Work request, Turn completed, View delivery; result-kind event retains generic title.',browser_writes=result['writes'],page_errors=result['pageErrors'],provider_invocations=final['provider_invocations'],before=raw['before'],after=raw['after'],before_after_equal=raw['before']==raw['after'],fixture_cleanup=raw['cleanup'],containment=raw['containment'],physical=dict(remaining_births=remaining,profiles=profiles,listeners=listeners,port=port),canonical_close=dict(unknown=final['unknown'],sessions=[dict(session_id=v['session_id'],confirmed=v['closed'])for v in final['sessions']]),clipboard='Not clicked; Windows clipboard untouched.',redactions=redactions,root=str(root))
(out/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
(out/'README.md').write_text('''# Cp1 overlay focal — first failure preserved

Real Chrome + real installed R9 HTTP API + new Vite static-only overlay, not a newly installed package. The prefix/wheel were never modified. New HTML/JS/CSS were copied into own Temp and only their exact static paths were served by the fixture wrapper; APIs delegated unchanged to the R9 app.

The cut stopped at the generic Work request heading still visible in the idle result-event preview. Exact AX is preserved. Removal of Connection details/Evidence observed passed. Timestamp, View work, technical-identity and terminal-command checks were not reached and are not promoted. No productive browser action or clipboard click occurred.

Runner exit1 is retained. Normal fixture exit0 and physical absence are separate from canonical close: B1 confirmed; A1/A2 UNKNOWN. Raw remains Temp; exact own CAS/cookie values were scanned/redacted from public artifacts. No human/provider/installed-candidate claim.
''')
manifest={p.relative_to(out).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)for p in out.rglob('*')if p.is_file()}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(status=report['status'],manifest_sha256=sha(out/'manifest.json'),physical=report['physical'],fixture_cleanup=report['fixture_cleanup'],redactions=redactions),indent=2))
