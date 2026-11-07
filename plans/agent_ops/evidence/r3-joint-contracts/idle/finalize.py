from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

root = Path(__file__).parent
checkout = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
relative = 'tests/execution_r4/test_external_idle_scheduler_isolation.py'
candidate = root/'snapshot'/relative
venv = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-ci-connector-refresh-la1tb1l6/venv')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
write = lambda p, data: p.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')

lines = candidate.read_text(encoding='utf-8').splitlines(keepends=True)
patch = 'diff --git a/'+relative+' b/'+relative+'\nnew file mode 100644\n--- /dev/null\n+++ b/'+relative+'\n@@ -0,0 +1,'+str(len(lines))+' @@\n'
patch += ''.join('+'+line for line in lines)
(root/'candidate.patch').write_text(patch, encoding='utf-8', newline='\n')
shutil.copy2(candidate, root/'candidate-final.py')

proof = json.loads((root/'source-wheel-proof.json').read_text())
with zipfile.ZipFile(proof['wheel']) as wheel:
    names = [name for name in wheel.namelist() if name.startswith('okto_nexus/') and not name.endswith('/')]
    source_mismatches = [name for name in names if wheel.read(name) != (checkout/'src'/name).read_bytes()]
    installed_mismatches = [name for name in names if wheel.read(name) != (venv/'Lib/site-packages'/name).read_bytes()]
assert not source_mismatches and not installed_mismatches
write(root/'final-package-proof.json', dict(package_files=len(names), source_mismatches=source_mismatches,
    installed_mismatches=installed_mismatches, wheel_sha256=proof['wheel_sha256']))
dependencies = {}
for artifact in json.loads((checkout/'vendor/ci/manifest.json').read_text())['artifacts']:
    dependency = checkout/artifact['path']
    assert sha(dependency) == artifact['sha256']
    with zipfile.ZipFile(dependency) as wheel:
        package_names = [name for name in wheel.namelist() if name.startswith(('nexus_connector_core/','okto_nexus_connector/')) and not name.endswith('/')]
        mismatches = [name for name in package_names if wheel.read(name) != (venv/'Lib/site-packages'/name).read_bytes()]
        assert package_names and not mismatches
        dependencies[dependency.name] = dict(sha256=sha(dependency),package_files=len(package_names),installed_mismatches=mismatches)
write(root/'dependency-package-proof.json', dependencies)

command = ['rtk', 'proxy', str(venv/'Scripts/python.exe'), '-I', '-c',
    "import json,sys,importlib.metadata as m,okto_nexus,nexus_connector_core,okto_nexus_connector; "
    "print(json.dumps(dict(executable=sys.executable,nexus=okto_nexus.__file__,core=nexus_connector_core.__file__,"
    "connector=okto_nexus_connector.__file__,versions={n:m.version(n) for n in ('okto-nexus','okto-nexus-connector',"
    "'okto-nexus-connector-core','mcp','pytest')})))"]
process = subprocess.run(command, capture_output=True, text=True, check=True, cwd=root)
write(root/'installed-modules.json', json.loads(process.stdout))

inputs = {p.relative_to(root/'snapshot').as_posix(): sha(p)
          for p in (root/'snapshot').rglob('*') if p.is_file() and p.suffix in ('.py', '.ini')}
write(root/'test-inputs.json', inputs)

tree = ET.parse(root/'rg03-qualified.xml')
cases = [dict(name=c.get('name'), passed=not any(c.find(t) is not None for t in ('failure','error','skipped')))
         for c in tree.iter('testcase')]
assert len(cases) == 6 and all(case['passed'] for case in cases)
retained = json.loads((root/'retained-evidence-map.json').read_text())
retained_files = sorted({item['path'] for item in retained})
write(root/'retained-evidence-hashes.json', {p: sha(checkout/p) for p in retained_files})

check = subprocess.run(['rtk', 'git', 'apply', '--check', str(root/'candidate.patch')],
    capture_output=True, text=True, cwd=checkout)
write(root/'patch-check.json', dict(exit_code=check.returncode, stdout=check.stdout, stderr=check.stderr))
assert check.returncode == 0
status = subprocess.run(['rtk', 'git', 'status', '--short'], capture_output=True, text=True, check=True, cwd=checkout)
write(root/'checkout-state.json', dict(head=subprocess.check_output(['rtk','git','rev-parse','HEAD'],
    cwd=checkout,text=True).strip(), status_short=status.stdout, candidate_applied=False))

write(root/'report.json', dict(requirement='RG-03', base_head=proof['base_head'], result='PASS',
    passed=6, failed=0, skipped=0, cases=cases, wheel_sha256=proof['wheel_sha256'],
    production_changes=False, checkout_changes=False, ledger_changes=False,
    initial_attempt=dict(passed=4,failed=1,cause='Candidate incorrectly required stable remaining_ms; Core TTL naturally decreased.'),
    scope=['HTTP TestClient', 'real migrated SQLite', 'installed Core and Nexus', 'synthetic native peers',
           'synthetic fixture credentials only', 'endpoint priority', 'one-shot FIFO', 'dispatch fairness',
           'auto-claim opt-in', 'creator audience', 'unconsumed claim reservation and no TTL renewal'],
    excludes=['personal credentials or vault', 'real provider', 'native user service', 'M1/M2', 'benchmark', 'automatic ledger promotion'],
    subprocesses_finished=True, proposal_path=relative, candidate_sha256=sha(candidate),
    patch_sha256=sha(root/'candidate.patch'), ruff_result='PASS', qualified_run='rg03-qualified.xml'))

allowlist = ['README.md','candidate.patch','candidate-initial.py','candidate-final.py','source-wheel-proof.json','final-package-proof.json',
    'dependency-package-proof.json',
    'installed-modules.json','test-inputs.json','retained-evidence-map.json','retained-evidence-hashes.json',
    'rg03-initial.log','rg03-initial.json','rg03-initial.xml','rg03-final.log','rg03-final.json','rg03-final.xml',
    'rg03-qualified.log','rg03-qualified.json','rg03-qualified.xml','ruff-initial.log','ruff-initial.json',
    'ruff-final.log','ruff-final.json','patch-check.json','checkout-state.json','report.json','run_redacted.py','finalize.py']
write(root/'manifest.json', {name: dict(sha256=sha(root/name),bytes=(root/name).stat().st_size) for name in allowlist})
(root/'public').mkdir(exist_ok=True)
for name in allowlist + ['manifest.json']:
    shutil.copy2(root/name, root/'public'/name)
sys.stdout.reconfigure(encoding='utf-8')
print(json.dumps(dict(root=str(root), tests=len(cases), patch_sha256=sha(root/'candidate.patch'),
    candidate_sha256=sha(candidate), manifest_sha256=sha(root/'manifest.json'),
    public_artifact_count=len(allowlist)+1, checkout_status=status.stdout),indent=2))
