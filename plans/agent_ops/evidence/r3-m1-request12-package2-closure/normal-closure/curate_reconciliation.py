"""Copy only finite public allowlists and metadata; never copy controller/DB/logs."""
import hashlib
import json
from pathlib import Path
import re
import tempfile

H=Path(__file__).resolve().parent
W=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-request12-package2')
O=Path('C:/Users/jpamb/AppData/Local/Temp/m1-package2-facade-reentry-0da1ewap')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def pin(p):return {'path':str(p),'sha256':sha(p)}
def write(p,v):
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n')

def main():
    evidence=read(H/'accounting-reconciliation.json')
    assert sha(W/'private/controller.json')==evidence['original_checkpoint']['sha256']
    assert not (W/'public/closure.json').exists()
    companion={'kind':'NORMAL_CLOSURE_COMPANION_WITH_POST_EXIT_ACCOUNTING','status':'FAILED_CAMPAIGN_NORMAL_CLEANUP_CONFIRMED',
        'original_closure_absent':True,'original_close_helper_executed':False,
        'scope':'Request12 productive attempt, transparent facade overlay, one canonical interrupt, normal service cohort exit and integration removal. No M1 acceptance.',
        'original_checkpoint':evidence['original_checkpoint'],'original_checkpoint_untouched':True,
        'original_request_settled':False,'original_faults':evidence['original_faults'],
        'accounting':pin(H/'accounting-reconciliation.json'),
        'observed_tokens':295262,'charged_reservations':12,'refunds':0,
        'request12':{'id':'m1v14-local-work-12','canonical_stage':'CANCELLED','receipt_revision':2,
                     'session_state':'CLOSED','lease_state':'CLOSED','native_pending_count':0,
                     'collector_post_exit_state':'settled_observed','cursor':47,'watermark':47,
                     'useful_result_accepted':False},
        'interrupt':{'operation_id':'op_851b83130e83385e1dc2eb47bfe06452','receipt_stage':'SUBMITTED',
                     'receipt_revision':1,'completion_receipt_confirmed':False,
                     'effect_evidence':'Target turn CANCELLED; native request STALE; session/lease CLOSED; cohort physical exit.',
                     'admission':pin(H/'runtime/execute-result.json')},
        'normal_cleanup':{'physical_exit':pin(W/'public/nexus-exit-proof.json'),
            'cleanup_proof':pin(W/'public/cleanup-nexus.json'),
            'uninstall':pin(W/'public/lifecycle-nexus-uninstall-result.json'),
            'final_presence':pin(W/'public/final-presence.json'),
            'primary_database_preservation':pin(H/'runtime/data-preservation.json'),
            'all_three_retained_handles_exited':True,'force_used':False,'tasks_absent':True,'port_probe':58631},
        'original_pre_dispatch_failure':pin(W/'runtime-private/work-local-useful.returned.json'),
        'overlay_actual_failure':pin(O/'runtime-private/work-local-useful.returned.json'),
        'overlay_manifest':pin(O/'manifest.json'),'package_freeze':pin(W/'runtime-freeze.json'),
        'request13_selected':False,'remote_dx40':'PENDING','m1_acceptance':False,
        'provider_billing_finality_claimed':False,'new_execution_authorized_by_companion':False,
        'collector_summary_is_observation_not_admission_authority':True,
        'original_failure_reclassified':False,'budgets_unchanged':{'preventive':500000,'tolerance':700000,'max_cumulative_admissions':13},
        'configuration_fields_reported_only_not_enforcement':True}
    write(H/'closure-companion.json',companion)
    destination=Path(tempfile.mkdtemp(prefix='m1-request12-package2-curation-'))
    copied=[]
    def copy(source,target,expected=None):
        source=Path(source);data=source.read_bytes();digest=hashlib.sha256(data).hexdigest()
        assert expected is None or digest==expected
        path=destination/target;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f:f.write(data)
        assert sha(path)==digest
        copied.append({'path':str(path),'relative_path':str(target).replace('\\','/'),'sha256':digest,'source':str(source),'bytes':len(data)})
    for root,group,expected in ((W,'preparation','4c81dfb5284ed05487f62958835904ed933defbc11780829a61654611e5fc428'),
                                (O,'overlay','518301dea4917460602b9bbd7400e76b239791bd1bbe5bccbc461900716c59b4')):
        allow=root/'public-allowlist.json';assert sha(allow)==expected
        for item in read(allow)['files']:
            source=Path(item['path']);copy(source,Path(group)/source.relative_to(root),item['sha256'])
        copy(allow,Path(group)/'public-allowlist.json')
    for name in ('root-driver-preparation.json','environment-upgrade-plan-result.json','environment-upgrade-apply-result.json',
                 'lifecycle-nexus-install-result.json','lifecycle-nexus-start-result.json','lifecycle-nexus-stop-result.json',
                 'lifecycle-nexus-uninstall-result.json','nexus-owner-selection.json','nexus-exit-proof.json',
                 'cleanup-nexus.json','final-presence.json','m1v14-local-work-12-dispatch-selection.json'):
        copy(W/'public'/name,Path('execution')/name)
    copy(W/'runtime-private/work-local-useful.returned.json',Path('execution/original-work-returned.json'))
    for name in ('work-local-useful.claimed.json','work-local-useful.process.json','work-local-useful.reserved.json','work-local-useful.returned.json'):
        copy(O/'runtime-private'/name,Path('overlay-execution')/name)
    for name in ('observe.py','observation.json','interrupt.py','manifest.json','workflow.json','reconcile_accounting.py',
                 'accounting-reconciliation.json','closure-companion.json','curate_reconciliation.py'):
        copy(H/name,Path('normal-closure')/name)
    for name in ('execute-reserved.json','resolve-reserved.json','resolved.json','admit-reserved.json','admitted.json',
                 'execute-result.json','data-before.json','data-preservation.json'):
        copy(H/'runtime'/name,Path('normal-closure/runtime')/name)
    diagnosis=Path('C:/Users/jpamb/AppData/Local/Temp/m1-w12-cli-refusal-kxl0gj3e/thread-configuration-projection.json')
    copy(diagnosis,Path('diagnosis/thread-configuration-projection.json'),'22f2c89f7f498b4e53272826589501d72a27e2e91b10ce5acf6bbb433137a786')
    suspicious=[]
    patterns=[r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'\bsk-[A-Za-z0-9_-]{20,}',
              r'"(?:access_token|refresh_token|password|client_secret)"\s*:\s*"[^"\s]{8,}"']
    for item in copied:
        text=Path(item['path']).read_text(encoding='utf-8')
        if any(re.search(pattern,text) for pattern in patterns):suspicious.append(item['relative_path'])
    assert not suspicious,suspicious
    review={'status':'CURATED_FAILED_CAMPAIGN_NORMAL_CLEANUP_NO_ACCEPTANCE','copied_files':len(copied),
            'all_copy_hashes_verified':True,'high_specificity_secret_scan_matches':suspicious,
            'review_scope':'Only allowlisted copies; no raw private controller, DB, stdout/stderr, transcript, provider configuration or credential files.',
            'reconciliation_tool':'31f1fc exit0','snapshot_seconds':1,'schema_seconds':2,'post_exit_elapsed_seconds':evidence['elapsed_seconds'],
            'original_checkpoint_unchanged':sha(W/'private/controller.json')==evidence['original_checkpoint']['sha256'],
            'original_faults_preserved':True,'observed_tokens':295262,'charged_reservations':12,
            'interrupt_completion_receipt_confirmed':False,'m1_acceptance':False,'scenario_count_unchanged':'123/132',
            'repository_modified':False,'ledger_modified':False}
    write(destination/'review.json',review)
    copied.append({'path':str(destination/'review.json'),'relative_path':'review.json','sha256':sha(destination/'review.json')})
    write(destination/'public-allowlist.json',{'files':copied,'excludes':['private/controller.json','DBs','stdout/stderr','auth','credentials','transcripts']})
    print(json.dumps({'destination':str(destination),'files':len(copied),'allowlist':pin(destination/'public-allowlist.json'),
                      'companion':pin(H/'closure-companion.json'),'accounting':pin(H/'accounting-reconciliation.json')}))

if __name__=='__main__':main()
