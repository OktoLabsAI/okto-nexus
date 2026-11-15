"""Explicit canonical installation check; preserves pending setup and authority."""
from pathlib import Path
from dataclasses import asdict, replace
from unittest.mock import patch
import argparse
import asyncio
import json
import os
import subprocess
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from recovery_context import RecoveryContext,require,read_json,sha,pin

PLAN_SHA='8980570ab636b7836ffa34a5976652c0cc19825af015c50d50a9c5b08bcf6a27'
NATIVE={'path':'C:/Users/jpamb/.local/bin/claude.exe',
        'sha256':'5064e6e0572dca86257363ca04d48653eef20ef27f1bd04b504ed7199ed3fd13'}
SERVER='srv_a3f134b449dbffa20c126dae6f9a8aa9'
AGENT='m1-sonnet-remote'
REQUEST='m1-sonnet-remote-setup-02'
REF='nexus-install-v1:cf87799010465f0cc6012cf0dec649059684bb5d87e716aa18c0326f7e79e2fa'
REVISION='sha256:77fa079717648de88b047b4558a4967b2763810cb4519a00d3dcc14069989797'
REVIEW_SHA='3dc685af12ef88e39f90ef649528861ca11f81546df673a585cdc4ae7afd059b'
SERVICE_CONTEXT_SHA='d53a6f24b771efb418597b8fb91143c2b28efacad1df4f51e389741254f7bb21'


def service_environment(context):
    path=context.P['source_contexts']['connector']['path']
    require(sha(path)==SERVICE_CONTEXT_SHA,'PERSISTED_SERVICE_CONTEXT_CHANGED')
    value=context.connector_env()
    value['PATH']=read_json(path)['environment']['PATH']
    return value


async def selected_inputs(context,environment):
    from okto_nexus_connector.platform.paths import state_file
    from okto_nexus_connector.storage.state_store import StateStore
    from okto_nexus_connector.services.remote_setup import load
    from okto_nexus_connector.services.discovery_configuration import configured_candidates
    from okto_nexus_connector.services.discovery_service import resolve_selection
    from nexus_connector_core import calculate_inventory_revision
    store=StateStore(state_file(Path(context.P['paths']['connector_state'])))
    state=store.load();identity=state.identity_by_alias(AGENT)
    require(identity is not None and identity.server_id==SERVER and identity.agent_id==AGENT
            and identity.credential_epoch==2 and identity.revoked is False,'EPOCH2_IDENTITY_REQUIRED')
    saved=state.preferences.get('configure.'+SERVER+'.'+AGENT+'.'+REQUEST)
    require(isinstance(saved,dict) and saved.get('stage')=='probe' and saved.get('probe_operation')=='pending'
            and saved.get('candidate_ref')==REF and saved.get('inventory_revision')==REVISION,
            'ORIGINAL_PENDING_PROBE_CHANGED')
    record=load(store,REQUEST)
    rows=[row for row in state.execution_executors if row.server_id==SERVER]
    require(len(rows)==1 and rows[0].state=='REGISTERED' and not rows[0].installation_observations,
            'EXPLICIT_FIRST_OBSERVATION_REQUIRED')
    registered=rows[0]
    with patch.dict(os.environ,environment,clear=True):
        candidates=await configured_candidates(registered.discovery_configuration,
                                               observations=registered.installation_observations)
    selected=resolve_selection(candidates,'claude_stream',REF)
    require(asdict(selected)==record['local']['candidate'],'REVIEWED_CANDIDATE_SOURCE_CHANGED')
    revision=calculate_inventory_revision(candidates)
    pin(NATIVE)
    require(sha(HERE/'public/recovery02-review.json')==REVIEW_SHA,'CANONICAL_REVIEW_CHANGED')
    return store,saved,record,registered,revision


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--expected-source-sha256',required=True)
    args=parser.parse_args()
    require(sha(__file__)==args.expected_source_sha256,'PROBE_HELPER_CHANGED')
    context=RecoveryContext(HERE/'lifecycle-plan.json',PLAN_SHA)
    environment=service_environment(context)
    context.require_ready()
    store,saved,record,registered,revision=asyncio.run(selected_inputs(context,environment))
    argv=[context.python,'-I','-B','-X','utf8','-m','okto_nexus_connector.cli.main',
          '--non-interactive','--json','--state-dir',context.P['paths']['connector_state'],
          'executor','probe','--server-id',SERVER,'--harness','claude_stream',
          '--candidate-ref',REF,'--inventory-revision',revision]
    context.save('recovery02-explicit-probe-reserved.json',{'argv':argv,'source_sha256':sha(__file__),
        'full_inventory_revision':revision,'candidate_source_exact':True,
        'native_sha256':NATIVE['sha256'],'path_source_context_sha256':SERVICE_CONTEXT_SHA,
        'checkpoint_mutation_selected':False,'discovery_configuration_mutation_selected':False,
        'native_checks_selected':['version','protocol'],'provider_model_calls_selected':0})
    context.require_ready()
    # Recheck the owned checkpoint and registration after reservation, without resetting pending.
    current=store.load()
    require(current.preferences.get('configure.'+SERVER+'.'+AGENT+'.'+REQUEST)==saved
        and [replace(row,inventory_publication_sequence=0) for row in current.execution_executors
             if row.server_id==SERVER]==[replace(registered,inventory_publication_sequence=0)],
        'PRE_EFFECT_REGISTRATION_OR_CHECKPOINT_CHANGED')
    stdout=context.PRIVATE/'recovery02-explicit-probe.stdout'
    stderr=context.PRIVATE/'recovery02-explicit-probe.stderr'
    with stdout.open('xb') as out,stderr.open('xb') as err:
        child=subprocess.Popen(argv,cwd=context.ROOT,env=environment,stdin=subprocess.DEVNULL,
            stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        # Core bounds its selected checks; retain the CLI, never kill or repeat it.
        code=child.wait()
    value={'returncode':code,'stdout_sha256':sha(stdout),'stderr_sha256':sha(stderr),
           'wrapper_exit_confirmed':True,'provider_model_calls_selected':0,'automatic_retry':False}
    try:
        document=read_json(stdout);data=document.get('data',document)
        value['projection']={key:data[key] for key in ('server_id','executor_id','publication_pending','runtime_authorized') if key in data}
    except (ValueError,TypeError,AttributeError):value['parse_error']='OUTPUT_UNCONFIRMED'
    context.save('recovery02-explicit-probe-returned.json',value)
    require(code==0 and 'parse_error' not in value,'EXPLICIT_PROBE_UNCONFIRMED_NO_RETRY')
    from okto_nexus_connector.services.remote_setup import recover_probe
    recover_probe(store,saved,SERVER)
    after=store.load();rows=[row for row in after.execution_executors if row.server_id==SERVER]
    require(len(rows)==1 and rows[0].discovery_configuration==registered.discovery_configuration
            and after.preferences.get('configure.'+SERVER+'.'+AGENT+'.'+REQUEST)==saved,
            'CHECKPOINT_OR_DISCOVERY_CONFIGURATION_CHANGED')
    observations=[x for x in rows[0].installation_observations if x.get('source')==record['local']['candidate']]
    require(len(observations)==1 and observations[0].get('version'),'DURABLE_OBSERVATION_MISSING')
    context.require_ready()
    context.save('recovery02-explicit-probe-result.json',{'status':'EXPLICIT_PROBE_CONFIRMED_RECOVERABLE',
        'candidate_source_exact':True,'observed_version':observations[0]['version'],
        'checkpoint_pending_preserved':True,'discovery_configuration_unchanged':True,
        'recover_probe_read_only_check':'PASS','canonical_host_resume_selected':False,
        'provider_model_calls_selected':0})
    print(json.dumps({'status':'EXPLICIT_PROBE_CONFIRMED_RECOVERABLE','provider_model_calls_selected':0}))


if __name__=='__main__':
    main()
