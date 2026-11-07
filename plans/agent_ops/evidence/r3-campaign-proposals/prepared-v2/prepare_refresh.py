"""Prepare a fresh candidate-only environment and two-task proposal. No services."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE / 'native'
SOURCE = Path('D:/Projetos/Techridy/okto_labs_okto_nexus/plans/agent_ops/evidence/r3-qualification-readiness/native-proposal')
OLD = Path('C:/Users/jpamb/AppData/Local/Temp/r3-windows-services-current-8uwywu7k')
BUILD = Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr')
PRODUCTS = {
    'okto_nexus': (BUILD / 'nexus-wheel-v1/okto_nexus-0.3.3-py3-none-any.whl', 'cd1653dbdb48031e6c04771889ecc3efa5de965973dfe29026436fe263b478ad'),
    'okto_nexus_connector': (BUILD / 'nexus-source-v1/vendor/ci/okto_nexus_connector-0.0.12-py3-none-any.whl', '73f1a3ba6daf1a4db6f98a9eaf7badaed0d32b151a30b4c0c6a0cf66c2eae1b5'),
    'nexus_connector_core': (BUILD / 'core-v2-wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl', '1407014ea12f7e6f04ac70b9da8dbf8ebd9a57d8021bb5e74437bc22bd274f7a'),
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(name, data):
    with (ROOT / name).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(data, indent=2) + '\n')

environment = {key: value for key, value in os.environ.items() if key.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT'}}
profile = ROOT / 'isolated-profile'
profile.mkdir()
for name in ('appdata', 'localappdata', 'tmp'):
    (profile / name).mkdir()
environment.update(USERPROFILE=str(profile), APPDATA=str(profile / 'appdata'), LOCALAPPDATA=str(profile / 'localappdata'),
    TEMP=str(profile / 'tmp'), TMP=str(profile / 'tmp'),
    PATH=os.pathsep.join([str(ROOT / 'venv/Scripts'), str(Path(sys.executable).parent), str(Path(os.environ['SystemRoot']) / 'System32')]),
    PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1', OKTO_NEXUS_NO_BANNER='1', OKTO_NEXUS_CONNECTOR_VAULT='file')
write('environment.json', environment)

def run(command, label):
    with (ROOT / (label + '.log')).open('x', encoding='utf-8') as stream:
        process = subprocess.run(command, cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT,
            timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if process.returncode:
        raise RuntimeError(label + ' failed; diagnostic retained; no native service operation attempted')
    return dict(argv=command, exit_code=0, log_sha256=sha(ROOT / (label + '.log')))

pool = ROOT / 'wheels'
pool.mkdir()
prior = json.loads((OLD / 'environment-preparation.json').read_bytes())
assert prior['dependencies']['mcp'] == '1.30.0'
dependencies = []
for row in prior['wheels']:
    source = Path(row['path'])
    if source.name.startswith(('okto_nexus-', 'okto_nexus_connector-', 'okto_nexus_connector_core-')):
        continue
    assert source.is_relative_to(OLD / 'wheels') and sha(source) == row['sha256']
    shutil.copyfile(source, pool / source.name)
    dependencies.append(dict(name=source.name, sha256=row['sha256'], bytes=source.stat().st_size))
for source, expected in PRODUCTS.values():
    assert sha(source) == expected
    shutil.copyfile(source, pool / source.name)
commands = [run([sys.executable, '-I', '-m', 'venv', str(ROOT / 'venv')], 'venv-create')]
python = ROOT / 'venv/Scripts/python.exe'
commands.append(run([str(python), '-I', '-m', 'pip', '--isolated', 'install', '--no-index', '--no-deps',
    *[str(path) for path in sorted(pool.glob('*.whl'))]], 'offline-install'))
commands.append(run([str(python), '-I', '-m', 'pip', '--isolated', 'check'], 'pip-check'))
write('environment-preparation.json', dict(status='CANDIDATE_PREPARATION_ONLY', system_site_packages=False,
    dependency_source='Existing immutable public-dependency wheel pool, hashes verified; no network or shared-venv mutation.',
    previous_dependency_manifest=str(OLD / 'environment-preparation.json'), previous_dependency_manifest_sha256=sha(OLD / 'environment-preparation.json'),
    dependencies=prior['dependencies'], dependency_wheels=dependencies, commands=commands,
    products={key:dict(original=str(path), sha256=expected) for key,(path,expected) in PRODUCTS.items()},
    qualification='Final candidate payloads supplied by root. Installed campaign qualification is still pending; this is not final acceptance.', service_operations_executed=[]))

inspect = (SOURCE / 'inspect_installed.py').read_text(encoding='utf-8')
inspect = inspect.replace("    assert current == inventory(installed) == wheel_files, package + ': current source/wheel/install mismatch'",
    "    assert inventory(installed) == wheel_files, package + ': wheel/install mismatch'\n    source_matches_candidate = current == wheel_files")
inspect = inspect.replace('current_source=str(repo), exact_source_wheel_install=True)',
    "current_source=str(repo), exact_source_wheel_install=source_matches_candidate, exact_wheel_install=True,\n        current_source_differences=sorted(key for key in set(current) | set(wheel_files) if current.get(key) != wheel_files.get(key)))")
(ROOT / 'inspect_installed.py').write_text(inspect, encoding='utf-8', newline='\n')

proposal = (SOURCE / 'prepare_proposal.py').read_text(encoding='utf-8')
proposal = proposal.replace("    clean = not subprocess.check_output(['git', '-C', repo, 'status', '--porcelain'], text=True).strip()\n    assert clean\n    heads[name] = dict(repository=repo, commit=commit, clean_at_preparation=True)",
    "    changes = subprocess.check_output(['git', '-C', repo, 'status', '--porcelain'], text=True).splitlines()\n    heads[name] = dict(repository=repo, commit=commit, clean_at_preparation=not changes, pending_paths=changes,\n        note='Concurrent SVC07 integration; candidate wheel bytes are pinned separately and no final source acceptance is inferred.')")
proposal = proposal.replace("revision=2, status='PREPARED_NOT_AUTHORIZED_NOT_RUN'", "revision=3, status='CANDIDATE_PREPARED_NOT_AUTHORIZED_NOT_RUN'")
proposal = proposal.replace("'No evidence of logout/reboot survival, real-provider readiness, client participation, or M1/M2 completion is claimed.'",
    "'No evidence of logout/reboot survival, real-provider readiness, client participation, or M1/M2 completion is claimed.',\n        'Candidate SVC07 wheel hashes are fixed here; final installed qualification is still in progress and not promoted by these checks.'")
proposal = proposal.replace("write('native-service-campaign-proposal.json', proposal)",
    "proposal['preparation_note'] = 'New Temp homes and new task names. Old proposals remain immutable. Uses three pinned SVC07 candidate wheels; this preparation installs no service and runs no campaign.'\nwrite('native-service-campaign-proposal.json', proposal)")
(ROOT / 'prepare_proposal.py').write_text(proposal, encoding='utf-8', newline='\n')
commands.append(run([str(python), '-I', '-B', str(ROOT / 'prepare_proposal.py')], 'proposal-readonly-checks'))
write('preparation-completion.json', dict(status='PREPARED_ONLY', final_command=commands[-1],
    no_shared_environment_mutations=True, no_campaign_executed=True, native_task_mutations=0, provider_calls=0))
print(json.dumps({'root': str(ROOT), 'proposal': str(ROOT / 'native-service-campaign-proposal.json'), 'readonly_checks_complete': True}))
