"""PREPARED installed J01/J02 owner; never install or alter product/source."""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
CASES = ('test_j01_exact_units_dedup_shared_work_and_page_independence',
    'test_j02_actual_sqlite_operations_reader_failure_keeps_other_positives')
PLUGIN = '''import importlib,json,pathlib,sys
import pytest
PREFIX=pathlib.Path(EXPECTED_PREFIX).resolve()
OUT=pathlib.Path(OUTPUT)
def origins(stage):
    names=('okto_nexus','nexus_connector_core','okto_nexus_connector')
    values={n:importlib.import_module(n).__file__ for n in names}
    assert all(pathlib.Path(v).resolve().is_relative_to(PREFIX) for v in values.values())
    loaded={n:getattr(m,'__file__',None) for n,m in list(sys.modules.items()) if any(n==p or n.startswith(p+'.') for p in names)}
    assert all(not p or pathlib.Path(p).resolve().is_relative_to(PREFIX) for p in loaded.values())
    (OUT/('origins-'+stage+'.json')).write_text(json.dumps(dict(origins=values,loaded=loaded,isolated=sys.flags.isolated,dont_write_bytecode=sys.dont_write_bytecode,stdin_isatty=sys.stdin.isatty()),indent=2))
def pytest_sessionstart(session):origins('start')
def pytest_sessionfinish(session,exitstatus):origins('end')
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item,call):
    report=(yield).get_result()
    value=dict(node=report.nodeid,phase=report.when,outcome=report.outcome)
    if report.failed:value['longrepr']=report.longreprtext
    with (OUT/'phases.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(value)+'\\n')
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save(path, value):
    assert not path.exists()
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def guards(manifest):
    for mapping in (manifest['source_pins'], manifest['helper_sha256']):
        assert all(sha(Path(path)) == expected for path, expected in mapping.items())
    ready = json.loads(Path(manifest['ready']).read_text(encoding='utf-8'))
    assert sha(Path(manifest['ready'])) == manifest['ready_sha256']
    assert ready['source_commit'] == manifest['source_commit']
    assert sha(Path(ready['wheel'])) == ready['wheel_sha256'] == manifest['wheel_sha256']
    site = Path(ready['python']).parent.parent / 'Lib/site-packages'
    assert len(manifest['payload_files']) == ready['payload_files'] == 1031
    assert all(sha(site / name) == expected for name, expected in manifest['payload_files'].items())
    return {'source_count': len(manifest['source_pins']), 'payload_files': 1031, 'drift': []}


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--gate', choices=['ROOT_APPROVED_COUNTS_COVERAGE_R9'], required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--case', choices=['all', '1', '2'], default='all')
    args = parser.parse_args()
    path = HERE / 'PREPARED.json'
    assert sha(path) == args.manifest_sha256
    manifest = json.loads(path.read_text(encoding='utf-8'))
    before = guards(manifest)  # No allocation/process/product import until gate.
    ready = json.loads(Path(manifest['ready']).read_text())
    root = Path(tempfile.mkdtemp(prefix='nexus-hst-counts-coverage-r9-')).resolve()
    for name in ('cwd', 'tmp', 'user', 'roaming', 'local', 'guard', 'reports'):
        (root / name).mkdir()
    tree = root / 'tree'
    shutil.copytree(REPO / 'tests', tree / 'tests', ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
    shutil.copytree(REPO / 'plans', tree / 'plans')
    assert not (tree / 'src').exists()
    for source, destination in manifest['copy_helpers'].items():
        target = tree / destination
        assert not target.exists()
        shutil.copyfile(source, target)
    copied = {str(path.relative_to(tree)): sha(path) for path in tree.rglob('*') if path.is_file()}
    helper = load('hst_count_owned_commands', Path(manifest['command_helper']))
    environment = load('hst_count_own_environment', Path(manifest['environment_helper']))
    env = environment.environment(root)
    env.update(PATH=os.pathsep.join((str(Path(ready['python']).parent), 'C:/Windows/System32', 'C:/Windows')),
        HOME=str(root / 'user'), USERPROFILE=str(root / 'user'), APPDATA=str(root / 'roaming'), LOCALAPPDATA=str(root / 'local'),
        TMP=str(root / 'tmp'), TEMP=str(root / 'tmp'), CODEX_HOME=str(root / 'nonexistent-codex'), CLAUDE_CONFIG_DIR=str(root / 'nonexistent-claude'))
    ini = root / 'pytest.ini'
    ini.write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n', encoding='utf-8')
    paths = [str(root / 'guard'), str(tree), str(tree / 'tests'),
        *[str(path) for path in sorted((tree / 'tests').rglob('*')) if path.is_dir() and any(path.glob('*.py'))]]
    selected = list(enumerate(CASES, 1)) if args.case == 'all' else [(int(args.case), CASES[int(args.case) - 1])]
    outputs, failure = [], None
    try:
        for number, node in selected:
            output = root / 'reports' / str(number)
            output.mkdir()
            plugin = 'OUTPUT=' + repr(str(output)) + '\nEXPECTED_PREFIX=' + repr(str(Path(ready['python']).parent.parent)) + '\n' + PLUGIN
            (root / 'guard/hst_counts_origins.py').write_text(plugin, encoding='utf-8')
            pytest_args = ['-p', 'hst_counts_origins', '-p', 'no:cacheprovider', '-c', str(ini), '--rootdir=' + str(tree),
                '--confcutdir=' + str(tree), str(tree / 'tests/execution_r4/test_counts_coverage_r9.py') + '::' + node,
                '-v', '--tb=short', '-x', '--junitxml=' + str(output / 'tests.xml')]
            code = 'import sys;sys.path[:0]=' + repr(paths) + ';import pytest;raise SystemExit(pytest.main(' + repr(pytest_args) + '))'
            command = [ready['python'], '-I', '-B', '-X', 'utf8', '-c', code]
            print(json.dumps({'phase': 'START', 'case': node}), flush=True)
            with (output / 'pytest.private.log').open('w', encoding='utf-8') as log:
                outcome = helper.run_owned(command, root=root, cwd=root / 'cwd', env=env, log=log, timeout=180, allow_canonical=False)
            outputs.append({'node': node, 'outcome': outcome})
            save(output / 'owned-command.json', outcome)
            print(json.dumps(outputs[-1]), flush=True)
            assert outcome['success'] and not outcome['remaining_known_processes'] and not outcome['remaining_listeners'], 'First error stops without retry'
    except BaseException as error:  # noqa: BLE001 -- retain failed cut and finally guards.
        failure = {'type': type(error).__name__, 'message': str(error)}
    finally:
        after = guards(manifest)
        copied_after = {name: sha(tree / name) for name in copied}
        assert copied_after == copied, 'Copied test/helper bytes changed'
        save(root / 'final.json', {'failure': failure, 'before': before, 'after': after, 'results': outputs,
            'copied_helpers_drift': [], 'not_run': [node for _, node in selected[len(outputs):]], 'root': str(root),
            'provider_invocations': 0, 'latencies_collected': False})
        print(json.dumps({'root': str(root), 'failure': failure, 'completed': len(outputs), 'guards': after}), flush=True)
    return int(bool(failure))


if __name__ == '__main__':
    raise SystemExit(main())
