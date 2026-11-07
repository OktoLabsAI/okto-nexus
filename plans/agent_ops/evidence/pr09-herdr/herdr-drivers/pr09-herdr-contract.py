"""Read a pinned Herdr CLI contract with an isolated child environment."""
import json
import os
from pathlib import Path
import subprocess

root = Path(r'C:\Users\jpamb\AppData\Local\Temp\pr09-herdr-0.9.5-_n3kwt9i')
environment = {name: value for name, value in os.environ.items()
               if name.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT',
                                    'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS', 'OS'}}
directories = {name: root / name for name in ('profile', 'appdata', 'localappdata', 'temp', 'work', 'contract')}
for value in directories.values():
    value.mkdir(exist_ok=True)
# Child-only standard application locations; the parent environment and actual
# user profile are untouched. No provider keys or ambient application creds.
environment.update(USERPROFILE=str(directories['profile']), APPDATA=str(directories['appdata']),
                   LOCALAPPDATA=str(directories['localappdata']), TEMP=str(directories['temp']),
                   TMP=str(directories['temp']), HERDR_CONFIG_PATH=str(root / 'config.toml'),
                   NO_COLOR='1')
(root / 'config.toml').write_text('# Disposable metadata-only Herdr qualification.\n', encoding='utf-8')
results = []
for name, args in [('version', ['--version']), ('help', ['--help']), ('schema', ['api', 'schema', '--json'])]:
    result = subprocess.run(['rtk', 'proxy', str(root / 'distribution/herdr.exe'), *args],
        cwd=directories['work'], env=environment, capture_output=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW)
    (directories['contract'] / (name + '.stdout.txt')).write_bytes(result.stdout)
    (directories['contract'] / (name + '.stderr.txt')).write_bytes(result.stderr)
    entry = dict(command=args, exit_code=result.returncode,
                 stdout_bytes=len(result.stdout), stderr_bytes=len(result.stderr))
    results.append(entry)
    print(json.dumps(entry), flush=True)
(root / 'contract/metadata-results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
