"""Focused installed RG-04 campaign; synthetic native peers, no real provider.

Only invokes the repository's immutable installed CI runner in test mode.
Does not install dependencies or alter the shared environment.
"""
from pathlib import Path
import json
import os
import subprocess
import time

root = Path(__file__).resolve().parent
spec = json.loads((root / 'selection.json').read_text(encoding='utf-8'))
private = root / 'private'
private.mkdir()
for name in ('home', 'temp', 'localappdata', 'appdata'):
    (private / name).mkdir()
env = {key: value for key, value in os.environ.items()
       if key.upper() in {'SYSTEMROOT', 'WINDIR', 'SYSTEMDRIVE', 'COMSPEC',
                          'PATHEXT', 'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS'}}
env.update(PATH=str(Path(spec['python']).parent) + os.pathsep + str(Path(env['SYSTEMROOT']) / 'System32'),
           TEMP=str(private / 'temp'), TMP=str(private / 'temp'),
           USERPROFILE=str(private / 'home'), HOME=str(private / 'home'),
           APPDATA=str(private / 'appdata'), LOCALAPPDATA=str(private / 'localappdata'),
           NO_COLOR='1')
command = [spec['python'], '-X', 'utf8', '-I',
           str(Path(spec['repo']) / 'tools' / 'ci_installed.py'), 'test',
           '--wheel', spec['wheel'], '--output', str(root / 'reports'),
           '--tests', *spec['tests']]
(root / 'invocation.json').write_text(json.dumps({
    'command': command, 'cwd': str(root), 'environment': env,
    'synthetic_native_peers': True, 'real_provider_qualification': False,
    'shared_environment_mutation': False,
}, indent=2) + '\n', encoding='utf-8')
started = time.monotonic()
with (root / 'stdout-private.log').open('wb') as log:
    result = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
(root / 'process-result.json').write_text(json.dumps({
    'exit_code': result.returncode, 'elapsed_seconds': time.monotonic() - started,
}, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'root': str(root), 'exit_code': result.returncode}))
raise SystemExit(result.returncode)
