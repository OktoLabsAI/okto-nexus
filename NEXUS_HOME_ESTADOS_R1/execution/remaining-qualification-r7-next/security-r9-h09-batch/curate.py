"""Allowlisted public curation; never copy raw logs/cookies/DB/private rows."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    root=args.root.resolve()
    assert root.name.startswith('nexus-hst-browser-')
    data=json.loads((root/'security-run.private.json').read_text())
    assert Path(data['root']).resolve()==root and data['cut_id'].startswith('hst-security-')
    output=HERE/'runs'/data['cut_id']
    assert not output.exists(), 'Antecedents are immutable; new cut needs a new ID'
    output.mkdir(parents=True)
    results=[]
    for phase in data['results']:
        value=phase['result']
        # Only check IDs/booleans and canonical paths; arbitrary browser details,
        # errors, body, storage and response payloads stay private in own Temp.
        results.append({'phase':phase['phase'],'status':value['status'],
            'checks':[{'id':item['id'],'ok':item['ok']} for item in value.get('checks',[])],
            'requests':[{'method':item['method'],'path':item['path']}
                        for item in value.get('requests',value.get('network',[]))],
            'limits':value.get('limits',[])})
    public={}
    for name in ['before','before-get','after-get','after-revoke','before-obs','after-idle','after-completion']:
        path=root/'control'/('security-'+name+'.json')
        if path.exists():
            public[name]=json.loads(path.read_text())
    missing=[]
    phases={row['phase'] for row in results}
    required={'connection-details'}
    missing=sorted(required-phases)
    fixture=data['fixture_cleanup']
    physical=fixture.get('status')=='EXITED' and fixture.get('exit_code')==0 and not fixture.get('remaining_known_births') and not data['browser_cleanup']['remaining'] and not data['listeners']
    guards=data['before']==data['after'] and data['after'] is not None and data['runtime_helper_guarded']
    forced=bool(fixture.get('signals') or data['browser_cleanup']['forced_births'])
    failures=bool(data['failure'] or missing or any(row['status']=='FAIL' for row in results)
                  or any(item['changes'] or item['expected_observation_errors'] for item in data['diffs']))
    normal=physical and not forced
    report={
        'status':'PASS_SCOPED' if not failures and normal and guards else 'FAIL_OR_INCONCLUSIVE_PRESERVED',
        'case':data['case'],'cut_id':data['cut_id'],'source_commit':data['before']['source_commit'],
        'wheel_sha256':data['before']['wheel_sha256'],'provider_invocations':0,
        'results':results,'missing_phases':missing,'table_snapshots':public,'drift':data['diffs'],
        'commands':data['commands'],
        'failure_type':data['failure']['type'] if data['failure'] else None,
        'guards':{'before':data['before'],'after':data['after'],'equal':guards},
        'cleanup':{'normal':normal,'physical_absence':physical,'forced':forced,
                   'fixture':fixture,'browser':data['browser_cleanup'],'listeners':data['listeners'],
                   'sampling_limit':data['sampling_limit'],
                   'runtime_close_observations':data['fixture_close_observations']},
        'counts':{'public_snapshot_tables':len(next(iter(public.values()))['tables']) if public else 0},
        'limits':['No ledger promotion or broad H01-H10/K completion by case count',
                  'Embedded executor fixture, not live multi-harness Connector daemon; running-daemon clause remains partial',
                  'Actual pinned Connector CLI scope is static source evidence, not a restart execution',
                  'Any productive table drift is retained with column deltas and no invented causal attribution'],
        'private_rows_copied':False,'raw_auth_copied':False,'data_retained_in_own_temp':True,
    }
    argv_path=root/'browser-argv-before-home.json'
    report['browser_environment_policy']='windows-path-allowlist-app-env-own-v1'
    report['npx_or_npm_used']=False
    if argv_path.exists():report['actual_own_browser_before_home']=json.loads(argv_path.read_text())
    origin_path=root/'control/origins.json' 
    if origin_path.exists():
        report['origins']=json.loads(origin_path.read_text())
    permission_path=root/'control/security-permissions-proof.json'
    if permission_path.exists():
        report['observation_permission_precondition']=json.loads(permission_path.read_text())
    (output/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
    # Hash all raw files without copying bytes or inferring successful phases.
    raw={p.relative_to(root).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)}
         for p in root.rglob('*') if p.is_file() and 'browser-profile' not in p.parts and 'npm-cache' not in p.parts}
    (output/'raw-hashes.json').write_text(json.dumps(raw,indent=2)+'\n')
    manifest={p.name:sha(p) for p in output.iterdir() if p.is_file()}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'output':str(output),'status':report['status'],
                      'qualification_sha256':sha(output/'qualification.json')}))


if __name__=='__main__':
    main()
