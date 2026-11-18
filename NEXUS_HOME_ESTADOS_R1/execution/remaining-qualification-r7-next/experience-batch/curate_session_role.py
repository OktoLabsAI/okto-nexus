"""Publish only redacted completed observations; raw native CAS stays in Temp."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlsplit
import psutil

HERE=Path(__file__).resolve().parent
BASE=HERE.parents[1]/'browser-hst'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--ready',type=Path,required=True);a=p.parse_args()
    root=a.root.resolve();assert root.name.startswith('nexus-hst-browser-')
    dest=HERE/'experience-r8-session-role';assert not dest.exists();dest.mkdir()
    spec=importlib.util.spec_from_file_location('own_cas_redaction',BASE/'curation_privacy.py');privacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(privacy)
    cas=privacy.cas_values(root);assert len(cas)==1
    ready=json.loads((root/'control/ready.json').read_text());cleanup=json.loads((root/'control/supervisor-cleanup.json').read_text());final=json.loads((root/'control/final.json').read_text());package=json.loads(a.ready.read_text())
    assert cleanup['exit_code']==0 and not cleanup['signals']and not cleanup['remaining_known_births']
    assert final['provider_invocations']==0 and not any(r['method']=='POST'for r in final['requests'])
    processes=[]
    for process in psutil.process_iter(['pid','cmdline','create_time']):
        try:
            if str(root/'browser-profile').lower()in ' '.join(process.info['cmdline']or[]).lower():processes.append(dict(pid=process.pid,birth=process.info['create_time']))
        except(psutil.NoSuchProcess,psutil.AccessDenied):pass
    port=urlsplit(ready['url']).port;listeners=[dict(pid=c.pid,port=c.laddr.port)for c in psutil.net_connections(kind='tcp')if c.status=='LISTEN'and c.laddr.port==port];assert not processes and not listeners
    payload=json.loads((a.ready.parent/'evidence/payload-manifest.json').read_text());site=Path(package['python']).parent.parent/'Lib/site-packages';count=sum(map(len,payload.values()));bad=[n for group in payload.values()for n,h in group.items()if not(site/n).is_file()or sha(site/n)!=h];assert count==1031 and not bad
    cookies=[c['value']for c in json.loads(Path(ready['storage']).read_text())['cookies']]
    names=['runtime-ready.json','fixture.py','experience-builder-proof.json','experience-failure.json','experience-steps.json','control/origins.json','control/final.json','control/supervisor-cleanup.json','control/controls.json']
    names+=[str(f.relative_to(root))for pattern in ['cli-experience-*.txt','experience-*.js','control/exp-*.json']for f in root.glob(pattern)]
    # These three captures precede native-question publication. The later failure
    # image may contain visible CAS details, so retain only its hash privately.
    names+=[f'experience-mobile-{column}.png'for column in ['active','needs_you','results']]
    entries=[];results={};redactions=0
    for name in names:
        source=root/name
        if not source.exists():continue
        original=source.read_bytes();raw,n=privacy.redact(original,cas);redactions+=n
        assert not any(s.encode()in raw for s in cookies)and not any(s.encode()in raw for s in cas)
        target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        entries.append(dict(path=name,raw_sha256=sha(source),curated_sha256=sha(target),cas_redactions=n))
        if name.startswith('cli-experience-'):
            text=raw.decode('utf-8').replace('\r\n','\n')
            if '### Result\n'in text:
                body=text.split('### Result\n',1)[1].split('\n###',1)[0].strip()
                if body.startswith('{'):results[source.stem.removeprefix('cli-experience-')]=json.loads(body)
    before=json.loads((root/'control/exp-base.json').read_text());after=json.loads((root/'control/exp-base-after.json').read_text());assert before['operations']==after['operations']and before['grant_digest']==after['grant_digest']
    summary={phase:dict(status=value['status'],passed=sum(c['pass']for c in value.get('checks',[])),failed=sum(not c['pass']for c in value.get('checks',[])),check_ids=[c['id']for c in value.get('checks',[])])for phase,value in results.items()}
    withheld=[dict(name=f.name,raw_sha256=sha(f),reason='Private native-question failure screenshot may show canonical CAS')for f in root.glob('experience-mobile-*-failure.png')]
    qualification=dict(status='PARTIAL_POSITIVE_UNTIL_MOVED_CLOSE_REVISION_ORACLE',source_commit=package['source_commit'],wheel_sha256=package['wheel_sha256'],results=results,summary=summary,base_authority_invariants=dict(operations_unchanged=True,grant_digest_unchanged=True),scope_limits=['G01/G02 exact observed checks only; G03 meaningful specific titles not produced','I01 bounded keyboard path, not entire application or AT speech','360 layout is not native 200 percent zoom','F13 notice must be reviewed from actual Home/modal status captures','moved-close failed before its assertions; focus return and moved-card DOM not qualified','Authority was never renewed; one native question was published canonically only after base phases'],cleanup=cleanup,physical=dict(port=port,listeners=listeners,browser_profile_processes=processes,active_resources=False),payload_after=dict(files=count,mismatches=bad),browser_post_count=0,provider_invocations=0,fixture_cas_redactions=redactions,cas_fingerprints=privacy.fingerprints(cas),withheld_private_images=withheld,curation=entries,original_root=str(root))
    (dest/'qualification.json').write_text(json.dumps(qualification,indent=2)+'\n')
    manifest={str(f.relative_to(dest)):{'sha256':sha(f),'bytes':f.stat().st_size}for f in sorted(dest.rglob('*'))if f.is_file()};(dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(qualification=str(dest/'qualification.json'),manifest_sha256=sha(dest/'manifest.json'),physical0=True,summary=summary,fixture_cas_redactions=redactions),indent=2))
if __name__=='__main__':main()
