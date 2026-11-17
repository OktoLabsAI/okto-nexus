"""Windows ownership/console primitives, used only for disposable test clients."""
import ctypes
from ctypes import wintypes as w
import os

kernel = ctypes.WinDLL('kernel32', use_last_error=True)
user = ctypes.WinDLL('user32', use_last_error=True)
kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
kernel.OpenProcess.restype = w.HANDLE
kernel.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4
kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
kernel.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
kernel.CloseHandle.argtypes = [w.HANDLE]
kernel.GetConsoleProcessList.argtypes = [ctypes.POINTER(w.DWORD), w.DWORD]
kernel.GetConsoleProcessList.restype = w.DWORD
kernel.GetConsoleWindow.restype = w.HWND
user.IsWindowVisible.argtypes = [w.HWND]
kernel.AttachConsole.argtypes = [w.DWORD]
kernel.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, w.BOOL]
kernel.GenerateConsoleCtrlEvent.argtypes = [w.DWORD, w.DWORD]
kernel.GetConsoleMode.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
kernel.SetConsoleMode.argtypes = [w.HANDLE, w.DWORD]


class Owned:
    def __init__(self, pid, parent=None):
        self.pid, self.parent = pid, parent
        self.handle = kernel.OpenProcess(0x1000 | 0x100000 | 0x1, False, pid)
        if not self.handle:
            raise ProcessLookupError(pid)
        times = [w.FILETIME() for _ in range(4)]
        assert kernel.GetProcessTimes(self.handle, *map(ctypes.byref, times))
        self.birth = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        size = w.DWORD(32768)
        image = ctypes.create_unicode_buffer(size.value)
        assert kernel.QueryFullProcessImageNameW(self.handle, 0, image, ctypes.byref(size))
        self.image = image.value

    def alive(self):
        return kernel.WaitForSingleObject(self.handle, 0) == 258

    def facts(self):
        return dict(pid=self.pid, parent_pid=self.parent, birth_filetime=self.birth,
            image=self.image, alive=self.alive())

    def close(self):
        kernel.CloseHandle(self.handle)


def console_members():
    values = (w.DWORD * 256)()
    count = kernel.GetConsoleProcessList(values, len(values))
    assert 0 < count <= len(values), 'Console membership unavailable or over bound'
    return sorted(values[:count])


def hidden_window():
    hwnd = kernel.GetConsoleWindow()
    return dict(hwnd=int(hwnd or 0), visible=bool(hwnd and user.IsWindowVisible(hwnd)))


class Character(ctypes.Union):
    _fields_ = [('UnicodeChar', w.WCHAR), ('AsciiChar', ctypes.c_char)]


class Key(ctypes.Structure):
    _fields_ = [('bKeyDown', w.BOOL), ('wRepeatCount', w.WORD), ('wVirtualKeyCode', w.WORD),
        ('wVirtualScanCode', w.WORD), ('uChar', Character), ('dwControlKeyState', w.DWORD)]


class Event(ctypes.Union):
    _fields_ = [('KeyEvent', Key)]


class Input(ctypes.Structure):
    _fields_ = [('EventType', w.WORD), ('Event', Event)]


def write_y(handle):
    assert ctypes.sizeof(Key) == 16 and ctypes.sizeof(Input) == 20
    values = (Input * 4)()
    for index, (character, key, down) in enumerate((('y', 0x59, True), ('y', 0x59, False),
            ('\r', 0x0D, True), ('\r', 0x0D, False))):
        values[index].EventType = 1
        value = values[index].Event.KeyEvent
        value.bKeyDown, value.wRepeatCount, value.wVirtualKeyCode = down, 1, key
        value.uChar.UnicodeChar = character
    kernel.WriteConsoleInputW.argtypes = [w.HANDLE, ctypes.POINTER(Input), w.DWORD, ctypes.POINTER(w.DWORD)]
    written = w.DWORD()
    assert kernel.WriteConsoleInputW(handle, values, len(values), ctypes.byref(written))
    assert written.value == len(values)
    return written.value


def input_handle():
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    kernel.CreateFileW.restype = w.HANDLE
    handle = kernel.CreateFileW('CONIN$', 0x80000000 | 0x40000000, 3, None, 3, 0, None)
    assert handle != ctypes.c_void_p(-1).value
    return handle


def same_image(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
