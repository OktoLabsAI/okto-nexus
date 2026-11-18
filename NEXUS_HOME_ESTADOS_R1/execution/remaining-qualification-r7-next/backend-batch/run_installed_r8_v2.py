"""Prepare-only until explicit Root gate; never install or mutate a prefix."""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
EXECUTION = HERE.parents[1]
PACKAGE = EXECUTION / 'package-hst-r8'
TEST = 'tests/execution_r4/test_backend_batch_r8.py'
CASES = [
    'test_shared_owner_bindings_keep_distinct_current_state',
    'test_hidden_productive_sibling_same_binding_prevents_false_full_block',
    'test_current_core_work_survives_external_unavailable_only',
    'test_explicit_nonblocking_input_keeps_working_and_one_independent_action',
    'test_idle_sibling_cannot_make_a_full_block_independent',
    'test_admitted_queued_sibling_has_no_independence_proof',
    'test_same_delivery_verification_three_files_seen_and_no_ack']

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
    outcome=yield
    report=outcome.get_result()
    value=dict(node=report.nodeid,phase=report.when,outcome=report.outcome)
    if report.failed:value['longrepr']=report.longreprtext
    with (OUT/'phases.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(value)+'\\n')
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--gate', required=True, choices=['ROOT_APPROVED_BACKEND_BATCH_R8'])
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--case', choices=['all', *[str(i) for i in range(1, 8)]], default='all')
    args = parser.parse_args()
    # No imports of product, allocations or process effects before the gate.
    ready = json.loads((PACKAGE / 'READY.json').read_text())
    assert ready['ready'] and ready['prefix_frozen'] and ready['source_commit'] == '6eaa325ea3ddf1dec1b03475b27f373211c81e53'
    assert ready['wheel_sha256'] == 'fc2afcccdf55236db21071a132a353a13cf1c56399767ea5223a69e50162902e'
    assert sha(Path(ready['wheel'])) == ready['wheel_sha256']
    manifest = HERE / 'PREPARED-r8-v2.json'
    assert sha(manifest) == args.manifest_sha256, 'Root gate manifest hash mismatch'
    gate = json.loads(manifest.read_text())
    assert gate['status'] == 'PREPARED_NOT_EXECUTED' and gate['expected_cases'] == 7
    assert gate['runtime_ready_sha256'] == sha(PACKAGE / 'READY.json')
    assert gate['runtime_source_commit'] == ready['source_commit']
    assert gate['runtime_wheel_sha256'] == ready['wheel_sha256']
    assert Path(gate['runtime_prefix']).resolve() == Path(ready['python']).parent.parent.resolve()
    assert gate['expected_payload_files'] == ready['payload_files'] == 1031
    for name, pin in gate['file_sha256'].items():
        assert sha(HERE / name) == pin, ('Prepared input changed', name)
    for name, pin in gate['external_sha256'].items():
        assert sha(Path(name)) == pin, ('Frozen helper/tooling input changed', name)
    reuse = json.loads((PACKAGE / 'runtime-equivalence-vs-r7.json').read_text())
    assert reuse['status'] == 'PASS_R7_R8_RUNTIME_BYTE_EQUIVALENCE'
    assert reuse['current_ready'] == ready
    assert reuse['python_version_equal'] and reuse['dependency_versions_equal']
    assert reuse['total_runtime_nonstatic_files'] == 1024
    owned_path = (PACKAGE / 'owned_commands.py').resolve()
    if 'owned_commands' not in sys.modules:
        sys.modules['owned_commands'] = load('owned_commands', owned_path)
    else:
        assert Path(sys.modules['owned_commands'].__file__).resolve() == owned_path
    builder = load('hst_batch_package_helpers', PACKAGE / 'package.py')
    package = Path(ready['root'])
    build = json.loads((package / 'build-manifest.json').read_text())
    expected = build['source_pins']
    assert len(expected) == gate['expected_base_pins'] == 1829
    source_before = builder.pins()
    assert all(source_before.get(name) == pin for name, pin in expected.items()), 'Frozen base input drift'
    prefix = Path(ready['python']).parent.parent
    wheels = [(Path(ready['wheel']), 'okto_nexus'),
        (REPO / 'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl', 'nexus_connector_core'),
        (REPO / 'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl', 'okto_nexus_connector')]
    def payload():
        values = {}
        for wheel, module in wheels:
            with zipfile.ZipFile(wheel) as archive:
                for name in archive.namelist():
                    if name.startswith(module + '/') and not name.endswith('/'):
                        data = (prefix / 'Lib/site-packages' / name).read_bytes()
                        assert data == archive.read(name), name
                        values[name] = hashlib.sha256(data).hexdigest()
        assert len(values) == 1031 == ready['payload_files']
        return values
    payload_before = payload()
    old_site = Path(reuse['baseline_ready']['python']).parent.parent / 'Lib/site-packages'
    nonstatic = [name for name in payload_before if not name.startswith('okto_nexus/adapters/inbound/http/static/')]
    assert len(nonstatic) == 1024
    for name in nonstatic:
        assert (old_site / name).read_bytes() == (prefix / 'Lib/site-packages' / name).read_bytes(), name
    root = Path(tempfile.mkdtemp(prefix='nexus-hst-backend-batch-r8-')).resolve()
    for name in ('cwd', 'tmp', 'user', 'roaming', 'local', 'reports', 'guard', 'tooling', 'ui'):
        (root / name).mkdir()
    tree = root / 'tree'
    shutil.copytree(REPO / 'tests', tree / 'tests', ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
    shutil.copytree(REPO / 'plans', tree / 'plans')
    assert not (tree / 'src').exists()
    additions = {'test_backend_batch.py': TEST, 'canonical_owner.py': 'tests/execution_r4/backend_batch_owner.py',
        'protocol_fixture.py': 'tests/execution_r4/backend_batch_protocol.py',
        'peer_source.py': 'tests/execution_r4/backend_batch_peer_source.py',
        'results_case.py': 'tests/execution_r4/backend_batch_results.py'}
    for source, target in additions.items():
        path = tree / target
        assert not path.exists(), ('Refuse helper overwrite', target)
        path.write_bytes((HERE / source).read_bytes())
    for name in ('homeStatePresentation.ts', 'homeStateContracts.ts'):
        shutil.copyfile(REPO / 'frontend/src' / name, root / 'ui' / name)
    tooling = REPO / 'frontend/node_modules/typescript/lib/typescript.js'
    shutil.copyfile(tooling, root / 'tooling/typescript.cjs')
    shutil.copyfile(HERE / 'presentation-check.mjs', root / 'presentation-check.mjs')
    save(root / 'presentation-config.json', {'typescript': str(root / 'tooling/typescript.cjs'), 'ui_source': str(root / 'ui')})
    presentation_paths = [root / 'presentation-check.mjs', root / 'tooling/typescript.cjs',
        root / 'ui/homeStatePresentation.ts', root / 'ui/homeStateContracts.ts', root / 'presentation-config.json']
    presentation_before = {str(path): sha(path) for path in presentation_paths}
    external_before = dict(gate['external_sha256'])
    closure_before = {str(HERE / name): pin for name, pin in gate['file_sha256'].items()}
    save(root / 'inputs-before.json', {'source': source_before, 'payload': payload_before,
        'additions': {name: sha(tree / target) for name, target in additions.items()},
        'presentation': presentation_before, 'external_helpers_and_tooling': external_before,
        'own_helper_closure': closure_before, 'r7_r8_nonstatic_bytes_equal': len(nonstatic)})
    copied = {str(path.relative_to(tree)): sha(path) for path in tree.rglob('*') if path.is_file()}
    owned = load('hst_batch_owned', PACKAGE.parent / 'package-hst-r3/owned_commands.py')
    env = builder.environment(root)
    env.update(PATH=os.pathsep.join((str(Path(ready['python']).parent), 'C:/Windows/System32', 'C:/Windows', 'C:/Program Files/nodejs')),
        HOME=str(root / 'user'), USERPROFILE=str(root / 'user'), APPDATA=str(root / 'roaming'), LOCALAPPDATA=str(root / 'local'),
        TMP=str(root / 'tmp'), TEMP=str(root / 'tmp'), HST_BACKEND_NODE='C:/Program Files/nodejs/node.exe',
        HST_BACKEND_PRESENTATION=str(root / 'presentation-check.mjs'), HST_BACKEND_PRESENTATION_CONFIG=str(root / 'presentation-config.json'))
    for name in ('CODEX_HOME', 'CLAUDE_CONFIG_DIR'):
        env[name] = str(root / ('nonexistent-' + name.lower()))
        assert not Path(env[name]).exists()
    ini = root / 'pytest.ini'
    ini.write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n', encoding='utf-8')
    helpers = [str(tree), str(tree / 'tests'), *[str(path) for path in sorted((tree / 'tests').rglob('*')) if path.is_dir() and any(path.glob('*.py'))]]
    selected = list(enumerate(CASES, 1)) if args.case == 'all' else [(int(args.case), CASES[int(args.case) - 1])]
    results = []
    print(json.dumps({'phase': 'PREPARED_OWN_COPY', 'root': str(root), 'selected': selected}), flush=True)
    try:
        for number, case in selected:
            output = root / 'reports' / str(number)
            output.mkdir()
            plugin = 'OUTPUT=' + repr(str(output)) + '\nEXPECTED_PREFIX=' + repr(str(prefix)) + '\n' + PLUGIN
            (root / 'guard/hst_backend_origin.py').write_text(plugin, encoding='utf-8')
            pytest_args = ['-p', 'hst_backend_origin', '-p', 'no:cacheprovider', '-c', str(ini), '--rootdir=' + str(tree),
                '--confcutdir=' + str(tree), str(tree / TEST) + '::' + case, '-v', '--tb=short', '-x',
                '--junitxml=' + str(output / 'tests.xml')]
            code = 'import sys;sys.path[:0]=' + repr([str(root / 'guard'), *helpers]) + ';import pytest;raise SystemExit(pytest.main(' + repr(pytest_args) + '))'
            command = [ready['python'], '-I', '-B', '-X', 'utf8', '-c', code]
            print(json.dumps({'phase': 'START', 'case': case, 'deadline_seconds': 180}), flush=True)
            with (output / 'pytest.log').open('w', encoding='utf-8') as log:
                result = owned.run_owned(command, root=root, cwd=root / 'cwd', env=env, log=log, timeout=180, allow_canonical=False)
            results.append({'case': case, 'owned_command': result})
            save(root / 'progress.json', results)
            print(json.dumps(results[-1]), flush=True)
            if not result['success']:
                break  # Preserve first failure/timeout; no automatic rerun or expectation edits.
    finally:
        source_after, payload_after = builder.pins(), payload()
        copied_after = {str(path.relative_to(tree)): sha(path) for path in tree.rglob('*') if path.is_file()}
        record = {'root': str(root), 'runtime_source': ready['source_commit'], 'wheel_sha256': ready['wheel_sha256'],
            'payload_files': len(payload_after), 'results': results,
            'not_run': [case for _, case in selected[len(results):]],
            'source_drift': [name for name in source_before.keys() | source_after.keys() if source_before.get(name) != source_after.get(name)],
            'payload_drift': [name for name in payload_before if payload_before[name] != payload_after[name]],
            'copied_drift': [name for name in copied.keys() | copied_after.keys() if copied.get(name) != copied_after.get(name)],
            'source_extra_inputs': [name for name in source_before if name not in expected],
            'presentation_drift': [name for name, pin in presentation_before.items() if sha(Path(name)) != pin],
            'external_helper_tooling_drift': [name for name, pin in external_before.items() if sha(Path(name)) != pin],
            'own_helper_closure_drift': [name for name, pin in closure_before.items() if sha(Path(name)) != pin],
            'r7_r8_nonstatic_drift': [name for name in nonstatic if (old_site / name).read_bytes() != (prefix / 'Lib/site-packages' / name).read_bytes()],
            'snapshot_scope': 'Six explicitly listed tables per test; not a whole-database read-only claim. Auth telemetry/real control renewal are separate.',
            'layer': 'Installed Python/Core/Connector; copied original fixtures + new tests; source-copy TypeScript presentation only; no provider/browser/latency qualification'}
        save(root / 'result.json', record)
        print(json.dumps({'phase': 'EXITED', 'root': str(root), **{key: record[key] for key in ('not_run', 'source_drift', 'payload_drift', 'copied_drift')}}), flush=True)
    raise SystemExit(0 if len(results) == len(selected) and all(row['owned_command']['success'] for row in results)
        and not any(record[key] for key in ('source_drift', 'payload_drift', 'copied_drift', 'presentation_drift',
            'external_helper_tooling_drift', 'own_helper_closure_drift', 'r7_r8_nonstatic_drift')) else 1)


if __name__ == '__main__':
    main()
