"""Linux birth-owned subprocesses, with one isolated guardian per connection.

The guardian inherits an owner pidfd and a private cancellation pipe before any
native launch. It is a subreaper before spawning. No periodic ps/PID ancestry
snapshot is used. stdout/stderr remain the native pipes.
"""
import os
import errno
from pathlib import Path
import shutil
import subprocess
import sys
import threading

from .linux_process_guardian import pidfd_open


class OwnedLinuxPopen(subprocess.Popen):
    _slots = threading.BoundedSemaphore(32)

    def __init__(self, argv, **kwargs):
        if sys.platform != "linux":
            raise RuntimeError("Linux process ownership requires pidfd support")
        if isinstance(argv, (str, bytes)) or any(kwargs.get(key) for key in ("shell", "preexec_fn", "executable")):
            raise ValueError("Owned Linux processes require argv without shell/preexec overrides")
        if kwargs.get("pass_fds"):
            raise ValueError("Extra inherited descriptors are not supported")
        # Preserve Popen's pre-spawn configuration failures. Otherwise a missing
        # native binary looks like a successfully spawned guardian followed by a
        # protocol EOF. This is only validation; execution can still fail later.
        argv = list(argv)
        if not argv:
            raise ValueError("An executable is required")
        executable = os.fspath(argv[0])
        if os.path.dirname(executable):
            resolved = os.path.join(kwargs.get("cwd") or os.curdir, executable)
        else:
            resolved = shutil.which(executable, path=(kwargs.get("env") or {}).get("PATH", os.defpath))
        if resolved is None or not os.path.exists(resolved):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), executable)
        if not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), executable)
        argv[0] = os.path.abspath(resolved)
        self._ownership_lock = threading.Lock()
        self._cancel_fd = None
        self._proof_fd = None
        self.tree_stopped = False
        self._slot_pool = type(self)._slots
        self._owns_slot = self._slot_pool.acquire(blocking=False)
        if not self._owns_slot:
            raise RuntimeError("Linux owned-process capacity exhausted; unresolved trees retain their slots")
        inherited = []
        try:
            owner_fd = pidfd_open(os.getpid())
            inherited.append(owner_fd)
            cancel_read, self._cancel_fd = os.pipe()
            os.set_blocking(self._cancel_fd, False)
            inherited.append(cancel_read)
            self._proof_fd, proof_write = os.pipe()
            inherited.append(proof_write)
            os.set_blocking(self._proof_fd, False)
            helper = str(Path(__file__).with_name("linux_process_guardian.py"))
            command = [sys.executable, "-I", helper, str(owner_fd), str(cancel_read), str(proof_write), *argv]
            kwargs.update(pass_fds=tuple(inherited), close_fds=True, start_new_session=True)
            super().__init__(command, **kwargs)
        except BaseException:
            self._close_ownership_fds()
            self._release_slot()
            raise
        finally:
            for fd in inherited:
                os.close(fd)

    def _release_slot(self):
        with self._ownership_lock:
            if self._owns_slot:
                self._owns_slot = False
                self._slot_pool.release()

    def _close_ownership_fds(self):
        with self._ownership_lock:
            for name in ("_cancel_fd", "_proof_fd"):
                fd = getattr(self, name)
                if fd is not None:
                    os.close(fd)
                    setattr(self, name, None)

    def kill(self):
        # Never SIGKILL the guardian: it must retain ownership until the owned
        # tree is drained. Closing this pipe requests forceful native cleanup.
        with self._ownership_lock:
            if self._cancel_fd is not None:
                os.close(self._cancel_fd)
                self._cancel_fd = None

    def terminate(self):
        with self._ownership_lock:
            if self._cancel_fd is not None:
                try:
                    os.write(self._cancel_fd, b"T")
                except (BrokenPipeError, BlockingIOError):
                    os.close(self._cancel_fd)
                    self._cancel_fd = None

    def _observe_proof(self, result):
        if result is not None:
            with self._ownership_lock:
                if self._proof_fd is not None:
                    try:
                        self.tree_stopped = os.read(self._proof_fd, 1) == b"D"
                    except BlockingIOError:
                        pass
            self._close_ownership_fds()
            if self.tree_stopped:
                self._release_slot()
        return result

    def poll(self):
        return self._observe_proof(super().poll())

    def wait(self, timeout=None):
        return self._observe_proof(super().wait(timeout=timeout))
