import _thread
import hashlib
import importlib
import json
import os
from pathlib import Path
import runpy
import sys
import threading
import zipfile

wheel=Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus/vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl')
digest=hashlib.sha256(wheel.read_bytes()).hexdigest()
assert digest=='5721e462add21d65380f070a68db07a653a498a78d4be9ea0cf949909d3cfecb'
verify=runpy.run_path(r'D:/Projetos/Techridy/okto-nexus-connector-core/tools/verify_wheel.py')['verify_import_boundaries']
with zipfile.ZipFile(wheel) as archive:
    names=sorted(n for n in archive.namelist() if n.startswith('nexus_connector_core/') and n.endswith('.py'))
    for n in names:
        verify(archive.read(n),n)
        assert (Path(sys.prefix)/'Lib/site-packages'/n).read_bytes()==archive.read(n),n
modules=sorted(set(n[:-3].replace('/','.') if not n.endswith('/__init__.py') else n[:-12].replace('/','.') for n in names))
sys.dont_write_bytecode=True
allowed=[Path(sys.prefix).resolve(),Path(sys.base_prefix).resolve()]
reads=0
denied=[]
def reject(event):
    denied.append(event)
    raise RuntimeError('Import boundary violation: '+event)
def audit(event,args):
    global reads
    if event.startswith('socket.') or event in ('subprocess.Popen','os.system','os.fork','os.posix_spawn','os.spawn'):
        reject(event)
    if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
        p=Path(os.fsdecode(args[0])).resolve()
        flags=args[2] if len(args)>2 and isinstance(args[2],int) else 0
        if flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC): reject('file_write')
        if not any(p.is_relative_to(base) for base in allowed): reject('read_outside_python_installations')
        reads+=1
def no_thread(*args,**kwargs): reject('thread_start')
for module in (_thread,threading):
    for name in ('start_new_thread','start_new','_start_new_thread','start_joinable_thread','_start_joinable_thread'):
        if hasattr(module,name): setattr(module,name,no_thread)
sys.addaudithook(audit)
loaded=[]
for module in modules:
    value=importlib.import_module(module)
    assert Path(value.__file__).is_relative_to(Path(sys.prefix))
    loaded.append(module)
assert not denied
print(json.dumps(dict(status='PASS',core_wheel_sha256=digest,static_python_files=len(names),imported_modules=loaded,
    denied_events=denied,reads_within_python_installations=reads,
    scope='Import every Core Python module; static prohibited-application/dependency check; socket/process/thread/write/outside-installation-read guards. No adapter or service execution; no claim of runtime credentials/backend behavior.'),indent=2))
