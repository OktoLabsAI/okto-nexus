from pathlib import Path
import hashlib,json,subprocess,time
S=Path(__file__).resolve().parent;B=S.parent;D=S/'draft';Q=S/'affected-001';Q.mkdir()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
sources={str(f):sha(f) for f in [*D.glob('*.py'),*(D/'controller').glob('*.py'),S/'test_control_adoption.py']}
env=json.loads((B/'draft/installation/environment.json').read_bytes());env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
code='''import sys
from pathlib import Path
D=Path(sys.argv[1]);Q=Path(sys.argv[2]);S=D.parent
sys.path[:0]=[str(D/'controller'),str(D)]
import okto_nexus,nexus_connector_core,pytest
assert Path(okto_nexus.__file__).is_relative_to(Path(sys.prefix))
assert Path(nexus_connector_core.__file__).is_relative_to(Path(sys.prefix))
tests=[str(D/'controller'/name) for name in ('test_v11_allocation.py','test_v14_delta.py','test_cli_flow.py','test_work_wrapper.py')]
tests += [str(D/'controller/test_independent.py')+'::'+name for name in ('test_deadline_tick_does_not_wait_for_blocked_http_and_cannot_replay','test_effect_boundary_checks_deadline_without_owner_tick','test_adopted_setup_ignored_across_local_continuation_reopen_remote_work')]
tests += [str(S/'test_control_adoption.py')]
raise SystemExit(pytest.main(['-q','-p','no:cacheprovider',*tests,'--basetemp',str(Q/'pytest-tmp'),'--junitxml',str(Q/'results.xml')]))
'''
started=time.monotonic()
with (Q/'stdout.txt').open('xb') as out,(Q/'stderr.txt').open('xb') as err:
    p=subprocess.Popen([str(B/'draft/installation/venv/Scripts/python.exe'),'-I','-B','-X','utf8','-c',code,str(D),str(Q)],cwd=Q,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    rc=p.wait()
proof={'exit_code':rc,'duration_seconds':time.monotonic()-started,'sources_before':sources,'sources_unchanged':all(sha(k)==v for k,v in sources.items()),'scope':'Affected v14 delta: carry9/134199/new4/max13/deadline600, real installed CLI new-session from retained predecessor, exact3decision/lane transport/recovery, immutable adoption and whole four-work wrapper. Synthetic effects only; allocation reader clocks deterministic, nominal other clocks real.'}
(Q/'result.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({k:v for k,v in proof.items() if k!='sources_before'}));raise SystemExit(rc)
