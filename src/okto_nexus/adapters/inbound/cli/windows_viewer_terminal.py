"""Own the Windows terminal of a viewer, independently of its runtime."""

import codecs
import ctypes as ct
import msvcrt
import os
import re
import subprocess
import sys
from contextlib import ExitStack
from ctypes import wintypes as wt
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event, Thread


class _Size(ct.Structure):
    _fields_ = [('columns', wt.SHORT), ('lines', wt.SHORT)]


class _StartupInfo(ct.Structure):
    _fields_ = [
        ('size', wt.DWORD), ('reserved', wt.LPWSTR), ('desktop', wt.LPWSTR), ('title', wt.LPWSTR),
        ('x', wt.DWORD), ('y', wt.DWORD), ('width', wt.DWORD), ('height', wt.DWORD),
        ('columns', wt.DWORD), ('lines', wt.DWORD), ('attributes', wt.DWORD), ('flags', wt.DWORD),
        ('show', wt.WORD), ('reserved_size', wt.WORD), ('reserved_bytes', ct.c_void_p),
        ('stdin', wt.HANDLE), ('stdout', wt.HANDLE), ('stderr', wt.HANDLE),
    ]


class _StartupInfoEx(ct.Structure):
    _fields_ = [('info', _StartupInfo), ('attribute_list', ct.c_void_p)]


class _ProcessInfo(ct.Structure):
    _fields_ = [('process', wt.HANDLE), ('thread', wt.HANDLE), ('pid', wt.DWORD), ('tid', wt.DWORD)]


_kernel = ct.WinDLL('kernel32', use_last_error=True)


def _api(name, result, *arguments):
    function = getattr(_kernel, name)
    function.restype = result
    function.argtypes = arguments
    return function


_dword = ct.POINTER(wt.DWORD)
_handle = ct.POINTER(wt.HANDLE)
_size_t = ct.POINTER(ct.c_size_t)
_get_mode = _api('GetConsoleMode', wt.BOOL, wt.HANDLE, _dword)
_set_mode = _api('SetConsoleMode', wt.BOOL, wt.HANDLE, wt.DWORD)
_pipe = _api('CreatePipe', wt.BOOL, _handle, _handle, ct.c_void_p, wt.DWORD)
_close_handle = _api('CloseHandle', wt.BOOL, wt.HANDLE)
_create_pty = _api('CreatePseudoConsole', ct.c_long, _Size, wt.HANDLE, wt.HANDLE, wt.DWORD, _handle)
_resize_pty = _api('ResizePseudoConsole', ct.c_long, wt.HANDLE, _Size)
_close_pty = _api('ClosePseudoConsole', None, wt.HANDLE)
_attributes = _api('InitializeProcThreadAttributeList', wt.BOOL, ct.c_void_p, wt.DWORD, wt.DWORD, _size_t)
_delete_attributes = _api('DeleteProcThreadAttributeList', None, ct.c_void_p)
_update_attributes = _api('UpdateProcThreadAttribute', wt.BOOL, ct.c_void_p, wt.DWORD, ct.c_size_t,
                          ct.c_void_p, ct.c_size_t, ct.c_void_p, _size_t)
_spawn = _api('CreateProcessW', wt.BOOL, wt.LPCWSTR, wt.LPWSTR, ct.c_void_p, ct.c_void_p, wt.BOOL,
              wt.DWORD, ct.c_void_p, wt.LPCWSTR, ct.POINTER(_StartupInfoEx), ct.POINTER(_ProcessInfo))
_wait = _api('WaitForSingleObject', wt.DWORD, wt.HANDLE, wt.DWORD)
_exit_code = _api('GetExitCodeProcess', wt.BOOL, wt.HANDLE, _dword)
_terminate = _api('TerminateProcess', wt.BOOL, wt.HANDLE, wt.UINT)
_read_file = _api('ReadFile', wt.BOOL, wt.HANDLE, ct.c_void_p, wt.DWORD, _dword, ct.c_void_p)
_write_file = _api('WriteFile', wt.BOOL, wt.HANDLE, ct.c_void_p, wt.DWORD, _dword, ct.c_void_p)
_read_console = _api('ReadConsoleW', wt.BOOL, wt.HANDLE, ct.c_void_p, wt.DWORD, _dword, ct.c_void_p)
_write_console = _api('WriteConsoleW', wt.BOOL, wt.HANDLE, ct.c_void_p, wt.DWORD, _dword, ct.c_void_p)
_open_thread = _api('OpenThread', wt.HANDLE, wt.DWORD, wt.BOOL, wt.DWORD)
_thread_id = _api('GetCurrentThreadId', wt.DWORD)
_cancel_io = _api('CancelSynchronousIo', wt.BOOL, wt.HANDLE)

_WAIT_TIMEOUT = 258
_PIPE_CLOSED = {38, 109, 232, 995}
_DETACH = '\x1d'
_START_PASTE = '\x1b[200~'
_END_PASTE = '\x1b[201~'
# ConPTY can emit Win32 key records even when the outer console receives VT bytes.
_WIN32_KEY_DOWN = re.compile(r'\x1b\[[0-9]{0,5};[0-9]{0,5};(?:29|93);1;([0-9]{1,5});[0-9]{0,5}_$')


@dataclass(frozen=True, slots=True)
class ViewerExit:
    returncode: int
    detached: bool


def _check(ok):
    if not ok:
        raise ct.WinError(ct.get_last_error())


def _mode(handle):
    value = wt.DWORD()
    _check(_get_mode(handle, ct.byref(value)))
    return value.value


def _new_pipe(resources, peer_resources, *, input_pipe):
    read_end, write_end = wt.HANDLE(), wt.HANDLE()
    _check(_pipe(ct.byref(read_end), ct.byref(write_end), None, 0))
    host, peer = (write_end, read_end) if input_pipe else (read_end, write_end)
    resources.callback(_close_handle, host)
    peer_resources.callback(_close_handle, peer)
    return host, peer


def _launch(terminal, argv, cwd, env):
    size = ct.c_size_t()
    _attributes(None, 1, 0, ct.byref(size))
    buffer = ct.create_string_buffer(size.value)
    _check(_attributes(buffer, 1, 0, ct.byref(size)))
    try:
        # PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE
        _check(_update_attributes(buffer, 0, 0x00020016, terminal, ct.sizeof(terminal), None, None))
        startup = _StartupInfoEx()
        startup.info.size = ct.sizeof(startup)
        startup.attribute_list = ct.cast(buffer, ct.c_void_p)
        command = ct.create_unicode_buffer(subprocess.list2cmdline(argv))
        entries = '\0'.join(f'{key}={env[key]}' for key in sorted(env, key=str.casefold))
        environment = ct.create_unicode_buffer(entries + '\0\0')
        process = _ProcessInfo()
        _check(_spawn(argv[0], command, None, None, False, 0x00080000 | 0x00000400,
                      environment, str(cwd), ct.byref(startup), ct.byref(process)))
        _close_handle(process.thread)
        return process.process
    finally:
        _delete_attributes(buffer)


def _read(function, handle, buffer, units, unit_size):
    count = wt.DWORD()
    if not function(handle, buffer, units, ct.byref(count), None):
        code = ct.get_last_error()
        if code in _PIPE_CLOSED:
            return b''
        raise ct.WinError(code)
    return buffer.raw[:count.value * unit_size]


def _write(function, handle, data, unit_size):
    while data:
        count = wt.DWORD()
        _check(function(handle, data, len(data) // unit_size, ct.byref(count), None))
        if not count.value:
            raise OSError('The viewer terminal stopped accepting output.')
        data = data[count.value * unit_size:]


class _DetachKey:
    """Separate Ctrl+] from bracketed pastes, across input reads."""

    def __init__(self):
        self._suffix = ''
        self._in_paste = False

    def pressed(self, text):
        for character in text:
            if character == _DETACH and not self._in_paste:
                return True
            self._suffix = (self._suffix + character)[-40:]
            if self._suffix.endswith(_START_PASTE):
                self._in_paste = True
            elif self._suffix.endswith(_END_PASTE):
                self._in_paste = False
            elif character == '_' and not self._in_paste:
                record = _WIN32_KEY_DOWN.search(self._suffix)
                if record is not None:
                    modifiers = int(record[1])
                    if modifiers & 0x0c and not modifiers & 0x13:  # Ctrl and no Alt or Shift.
                        return True
        return False


class _Pump:
    """Keep the owned thread handle needed to cancel synchronous input or output."""

    def __init__(self, task, failures, stopping):
        ready = Event()
        self.handle = None

        def run():
            self.handle = _open_thread(0x0001, False, _thread_id())  # THREAD_TERMINATE for CancelSynchronousIo.
            ready.set()
            try:
                _check(self.handle)
                task()
            except OSError as error:
                if not stopping.is_set():
                    failures.append(error)

        self.thread = Thread(target=run, daemon=True)
        self.thread.start()
        ready.wait()

    def join(self, *, drain=False):
        # Leave the output reader running during ConPTY shutdown. Older Windows
        # versions can write a final frame from ClosePseudoConsole itself.
        if drain:
            self.thread.join(1)
        try:
            for _ in range(40):
                if not self.thread.is_alive():
                    return
                if self.handle:
                    _cancel_io(self.handle)
                self.thread.join(.05)
            raise OSError('The viewer terminal did not release its I/O.')
        finally:
            if self.handle:
                _close_handle(self.handle)


def run_viewer_terminal(argv, *, cwd, env):
    """Run only the viewer in a private ConPTY and return after keyboard detach."""
    stdin = msvcrt.get_osfhandle(sys.stdin.fileno())
    stdout_fd = sys.stdout.fileno()
    stdout = msvcrt.get_osfhandle(stdout_fd)
    input_mode, output_mode = _mode(stdin), _mode(stdout)
    sys.stdout.flush()
    stopping, detach = Event(), Event()
    keyboard = Queue(maxsize=128)
    failures = []

    def read_keyboard():
        buffer = ct.create_string_buffer(2048)
        decode = codecs.getincrementaldecoder('utf-16-le')(errors='replace').decode
        key = _DetachKey()
        while not stopping.is_set():
            raw = _read(_read_console, stdin, buffer, len(buffer) // 2, 2)
            if stopping.is_set():
                return
            text = decode(raw)
            if not raw or key.pressed(text):
                detach.set()
                return
            try:
                keyboard.put_nowait(text.encode('utf-8'))
            except Full:
                raise OSError('The viewer terminal input buffer is full.') from None

    def forward_keyboard():
        while not stopping.is_set():
            try:
                data = keyboard.get(timeout=.05)
            except Empty:
                continue
            if not stopping.is_set() and not detach.is_set():
                _write(_write_file, input_pipe, data, 1)

    def drain_output():
        buffer = ct.create_string_buffer(16384)
        decode = codecs.getincrementaldecoder('utf-8')(errors='replace').decode
        displaying = True
        while data := _read(_read_file, output_pipe, buffer, len(buffer), 1):
            if displaying:
                try:
                    _write(_write_console, stdout, decode(data).encode('utf-16-le'), 2)
                except OSError as error:
                    failures.append(error)
                    displaying = False
        if displaying:
            _write(_write_console, stdout, decode(b'', final=True).encode('utf-16-le'), 2)

    with ExitStack() as resources:
        # Forward native input and VT sequences. Ctrl+] is consumed locally.
        _check(_set_mode(stdin, (input_mode & ~0x47) | 0x0280))
        resources.callback(_set_mode, stdin, input_mode)
        _check(_set_mode(stdout, output_mode | 0x000d))
        resources.callback(_set_mode, stdout, output_mode)
        terminal = wt.HANDLE()
        dimensions = os.get_terminal_size(stdout_fd)
        with ExitStack() as peers:
            input_pipe, to_viewer = _new_pipe(resources, peers, input_pipe=True)
            output_pipe, from_viewer = _new_pipe(resources, peers, input_pipe=False)
            if _create_pty(_Size(*dimensions), to_viewer, from_viewer, 0, ct.byref(terminal)) < 0:
                raise OSError('Could not create the viewer pseudoconsole.')
            output = _Pump(drain_output, failures, stopping)
            try:
                process = _launch(terminal, argv, cwd, env)
            except BaseException:
                _close_pty(terminal)
                peers.close()
                output.join(drain=True)
                raise
        resources.callback(_close_handle, process)
        pumps = []
        try:
            pumps.append(_Pump(read_keyboard, failures, stopping))
            pumps.append(_Pump(forward_keyboard, failures, stopping))
            while not detach.is_set() and not failures:
                status = _wait(process, 75)
                if status == 0:
                    break
                if status != _WAIT_TIMEOUT:
                    _check(False)
                current = os.get_terminal_size(stdout_fd)
                if current != dimensions and _resize_pty(terminal, _Size(*current)) == 0:
                    dimensions = current
            if failures:
                raise failures[0]
            if detach.is_set():
                return ViewerExit(0, True)
            code = wt.DWORD()
            _check(_exit_code(process, ct.byref(code)))
            return ViewerExit(code.value, False)
        finally:
            stopping.set()
            # These handles belong only to the frontend started above. The
            # independently owned engine is connected over the Nexus relay.
            if _wait(process, 0) == _WAIT_TIMEOUT:
                _terminate(process, 1)
            _close_pty(terminal)
            for pump in pumps:
                resources.callback(pump.join)
            output.join(drain=True)
            if _wait(process, 3000) != 0:
                raise OSError('The detached viewer did not exit.')
            if detach.is_set():
                _write(_write_console, stdout, '\x1b[0m\x1b[?25h\x1b[?2004l\r\n'.encode('utf-16-le'), 2)
