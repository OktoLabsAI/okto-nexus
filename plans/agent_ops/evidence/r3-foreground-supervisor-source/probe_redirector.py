import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
pythonw = Path('C:/Users/jpamb/AppData/Local/Temp/r3-native-t19-t20-39ycaumc/venv/Scripts/pythonw.exe')
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
child = subprocess.Popen([str(pythonw), '-I', '-B', '-X', 'utf8', str(root/'redirector_child.py')],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
stamps = [wintypes.FILETIME() for _ in range(4)]
assert kernel.GetProcessTimes(child._handle, *[ctypes.byref(t) for t in stamps])
birth = (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime
code = child.wait(timeout=30)
runtime = json.loads((root/'redirector-child-result.json').read_text())
value = {'popen_pid':child.pid,'popen_birth':birth,'exit_code':code,'runtime':runtime,
         'same_pid_and_birth':child.pid == runtime['pid'] and birth == runtime['birth'],
         'no_service_task_provider':True}
with (root/'redirector-probe.json').open('x',encoding='utf-8') as out: json.dump(value,out,indent=2)
print(json.dumps(value))
