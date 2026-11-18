"""Publish explicit I04 observations only; private cookies/CAS/profile remain Temp."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlsplit
import psutil

HERE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve();assert root.name.startswith('nexus-hst-browser-')
    raw=json.loads((root/'native-zoom-run.private.json').read_text());assert raw['scope']=='I04_APP_NATIVE_ZOOM'
    remaining=[]
    for record in raw['known_births']:
        try:
            process=psutil.Process(record['pid'])
            if abs(process.create_time()-record['birth'])<.01 and process.exe()==record['exe']:remaining.append(record['pid'])
        except psutil.NoSuchProcess:pass
    profiles=[]
    for process in psutil.process_iter(['pid','cmdline','create_time']):
        try:
            if str(root/'browser-profile').lower()in ' '.join(process.info['cmdline']or[]).lower():profiles.append(dict(pid=process.pid,birth=process.info['create_time']))
        except(psutil.NoSuchProcess,psutil.AccessDenied):pass
    ports=[]
    for name in ['zoom-probe-ready.json','ready.json']:
        path=root/'control'/name
        if path.exists():
            value=json.loads(path.read_text());ports.append(urlsplit(value.get('origin')or value['url']).port)
    listeners=[dict(pid=item.pid,port=item.laddr.port)for item in psutil.net_connections(kind='tcp')if item.status=='LISTEN'and item.laddr.port in ports]
    assert not remaining and not profiles and not listeners and not raw['containment']['remaining'],'Own resources still present'
    privacy_path=HERE.parents[1]/'browser-hst/curation_privacy.py';spec=importlib.util.spec_from_file_location('i04_privacy',privacy_path);privacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(privacy)
    cas=privacy.cas_values(root);cookies=[];storage=root/'control/browser-storage.private.json'
    if storage.exists():cookies=[item['value']for item in json.loads(storage.read_text())['cookies']]
    dest=HERE/'runs'/raw['cut_id'];assert not dest.exists();dest.mkdir(parents=True)
    names=['i04-control-invalid-reads.jsonl','native-zoom-run.private.json','native-guard-result.private.json','first-failure.private.json','chrome-argv.private.json','probe-process-proof.json','runtime-ready.json','i04-builder-proof.json','i04-public-preflight.json','native-zoom.js','zoom-probe.py','fixture.py','playwright-cli.json','control/zoom-probe-ready.json','control/zoom-probe-final.json','control/final.json','control/origins.json','control/controls.json','control/exp-base.json','control/exp-active.json','control/exp-history.json','control/exp-theme-unknown.json','control/exp-theme-restored.json']
    names+=[str(path.relative_to(root))for pattern in ['command-*.private.txt','app-*.js','theme-*.js','ui-native100.js','*-result.private.json','native-zoom-*.png','i04-app-*.png']for path in root.glob(pattern)]
    copied=[];redactions=0
    for name in sorted(set(names)):
        source=root/name
        if not source.exists():continue
        original=source.read_bytes();body,count=privacy.redact(original,cas);redactions+=count
        for cookie in cookies:count_cookie=body.count(cookie.encode());redactions+=count_cookie;body=body.replace(cookie.encode(),b'<redacted-own-operator-cookie>')
        assert not any(value.encode()in body for value in cas|set(cookies))
        target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body);copied.append(dict(path=name,raw_sha256=sha(source),curated_sha256=sha(target)))
    cases={entry['phase']:entry['result']for entry in raw['app_results']};complete=all(name in cases and cases[name]['status']=='PASS_I04_EXECUTED_SUBSET'for name in ['theme-known','theme-unknown'])
    normal=not raw['cleanup_errors']and not raw['containment']['forced_births']and raw['probe_exit_code']==0
    fixture=raw['fixture_final'];canonical=dict(unknown=fixture['unknown'],sessions=[dict(session_id=item['session_id'],close_confirmed=item['closed'])for item in fixture['sessions']])if fixture else None
    if complete and normal and not raw['first_failure']:status='PASS_I04_BROWSER_CANONICAL_CLOSE_UNKNOWN'if canonical and canonical['unknown']else'PASS_I04_BROWSER'
    else:status='PARTIAL_OR_DIAGNOSTIC_FAIL_I04'
    qualification=dict(status=status,scope='I04 both UI themes, known and read-fault unknown phases; five meanings only',result_summary={name:dict(status=value['status'],passed=sum(check['pass']for check in value.get('checks',[])),failed=sum(not check['pass']for check in value.get('checks',[])))for name,value in cases.items()},first_failure=raw['first_failure'],cleanup_errors=raw['cleanup_errors'],canonical_close=canonical,fixture_cleanup=raw['fixture_cleanup'],forced_births=raw['containment']['forced_births'],physical=dict(remaining_births=remaining,profile_processes=profiles,listeners=listeners,ports=ports),nexus_processes_started=raw['nexus_processes_started'],provider_invocations=raw['provider_invocations'],before=raw['before'],after=raw['after'],fixture_cas_redactions=redactions,copied=copied,source_root=str(root),limits=['Inert protocol peer; no real harness/provider qualification','No human or AT speech; only the asserted keyboard path','300s supervisor never extends original120s question/lease or150s peer validity','Process exit0 is not a claim that every canonical runtime.close settled'])
    (dest/'qualification.json').write_text(json.dumps(qualification,indent=2)+'\n')
    manifest={str(path.relative_to(dest)):{'sha256':sha(path),'bytes':path.stat().st_size}for path in sorted(dest.rglob('*'))if path.is_file()};(dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(status=status,qualification=str(dest/'qualification.json'),manifest_sha256=sha(dest/'manifest.json')),indent=2))
if __name__=='__main__':main()
