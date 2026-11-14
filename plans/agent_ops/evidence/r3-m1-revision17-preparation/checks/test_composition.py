import json,sys,subprocess,hashlib
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime,timezone,timedelta
import pytest

W=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(W),str(W/'modules')]
import request_context as cm

@pytest.fixture(scope='module')
def context():
    path=W/'amendment.json'
    return cm.gate(SimpleNamespace(amendment=str(path),expected_amendment_sha256=cm.sha(path)))

def test_real_gate_and_facade_prompt_package_exact(context):
    import controller,independent_controller,legacy_controller
    assert controller.POLICY==independent_controller.POLICY==legacy_controller.POLICY==context.amendment['policy']
    assert context.P['finite_work']['maximum_cumulative_admissions']==18
    plan=json.loads(cm.pinned(context.amendment['execution_plan']).read_bytes())
    assert context.P['finite_work']['request']==plan['prompt_revision']['request']
    assert context.P['finite_work']['continuation']==plan['prompt_revision']['continuation']
    assert Path(sys.prefix)==W.with_name('work-revision16')/'package/venv'
    assert not any((W/n).exists() for n in ('public','private','runtime-private','package'))

def derived(context):
    from fresh_work_controller import prepare_derived
    basis=context.amendment['basis']
    return prepare_derived(*[json.loads(cm.pinned(basis[k]).read_bytes()) for k in ('checkpoint','companion','accounting')],source_pins=basis)

def test_real_derivation_closure_keep_five_histories(context):
    from close_campaign import checkpoint_summary
    import token_collector
    cp=derived(context)
    summary=checkpoint_summary(context,cp,token_collector.summary(token_collector.restore(cp['collector'])))
    assert summary['cumulative_minimum_observed_tokens']==460793
    assert summary['cumulative_reserved_admissions']==14
    assert summary['historical_original_unsettled_requests']==2
    assert summary['historical_control_receipt_completion_asserted'] is False
    assert summary['unsettled_requests']==0 and cp['requests']=={}
    assert len(cp['fresh_local_work']['historical_records'])==5

def test_faulted_current_work_not_settled_by_cleanup(context):
    from close_campaign import checkpoint_summary
    from legacy_controller import seal
    cp=derived(context);cp['requests']['m1v17-local-useful-15']={'kind':'work','settled':False}
    cp['faults']=['API_OBSERVATION_UNKNOWN'];cp['state_sha256']=seal(cp)
    summary=checkpoint_summary(context,cp,{'known_observed_tokens':25})
    assert summary['unsettled_requests']==1 and summary['cumulative_minimum_observed_tokens']==460818
    assert summary['billing_final'] is False

@pytest.mark.parametrize('mode,selection,code',[
    ('upgrade',['apply'],'FINITE_MODE_INVALID'),('work',['remote','useful'],'REMOTE_SELECTORS_HELD_LOCAL_ONLY')])
def test_nonselected_modes_refuse_before_entry(tmp_path,mode,selection,code):
    import request_entry
    (tmp_path/'root-driver-preparation.json').write_text('{}')
    with pytest.raises(RuntimeError,match=code):
        request_entry.execute(SimpleNamespace(PUBLIC=tmp_path),mode,selection,run=lambda *_a,**_k:pytest.fail('executed'))

def test_expiry_clock_is_only_preobservation_boundary(context):
    expiry=datetime.fromisoformat(context.amendment['grant_plan']['old_expiry_utc'].replace('Z','+00:00'))
    with pytest.raises(RuntimeError,match='PRIOR_GRANT_EXPIRY_WINDOW_NOT_REACHED'):
        cm.require_expiry_boundary(context.amendment,now=expiry-timedelta(microseconds=1))
    assert cm.require_expiry_boundary(context.amendment,now=expiry)

def test_available_one_action_reported_not_expired_and_cannot_issue(context):
    from authorize_local import validate_review
    old=W.with_name('work-revision16')
    review=json.loads((old/'public/authorize-local-review.json').read_bytes())['review']
    active=next(g for g in review['current_grants'] if g['state']=='available')
    active['used_executions']=2
    assert validate_review(context,review,allow_available=True)==active['grant_id']
    with pytest.raises(RuntimeError,match='HISTORICAL_GRANT_CHANGED'):validate_review(context,review)
    active['state']='expired';review['can_issue']=True
    assert validate_review(context,review) is None
    active['used_executions']=1
    with pytest.raises(RuntimeError,match='HISTORICAL_GRANT_CHANGED'):validate_review(context,review)

def test_reused_service_context_and_no_upgrade_commands(context):
    assert cm.sha(context.amendment['reused_service_context']['path'])==context.amendment['reused_service_context']['sha256']
    assert context.C['counts']['canonical_environment_upgrade_commands']==0
    assert context.amendment['predecessor_connection_generation']==9
    assert len(context.P['adoption']['expected_historical_grants'])==6

def test_predecessor_receipt_completion_not_invented(context,tmp_path):
    proof=json.loads(cm.pinned(context.amendment['technical_predecessor']).read_bytes())
    companion=json.loads(cm.pinned(proof['files']['companion']).read_bytes())
    companion['decision_receipts']['final_receipt_completion_asserted']=True
    path=tmp_path/'companion.json';path.write_text(json.dumps(companion))
    proof['files']['companion']={'path':str(path),'sha256':cm.sha(path)}
    path=tmp_path/'proof.json';path.write_text(json.dumps(proof))
    with pytest.raises(RuntimeError,match='PREDECESSOR_UNCERTAINTY_CHANGED'):
        cm.verify_technical_predecessor({'path':str(path),'sha256':cm.sha(path)})

def test_selected_absolute_rtk_python_powershell_quote_disposable_only(context,tmp_path):
    # Synthetic fixture, never campaign CSV/report. Tests invocation and quoting, not model output.
    rtk=cm.pinned(context.amendment['prompt_revision']['rtk_binary'])
    python=cm.pinned(context.amendment['prompt_revision']['python_binary'])
    source=tmp_path/'synthetic numbers.csv';output=tmp_path/'synthetic report.json'
    source.write_bytes(b'value\n3\n8\n')
    code=("import csv,hashlib,json,pathlib; p=pathlib.Path("+repr(str(source))+"); "
          "rows=list(csv.DictReader(p.read_text().splitlines())); "
          "pathlib.Path("+repr(str(output))+").write_text(json.dumps(dict(row_count=len(rows),sum=sum(int(r['value']) for r in rows),input_sha256=hashlib.sha256(p.read_bytes()).hexdigest())))")
    def quote(value):return "'"+str(value).replace("'","''")+"'"
    script=tmp_path/'invoke-fixture.ps1'
    script.write_text('& '+quote(rtk)+' proxy '+quote(python)+' -B -I -X utf8 -c '+quote(code)+'\n',encoding='utf-8')
    result=subprocess.run(['C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe','-NoLogo','-NoProfile','-NonInteractive','-File',str(script)],capture_output=True,timeout=30)
    assert result.returncode==0,(result.returncode,result.stderr.decode(errors='replace'))
    assert json.loads(output.read_bytes())=={'row_count':2,'sum':11,'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    assert not Path(context.P['finite_work']['delivery']['local_output']).exists()
    evidence={'status':'DISPOSABLE_POWERSHELL_ABSOLUTE_RTK_PYTHON_QUOTE_PASS','fixture_only':True,
      'campaign_input_read':False,'campaign_report_generated':False,'provider_calls':0,
      'rtk':context.amendment['prompt_revision']['rtk_binary'],'python':context.amendment['prompt_revision']['python_binary'],
      'invocation_form':'PowerShell direct &: pinned RTK proxy pinned Python -c single-line argument; no nested PowerShell or PATH lookup',
      'returncode':result.returncode,'synthetic_source_sha256':cm.sha(source),'synthetic_report_sha256':cm.sha(output),
      'script_sha256':cm.sha(script),'script_path':str(script),'elapsed_limit_seconds':30}
    (W/'checks/quote-qualification.json').write_text(json.dumps(evidence,indent=2)+'\n')
