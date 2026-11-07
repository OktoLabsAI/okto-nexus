"""Small Windows handle owner for the isolated preparation helper."""
import ctypes as C
from ctypes import wintypes as W
import uuid

K = C.WinDLL('kernel32', use_last_error=True)
SIZE = C.c_size_t

class BASIC(C.Structure):
    _fields_ = [('process_time', C.c_longlong), ('job_time', C.c_longlong), ('flags', W.DWORD),
                ('minimum', SIZE), ('maximum', SIZE), ('processes', W.DWORD), ('affinity', SIZE),
                ('priority', W.DWORD), ('scheduling', W.DWORD)]
class IO(C.Structure):
    _fields_ = [(name, C.c_ulonglong) for name in ('reads', 'writes', 'others', 'read_bytes', 'write_bytes', 'other_bytes')]
class EXTENDED(C.Structure):
    _fields_ = [('basic', BASIC), ('io', IO), ('process_memory', SIZE), ('job_memory', SIZE),
                ('peak_process', SIZE), ('peak_job', SIZE)]
class ACCOUNT(C.Structure):
    _fields_ = [(name, C.c_longlong) for name in ('user', 'kernel', 'period_user', 'period_kernel')] + [
        (name, W.DWORD) for name in ('faults', 'total', 'active', 'terminated')]

for name, args, result in [
    ('CreateJobObjectW', [W.LPVOID, W.LPCWSTR], W.HANDLE),
    ('OpenJobObjectW', [W.DWORD, W.BOOL, W.LPCWSTR], W.HANDLE),
    ('SetInformationJobObject', [W.HANDLE, C.c_int, W.LPVOID, W.DWORD], W.BOOL),
    ('QueryInformationJobObject', [W.HANDLE, C.c_int, W.LPVOID, W.DWORD, W.LPVOID], W.BOOL),
    ('AssignProcessToJobObject', [W.HANDLE, W.HANDLE], W.BOOL),
    ('IsProcessInJob', [W.HANDLE, W.HANDLE, C.POINTER(W.BOOL)], W.BOOL),
    ('TerminateJobObject', [W.HANDLE, W.UINT], W.BOOL),
    ('OpenProcess', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
    ('GetProcessTimes', [W.HANDLE, C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME)], W.BOOL),
    ('CloseHandle', [W.HANDLE], W.BOOL),
]:
    fn = getattr(K, name)
    fn.argtypes, fn.restype = args, result

def require(value):
    if not value:
        raise C.WinError(C.get_last_error())
    return value

def birth(handle):
    values = [W.FILETIME() for _ in range(4)]
    require(K.GetProcessTimes(int(handle), *(C.byref(value) for value in values)))
    return (values[0].dwHighDateTime << 32) | values[0].dwLowDateTime

class Job:
    def __init__(self, name=None):
        self.name = name or ('Local\\M1PTY-' + uuid.uuid4().hex)
        self.handle = require(K.CreateJobObjectW(None, self.name) if name is None else
                              K.OpenJobObjectW(4, False, name))
        if name is None:
            limit = EXTENDED()
            limit.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, no breakaway
            require(K.SetInformationJobObject(self.handle, 9, C.byref(limit), C.sizeof(limit)))

    def contains(self, handle):
        result = W.BOOL()
        require(K.IsProcessInJob(int(handle), self.handle, C.byref(result)))
        return bool(result.value)

    def assign(self, process):
        require(K.AssignProcessToJobObject(self.handle, int(process._handle)))
        assert self.contains(process._handle)

    def identity(self, pid):
        handle = require(K.OpenProcess(0x100000 | 0x1000, False, pid))
        try:
            assert self.contains(handle), 'child not in the exact owned job'
            return {'pid': pid, 'birth_filetime': birth(handle), 'exact_job_member': True}
        finally:
            K.CloseHandle(handle)

    def active(self):
        info = ACCOUNT()
        require(K.QueryInformationJobObject(self.handle, 1, C.byref(info), C.sizeof(info), None))
        return info.active

    def terminate(self):
        require(K.TerminateJobObject(self.handle, 125))

    def close(self):
        if self.handle:
            K.CloseHandle(self.handle)
            self.handle = None
