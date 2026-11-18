"""Read only a completed own naming cut; publish explicit safe artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from urllib.parse import urlsplit
import psutil

HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--ready',required=True,type=Path);a=p.parse_args()
    root=a.root.resolve();assert root.name.startswith('nexus-hst-browser-')
    dest=HERE/'naming-r7';assert not dest.exists();dest.mkdir()
    ready=json.loads((root/'control/ready.json').read_text());runtime=json.loads((root/'runtime-ready.json').read_text());final=json.loads((root/'control/final.json').read_text());cleanup=json.loads((root/'control/supervisor-cleanup.json').read_text())
    assert cleanup['exit_code']==0 and not cleanup['signals']and not cleanup['remaining_known_births']
    assert final['sessions']==[]and final['operations']==[]and final['provider_invocations']==0
    assert not any(r['method']=='POST'for r in final['requests'])
    port=urlsplit(ready['url']).port;browser=[]
    for process in psutil.process_iter(['pid','cmdline','create_time']):
        try:
            argv=' '.join(process.info['cmdline']or[])
            if str(root/'browser-profile').lower()in argv.lower():browser.append(dict(pid=process.pid,birth=process.info['create_time']))
        except(psutil.NoSuchProcess,psutil.AccessDenied):pass
    listeners=[dict(pid=c.pid,port=c.laddr.port)for c in psutil.net_connections(kind='tcp')if c.status=='LISTEN'and c.laddr.port==port]
    assert not browser and not listeners
    package=json.loads(a.ready.read_text());manifest=json.loads((a.ready.parent/'evidence/payload-manifest.json').read_text());site=Path(package['python']).parent.parent/'Lib/site-packages'
    mismatch=[n for group in manifest.values()for n,h in group.items()if not(site/n).is_file()or sha(site/n)!=h];count=sum(map(len,manifest.values()))
    assert count==1031==package['payload_files']and not mismatch
    text=(root/'cli-experience-naming.txt').read_text().replace('\r\n','\n');result=json.loads(text.split('### Result\n',1)[1].split('\n###',1)[0])
    assert result['status']=='PRODUCT_DEFECT_UNNAMED_HEADER_MENU'
    storage=json.loads(Path(ready['storage']).read_text());secrets=[c['value']for c in storage.get('cookies',[])]
    names=['runtime-ready.json','fixture.py','experience-naming.js','experience-builder-proof.json','experience-steps.json','experience-failure.json','cli-experience-naming.txt','cli-experience-close.txt','control/final.json','control/origins.json','control/supervisor-cleanup.json']
    entries=[]
    for name in names:
        source=root/name
        if not source.exists():continue
        raw=source.read_bytes();assert not any(s.encode()in raw for s in secrets)
        target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);entries.append(dict(path=name,bytes=len(raw),sha256=sha(target)))
    for name in ['run.py','builder.py','browser.js']:
        shutil.copyfile(HERE/name,dest/('executed-'+name))
    qualification=dict(status='FAIL_PRODUCT_ACCESSIBLE_NAME',scenario='I01',scope='Only actual header-menu accessible name, not whole keyboard journey',source_commit=package['source_commit'],wheel_sha256=package['wheel_sha256'],runtime=result,canonical_fixture=dict(sessions=0,runtime_operations=0,provider_invocations=0,browser_posts=0,registered_connections=len(ready['references'])),cleanup=cleanup,physical=dict(browser_profile_processes=browser,listeners=listeners,port=port,active_resources=False),payload_after=dict(files=count,mismatches=mismatch),payload_before='Runner validated all READY-manifest bytes before allocation; no separate initial JSON was persisted on failure',preserved_private_data=str(root),limitations=['No screen reader speech','No complete I01 keyboard traversal','No new product test/build or full experience batch','Physical scan is a point-in-time observation; supervisor sampling cannot inventory every short-lived child'])
    (dest/'qualification.json').write_text(json.dumps(qualification,indent=2)+'\n')
    entries=[dict(path=str(f.relative_to(dest)),bytes=f.stat().st_size,sha256=sha(f))for f in sorted(dest.rglob('*'))if f.is_file()]
    (dest/'manifest.json').write_text(json.dumps(dict(files=entries),indent=2)+'\n')
    print(json.dumps(dict(qualification=str(dest/'qualification.json'),manifest_sha256=sha(dest/'manifest.json'),physical0=True,payload_files=count,result=result['status']),indent=2))
if __name__=='__main__':main()
