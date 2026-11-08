"""Curate only the closed v10 campaign's explicit metadata/script allowlist."""
from pathlib import Path
import hashlib,json,re

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'public'
C=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v10-bundle-pscf18t5/campaign')
D=C.parent/'draft';A=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v10-approved-execution')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
closure=read(C/'public/closure.json');checkpoint_path=C/'private/controller.json'
assert sha(C/'public/closure.json')=='c3d3e5f5b5b8fbec2c86ea711350ba1a7de44022e568b1c6cfc4fe2e93ff6db0'
assert sha(checkpoint_path)==closure['controller_checkpoint_sha256']=='8edf98687a374e607a662f00a21cc05e6461e87e4fd8118bf6fc6ecb52948f3e'
assert sha(A/'authorization.json')==closure['approval_sha256']=='8500ae2cd11ff8dca2bc1551a9a5349f76075a0578f2e931c436a09ee2515620'
proposal=read(D/'m1-codex-campaign-proposal-v10.json')
assert sha(D/'m1-codex-campaign-proposal-v10.json')==closure['proposal_sha256']
assert not OUT.exists();OUT.mkdir()

public_names=[
 'authorization-reference.json','cleanup-nexus.json','closure.json','final-presence.json',
 'lifecycle-nexus-install-result.json','lifecycle-nexus-install.json',
 'lifecycle-nexus-start-result.json','lifecycle-nexus-start.json',
 'lifecycle-nexus-stop-result.json','lifecycle-nexus-stop.json',
 'lifecycle-nexus-uninstall-result.json','lifecycle-nexus-uninstall.json',
 'live-accounting.json','local-setup-dispatch.json','local-setup-result.json',
 'm1v10-local-work-01-dispatch-selection.json','m1v10-local-work-01-runner-error.json',
 'nexus-exit-proof.json','nexus-exit-watch-started.json','nexus-owner-selection.json',
 'nexus-status-1794136555950496900.json','observer-error-diagnosis.json',
 'process-nexus-install.json','process-nexus-start.json','process-nexus-stop.json','process-nexus-uninstall.json']
driver_names=['invoke.py','m1_v10_nexus_observation.py','m1_v10_confirm_cleanup.py',
              'confirm_final_presence.py','close_campaign.py','prepare_observation.py']
execution_names=['authorization.json','authorization-pin-check.json','preflight-before-install.json',
 'observation-driver-pins.json','lifecycle-initialize-process.json','lifecycle-nexus-install-process.json',
 'lifecycle-nexus-start-process.json','lifecycle-nexus-uninstall-process.json',
 'plan-local_plan-process.json','setup-local-process.json','work-local-useful-process.json']
source_pairs=[(C/'public'/n,Path('campaign')/n) for n in public_names]
source_pairs +=[(A/n,Path('drivers')/n) for n in driver_names]
source_pairs +=[(A/n,Path('execution')/n) for n in execution_names]
source_pairs +=[(D/'installation'/n,Path('installation')/n) for n in ('installation-reserved.json','installation-result.json')]
source_pairs +=[(Path(__file__),Path('collect_public.py'))]
before={str(p):sha(p) for p,_ in source_pairs}
before[str(checkpoint_path)]=sha(checkpoint_path)

# Top-level and nested metadata inspected before curation. Reject plausible
# actual credential material; do not redact/mutate a frozen original silently.
secret=re.compile(rb'(?<![A-Za-z0-9])nxs_[0-9a-fA-F]{48}(?![0-9a-fA-F])|Bearer\s+[A-Za-z0-9._~-]{20,}',re.I)
for source,_ in source_pairs:assert not secret.search(source.read_bytes()),source.name
selection=read(C/'public/m1v10-local-work-01-dispatch-selection.json')
assert set(selection)=={'request_id','lane','phase','time','prompt_sha256','client_pin'}
assert selection['client_pin']==proposal['package_pins']
assert selection['request_id']=='m1v10-local-work-01' and selection['lane']=='local' and selection['phase']=='useful'
assert selection['prompt_sha256']==hashlib.sha256(proposal['finite_work']['resolved_requests']['local'].encode()).hexdigest()

entries=[]
for source,relative in source_pairs:
    target=OUT/relative;target.parent.mkdir(parents=True,exist_ok=True)
    raw=source.read_bytes()
    with target.open('xb') as f:f.write(raw)
    assert sha(target)==before[str(source)]
    entries.append({'path':relative.as_posix(),'source_path':str(source),'source_sha256':before[str(source)],
        'artifact_sha256':sha(target),'bytes':len(raw),'transformation':'byte_exact','redactions':0})

def generated(name,value,source=None):
    target=OUT/name;target.parent.mkdir(parents=True,exist_ok=True)
    raw=(json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode()
    assert not secret.search(raw)
    with target.open('xb') as f:f.write(raw)
    entries.append({'path':name,'source_path':str(source) if source else 'generated reconciliation',
        'source_sha256':before[str(source)] if source else None,'artifact_sha256':sha(target),'bytes':len(raw),
        'transformation':'explicit_allowlist_projection' if source else 'generated_summary','redactions':0})

state=read(checkpoint_path)
assert set(state['requests'])=={'m1v10-local-setup'}
assert state['faults']==['CAMPAIGN_RUNNER_EXCEPTION']
assert state['policy']==proposal['controller_preparation']['policy'] and state['ancestry']==proposal['controller_preparation']['ancestry']
record=state['requests']['m1v10-local-setup']
monitor_fields=('cursor','high_water','started','terminal','usage_seen','caught_up','result_stage','close_stage','owned_slot_released')
collector=state['collector']['state']
projection={
 'format':'okto.m1.controller-checkpoint-public-projection','revision':1,
 'source_sha256':before[str(checkpoint_path)],'source_copied_raw':False,
 'controller_format':state['format'],'proposal_sha256':state['proposal_sha256'],
 'authorization_sha256':state['authorization_sha256'],'state_sha256':state['state_sha256'],
 'policy':state['policy'],'ancestry':state['ancestry'],'faults':state['faults'],
 'requests':{'m1v10-local-setup':{'kind':record['kind'],'lane':record['lane'],'settled':record['settled'],
     'stop_selected':record['stop_selected'],'monitor':{k:record['monitor'][k] for k in monitor_fields}}},
 'work_request_reserved':False,'collector':{'format':state['collector']['format'],
     'sha256':state['collector']['sha256'],'current_request':collector['current_request'],'faults':collector['faults'],
     'counts':{k:len(collector[k]) for k in ('requests','streams','threads','turns')}},
 'independent_owner_stops':{lane:{k:r[k] for k in ('state','reason','native_exit_confirmed','force_used')} for lane,r in state['independent_owner_stops'].items()},
 'independent_observation':{k:state['independent_observation'][k] for k in ('maximum_poll_start_interval_seconds','source','worker_in_flight')},
 'limits':'Allowlist projection only. No private checkpoint body, provider payload, prompt, paths to provider state, credential or transcript is copied. Owner-stop reservation is not itself proof of exit; use separate cleanup/retained HANDLE proof.'}
generated('controller-checkpoint-projection.json',projection,checkpoint_path)

setup=read(C/'public/local-setup-result.json');failure=read(C/'public/m1v10-local-work-01-runner-error.json')
presence=read(C/'public/final-presence.json');install=read(D/'installation/installation-result.json')
assert setup['cli_exit']==0 and setup['monitor']['result_stage']=='SUCCEEDED'
assert setup['monitor']['high_water']==21815 and setup['monitor']['usage_seen'] and setup['monitor']['caught_up']
assert failure['request'] is None and failure['summary']['can_admit'] is False
assert presence['work_intent_rows']==0 and not presence['work_reservation_exists'] and not presence['work_dispatched']
assert install['status']=='INSTALLED_VERIFIED' and install['payload_count']==983 and install['pip_check']['returncode']==0
assert install['reservation_sha256']==sha(D/'installation/installation-reserved.json')
for name,digest in closure['evidence_sha256'].items():assert sha(C/'public'/name)==digest
for action in ('install','start','stop','uninstall'):
    assert read(C/'public'/f'lifecycle-nexus-{action}-result.json')['returncode']==0
summary={
 'status':'V10_CLOSED_AFTER_OBSERVER_PREFLIGHT_FAILURE_NO_M1_ACCEPTANCE',
 'proposal_sha256':closure['proposal_sha256'],'approval_sha256':closure['approval_sha256'],
 'closure_sha256':sha(C/'public/closure.json'),'checkpoint_sha256':before[str(checkpoint_path)],
 'installation':{'attempts':1,'status':'INSTALLED_VERIFIED','product_payloads':983,'pip_check_returncode':0,
     'receipt':'installation/installation-result.json','first_useful_result':False,'base06_complete':False},
 'setup':{'confirmed_productive_admissions':1,'cli_exit':0,'result_stage':'SUCCEEDED','new_minimum_observed_tokens':21815,
     'usage_seen':True,'caught_up':True,'owned_slot_released':True,'close_stage_reported':setup['monitor']['close_stage']},
 'useful_work':{'dispatch_selection_artifact_exists':True,'controller_reservation_created':False,
     'api_post_dispatched':False,'canonical_intent_rows':0,'native_admitted':False,'model_turns':0,'report_exists':False,
     'failure':'Observer freshness SELECT raised sqlite3.OperationalError: interrupted before start_work reservation.',
     'diagnosis':'campaign/observer-error-diagnosis.json','original_numeric_sqlite_code_retained':False},
 'accounting':{'prior_reserved':5,'new_reserved':1,'cumulative_reserved':6,
     'prior_minimum_observed_tokens':67658,'new_minimum_observed_tokens':21815,'cumulative_minimum_observed_tokens':89473,
     'billing_final':False,'historical_confirmed_productive_admissions':3,'new_confirmed_productive_admissions':1},
 'closure':{'normal_stop_returncode':0,'drain':'DRAINED','retained_handle_exit_confirmed':True,
     'uninstall_returncode':0,'two_exact_tasks_absent':True,'port_free_at_root_observation':56237,
     'forced_service_stop':False,'connector_started':False,'claude_executed':False,'data_retained':True},
 'snapshot_order_note':'campaign/live-accounting.json is an earlier pre-failure snapshot with can_admit=true. It is preserved as historical evidence and does not supersede the final faulted checkpoint/runner-error/closure. Dispatch-selection.json is selection metadata, not proof of admission.',
 'limits':['No useful work, native decision, continuation, Connector lane or M1 acceptance is promoted.',
     'The observer failure is distinct from the prior v9 product DB_ERROR; root supplied a sanitized diagnosis. This collector neither reproduces nor establishes a deeper SQLite cause.',
     'Setup close_stage SUBMITTED is preserved exactly; separate owned-slot and service-exit evidence is not relabeled as a native close receipt.',
     'Observed tokens are not final provider billing. This closed campaign confers no replay or future admission authority.',
     'No test, service, provider, HTTP, Scheduler or database operation was executed by the collector. Original metadata/source hashes are checked before and after copying.'],
 'redactions':0,'private_material_excluded':['raw stdout/stderr','private logs','raw controller checkpoint','SQLite databases','vaults','provider authentication/configuration/transcripts','wheels and venvs']}
generated('summary.json',summary)
assert all(sha(path)==digest for path,digest in before.items())
generated('source-stability.json',{'status':'PASS','source_count':len(before),'hashes_before':before,
    'all_hashes_unchanged_after':True,'database_opened':False,'product_invoked':False,'campaign_or_checkpoint_mutated':False})
entries.sort(key=lambda e:e['path'])
aggregate=hashlib.sha256(''.join(e['path']+'\0'+e['artifact_sha256']+'\n' for e in entries).encode()).hexdigest()
manifest={'format':'okto.public-artifact-allowlist','revision':1,'artifact_count':len(entries),'aggregate_sha256':aggregate,
    'artifacts':entries,'copy_policy':'Exact allowlist; byte-identical source copies plus explicitly identified generated projections/summaries.',
    'redactions':0,'no_raw_private_logs_or_databases':True,'all_sources_unchanged':True}
M=OUT/'artifact-manifest.json';M.write_bytes((json.dumps(manifest,indent=2,ensure_ascii=False)+'\n').encode())
print(json.dumps({'public':str(OUT),'manifest_sha256':sha(M),'aggregate_sha256':aggregate,
    'artifacts':len(entries),'summary_sha256':sha(OUT/'summary.json'),'closure_sha256':sha(OUT/'campaign/closure.json'),
    'checkpoint_projection_sha256':sha(OUT/'controller-checkpoint-projection.json'),'redactions':0}))
