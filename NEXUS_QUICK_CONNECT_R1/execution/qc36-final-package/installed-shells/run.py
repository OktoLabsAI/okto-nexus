"""Real-shell argv echo only; never a Nexus/provider invocation."""
import base64
import hashlib
import importlib.util
import zipfile
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PACKAGE=Path(json.loads((HERE.parent/'allocation.json').read_text())['root']).resolve()
PREFIX=PACKAGE/'venv'
assert Path(sys.prefix).resolve()==PREFIX
ready=json.loads((HERE.parent/'READY.json').read_text())
expected='d2c322168d56e87bde22cfe262d5d2fbc9a5737b0572144774894624d561cf88'
wheel=PACKAGE/'artifacts/okto_nexus-0.3.6-py3-none-any.whl'
assert hashlib.sha256(wheel.read_bytes()).hexdigest()==expected
def payload():
    values={}
    for module,archive in [('okto_nexus',wheel),('nexus_connector_core',REPO/'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'),('okto_nexus_connector',REPO/'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl')]:
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if name.startswith(module+'/') and not name.endswith('/'):
                    data=(PREFIX/'Lib/site-packages'/name).read_bytes()
                    assert data==z.read(name),name
                    values[name]=hashlib.sha256(data).hexdigest()
    return values
def origins():
    found={n:importlib.util.find_spec(n).origin for n in ['okto_nexus','nexus_connector_core','okto_nexus_connector']}
    assert all(Path(v).resolve().is_relative_to(PREFIX) for v in found.values())
    invalid={n:m.__file__ for n,m in list(sys.modules.items()) if n.startswith(('okto_nexus','nexus_connector_core')) and getattr(m,'__file__',None) and not Path(m.__file__).resolve().is_relative_to(PREFIX)}
    assert not invalid,invalid
    assert not any(Path(p).resolve()==REPO/'src' for p in sys.path if p)
    return dict(origins=found,invalid=invalid,sys_path=sys.path,isolated=sys.flags.isolated,executable=sys.executable)
before=payload()
start=origins()
from okto_nexus.adapters.inbound.cli import quick_connect_render
from okto_nexus.adapters.inbound.cli.quick_connect_render import render_resume_command
assert Path(quick_connect_render.__file__).resolve().is_relative_to(PREFIX)
(HERE/'payload-start.json').write_text(json.dumps(before,indent=2))
(HERE/'origins-start.json').write_text(json.dumps(start,indent=2))

root = Path(tempfile.mkdtemp(prefix='nexus-qc39-shell-')).resolve()
allowed = {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'SYSTEMDRIVE', 'NUMBER_OF_PROCESSORS'}
env = {k:v for k,v in os.environ.items() if k.upper() in allowed}
for key, name in [('HOME','user'),('USERPROFILE','user'),('APPDATA','appdata'),
                  ('LOCALAPPDATA','localappdata'),('TMP','tmp'),('TEMP','tmp')]:
    (root/name).mkdir(exist_ok=True)
    env[key] = str(root/name)
env['PATH'] = 'C:/Windows/System32;C:/Windows'
values = ['project with spaces Ω', "O'Brien", '"double quoted"', '$(touch QC39_MARKER)',
          '`touch QC39_MARKER`', '; touch QC39_MARKER', '& echo QC39_MARKER',
          'pipe|redirect>less<caret^percent%bang!', 'back\\slash\\', '', '--profile', '--home']
echo = 'import json,sys;sys.stdout.buffer.write(json.dumps(sys.argv[1:],ensure_ascii=False).encode("utf-8"))'
records = []

def run(argv, *, timeout=15):
    completed = subprocess.run(argv, cwd=root, env=env,
        input=b'', capture_output=True, timeout=timeout, shell=False)
    assert completed.returncode == 0, (completed.returncode, completed.stderr.decode('utf-8',errors='replace'))
    return completed

pwsh = 'C:/Program Files/PowerShell/7/pwsh.exe'
version_script = '$PSVersionTable.PSVersion.ToString()'
version = run([pwsh,'-NoLogo','-NoProfile','-NonInteractive','-EncodedCommand',
               base64.b64encode(version_script.encode('utf-16-le')).decode()]).stdout.decode('utf-8').strip()
vector = [sys.executable,'-I','-B','-X','utf8','-c',echo,*values]
command = render_resume_command(vector, shell='powershell')
completed = run([pwsh,'-NoLogo','-NoProfile','-NonInteractive','-EncodedCommand',
                 base64.b64encode(command.encode('utf-16-le')).decode()])
assert json.loads(completed.stdout.decode('utf-8-sig')) == values
assert not (root/'QC39_MARKER').exists()
records.append(dict(shell='PowerShell',version=version,renderer='powershell',arguments=values,
    received_exactly=True,marker_absent=True,exit_code=completed.returncode,stderr_bytes=len(completed.stderr)))

# The legacy shell must fail before the echo executable is invoked.
legacy = run(['C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe','-NoProfile','-NonInteractive',
              '-EncodedCommand',base64.b64encode(version_script.encode('utf-16-le')).decode()]).stdout.decode('utf-8',errors='replace').strip()
refused = subprocess.run(['C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe','-NoProfile','-NonInteractive',
    '-EncodedCommand',base64.b64encode(command.encode('utf-16-le')).decode()], cwd=root,env=env,
    input=b'',capture_output=True,timeout=15,shell=False)
assert refused.returncode != 0 and not refused.stdout.strip()
assert b'PowerShell 7.3+' in refused.stderr and not (root/'QC39_MARKER').exists()
records.append(dict(shell='Windows PowerShell',version=legacy,expected='refusal_before_invocation',
    exit_code=refused.returncode,stdout_empty=True,marker_absent=True))

wsl = 'C:/Windows/System32/wsl.exe'
linux = run([wsl,'--exec','/usr/bin/mktemp','-d','/tmp/nexus-qc39-shell-XXXXXX']).stdout.decode('utf-8').strip()
assert linux.startswith('/tmp/nexus-qc39-shell-') and len(linux.split('/')) == 3
linux_env = [wsl,'--exec','/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME='+linux,'TMPDIR='+linux]
vector = ['/usr/bin/python3','-I','-B','-c',echo,*values]
command = render_resume_command(vector, shell='posix')
completed = run([*linux_env,'/bin/sh','-c','cd '+shlex.quote(linux)+' && '+command])
assert json.loads(completed.stdout.decode('utf-8')) == values
probe = run([*linux_env,'/bin/sh','-c','test ! -e '+shlex.quote(linux+'/QC39_MARKER')+' && /usr/bin/uname -srm'])
python_version = run([*linux_env,'/usr/bin/python3','--version']).stdout.decode('utf-8').strip()
shell_target = run([*linux_env,'/usr/bin/readlink','-f','/bin/sh']).stdout.decode('utf-8').strip()
records.append(dict(shell='POSIX sh',shell_target=shell_target,OS=probe.stdout.decode('utf-8').strip(),
    python=python_version,WSL=True,arguments=values,received_exactly=True,marker_absent=True,
    exit_code=completed.returncode,stderr_bytes=len(completed.stderr)))
# Remove only this exact mktemp-created empty directory; no recursive deletion.
run([*linux_env,'/usr/bin/rmdir',linux])
result = dict(status='PASS',purpose='Real shell argv echo, no Nexus/model/provider execution',
    installed_helper_sha256=hashlib.sha256(Path(quick_connect_render.__file__).read_bytes()).hexdigest(),
    records=records,Windows_temp=str(root),Linux_temp=linux,Linux_temp_removed=True,
    per_process_timeout_seconds=15,stdin='closed PIPE',shell_false=True,provider_calls=0,
    owned_child_processes_exited=True,
    limits=['POSIX proof is WSL2 /bin/sh, not every POSIX shell or native OS.',
        'PowerShell7.3+ is the supported Windows syntax, tested on the exact available version.',
        'Windows PowerShell5.1 deliberately refuses; cmd.exe is not supported.',
        'Only an inert Python argv echo runs; no authenticated CLI, Nexus, profile recovery or provider call.'])
after=payload()
assert before==after
finish=origins()
(HERE/'payload-end.json').write_text(json.dumps(after,indent=2))
(HERE/'origins-finish.json').write_text(json.dumps(finish,indent=2))
result.update(mode='INSTALLED_HELPER_NO_CHECKOUT_IMPORT',wheel_sha256=expected,payload_files=len(before),payload_drift=[],helper_origin=quick_connect_render.__file__)
(HERE/'qualification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(status='PASS',shells=[r['shell'] for r in records],provider_calls=0)))
