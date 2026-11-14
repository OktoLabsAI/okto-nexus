from pathlib import Path
import hashlib,json,subprocess,time
S=Path(__file__).resolve().parent;B=S.parent;D=S/'draft';Q=S/'threshold-delta';Q.mkdir()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
sources={str(p):sha(p) for p in (D/'controller').glob('*.py')}
tests=[str(D/'controller/test_v11_allocation.py'),str(D/'controller/test_independent.py')+'::test_threshold_and_late_post_fence_share_one_normal_stop',str(D/'controller/test_observation_budget.py')+'::test_usage_fences_effects_before_durable_io',str(D/'controller/test_observation_budget.py')+'::test_worker_post_checks_new_clock_after_get_io',str(D/'controller/test_work_wrapper.py')+'::test_whole_work_wrapper_local_continuation_remote_lost_response_and_continuation']
code='import sys;sys.path[:0]=[sys.argv[1],sys.argv[2]];import pytest;raise SystemExit(pytest.main(sys.argv[3:]))'
env=json.loads((B/'draft/installation/environment.json').read_bytes());env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
started=time.monotonic()
with (Q/'stdout.txt').open('xb') as out,(Q/'stderr.txt').open('xb') as err:
    child=subprocess.Popen([str(B/'draft/installation/venv/Scripts/python.exe'),'-I','-B','-X','utf8','-c',code,str(D/'controller'),str(D),'-q','-p','no:cacheprovider',*tests,'--basetemp',str(Q/'pytest-tmp'),'--junitxml',str(Q/'results.xml')],cwd=Q,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    rc=child.wait()
proof={'exit_code':rc,'duration_seconds':time.monotonic()-started,'source_before':sources,'sources_unchanged':all(sha(k)==v for k,v in sources.items()),'scope':'Focused delta preventive500000/tolerance700000, carry8/111651/new4/cumulative12; actual thresholds, before-persist fence, post-GET clock and full four-work synthetic wrapper. No provider/service/install/credentials.'}
(Q/'result.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8',newline='\n');print(json.dumps({k:v for k,v in proof.items() if k!='source_before'}));raise SystemExit(rc)
