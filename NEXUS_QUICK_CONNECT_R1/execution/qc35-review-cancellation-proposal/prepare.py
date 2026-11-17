"""Red installed cut first; optional one-module overlay is explicitly derived."""
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
derived='--derived' in sys.argv
root=Path(tempfile.mkdtemp(prefix='nexus-qc35-derived-' if derived else 'nexus-qc35-red-')).resolve()
previous=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc24-namespace-h8li_lxe')
shutil.copytree(previous/'after',root/'after',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copyfile(previous/'pytest.ini',root/'pytest.ini')
shutil.copyfile(HERE/'test_review_cancel.py',root/'after/tests/quick_connect/test_qc35_review_cancel.py')
pins={p.relative_to(REPO).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for directory in ('src','tests','docs') for p in (REPO/directory).rglob('*')
    if p.is_file() and '__pycache__' not in p.parts}
(root/'source-pins.json').write_text(json.dumps(pins,indent=2))
allocation='derived-allocation.json' if derived else 'allocation.json'
(HERE/allocation).write_text(json.dumps(dict(root=str(root)),indent=2))
runner=(HERE.parent/'qc24-namespace-scenarios/run.py').read_text()
runner=runner.replace("nodes=[('namespace','tests/execution_r4/test_qc24_namespace_http.py')]",
    "nodes=[('cancel','tests/quick_connect/test_qc35_review_cancel.py')]")
if derived:
    runner=runner.replace("HERE/'allocation.json'","HERE/'derived-allocation.json'")
    installed=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-t24_dnfc/venv/Lib/site-packages/okto_nexus/adapters/inbound/cli/connect.py')
    before=installed.read_text(encoding='utf-8')
    assert installed.read_bytes()==(REPO/'src/okto_nexus/adapters/inbound/cli/connect.py').read_bytes()
    old="""                if answer != 'y':
                    return 0
                approval = saved['review_revision']"""
    new="""                if answer != 'y':
                    _display(dict(state='canceled', lifecycle_requested=not args.plan,
                        canonical_metadata_revalidation_requested=True, effects_started=None), args.json)
                    return 0
                approval = saved['review_revision']"""
    assert before.count(old)==1
    after=before.replace(old,new)
    overlay=root/'overlay/connect.py'
    overlay.parent.mkdir()
    overlay.write_text(after,encoding='utf-8')
    (HERE/'connect-cancellation.patch').write_text(''.join(difflib.unified_diff(
        before.splitlines(True),after.splitlines(True),fromfile='a/src/okto_nexus/adapters/inbound/cli/connect.py',
        tofile='b/src/okto_nexus/adapters/inbound/cli/connect.py')),encoding='utf-8')
    shutil.copyfile(overlay,HERE/'derived-connect.py.txt')
    (HERE/'overlay-metadata.json').write_text(json.dumps(dict(module='okto_nexus.adapters.inbound.cli.connect',
        installed_source_sha256=hashlib.sha256(installed.read_bytes()).hexdigest(),
        overlay_sha256=hashlib.sha256(overlay.read_bytes()).hexdigest(),
        path=str(overlay),not_a_new_wheel=True),indent=2))
    loader="""
    import importlib.util,sys
    import okto_nexus.adapters.inbound.cli as cli_package
    path=pathlib.Path(%r)
    name='okto_nexus.adapters.inbound.cli.connect'
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    cli_package.connect=module
    (OUT/'overlay-origin.json').write_text(json.dumps(dict(module=name,path=str(path),sha256=__import__('hashlib').sha256(path.read_bytes()).hexdigest(),derived_not_wheel=True),indent=2))
""" % overlay.as_posix()
    runner=runner.replace('def pytest_sessionstart(session):\n','def pytest_sessionstart(session):\n'+loader)
    runner=runner.replace("and not pathlib.Path(module.__file__).resolve().is_relative_to(PREFIX)}",
        "and not pathlib.Path(module.__file__).resolve().is_relative_to(PREFIX) and not (name=='okto_nexus.adapters.inbound.cli.connect' and pathlib.Path(module.__file__).resolve()==pathlib.Path("+repr(overlay.as_posix())+"))}")
    choices=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc16-id-choices-final-lpx96e5q/after/tests/quick_connect/test_id_choice_scenarios.py')
    shutil.copyfile(choices,root/'after/tests/quick_connect/test_qc35_id_choice_antecedents.py')
    runner=runner.replace("nodes=[('cancel','tests/quick_connect/test_qc35_review_cancel.py')]",
        "nodes=[('cancel','tests/quick_connect/test_qc35_review_cancel.py'),('choices','tests/quick_connect/test_qc35_id_choice_antecedents.py'),('json-plan','tests/quick_connect/test_quick_connect_cli.py::test_real_http_plan_apply_and_recovery_preserve_public_id_without_test_or_grant_replay')]")
    runner=runner.replace("record=dict(label=label,argv=command", "if label=='choices':\n        command.extend(['-k','test_cancel_reports_lifecycle_and_metadata_without_false_no_effect_claim or test_explicit_resume_uses_actual_binding_family or test_json_cross_family_conflict_never_reads_stdin'])\n    record=dict(label=label,argv=command")
(HERE/('run_derived.py' if derived else 'run.py')).write_text(runner)
print(json.dumps(dict(root=str(root),derived=derived)))
