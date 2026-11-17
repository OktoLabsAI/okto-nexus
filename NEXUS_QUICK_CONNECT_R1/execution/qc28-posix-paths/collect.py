"""Copy already-completed Linux evidence to the repository execution folder."""
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path('/tmp/nexus-qc28-xmlie7rv')
HERE = Path('/mnt/d/Projetos/Techridy/okto_labs_okto_nexus/NEXUS_QUICK_CONNECT_R1/execution/qc28-posix-paths')
REPO = HERE.parents[2]
assert sys.flags.isolated and sys.dont_write_bytecode and Path(sys.prefix) == ROOT / 'venv'
result = json.loads((ROOT / 'result.json').read_text())
assert all(r['exit_code'] == 0 and not r['remaining_process_group'] for r in result['cases'])
prefix = Path(sys.prefix).resolve()
origins = {name: str(Path(importlib.import_module(name).__file__).resolve()) for name in
           ('okto_nexus', 'nexus_connector_core', 'okto_nexus_connector')}
assert all(Path(path).is_relative_to(prefix) for path in origins.values())
out = HERE / 'evidence'
out.mkdir(exist_ok=True)
for path in ROOT.iterdir():
    if path.is_file() and path.suffix in ('.json', '.log'):
        shutil.copyfile(path, out / path.name)
shutil.copytree(ROOT / 'test-output', out / 'test-output', dirs_exist_ok=True)
copies = out / 'copied-tests'
copies.mkdir(exist_ok=True)
for path in (ROOT / 'tests').glob('*.py'):
    shutil.copyfile(path, copies / (path.name + '.txt'))
shutil.copyfile(ROOT / 'pytest.ini', out / 'pytest.ini.txt')
counts = []
for run in result['cases']:
    label = Path(run['argv'][-1]).stem if False else next(Path(arg).stem for arg in run['argv'] if arg.endswith('.py'))
    folder = ROOT / 'test-output' / label
    suites = ET.parse(folder / 'junit.xml').getroot()
    nodes = list(suites.iter('testcase'))
    assert json.loads((folder / 'origins-finish.json').read_text())['bad'] == {}
    counts.append(dict(label=label, passed=sum(x.find('failure') is None and x.find('error') is None and x.find('skipped') is None for x in nodes),
        failed=sum(x.find('failure') is not None or x.find('error') is not None for x in nodes),
        skipped=sum(x.find('skipped') is not None for x in nodes)))
pins = json.loads((ROOT / 'copied-test-pins.json').read_text())
assert all(hashlib.sha256((REPO / name).read_bytes()).hexdigest() == pin for name, pin in pins.items())
sourcepins = json.loads((HERE.parent / 'qc11-package/evidence/source-pins-before.json').read_text())
source_drift = [name for name, pin in sourcepins.items() if hashlib.sha256((REPO / name).read_bytes()).hexdigest() != pin]
assert not source_drift, source_drift
fs = []
for path in (ROOT / 'test-tmp/test_posix_physical_paths').rglob('*'):
    if (path.name in ('Repo', 'repo', 'Physical', 'LogicalLink', 'leaf') or chr(92) in path.name) and path.is_dir():
        stat = path.stat()
        fs.append(dict(path=str(path), resolved=str(path.resolve()), symlink=path.is_symlink(), device=stat.st_dev, inode=stat.st_ino))
versions = {name: importlib.metadata.version(name) for name in ('okto-nexus', 'okto-nexus-connector-core', 'okto-nexus-connector')}
dependencies = {d.metadata['Name']: d.version for d in importlib.metadata.distributions()}
managed = Path(sys.executable).resolve()
env = dict(PATH='/usr/bin:/bin', HOME=str(ROOT / 'home'), XDG_CONFIG_HOME=str(ROOT / 'xdg-config'),
           GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_SYSTEM='/dev/null', GIT_CONFIG_GLOBAL='/dev/null')
git = subprocess.run(['/usr/bin/git', '--version'], cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
system = subprocess.run(['/usr/bin/python3', '-I', '-B', '-c', 'import sys;print(sys.version)'], cwd=ROOT, env=env,
                        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
report = dict(status='PASS_202_SELECTED_INSTALLED_POSIX_CASES', passed=sum(x['passed'] for x in counts),
    failed=sum(x['failed'] for x in counts), skipped=sum(x['skipped'] for x in counts), cuts=counts,
    source_candidate='fa031697b37a1b879d855f7858f01320addf0df7',
    wheel_pins=json.loads((ROOT / 'wheel-pins.json').read_text()),
    uv_release=json.loads((ROOT / 'uv-download.json').read_text()),
    environment=dict(OS=platform.platform(), distro=Path('/etc/os-release').read_text(), WSL=True, python=sys.version,
        executable=sys.executable, executable_resolved=str(managed), python_sha256=hashlib.sha256(managed.read_bytes()).hexdigest(),
        prefix=sys.prefix, origins=origins, versions=versions, dependencies=dependencies,
        system_python_observed_after=system.stdout.strip(), system_python_observed_before='3.10.12',
        git_version=git.stdout.strip(), scope='All tools/runtime/deps installed exclusively under own /tmp root.'),
    real_filesystem=fs, integrity=dict(payload_files=1027, payload_drift=[], source_files=len(sourcepins), source_drift=[],
        copied_test_pins=pins, no_src_copy=True),
    isolation=dict(env_allowlist=True, HOME_XDG_caches_tmp_owned=True, pytest_parent_python_flags=['-I', '-B'],
        stdin_pipe_closed=True, cwd_tmp_siblings=True, per_cut_deadline_seconds=180, own_process_groups=True,
        pytest_groups_remaining=[], service_started=False, provider_invocations=0, global_user_installs=False,
        apt_sudo_used=False, WSL_configuration_changed=False),
    antecedents=['First isolated /tmp directory disappeared between WSL invocations before any download/install. A finite own keeper then preserved the temporary guest window; no WSL configuration changed.',
        'Original uv-version oracle expected a trailing build annotation. Official binary prints uv 0.10.7 newline; failed before Python install. The continuation verifies exact version tokens and the already-verified binary SHA.'],
    limits=['Ubuntu22.04 under Windows WSL2, not a native Ubuntu host or full Linux CI/platform matrix.',
        'Selected parser/project/ID tests include fake authorized GET DTOs as declared by their existing source; they do not establish real Linux SQLite/HTTP authority or service execution.',
        'Three added POSIX cases use real /tmp filesystem and installed path/identity functions: case sensitivity, symlink resolution and literal backslash filename.',
        'Git tests use actual own local repositories plus explicit unit mocks for error/budget branches; no remote Git transport/account access.',
        'uv archive SHA is checked against the official release SHA256 over verified HTTPS; no separate artifact-attestation verification claim.',
        'Runtime/venv/cache are temporary and may disappear when WSL becomes idle. Curated evidence is copied to Windows before stopping the own keeper.',
        'Windows system/personal prefixes and Ubuntu system/user installation locations were not targeted.'])
assert report['passed'] == 202 and report['failed'] == report['skipped'] == 0
(HERE / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(dict(passed=report['passed'], failed=0, skipped=0, source_drift=[], real_fs_records=len(fs))))
