"""Disposable Herdr qualification driver; never imported by the observer."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(r'C:\Users\jpamb\AppData\Local\Temp\pr09-herdr-0.9.5-_n3kwt9i')
EXE = ROOT / 'distribution/herdr.exe'
SESSION = 'nexus-pr09-6fcb0c9a'
ENV = {name: value for name, value in os.environ.items()
       if name.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT',
                            'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS', 'OS'}}
ENV.update(USERPROFILE=str(ROOT / 'profile'), APPDATA=str(ROOT / 'appdata'),
           LOCALAPPDATA=str(ROOT / 'localappdata'), TEMP=str(ROOT / 'temp'),
           TMP=str(ROOT / 'temp'), HERDR_CONFIG_PATH=str(ROOT / 'config.toml'), NO_COLOR='1')
(ROOT / 'live').mkdir(exist_ok=True)

def call(name, args, timeout=15):
    result = subprocess.run(['rtk', 'proxy', str(EXE), '--session', SESSION, *args],
                            cwd=ROOT / 'work', env=ENV, capture_output=True,
                            timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
    (ROOT / 'live' / (name + '.stdout.txt')).write_bytes(result.stdout)
    (ROOT / 'live' / (name + '.stderr.txt')).write_bytes(result.stderr)
    print(json.dumps(dict(name=name, command=args, exit_code=result.returncode,
                         stdout_bytes=len(result.stdout), stderr_bytes=len(result.stderr))), flush=True)
    return result

if __name__ == '__main__':
    # A Python REPL is a benign disposable terminal fallback. It receives no
    # provider credentials, PYTHONSTARTUP or user shell profile configuration.
    config = 'onboarding = false\n[terminal]\ndefault_shell = ' + json.dumps(sys.executable) + '\nshell_mode = "non_login"\nnew_cwd = "current"\n'
    (ROOT / 'config.toml').write_text(config, encoding='utf-8')
    before = call('before-start', ['status', 'server', '--json'])
    if before.returncode != 0 or json.loads(before.stdout).get('running') is not False:
        raise SystemExit('Refusing to start: disposable session already exists.')
    with (ROOT / 'live/server.stdout.txt').open('wb') as out, (ROOT / 'live/server.stderr.txt').open('wb') as err:
        proc = subprocess.Popen(['rtk', 'proxy', str(EXE), '--session', SESSION, 'server'],
                                cwd=ROOT / 'work', env=ENV, stdout=out, stderr=err,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    (ROOT / 'live/launcher.json').write_text(json.dumps({'pid': proc.pid, 'session': SESSION}) + '\n')
    for index in range(10):
        status = call('status-' + str(index), ['status', 'server', '--json'])
        if status.returncode == 0 and json.loads(status.stdout).get('running') is True:
            break
        if proc.poll() is not None:
            raise SystemExit('Herdr server exited during startup.')
        time.sleep(.5)
    call('snapshot-initial', ['api', 'snapshot'])
