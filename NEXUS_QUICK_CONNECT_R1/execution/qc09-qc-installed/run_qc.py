"""Installed Quick Connect scope, strict main/child provenance and no providers."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / 'qc09-installed-01'))  # Own runner modules only, never src.
import engine  # noqa: E402
from run_shard import WHEEL, EXPECTED  # noqa: E402

SELECTED = ['tests/quick_connect', *['tests/execution_r4/' + name + '.py' for name in (
    'test_public_connection_ids', 'test_public_id_retirement', 'test_connection_catalog',
    'test_connection_workspaces', 'test_connection_setup', 'test_connection_setup_recovery',
    'test_terminal_connect', 'test_terminal_scripted_recovery', 'test_remote_operator_terminal')]]
AUDIT = '''
import hashlib,os,sys
SOURCE=SOURCE_VALUE
def qc_child_audit(event,args):
    if event!='subprocess.Popen':
        return
    executable,argv,cwd,env=args
    words=list(argv) if isinstance(argv,(list,tuple)) else [str(argv)]
    values=[str(v) for v in words]
    source=SOURCE.replace('\\\\','/').lower()
    candidate=' '.join(values).replace('\\\\','/').lower()
    path=(env or {}).get('PYTHONPATH','').replace('\\\\','/').lower()
    forbidden=source in candidate or source in path
    has_app=any('okto_nexus' in v for v in values)
    if has_app and ('sys.path.insert' in candidate or 'spec_from_file_location' in candidate):
        forbidden=True
    row=dict(executable=str(executable),cwd=str(cwd),argument_sha256=hashlib.sha256(repr(values).encode()).hexdigest(),
        app_child=has_app,checkout_source_forbidden=forbidden,environment_keys=sorted((env or {}).keys()))
    with (OUT/'child-audit.jsonl').open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(row)+'\\n')
    if forbidden:
        raise RuntimeError('QC installed child attempted a forbidden checkout application import')
sys.addaudithook(qc_child_audit)
'''


def main():
    index = int(sys.argv[1])
    assert index in (0, 1)
    spec = importlib.util.spec_from_file_location('qc_scope_ci', ROOT / 'tools/ci_installed.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    partitions = helper.partition_tests(SELECTED, 2)
    own = Path(tempfile.mkdtemp(prefix=f'nexus-qc09-qc-installed-{index}-'))
    before = helper.input_hashes()
    (own / 'input-before.json').write_text(json.dumps(before, indent=2)+'\n', encoding='utf-8')
    engine.PLUGIN += AUDIT.replace('SOURCE_VALUE', repr(str(ROOT / 'src')))
    ready = dict(shard=index, scope=SELECTED, selected_files=partitions[index], all_partitions=partitions,
        own_root=str(own), orchestrator_pid=os.getpid(), prefix=str(engine.PACKAGE / 'venv'),
        wheel=str(WHEEL), wheel_sha256=hashlib.sha256(WHEEL.read_bytes()).hexdigest(),
        excluded_helper='browser_public_ids_fixture.py is not a collected test module; no browser/service launch',
        child_policy='No checkout app child; own Git and pure synthetic Python peers allowed; no native provider/auth')
    (HERE / f'shard{index}-ready.json').write_text(json.dumps(ready, indent=2)+'\n', encoding='utf-8')
    assert ready['wheel_sha256'] == EXPECTED
    print(json.dumps(dict(shard=index, files=len(partitions[index]), own_root=str(own), orchestrator_pid=os.getpid())), flush=True)
    output, result = engine.execute(own / 'run', partitions[index])
    after = helper.input_hashes()
    changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
    (own / 'input-after.json').write_text(json.dumps(after, indent=2)+'\n', encoding='utf-8')
    report = dict(ready, result=result, output=str(output), changed_inputs=changed,
        status='INPUTS_CHANGED' if changed else 'INTERRUPTED' if result['phases'] else 'PASS' if result['exit_code']==0 else 'FAIL')
    (HERE / f'shard{index}-result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(shard=index, exit_code=result['exit_code'], changed_inputs=changed, status=report['status'], output=str(output))), flush=True)
    return result['exit_code'] or (2 if changed else 0)


if __name__ == '__main__':
    raise SystemExit(main())
