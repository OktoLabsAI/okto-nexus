import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys

kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.GetCurrentProcess.restype = wintypes.HANDLE
kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
times = [wintypes.FILETIME() for _ in range(4)]
assert kernel.GetProcessTimes(kernel.GetCurrentProcess(), *[ctypes.byref(t) for t in times])
birth = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
path = Path(__file__).with_name('redirector-child-result.json')
with path.open('x', encoding='utf-8') as out:
    json.dump({'pid': os.getpid(), 'parent_pid': os.getppid(), 'birth': birth,
               'executable': sys.executable, 'base_executable': sys._base_executable,
               'prefix': sys.prefix, 'base_prefix': sys.base_prefix}, out, indent=2)
