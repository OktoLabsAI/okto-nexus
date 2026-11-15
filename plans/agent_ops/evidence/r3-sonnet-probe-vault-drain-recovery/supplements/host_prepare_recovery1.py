"""Resume the same host checkpoint after one explicit, durably observed probe."""
from pathlib import Path
import argparse
import json
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from recovery_context import require,read_json,sha,pin

BINDING_SHA='400724cd74381e58f6efa5cd4feb439c2c21d7108eaf2cad178ebc479618e30c'
REVIEW_SHA='3dc685af12ef88e39f90ef649528861ca11f81546df673a585cdc4ae7afd059b'
PROBE_SOURCE_SHA='7c63ec42bee41d3507fb54e227f2a961abbfcf08bb0db566fa95eeea48aeada7'


class SameServiceEnvironment:
    def __init__(self,base,environment):
        self.base,self.environment=base,environment
    def __getattr__(self,name):
        return getattr(self.base,name)
    def connector_env(self):
        return dict(self.environment)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--expected-source-sha256',required=True)
    parser.add_argument('--expected-probe-result-sha256',required=True)
    args=parser.parse_args()
    require(sha(__file__)==args.expected_source_sha256,'RECOVERY_SOURCE_CHANGED')
    require(sha(HERE/'recovery_probe_once.py')==PROBE_SOURCE_SHA,'EXPLICIT_PROBE_SOURCE_CHANGED')
    require(sha(HERE/'recovery_binding.py')=='4dfe7f41b3f627daa8aaf2f6b27eca03d8af92f6d0512af94e59c0b02b8daea0',
            'FROZEN_BINDING_SOURCE_CHANGED')
    import recovery_binding as original
    import recovery_probe_once as probe
    X=original.Context(HERE/'binding02-plan.json',BINDING_SHA,REVIEW_SHA)
    result_path=X.PUBLIC/'recovery02-explicit-probe-result.json'
    require(sha(result_path)==args.expected_probe_result_sha256,'EXPLICIT_PROBE_RESULT_CHANGED')
    result=read_json(result_path);X.base.require_tags(result)
    require(result.get('status')=='EXPLICIT_PROBE_CONFIRMED_RECOVERABLE'
            and result.get('candidate_source_exact') is True and result.get('checkpoint_pending_preserved') is True
            and result.get('discovery_configuration_unchanged') is True
            and result.get('recover_probe_read_only_check')=='PASS','EXPLICIT_PROBE_NOT_CONFIRMED')
    returned=read_json(X.PUBLIC/'recovery02-explicit-probe-returned.json');X.base.require_tags(returned)
    require(returned.get('returncode')==0,'EXPLICIT_PROBE_FAILED')
    require(not (X.PUBLIC/'binding02-host-prepare-result.json').exists(),'HOST_PREPARATION_ALREADY_CONFIRMED')
    failed_path=X.PUBLIC/'binding02-host-prepare-returned.json'
    failed=read_json(failed_path)
    require(failed.get('binding_plan_sha256')==BINDING_SHA and failed.get('returncode')!=0,
            'ORIGINAL_HOST_FAILURE_REQUIRED')
    failed_sha=sha(failed_path)
    rotation=X.rotation();doc,review=X.retained_review()
    X.require_prior('bootstrap');original.validate_bootstrap(doc,X.P)
    local=X.local_setup()
    require(doc['state']=='awaiting_host' and local is not None and local.get('stage')=='probe'
            and local.get('probe_operation')=='pending' and local.get('candidate_ref')==probe.REF
            and local.get('remote_setup')=={'setup_run_id':X.P['setup_request_id'],
                                           'review_revision':doc['review_revision']},'EXACT_PENDING_HOST_CHECKPOINT_REQUIRED')
    from okto_nexus_connector.platform.paths import state_file
    from okto_nexus_connector.storage.state_store import StateStore
    from okto_nexus_connector.services.remote_setup import recover_probe
    store=StateStore(state_file(Path(X.P['paths']['connector_state'])))
    recover_probe(store,local,X.P['server_id'])  # Pure reuse of durable observation; no native call.
    environment=probe.service_environment(X.base)
    X.base.require_ready()
    _,_,host=original.canonical_commands(X)
    X.PRIVATE=X.PRIVATE/'hostprepare-recovery1'
    X.PRIVATE.mkdir(exist_ok=False)
    X.base=SameServiceEnvironment(X.base,environment)
    original_save=X.save
    def save_recovery(name,value):
        require(name in ('binding02-host-prepare-reserved.json','binding02-host-prepare-returned.json'),
                'RECOVERY_INVOKE_SCOPE_CHANGED')
        original_save(name.replace('binding02-host-prepare-','binding02-hostprepare-recovery1-',1),
            dict(value,original_failed_returned_sha256=failed_sha,
                 explicit_probe_result_sha256=args.expected_probe_result_sha256))
    X.save=save_recovery
    try:
        X.invoke('host-prepare',host,connector=True)
    finally:
        X.save=original_save
    after=X.local_setup()
    require(after is not None and after.get('stage') in ('apply','done')
            and after.get('remote_setup')==local['remote_setup'],'HOST_PREPARATION_UNCONFIRMED')
    X.retained_review();X.base.require_ready()
    require(sha(failed_path)==failed_sha,'ORIGINAL_FAILURE_CHANGED')
    X.save('binding02-host-prepare-result.json',{'status':'RECOVERED_AFTER_EXPLICIT_PROBE',
        'profile_state':read_json(X.profile_path)['state'],'current_credential_epoch':2,
        'rotation_import_result_pin':rotation,'provider_calls':0,
        'actual_selection':'hostprepare-recovery1','original_failed_returned_sha256':failed_sha,
        'explicit_probe_result_sha256':args.expected_probe_result_sha256,
        'recovery_returned_sha256':sha(X.PUBLIC/'binding02-hostprepare-recovery1-returned.json'),
        'original_failed_returned_preserved':True})
    print(json.dumps({'status':'RECOVERED_AFTER_EXPLICIT_PROBE','provider_calls':0}))


if __name__=='__main__':
    main()
