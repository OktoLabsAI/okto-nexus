"""Prepare a second compatibility derivative while repository CI inputs freeze."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ROOT = Path(tempfile.mkdtemp(prefix='nexus-qc-legacy-gate-')).resolve()
PREFIX = Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-0s9w2_3_/venv')
shutil.copytree(PREFIX / 'Lib/site-packages/okto_nexus', ROOT / 'overlay/okto_nexus',
    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
path = ROOT / 'overlay/okto_nexus/adapters/inbound/cli/connect.py'
before = path.read_text(encoding='utf-8')
needle = 'def _run_connect_once(argv, *, invocation_cwd=None, frozen_name=None):'
helper = '''def _quick_entry_requested(args):
    # Public syntax opts in explicitly. Legacy selectors keep their old flow;
    # a retained Quick checkpoint is handled after the exact profile is read.
    if args.harness or args.project_name or args.connect_id:
        return True
    legacy = ('profile', 'project', 'client', 'agent', 'new_agent', 'name',
        'workspace_id', 'binding_id', 'candidate_ref', 'provider_home',
        'operator_profile', 'remote_draft', 'setup_receipt_output', 'approve')
    return not (any(getattr(args, key, None) is not None for key in legacy)
        or args.new_connection or args.review_current)


'''
assert needle in before
after = before.replace(needle, helper + needle).replace(
    'enabled and bool(args.harness or args.project_name or args.connect_id or not args.profile)',
    'enabled and _quick_entry_requested(args)')
assert after != before
path.write_text(after, encoding='utf-8', newline='\n')
(ROOT / 'changes.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
    fromfile='a/src/okto_nexus/adapters/inbound/cli/connect.py',
    tofile='b/src/okto_nexus/adapters/inbound/cli/connect.py')), encoding='utf-8')
index = {}
for directory in (REPO / 'tests/execution_r4', REPO / 'tests'):
    for item in sorted(directory.glob('*.py')):
        index.setdefault(item.stem, item)
selected = set()
queue = [index[name] for name in ('test_connection_catalog', 'test_terminal_multi_harness')]
queue.extend((REPO / 'tests/conftest.py', REPO / 'tests/execution_r4/conftest.py'))
while queue:
    item = queue.pop()
    if item in selected:
        continue
    selected.add(item)
    for node in ast.walk(ast.parse(item.read_text(encoding='utf-8-sig'))):
        names = [v.name.split('.')[0] for v in node.names] if isinstance(node, ast.Import) else (
            [node.module.split('.')[0]] if isinstance(node, ast.ImportFrom) and node.module else [])
        queue.extend(index[name] for name in names if name in index and index[name] not in selected)
selected.update((REPO / 'tests/legacy_native_fixture').rglob('*.py'))
selected.update((REPO / 'plans/contratos').glob('*.json'))
pins = {}
for item in selected:
    relative = item.relative_to(REPO)
    pins[relative.as_posix()] = hashlib.sha256(item.read_bytes()).hexdigest()
    target = ROOT / 'after' / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(item, target)
(ROOT / 'source-pins.json').write_text(json.dumps(pins, indent=2), encoding='utf-8')
(ROOT / 'pytest.ini').write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n'
    'pythonpath=after/tests after/tests/execution_r4\n', encoding='utf-8')
(HERE / 'gate-allocation.json').write_text(json.dumps(dict(root=str(ROOT)), indent=2), encoding='utf-8')
test = '''import json
from types import SimpleNamespace
import pytest
from okto_nexus.adapters.inbound.cli.connect_arguments import parse_connect_args
from okto_nexus.adapters.inbound.cli import connect, quick_connect_selection
from okto_nexus.application.terminal_connection import ConnectionError

@pytest.mark.parametrize('flags', [[], ['--plan'], ['--json'], ['--no-chat'],
    ['--timeout','12'], ['--start-at-login'], ['codex'], ['codex','Project'],
    ['--id','reviewer'], ['codex','--project','C:/owned'], ['codex','--client','codex'],
    ['--id','reviewer','--profile','existing']])
def test_public_entry(flags):
    args, _ = parse_connect_args(flags)
    assert connect._quick_entry_requested(args) is True

@pytest.mark.parametrize('flags', [['--profile','existing'], ['--project','C:/owned'],
    ['--client','codex'], ['--agent','a'], ['--new-agent','b'], ['--name','Named'],
    ['--workspace-id','w'], ['--binding-id','b'], ['--candidate-ref','c'],
    ['--provider-home','C:/owned'], ['--operator-profile','remote'],
    ['--remote-draft','C:/owned'], ['--setup-receipt-output','C:/owned'],
    ['--approve','revision'], ['--new-connection'], ['--review-current']])
def test_legacy_selectors(flags):
    args, _ = parse_connect_args(flags)
    assert connect._quick_entry_requested(args) is False

@pytest.mark.parametrize('flags,checkpoint', [([],False),(['codex'],False),
    (['--id','reviewer'],False),(['--profile','retained'],True)])
def test_quick_route_and_saved_checkpoint_reach_prepare(tmp_path, monkeypatch, capsys, flags, checkpoint):
    home = tmp_path/'home'
    if checkpoint:
        target=home/'terminal/profiles/retained.json'
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({'selection':{'quick_connect':{'version':1}}}))
    service=SimpleNamespace(adapter=SimpleNamespace(home=home,host='127.0.0.1',port=1),
        ensure_running=lambda **kwargs: {'state':'ready'}, inspect=lambda: {'state':'ready'})
    monkeypatch.setattr(connect,'resolve_local_service',lambda args:service)
    monkeypatch.setattr(connect.sys,'stdin',SimpleNamespace(isatty=lambda:False))
    calls=[]
    def prepare(*args,**kwargs):
        calls.append(kwargs.get('saved'))
        raise ConnectionError('QUICK_ROUTE_SENTINEL','No HTTP, provider or setup effects')
    monkeypatch.setattr(quick_connect_selection,'prepare',prepare)
    assert connect.run_connect([*flags,'--home',str(home),'--json','--plan'])==3
    assert len(calls)==1
    assert 'QUICK_ROUTE_SENTINEL' in capsys.readouterr().out
    assert bool(calls[0]) is checkpoint
'''
(ROOT / 'after/tests/test_gate_derivative.py').write_text(test, encoding='utf-8')
runner = (HERE / 'run_derivative.py').read_text(encoding='utf-8')
runner = runner.replace("HERE/'derivative-allocation.json'", "HERE/'gate-allocation.json'")
runner = runner.replace("assert all(pathlib.Path(value).resolve().is_relative_to(PREFIX) for value in origins.values()),origins",
    "assert pathlib.Path(origins['okto_nexus']).resolve().is_relative_to(ROOT/'overlay'),origins\n    assert all(pathlib.Path(value).resolve().is_relative_to(PREFIX) for name,value in origins.items() if name!='okto_nexus'),origins")
start = runner.index("nodes=[('mutable-feature'")
end = runner.index('\nfor label,node in nodes:', start)
runner = runner[:start] + "nodes=" + repr([
    ('gate-matrix', 'tests/test_gate_derivative.py'),
    ('canonical-shortcut', 'tests/execution_r4/test_connection_catalog.py::test_cli_existing_canonical_without_profile_creates_only_shortcut'),
    ('single-harness', 'tests/execution_r4/test_terminal_multi_harness.py::test_single_observed_harness_needs_no_profile_and_existing_connection_offers_all_intents'),
    ('two-harnesses', 'tests/execution_r4/test_terminal_multi_harness.py::test_two_distinct_harnesses_share_project_keep_custom_a_and_recover_b_finish')]) + runner[end:]
runner = runner.replace("'-I','-B','-m','pytest'", "'-I','-B','-c',\"import sys,runpy;sys.path.insert(0,\"+repr(str(root/'overlay'))+\");runpy.run_module('pytest',run_name='__main__')\"")
(HERE / 'run_gate.py').write_text(runner, encoding='utf-8')
print(json.dumps(dict(root=str(ROOT), copied_test_files=len(pins))))
