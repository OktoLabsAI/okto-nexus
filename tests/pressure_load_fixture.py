"""Isolated bounded CPU worker; invoked as a subprocess by pressure tests."""

import ctypes,os
if os.name == 'nt':
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.GetCurrentProcess.restype=ctypes.c_void_p
    k.GetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_size_t)]
    k.SetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
    available,system=ctypes.c_size_t(),ctypes.c_size_t()
    assert k.GetProcessAffinityMask(k.GetCurrentProcess(),ctypes.byref(available),ctypes.byref(system))
    cpu_mask=available.value & -available.value
    assert k.SetProcessAffinityMask(k.GetCurrentProcess(),cpu_mask)
    affinity=cpu_mask.bit_length()-1
else:
    affinity=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{affinity})

import json,sys,time
from pathlib import Path
root=Path(sys.argv[1]); name=sys.argv[2]
began=time.monotonic(); deadline=began+300; last=0; iterations=0; value=1; retries=0
while time.monotonic()<deadline and not (root/'stop').exists():
    if not (root/'active').exists():
        time.sleep(.01)
    for _ in range(20000 if (root/'active').exists() else 0):
        value=(value*1664525+1013904223)&0xffffffff
    iterations+=20000 if (root/'active').exists() else 0
    now=time.monotonic()
    if now-last>.2:
        data={'affinity':affinity,'cpu_seconds':time.process_time(),'wall_seconds':now-began,'iterations':iterations,'publication_retries':retries}
        temporary=root/(name+'.tmp'); temporary.write_text(json.dumps(data))
        publish_deadline=min(deadline,time.monotonic()+2)
        while True:
            try:
                temporary.replace(root/(name+'.json'))
                break
            except PermissionError:
                retries+=1
                if time.monotonic()>=publish_deadline:
                    raise
                time.sleep(.01)
        last=now
