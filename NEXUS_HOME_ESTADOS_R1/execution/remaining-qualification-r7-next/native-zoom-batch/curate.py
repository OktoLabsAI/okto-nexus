"""Curate a completed browser-only cut, never the Chrome profile or OS state."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
import psutil

HERE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);a=p.parse_args();root=a.root.resolve();assert root.name.startswith('nexus-hst-browser-')
    raw=json.loads((root/'native-zoom-run.private.json').read_text());assert raw['nexus_processes_started']==0 and raw['provider_invocations']==0
    remaining=[]
    for record in raw['known_births']:
        try:
            process=psutil.Process(record['pid'])
            if abs(process.create_time()-record['birth'])<.01 and process.exe()==record['exe']:remaining.append(record['pid'])
        except psutil.NoSuchProcess:pass
    profile_processes=[]
    for process in psutil.process_iter(['pid','cmdline','create_time']):
        try:
            if str(root/'browser-profile').lower()in ' '.join(process.info['cmdline']or[]).lower():profile_processes.append(dict(pid=process.pid,birth=process.info['create_time']))
        except(psutil.NoSuchProcess,psutil.AccessDenied):pass
    probe_ready_path=root/'control/zoom-probe-ready.json';port=urlsplit(json.loads(probe_ready_path.read_text())['origin']).port if probe_ready_path.exists()else None
    listeners_now=[dict(pid=item.pid,port=item.laddr.port)for item in psutil.net_connections(kind='tcp')if port and item.status=='LISTEN'and item.laddr.port==port]
    assert not remaining and not profile_processes and not listeners_now and not raw['containment']['remaining']and not raw['listeners'],'Do not publish while own resources remain'
    assert not(root/'control/ready.json').exists()and not(root/'control/origins.json').exists(),'Unexpected Nexus fixture startup artifacts'
    dest=HERE/'runs'/raw['cut_id'];assert not dest.exists();dest.mkdir(parents=True)
    names=['native-zoom-run.private.json','native-guard-result.private.json','first-failure.private.json','chrome-argv.private.json','runtime-ready.json','native-zoom.js','zoom-probe.py','playwright-cli.json','probe.private.log','control/zoom-probe-ready.json','control/zoom-probe-final.json']
    names+=[str(p.relative_to(root))for pattern in ['command-*.private.txt','native-zoom-*.png']for p in root.glob(pattern)]
    copied=[]
    for name in names:
        source=root/name
        if not source.exists():continue
        target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes());copied.append(dict(path=name,sha256=sha(target)))
    result=raw['result'];normal=not raw['cleanup_errors']and not raw['containment']['forced_births']and raw['probe_exit_code']==0
    status='PASS_NATIVE_BROWSER_ONLY'if normal and not raw['first_failure']and result and result['status']=='PASS_NATIVE_200_ZOOM_GUARD'else'DIAGNOSTIC_FAIL_OR_NOT_RUN'
    qualification=dict(status=status,actual_browser_status=result.get('status')if result else None,scope='Native Chrome Settings zoom only; I05 application scenario NOT_RUN',first_failure=raw['first_failure'],cleanup_errors=raw['cleanup_errors'],forced_births=raw['containment']['forced_births'],remaining_births=remaining,physical=dict(profile_processes=profile_processes,listeners=listeners_now,port=port),probe_exit_code=raw['probe_exit_code'],nexus_processes_started=0,provider_invocations=0,before=raw['before'],after=raw['after'],source_root=str(root),copied=copied,limits=['No Nexus application was started','No human/AT/native display settings','Containment, if used, is a diagnostic failure, never normal cleanup','Own profile/preferences/OS config files are not copied'])
    (dest/'qualification.json').write_text(json.dumps(qualification,indent=2)+'\n')
    manifest={str(path.relative_to(dest)):{'sha256':sha(path),'bytes':path.stat().st_size}for path in sorted(dest.rglob('*'))if path.is_file()};(dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(status=status,qualification=str(dest/'qualification.json'),manifest_sha256=sha(dest/'manifest.json')),indent=2))
if __name__=='__main__':main()
