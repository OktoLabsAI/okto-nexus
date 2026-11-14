"""Read-only accounting linkage after original closure; no controller construction."""
from pathlib import Path
import argparse,hashlib,json,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from entry import BASE,static,require,sha,read

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--expected-manifest-sha256',required=True)
    args=p.parse_args();m=static(args)
    closure_path=BASE/'public/closure.json';closure=read(closure_path)
    require(closure.get('status')=='CLOSED_NORMAL_CLEANUP_ACCEPTANCE_NOT_INFERRED'
        and closure.get('amendment_sha256')==m['basis']['amendment']['sha256']
        and closure.get('all_temporary_tasks_absent') is True,'ORIGINAL_CLOSURE_REQUIRED')
    require(sha(BASE/'private/controller.json')==closure['controller_checkpoint_sha256'],'CLOSED_CHECKPOINT_CHANGED')
    ledger={}
    for path in (HERE/'runtime-private').glob('*.reserved.json'):
        selected=read(path);phase=selected['phase'];require(phase in ('useful','continuation'),'FINITE_LEDGER_REQUIRED')
        result_path=path.with_name(path.name.replace('.reserved.json','.returned.json'));result=read(result_path)
        require(result['phase']==phase and result['manifest_sha256']==args.expected_manifest_sha256
            and result['wrapper_exit_confirmed'] is True,'SUPPLEMENT_WRAPPER_EXIT_REQUIRED')
        ledger[phase]={'reservation_sha256':sha(path),'returned_sha256':sha(result_path),'returncode':result['returncode']}
    require('useful' in ledger,'REENTRY_EVIDENCE_REQUIRED')
    value={'status':'CLOSED_WITH_PREDISPATCH_REENTRY_COMPANION','original_closure_sha256':sha(closure_path),
        'original_checkpoint_sha256':closure['controller_checkpoint_sha256'],
        'original_failed_wrapper':m['basis']['failed_wrapper'],'original_returncode':1,
        'original_failure_reclassified':False,'sidecar_manifest_sha256':args.expected_manifest_sha256,'invocations':ledger,
        'cumulative_minimum_observed_tokens':closure['cumulative_minimum_observed_tokens'],
        'cumulative_reserved_admissions':closure['cumulative_reserved_admissions'],
        'accounting_copied_without_mutation':True,'acceptance_promoted':False,'replay_allowed':False}
    with (HERE/'closure-companion.json').open('x',encoding='utf-8') as out:json.dump(value,out,indent=2)
    print(json.dumps(value));return 0
if __name__=='__main__':raise SystemExit(main())
