"""Query/synchronize-only process identity observer, copied from qualified cohort reference. No campaign controller."""
from pathlib import Path
import ctypes
from ctypes import wintypes
def require(value, reason):
    if not value: raise ValueError(reason)

class Process:
    def __init__(self, pid):
        self.pid, self.handle = pid, None
        self.k = k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k.OpenProcess.restype = wintypes.HANDLE
        k.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
        k.GetProcessTimes.restype = wintypes.BOOL
        k.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        k.WaitForSingleObject.restype = wintypes.DWORD
        k.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
        k.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k.CloseHandle.argtypes = (wintypes.HANDLE,)
        k.CloseHandle.restype = wintypes.BOOL
        k.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        k.GetExitCodeProcess.restype = wintypes.BOOL
        self.handle = k.OpenProcess(0x1000 | 0x100000, False, pid)
        require(bool(self.handle), 'PROCESS_HANDLE_UNAVAILABLE')
        try:
            fields = [wintypes.FILETIME() for _ in range(4)]
            require(k.GetProcessTimes(self.handle, *[ctypes.byref(v) for v in fields]), 'PROCESS_BIRTH_UNAVAILABLE')
            self.birth = (fields[0].dwHighDateTime << 32) | fields[0].dwLowDateTime
            buf, size = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
            require(k.QueryFullProcessImageNameW(self.handle, 0, buf, ctypes.byref(size)), 'PROCESS_IMAGE_UNAVAILABLE')
            self.image = str(Path(buf.value).resolve())
            require(not self.exited(), 'PROCESS_ALREADY_EXITED')
        except BaseException:
            self.close()
            raise

    def exited(self):
        value = self.k.WaitForSingleObject(self.handle, 0)
        require(value in (0, 258), 'PROCESS_WAIT_UNKNOWN')
        return value == 0

    def exit_code(self):
        require(self.exited(), 'PROCESS_STILL_ALIVE')
        value = wintypes.DWORD()
        require(self.k.GetExitCodeProcess(self.handle, ctypes.byref(value)), 'EXIT_CODE_UNKNOWN')
        return value.value

    def close(self):
        if self.handle:
            self.k.CloseHandle(self.handle)
            self.handle = None
