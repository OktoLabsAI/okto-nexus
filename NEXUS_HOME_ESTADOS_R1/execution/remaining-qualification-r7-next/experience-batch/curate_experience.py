"""Curate a finished experience cut; preserves the first oracle failure verbatim."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
import psutil

HERE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def result(path):
    raw=path.read_text().replace('\r\n','\n')
    return json.loads(raw.split('### Result\n',1)[1].split('\n###',1)[0])
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--ready',type=Path,required=True);p.add_argument('--tag',required=True);a=p.parse_args()
    root=a.root.resolve();assert root.name.startswith('nexus-hst-browser-')and a.tag=='experience-r8-first-oracle'
    dest=HERE/a.tag;assert not dest.exists();dest.mkdir()
    ready=json.loads((root/'control/ready.json').read_text());final=json.loads((root/'control/final.json').read_text());cleanup=json.loads((root/'control/supervisor-cleanup.json').read_text());package=json.loads(a.ready.read_text())
    assert cleanup['exit_code']==0 and not cleanup['remaining_known_births']and not cleanup['signals']
    assert final['provider_invocations']==0 and not any(r['method']=='POST'for r in final['requests'])
    port=urlsplit(ready['url']).port;processes=[]
    for process in psutil.process_iter(['pid','cmdline','create_time']):
        try:
            if str(root/'browser-profile').lower()in ' '.join(process.info['cmdline']or[]).lower():processes.append(dict(pid=process.pid,birth=process.info['create_time']))
        except(psutil.NoSuchProcess,psutil.AccessDenied):pass
    listeners=[dict(pid=c.pid,port=c.laddr.port)for c in psutil.net_connections(kind='tcp')if c.status=='LISTEN'and c.laddr.port==port]
    assert not processes and not listeners
    manifest=json.loads((a.ready.parent/'evidence/payload-manifest.json').read_text());site=Path(package['python']).parent.parent/'Lib/site-packages';count=sum(map(len,manifest.values()));bad=[n for g in manifest.values()for n,h in g.items()if not(site/n).is_file()or sha(site/n)!=h];assert count==1031 and not bad
    cookies=[c['value']for c in json.loads(Path(ready['storage']).read_text())['cookies']]
    names=['runtime-ready.json','fixture.py','experience-builder-proof.json','experience-naming.js','experience-base.js','experience-failure.json','experience-steps.json','cli-experience-naming.txt','cli-experience-base.txt','cli-experience-close.txt','control/exp-base.json','control/final.json','control/origins.json','control/supervisor-cleanup.json']
    for name in names:
        source=root/name
        if source.exists():
            raw=source.read_bytes();assert not any(s.encode()in raw for s in cookies)
            target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    naming=result(root/'cli-experience-naming.txt');base=result(root/'cli-experience-base.txt')
    assert naming['status']=='PASS_NAMING_PREFLIGHT'and base['status']=='INCOMPLETE'and base['checks']==[]
    raw=(root/'cli-experience-base.txt').read_text();url=raw.split('- Page URL: ',1)[1].splitlines()[0];actual_target=json.loads(__import__('urllib.parse',fromlist=['parse_qs']).parse_qs(urlsplit(url).query)['home_target'][0]);preflight=json.loads((root/'control/exp-base.json').read_text());known=preflight['sessions'][0]['scope']
    assert all(actual_target[k]==known[k]for k in ['server_id','executor_id','workspace_id','session_id'])and actual_target['kind']=='session'
    assert base['posts']==[]and base['errors']==[]
    qualification=dict(status='INCOMPLETE_ORACLE_SINGLETON_SELECTOR',source_commit=package['source_commit'],wheel_sha256=package['wheel_sha256'],naming=naming,base=base,base_assertions_completed=0,interpretation='The singleton path deliberately opens an exact session target directly. The test incorrectly waited for the multi-session selector. No product regression established.',observed_target=actual_target,preflight_exact_target_match=True,not_asserted=['Viewer output after timeout','G01 full Then','G04 and all subsequent phases','No-authority-change digest comparison (not reached)'],cleanup=cleanup,physical=dict(port=port,browser_profile_processes=processes,listeners=listeners,active_resources=False),payload_after=dict(files=count,mismatches=bad),provider_invocations=0,browser_post_count=0,original_root=str(root))
    (dest/'qualification.json').write_text(json.dumps(qualification,indent=2)+'\n')
    entries={str(f.relative_to(dest)):{'sha256':sha(f),'bytes':f.stat().st_size}for f in sorted(dest.rglob('*'))if f.is_file()}
    (dest/'manifest.json').write_text(json.dumps(entries,indent=2)+'\n')
    print(json.dumps(dict(qualification=str(dest/'qualification.json'),manifest_sha256=sha(dest/'manifest.json'),physical0=True,payload_files=count),indent=2))
if __name__=='__main__':main()
