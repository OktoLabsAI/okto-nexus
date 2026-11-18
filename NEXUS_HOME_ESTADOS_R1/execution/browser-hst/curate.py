"""Curate only explicit own fixture paths; never copy credential state/wire logs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import psutil
from curation_privacy import cas_values,redact,fingerprints

HERE=Path(__file__).resolve().parent


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--tag',required=True)
    p.add_argument('--classification',required=True)
    a=p.parse_args()
    root=a.root.resolve();assert root.name.startswith('nexus-hst-browser-')
    assert all(c.isalnum()or c in '-_' for c in a.tag)
    dest=HERE/'cuts'/a.tag;dest.mkdir(parents=True,exist_ok=True)
    assert not (dest/'qualification.json').exists(),'Do not rewrite a published cut'
    supervisor=json.loads((root/'control/supervisor-cleanup.json').read_text())
    assert supervisor['exit_code'] is not None and not supervisor['remaining_known_births']
    cookies=[]
    cas=cas_values(root);redacted_count=0
    private=root/'control/browser-storage.private.json'
    if private.exists():cookies=[x['value'] for x in json.loads(private.read_text())['cookies']]
    copied=[];results={}
    names=['runtime-ready.json','fixture.py','timing.js','functional.js','functional2.js','initialize.js',
           'partial.js','logout.js','j5-claimed.js','j5-verifying.js','j5-completed.js',
           'question-parallel.js','question-blocked.js','question-confirmation.js','question-form.js','r4-freshness.js',
           'after-terminal.js','alerts.js','info-upgrade.js','scope-race.js','negative.js','final-smoke.js','mobile-intents.js','r7-context.js','case-steps.json']
    names+=[p.name for p in root.glob('cli-*.txt')]
    names+=['control/initial-board.json','control/final.json','control/origins.json','control/j5-preflight.json',
            'control/controls.json','control/failure.json','control/blocked.json','control/supervisor-cleanup.json','control/negative-preflight.json']
    for name in names:
        source=root/name
        if not source.exists():continue
        original=source.read_bytes();raw,count=redact(original,cas);redacted_count+=count
        assert not any(value.encode()in raw for value in cookies),'Private cookie found; stop curation'
        target=dest/name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert target.read_bytes()==raw,'Existing antecedent bytes changed'
        else:target.write_bytes(raw)
        copied.append(dict(path=name,source_sha256=sha(source),curated_sha256=sha(target),fixture_cas_redactions=count))
        if name.startswith('cli-'):
            text=raw.decode('utf-8',errors='replace').replace('\r\n','\n')
            if '### Result\n'in text:
                body=text.split('### Result\n',1)[1].split('\n###',1)[0].strip()
                if not body.startswith(('{','[')):continue # CLI storage-state prose is not a test result.
                result=json.loads(body)
                key=Path(name).stem.removeprefix('cli-');results[key]=result
                (dest/(key+'-result.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    preclose=root/'control/preclose-runtime-facts.json'
    if preclose.exists():
        value=json.loads(preclose.read_text())
        (dest/'runtime-facts-public.json').write_text(json.dumps(dict(at=value['at'],facts=value['facts']),indent=2)+'\n')
    ready=None;ready_path=root/'control/ready.json'
    if ready_path.exists():
        ready=json.loads(ready_path.read_text());ready.pop('storage',None)
        (dest/'ready-public.json').write_text(json.dumps(ready,indent=2)+'\n')
    own_alive=[]
    curator_ancestors={psutil.Process().pid,*[x.pid for x in psutil.Process().parents()]}
    for process in psutil.process_iter(['pid','cmdline']):
        try:
            if any(str(root).lower()in str(arg).lower() for arg in process.info['cmdline']or[]):
                if process.pid not in curator_ancestors:own_alive.append(process.pid)
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    port=int(ready['url'].rsplit(':',1)[1])if ready else None
    listeners=[c.pid for c in psutil.net_connections('tcp')if port and c.laddr and c.laddr.port==port and c.status=='LISTEN']
    clean=dict(supervisor=supervisor,own_root_processes=own_alive,listener_port=port,listener_pids=listeners,
               excluded='Current curation process/ancestors, not runtime or browser',
               secret_cookie_scan='NO_MATCH',private_auth_and_wire_logs='Not copied',data_preserved=True)
    (dest/'physical-cleanup.json').write_text(json.dumps(clean,indent=2)+'\n')
    positives=sum(sum(c.get('ok')is True for c in r.get('checks',[]))for r in results.values()if isinstance(r,dict))
    negatives=sum(sum(c.get('ok')is False for c in r.get('checks',[]))for r in results.values()if isinstance(r,dict))
    q=dict(status=a.classification,provider_invocations=0,checks_pass=positives,checks_fail=negatives,
           results={k:v.get('status')for k,v in results.items()if isinstance(v,dict)},own_root=str(root),cleanup=clean,
           limits=['Synthetic Codex protocol through real Core/Server; no real provider or three-adapter claim',
                   'No human/AT/native-zoom claim', 'Functional runs after DOM timing may share CPU with installed pytest'],
           copies=copied)
    q['privacy']=dict(fixture_cas_values_redacted=redacted_count,fixture_cas_fingerprints=fingerprints(cas),raw='Retained only in explicitly owned Temp root')
    final=root/'control/final.json'
    if final.exists():
        value=json.loads(final.read_text());requests=value['requests']
        q['browser_http_counts']={m:sum(r['method']==m for r in requests)for m in sorted({r['method']for r in requests})}
        q['browser_status_counts']={str(s):sum(r.get('status')==s for r in requests)for s in sorted({r['status']for r in requests if 'status'in r})}
    (dest/'qualification.json').write_text(json.dumps(q,indent=2)+'\n')
    files=[dict(path=x.relative_to(dest).as_posix(),bytes=x.stat().st_size,sha256=sha(x))for x in sorted(dest.rglob('*'))if x.is_file()]
    (dest/'manifest.json').write_text(json.dumps(dict(files=files),indent=2)+'\n')
    print(json.dumps(dict(path=str(dest),checks_pass=positives,checks_fail=negatives,own_root_processes=own_alive,listener_pids=listeners)))


if __name__=='__main__':main()
