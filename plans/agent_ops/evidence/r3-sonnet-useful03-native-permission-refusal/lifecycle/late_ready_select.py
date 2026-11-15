"""Observe the same late-READY owner; preserve the failed start and never retry it."""
from pathlib import Path
import argparse
import json
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from lifecycle import Context,require,read_json,sha,observed,validate_fresh

PLAN='101ca1a6aad80e849911e2612083ec7575120577f57b41ced7cc16497756a646'
STDOUT='3289bef5abb1d17787482d27b61f7773bb5ad65d2fd9f78238ad1af7b91c40d6'
OWNER={'pid':24972,'generation':'f8d19439521b499275eee719e97c8e12',
       'instance_id':'svc_0450942fe9a6c7193b066e766742217a829264e7520801f7baa7e89469468c11'}
CYCLE='3603e0f640de3ecef0220ed9422eb816'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--expected-source-sha256',required=True)
    parser.add_argument('--expected-start-returned-sha256',required=True)
    args=parser.parse_args()
    require(sha(__file__)==args.expected_source_sha256,'ADDITIVE_SOURCE_CHANGED')
    context=Context(HERE/'plan.json',PLAN)
    returned=context.PUBLIC/'start-returned.json'
    require(sha(returned)==args.expected_start_returned_sha256,'ORIGINAL_START_RETURN_CHANGED')
    receipt=read_json(returned);context.require_tags(receipt)
    require(receipt.get('returncode')==3 and receipt.get('stdout_sha256')==STDOUT,'ORIGINAL_CLI3_REQUIRED')
    output=context.PRIVATE/'start.stdout'
    require(sha(output)==STDOUT,'ORIGINAL_START_STDOUT_CHANGED')
    raw=read_json(output)
    require(raw.get('state')=='degraded' and raw.get('reason')=='SERVICE_UNREACHABLE'
        and raw.get('observation_error')=='transient_transport' and raw.get('observation_retryable') is True
        and raw.get('observed_owner')==OWNER,'ORIGINAL_TRANSIENT_SAME_OWNER_REQUIRED')
    require(not (context.PUBLIC/'nexus-owner-selection.json').exists(),'SELECTION_ALREADY_EXISTS')
    context.save('late-ready-select-reserved.json',{'service_actions':0,'provider_calls':0,
        'original_returned_sha256':args.expected_start_returned_sha256,'source_sha256':args.expected_source_sha256})
    selected,handles=observed.capture(context)
    try:
        require(all(selected.get(k)==v for k,v in OWNER.items()) and selected['cohort']['cycle_id']==CYCLE
            and selected['cohort']['attempts_started']==1,'OBSERVED_OWNER_OR_CYCLE_CHANGED')
        validate_fresh(selected,context.previous['cohorts']['nexus'])
        observed.same_cycle(selected['cohort'],observed.cycle(context))
        require(not any(h.exited() for h in handles.values()),'OWNER_EXITED_BEFORE_SELECTION')
        require(sha(returned)==args.expected_start_returned_sha256,'ORIGINAL_RETURN_CHANGED')
        context.save('nexus-owner-selection.json',selected)
        context.save('late-ready-select-result.json',{'status':'SAME_OWNER_READY_OBSERVED',
            'original_start_returncode':3,'original_failure_preserved':True,'owner':OWNER,'cycle_id':CYCLE,
            'selection_sha256':sha(context.PUBLIC/'nexus-owner-selection.json'),
            'service_actions':0,'provider_calls':0,'start_replay':False})
        print(json.dumps({'status':'SAME_OWNER_READY_OBSERVED','service_actions':0}))
    finally:
        for h in handles.values():h.close()


if __name__=='__main__':main()
