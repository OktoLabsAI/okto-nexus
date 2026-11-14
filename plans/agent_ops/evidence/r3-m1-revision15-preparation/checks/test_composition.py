import json,sys
from pathlib import Path
from types import SimpleNamespace
import pytest

W=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(W),str(W/'modules')]
import request_context as context_module

@pytest.fixture(scope='module')
def context():
    path=W/'amendment.json'
    return context_module.gate(SimpleNamespace(amendment=str(path),expected_amendment_sha256=context_module.sha(path)))

def test_real_gate_and_facade_bind_revision15(context):
    import controller,independent_controller,legacy_controller
    assert controller.POLICY==independent_controller.POLICY==legacy_controller.POLICY==context.amendment['policy']
    assert controller.ANCESTRY==legacy_controller.ANCESTRY==context.amendment['controller_ancestry']
    assert context.P['request_ids']['work']==list(context.amendment['request_ids'].values())
    assert context.P['finite_work']['maximum_cumulative_admissions']==16
    assert context.C['counts']['remote_selectors_enabled'] is False
    assert not context.PUBLIC.exists() and not context.PRIVATE.exists()

def test_real_derivation_and_closure_keep_failed_history(context):
    from fresh_work_controller import prepare_derived
    from close_campaign import checkpoint_summary
    import token_collector
    basis=context.amendment['basis']
    values=[json.loads(Path(basis[k]['path']).read_bytes()) for k in ('checkpoint','companion','accounting')]
    derived=prepare_derived(*values,source_pins=basis)
    summary=checkpoint_summary(context,derived,token_collector.summary(token_collector.restore(derived['collector'])))
    assert summary['cumulative_minimum_observed_tokens']==295262
    assert summary['cumulative_reserved_admissions']==12
    assert summary['historical_control_receipt_stage_snapshot']=='SUBMITTED'
    assert summary['historical_stream_settlement_synthesized'] is False
    assert summary['unsettled_requests']==0 and derived['requests']=={}
    assert derived['fresh_local_work']['historical_checkpoint']==values[0]

def test_closure_does_not_settle_current_faulted_request(context):
    from fresh_work_controller import prepare_derived
    from close_campaign import checkpoint_summary
    from legacy_controller import seal
    basis=context.amendment['basis']
    derived=prepare_derived(*[json.loads(Path(basis[k]['path']).read_bytes()) for k in ('checkpoint','companion','accounting')],source_pins=basis)
    derived['requests']['m1v15-local-useful-13']={'kind':'work','settled':False}
    derived['faults']=['API_OBSERVATION_UNKNOWN'];derived['state_sha256']=seal(derived)
    summary=checkpoint_summary(context,derived,{'known_observed_tokens':25})
    assert summary['unsettled_requests']==1 and summary['faults_preserved']==['API_OBSERVATION_UNKNOWN']
    assert summary['cumulative_minimum_observed_tokens']==295287 and summary['billing_final'] is False

def test_remote_selector_refused_before_entry(tmp_path):
    import request_entry
    (tmp_path/'root-driver-preparation.json').write_text('{}')
    fake=SimpleNamespace(PUBLIC=tmp_path)
    with pytest.raises(RuntimeError,match='REMOTE_SELECTORS_HELD_LOCAL_ONLY'):
        request_entry.execute(fake,'work',['remote','useful'],run=lambda *_a,**_k:pytest.fail('remote entry executed'))

def test_predecessor_control_completion_not_invented(context,tmp_path):
    proof=json.loads(Path(context.amendment['technical_predecessor']['path']).read_bytes())
    companion=json.loads(Path(proof['files']['companion']['path']).read_bytes())
    companion['interrupt']['completion_receipt_confirmed']=True
    path=tmp_path/'companion.json';path.write_text(json.dumps(companion))
    proof['files']['companion']={'path':str(path),'sha256':context_module.sha(path)}
    path=tmp_path/'proof.json';path.write_text(json.dumps(proof))
    with pytest.raises(RuntimeError,match='PREDECESSOR_UNCERTAINTY_CHANGED'):
        context_module.verify_technical_predecessor({'path':str(path),'sha256':context_module.sha(path)})

def test_new_migration_source_revision_is_current_closed_context(context):
    from okto_nexus.adapters.outbound.service_manager.context import document_revision
    migration=context.amendment['migration']
    source=json.loads(Path(migration['source_context']['path']).read_bytes())
    assert context_module.sha(migration['source_context']['path'])==migration['source_context']['sha256']
    assert source['revision']==2 and document_revision(source)==migration['source_context_revision']
    assert context.amendment['predecessor_connection_generation']==7
