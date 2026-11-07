"""Read-only Windows process birth proof for explicitly selected local PIDs.

Never enumerates processes, reads command lines or enables debug privileges.
The caller brackets Herdr reads while keeping the returned handle alive, and
must validate the Herdr selection separately. MachineGuid is only returned as a
domain-separated hash; its raw value never enters records or diagnostics.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import sys

from ....domain.herdr_observations import HerdrObservationError, WindowsProcessIdentity


def local_host_id() -> str:
    if sys.platform != 'win32':
        raise HerdrObservationError('HERDR_LOCAL_WINDOWS_REQUIRED')
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography', 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            value, kind = winreg.QueryValueEx(key, 'MachineGuid')
        if kind != winreg.REG_SZ or type(value) is not str or not 1 <= len(value.strip()) <= 256:
            raise ValueError
        return hashlib.sha256(b'nexus-herdr-host-v1\0' + value.strip().lower().encode('utf-8')).hexdigest()
    except (OSError, ValueError, UnicodeError):
        raise HerdrObservationError('HERDR_HOST_ID_UNAVAILABLE') from None


def _kernel():
    if sys.platform != 'win32':
        raise HerdrObservationError('HERDR_LOCAL_WINDOWS_REQUIRED')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    return kernel


def _facts(kernel, handle, *, host_id, pid):
    if kernel.WaitForSingleObject(handle, 0) != 0x102:  # WAIT_TIMEOUT = still alive.
        raise HerdrObservationError('HERDR_PROCESS_NOT_ALIVE')
    created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
    if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                  ctypes.byref(kernel_time), ctypes.byref(user_time)):
        raise HerdrObservationError('HERDR_PROCESS_IDENTITY_UNAVAILABLE')
    image = ctypes.create_unicode_buffer(32768)
    size = wintypes.DWORD(len(image))
    if not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
        raise HerdrObservationError('HERDR_PROCESS_IDENTITY_UNAVAILABLE')
    if kernel.WaitForSingleObject(handle, 0) != 0x102:
        raise HerdrObservationError('HERDR_PROCESS_NOT_ALIVE')
    birth = (int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime)
    return WindowsProcessIdentity(host_id, pid, birth, image.value)


class WindowsProcessGuard:
    """Handle owned by open_process_identity; usable only inside its context."""

    def __init__(self, kernel, handle, identity):
        self._kernel, self._handle = kernel, handle
        self.identity = identity

    def require_alive(self) -> WindowsProcessIdentity:
        if self._handle is None:
            raise HerdrObservationError('HERDR_PROCESS_GUARD_CLOSED')
        current = _facts(self._kernel, self._handle, host_id=self.identity.host_id, pid=self.identity.pid)
        if current != self.identity:
            raise HerdrObservationError('HERDR_PROCESS_IDENTITY_CHANGED')
        return current


@contextmanager
def open_process_identity(pid: int):
    if type(pid) is not int or not 0 < pid < (1 << 32):
        raise HerdrObservationError('HERDR_PROCESS_IDENTITY_UNAVAILABLE')
    host_id = local_host_id()
    kernel = _kernel()
    handle = kernel.OpenProcess(0x1000 | 0x100000, False, pid)  # QUERY_LIMITED_INFORMATION | SYNCHRONIZE.
    if not handle:
        raise HerdrObservationError('HERDR_PROCESS_IDENTITY_UNAVAILABLE')
    guard = None
    try:
        identity = _facts(kernel, handle, host_id=host_id, pid=pid)
        guard = WindowsProcessGuard(kernel, handle, identity)
        yield guard
    finally:
        if guard is not None:
            guard._handle = None
        kernel.CloseHandle(handle)


def read_process_identity(pid: int) -> WindowsProcessIdentity:
    """One sample; use the context manager when proving a bracketed read."""
    with open_process_identity(pid) as guard:
        return guard.require_alive()
