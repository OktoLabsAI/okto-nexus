"""Disposable Scheduler action: no product, credentials, network or child process."""
import ctypes
import json
import os
from pathlib import Path
import sys
import time
from ctypes import wintypes

ROOT = Path(__file__).resolve().parent
CASES = {'manual-3': 3, 'manual-ffffffff': 0xFFFFFFFF,
         'timer-3': 3, 'timer-ffffffff': 0xFFFFFFFF}

def main():
    case = sys.argv[1]
    intended = CASES[case]
    directory = ROOT / 'attempts' / case
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.ExitProcess.argtypes = [wintypes.UINT]
    times = [wintypes.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(kernel.GetCurrentProcess(), *[ctypes.byref(t) for t in times]):
        raise ctypes.WinError(ctypes.get_last_error())
    birth = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    # A third unexpected native launch is recorded and exits normally, preventing
    # more deliberate failures if the Scheduler does not honor Count=1.
    ordinal = len(list(directory.glob('*.json'))) + 1
    selected = intended if ordinal <= 2 else 0
    receipt = {'case': case, 'pid': os.getpid(), 'birth_filetime': birth,
               'wall_time': time.time(), 'ordinal': ordinal,
               'intended_exit_code': selected, 'budget_guard': ordinal > 2}
    temporary = directory / f'{os.getpid()}-{birth}.tmp'
    with temporary.open('x', encoding='utf-8') as out:
        json.dump(receipt, out, sort_keys=True)
        out.flush()
        os.fsync(out.fileno())
    temporary.replace(directory / f'{os.getpid()}-{birth}.json')
    time.sleep(3)  # Lets the observer retain this exact process handle.
    kernel.ExitProcess(selected)

if __name__ == '__main__':
    main()
