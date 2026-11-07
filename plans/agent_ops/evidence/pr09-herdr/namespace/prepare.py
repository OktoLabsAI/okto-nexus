"""Prepare an isolated second Herdr; no start or primary-session mutation."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
ORIGINAL = Path('C:/Users/jpamb/AppData/Local/Temp/pr09-herdr-0.9.5-_n3kwt9i')
SESSION = 'nexus-pr09-namespace-cvxe4ar4'
reference = json.loads((ORIGINAL / 'distribution-proof.json').read_text())
shutil.copytree(ORIGINAL / 'distribution', ROOT / 'distribution')
for folder in ('work', 'profile', 'appdata', 'localappdata', 'temp', 'evidence'):
    (ROOT / folder).mkdir()
for name in ('Fixture.cs', 'codex.exe'):
    shutil.copy2(ORIGINAL / 'work' / name, ROOT / 'work' / name)
hashes = {name: hashlib.sha256((ROOT / 'distribution' / name).read_bytes()).hexdigest()
          for name in reference['extracted_files']}
assert hashes == reference['extracted_files']
config = ('onboarding = false\n[terminal]\ndefault_shell = "C:\\\\Python313\\\\python.exe"\n'
    'shell_mode = "non_login"\nnew_cwd = "current"\n[update]\nversion_check = false\n'
    'manifest_check = false\n[session]\nresume_agents_on_restore = false\n')
(ROOT / 'config.toml').write_text(config, encoding='utf-8')
env = {name: value for name, value in os.environ.items() if name.upper() in {
    'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS', 'OS'}}
env.update(PATH='C:\\Windows\\System32;C:\\Windows;C:\\Python313', HOME=str(ROOT / 'profile'),
    USERPROFILE=str(ROOT / 'profile'), APPDATA=str(ROOT / 'appdata'),
    LOCALAPPDATA=str(ROOT / 'localappdata'), TEMP=str(ROOT / 'temp'), TMP=str(ROOT / 'temp'),
    HERDR_CONFIG_PATH=str(ROOT / 'config.toml'), NO_COLOR='1')
for name, args in [('workspace-create-help', ['workspace', 'create', '--help']),
                   ('pane-split-help', ['pane', 'split', '--help']),
                   ('server-stop-help', ['server', 'stop', '--help'])]:
    result = subprocess.run([str(ROOT / 'distribution/herdr.exe'), '--session', SESSION, *args],
        cwd=ROOT / 'work', env=env, capture_output=True, timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0
    (ROOT / 'evidence' / (name + '.txt')).write_bytes(result.stdout)
proof = {'revision': 1, 'session': SESSION, 'root': str(ROOT), 'official_version': '0.9.5',
    'distribution_hashes': hashes, 'distribution_original_proof': str(ORIGINAL / 'distribution-proof.json'),
    'fixture': {'synthetic': True, 'is_openai_codex': False, 'provider_inference': False,
        'source': 'work/Fixture.cs', 'executable': 'work/codex.exe',
        'source_sha256': hashlib.sha256((ROOT / 'work/Fixture.cs').read_bytes()).hexdigest(),
        'executable_sha256': hashlib.sha256((ROOT / 'work/codex.exe').read_bytes()).hexdigest()},
    'environment_keys': sorted(env)}
(ROOT / 'evidence/preparation.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
print(json.dumps({'prepared': str(ROOT), 'session': SESSION, 'distribution_verified': True, 'started': False}))
