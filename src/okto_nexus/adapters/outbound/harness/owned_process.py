"""Launch only processes owned by this connector; never used for attach."""
import os
import signal
import subprocess

from ....application.runtime_lifecycle import current_lifecycle


def spawn_owned_process(argv, **kwargs):
    scope = current_lifecycle.get()
    if scope is not None:
        scope.check()
    if os.name == "nt":
        from .windows_process import OwnedWindowsPopen
        process = OwnedWindowsPopen(argv, **kwargs)
        stop = process.kill
    else:
        # A new group supports explicit teardown. Owner-crash guarantees on
        # POSIX require the separate guardian work; do not equate it with a Job.
        kwargs["start_new_session"] = True
        process = subprocess.Popen(argv, **kwargs)

        def stop():
            # While the leader is an unreaped child its PID cannot be reused.
            with process._waitpid_lock:
                if process.returncode is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    if scope is not None:
        scope.register(stop)
    return process
