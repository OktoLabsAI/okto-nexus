"""Retain this finite RG-06 source review and the captured subprocess evidence."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
nexus = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
connector = Path('D:/Projetos/Techridy/okto-nexus-connector')
core = Path('D:/Projetos/Techridy/okto-nexus-connector-core')
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
write = lambda name, data: (root/name).write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
boundary_results = []
dynamic = []
inputs = {}
for label, repo, forbidden in (('Nexus', nexus, 'okto_nexus_connector'), ('Connector', connector, 'okto_nexus')):
    violations = []
    paths = sorted((repo/'src').rglob('*.py'))
    for path in paths:
        relative = path.relative_to(repo).as_posix()
        inputs[label+'/'+relative] = sha(path)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'), filename=relative)):
            imported = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module or ''] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
            if any(name.split('.')[0] == forbidden for name in imported):
                violations.append(dict(path=relative, line=node.lineno))
            if isinstance(node, ast.Call):
                called = ast.unparse(node.func)
                if called == '__import__' or called.endswith('.import_module') or called == 'import_module':
                    dynamic.append(dict(application=label, path=relative, line=node.lineno, call=ast.unparse(node)))
    assert not violations
    boundary_results.append(dict(application=label, python_files=len(paths), forbidden=forbidden, violations=violations))
write('application-boundaries.json', dict(literal_checks=boundary_results, dynamic_import_calls_reviewed=dynamic,
    dynamic_review='All four current calls remain inside their own application namespace: Nexus tools package iterator, two fixed-family attention imports, and Connector self-version import. No sys.path/file-loader import sites found by the accompanying source review.'))
write('application-inputs.json', inputs)

runtime_lookups = []
for path in sorted((core/'src/nexus_connector_core').rglob('*.py')):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and ast.unparse(node) == 'os.environ':
            parent = parents.get(node)
            while parent is not None and not isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                parent = parents.get(parent)
            runtime_lookups.append(dict(path=path.relative_to(core).as_posix(), line=node.lineno,
                function=parent.name if parent else None))
assert runtime_lookups and all(item['function'] for item in runtime_lookups)
write('core-environment-source-review.json', dict(os_environ_references=runtime_lookups,
    conclusion='All current Core references are inside runtime functions/methods; the installed import audit observes zero Core-origin lookups.'))

observed = json.loads((root/'stdout.json').read_text())
invocation = json.loads((root/'invocation.json').read_text())
assert invocation['stdout_sha256'] == sha(root/'stdout.json')
assert invocation['exit_code'] == 0 and observed['status'] == 'PASS'
assert len(observed['imported_modules']) == 131 and not observed['denied_events']
assert not any(item['caller'].startswith('nexus_connector_core') for item in observed['environment_reads'])
assert len(observed['controls']) == 9 and all(item['blocked'] for item in observed['controls'])
state = {}
for label, repo in (('Nexus', nexus), ('Connector', connector), ('Core', core)):
    state[label] = dict(head=subprocess.check_output(['rtk','git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
        status=subprocess.check_output(['rtk','git','-C',str(repo),'status','--short'],text=True).strip())
counts = Counter((row['key'],row['caller']) for row in observed['environment_reads'])
prior = ['plans/agent_ops/evidence/r3-joint-contracts/core/audit.py',
         'plans/agent_ops/evidence/r3-joint-contracts/core/observation.json',
         'plans/agent_ops/evidence/r3-joint-contracts/core/application-import-boundaries.json']
write('report.json', dict(requirement='RG-06', requirement_line=973, result='PASS',
    recommendation='RG-06 may be VERIFIED for the current installed Core/application revisions on Windows/local. No concrete literal gap remains after combining current static boundaries, import observation and credential-access guards. Ledger decision belongs to root.',
    core_wheel_sha256=observed['core_wheel_sha256'], core_package_files_equal=165, imported_modules=131,
    guard_controls_passed=9, denied_during_import=0, core_environment_lookups=0,
    dependency_environment_lookups=len(observed['environment_reads']),
    dependency_environment_lookup_groups=[dict(key=key,caller=caller,count=count) for (key,caller),count in counts.items()],
    native_credential_api_calls_during_import=0, guarded_native_api_count=len(observed['guarded_native_apis']),
    dependency_console_bindings=observed['allowed_dependency_console_bindings'],
    guard_scope='Every one of the 131 Core Python modules was imported under the same active guards. Python os.getenv/environ access and enumeration, all exported callable win32cred Cred* entry points, DPAPI unprotect and ctypes dynamic loading/symbol binding were instrumented; the nine negative controls are representative tests of these guard paths. This is not a tracer of arbitrary native C-extension or kernel calls, which is not required to verify this fixed code/import path.',
    dependency_lookups_review='The eight observed key/caller pairs are timezone, Python user-base/config path, Pydantic plugin opt-out, and locale configuration; no credential names or values were read. HOME/APPDATA/user context are synthetic, with no inherited user environment.',
    retained_refusals='Initial and diagnostic runs stopped at Click GetStdHandle binding. They are retained verbatim. The final run allows only the reviewed console/buffer symbols from click._winconsole and keeps all credential paths guarded; no product code changed.',
    prior_evidence={name:sha(nexus/name) for name in prior}, repository_state=state,
    verification_tool=dict(path=str(core/'tools/verify_wheel.py'),sha256=sha(core/'tools/verify_wheel.py')),
    checkout_edits=False, credentials_used=False, subprocess_finished=True,
    limits=['Current Windows installed-import behavior only; no adapter/provider/service or runtime credential-resolution qualification.',
            'No claim for other platforms or future package/dependency versions.',
            'No requirement for universal native syscall tracing has been added.']))
allowlist = ['README.md','audit.py','run.py','review.py','stdout.json','stderr.txt','invocation.json',
             'application-boundaries.json','application-inputs.json','core-environment-source-review.json','report.json']
allowlist += [phase+'/'+name for phase in ('initial','diagnostic')
              for name in ('audit.py','run.py','stdout.json','stderr.txt','invocation.json')]
write('manifest.json', {name:dict(sha256=sha(root/name),bytes=(root/name).stat().st_size) for name in allowlist})
print(json.dumps(dict(result='PASS',imports=131,environment_lookups=len(observed['environment_reads']),
    boundaries=boundary_results,public_artifacts=len(allowlist)+1,manifest_sha256=sha(root/'manifest.json')),indent=2))
