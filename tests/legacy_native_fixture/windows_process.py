"""Windows processes born inside a kill-on-close Job Object.

The JOB_LIST startup attribute removes the create-then-assign orphan window.
See https://devblogs.microsoft.com/oldnewthing/20230209-00/?p=107812 .
Only native harness stdio launches use this deliberately narrow Popen adapter.
"""
import ctypes
from ctypes import wintypes as w
import inspect
import os
import subprocess
import threading

SIZE_T = ctypes.c_size_t


class _BasicLimits(ctypes.Structure):
    _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                ("flags", w.DWORD), ("min_working_set", SIZE_T), ("max_working_set", SIZE_T),
                ("active_process_limit", w.DWORD), ("affinity", SIZE_T),
                ("priority", w.DWORD), ("scheduling", w.DWORD)]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in
                ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("basic", _BasicLimits), ("io", _IoCounters), ("process_memory", SIZE_T),
                ("job_memory", SIZE_T), ("peak_process", SIZE_T), ("peak_job", SIZE_T)]


class _StartupInfo(ctypes.Structure):
    _fields_ = [("cb", w.DWORD), ("reserved", w.LPWSTR), ("desktop", w.LPWSTR), ("title", w.LPWSTR),
                *[(name, w.DWORD) for name in ("x", "y", "xsize", "ysize", "xchars", "ychars", "fill", "flags")],
                ("show", w.WORD), ("reserved_size", w.WORD), ("reserved_bytes", ctypes.c_void_p),
                ("stdin", w.HANDLE), ("stdout", w.HANDLE), ("stderr", w.HANDLE)]


class _StartupInfoEx(ctypes.Structure):
    _fields_ = [("startup", _StartupInfo), ("attributes", ctypes.c_void_p)]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [("process", w.HANDLE), ("thread", w.HANDLE), ("pid", w.DWORD), ("tid", w.DWORD)]


def _kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    declarations = {
        "CreateJobObjectW": ([ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
        "SetInformationJobObject": ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
        "CloseHandle": ([w.HANDLE], w.BOOL),
        "TerminateJobObject": ([w.HANDLE, w.UINT], w.BOOL),
        "InitializeProcThreadAttributeList": ([ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.POINTER(SIZE_T)], w.BOOL),
        "UpdateProcThreadAttribute": ([ctypes.c_void_p, w.DWORD, SIZE_T, ctypes.c_void_p, SIZE_T, ctypes.c_void_p, ctypes.c_void_p], w.BOOL),
        "DeleteProcThreadAttributeList": ([ctypes.c_void_p], None),
        "CreateProcessW": ([w.LPCWSTR, w.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, w.BOOL, w.DWORD,
                            ctypes.c_void_p, w.LPCWSTR, ctypes.POINTER(_StartupInfoEx), ctypes.POINTER(_ProcessInfo)], w.BOOL),
    }
    for name, (arguments, result) in declarations.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = arguments, result
    return kernel


def _check(success):
    if not success:
        raise ctypes.WinError(ctypes.get_last_error())


class OwnedWindowsPopen(subprocess.Popen):
    """Standard Popen pipes/waiting, with atomic kernel process-tree ownership."""
    def __init__(self, *args, **kwargs):
        self._job_lock = threading.Lock()
        self._kernel = _kernel()
        self._job = self._kernel.CreateJobObjectW(None, None)
        _check(self._job)
        try:
            limits = _ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            _check(self._kernel.SetInformationJobObject(self._job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
            super().__init__(*args, **kwargs)
        except BaseException:
            self._close_job()
            raise

    def _execute_child(self, *args, **kwargs):
        # CPython owns pipe creation/text wrapping/handle cleanup. Binding the
        # actual signature fails closed if a supported Python changes its ABI.
        parameters = inspect.signature(subprocess.Popen._execute_child).bind(self, *args, **kwargs).arguments
        if parameters["shell"] or parameters["pass_fds"] or parameters["startupinfo"] is not None:
            raise ValueError("Owned harness launch requires direct stdio without extra inherited handles")
        read, write, error = (int(parameters[name]) for name in ("p2cread", "c2pwrite", "errwrite"))
        if -1 in (read, write, error):
            raise ValueError("Owned harness launch requires all three standard pipes")
        attributes_size = SIZE_T()
        self._kernel.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(attributes_size))
        if not attributes_size.value:
            raise ctypes.WinError(ctypes.get_last_error())
        attributes = ctypes.create_string_buffer(attributes_size.value)
        initialized = False
        try:
            _check(self._kernel.InitializeProcThreadAttributeList(attributes, 2, 0, ctypes.byref(attributes_size)))
            initialized = True
            handles = (w.HANDLE * 3)(read, write, error)
            jobs = (w.HANDLE * 1)(self._job)
            _check(self._kernel.UpdateProcThreadAttribute(attributes, 0, 0x20002, handles, ctypes.sizeof(handles), None, None))
            _check(self._kernel.UpdateProcThreadAttribute(attributes, 0, 0x2000D, jobs, ctypes.sizeof(jobs), None, None))
            startup = _StartupInfoEx()
            startup.startup.cb = ctypes.sizeof(startup)
            startup.startup.flags = 0x101  # USESTDHANDLES | USESHOWWINDOW
            startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = read, write, error
            startup.attributes = ctypes.cast(attributes, ctypes.c_void_p)
            argv = parameters["args"]
            command = argv if isinstance(argv, str) else subprocess.list2cmdline(argv)
            environment = parameters["env"]
            env_block = None
            if environment is not None:
                env_block = ctypes.create_unicode_buffer("\0".join(
                    f"{key}={value}" for key, value in sorted(environment.items(), key=lambda item: item[0].upper())) + "\0\0")
            info = _ProcessInfo()
            flags = parameters["creationflags"] | 0x00080000 | 0x00000400 | 0x08000000
            _check(self._kernel.CreateProcessW(parameters["executable"], ctypes.create_unicode_buffer(command),
                None, None, True, flags, env_block, os.fsdecode(parameters["cwd"]) if parameters["cwd"] else None,
                ctypes.byref(startup), ctypes.byref(info)))
            self._child_created = True
            self._handle = subprocess.Handle(info.process)
            self.pid = info.pid
            self._kernel.CloseHandle(info.thread)
        finally:
            if initialized:
                self._kernel.DeleteProcThreadAttributeList(attributes)
            self._close_pipe_fds(*(parameters[name] for name in
                                  ("p2cread", "p2cwrite", "c2pread", "c2pwrite", "errread", "errwrite")))

    def _close_job(self):
        with self._job_lock:
            if self._job:
                self._kernel.CloseHandle(self._job)
                self._job = None

    def terminate(self):
        with self._job_lock:
            if self._job:
                _check(self._kernel.TerminateJobObject(self._job, 1))

    kill = terminate

    def poll(self):
        result = super().poll()
        if result is not None:
            self._close_job()
        return result

    def wait(self, timeout=None):
        result = super().wait(timeout)
        self._close_job()
        return result

    def __del__(self):
        if hasattr(self, "_job_lock"):
            self._close_job()
        super().__del__()
