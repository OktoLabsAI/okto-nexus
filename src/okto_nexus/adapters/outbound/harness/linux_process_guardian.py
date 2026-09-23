"""Isolated Linux subreaper. Invoked by OwnedLinuxPopen, never by payload commands.

Only direct, unreaped children are signalled. A guardian externally SIGKILLed
cannot attest cleanup: the parent requires the final proof byte for observed stop.
"""
import ctypes
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys


def _children():
    return [int(pid) for pid in Path(f"/proc/self/task/{os.getpid()}/children").read_text().split()]


def _reap_exited_except(leader):
    while True:
        try:
            child = os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        except ChildProcessError:
            return False
        if child is None:
            return False
        if child.si_pid == leader:
            return True  # Keep leader unreaped until its process group is killed.
        os.waitpid(child.si_pid, 0)


def run(owner_fd, cancel_fd, proof_fd, argv):
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "Cannot establish Linux child subreaper")
    signal.signal(signal.SIGCHLD, lambda *_: None)
    signal.signal(signal.SIGTERM, lambda *_: None)
    signal.signal(signal.SIGINT, lambda *_: None)
    wake_read, wake_write = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
    signal.set_wakeup_fd(wake_write)
    monitor = selectors.DefaultSelector()
    monitor.register(owner_fd, selectors.EVENT_READ, "owner")
    monitor.register(cancel_fd, selectors.EVENT_READ, "cancel")
    monitor.register(wake_read, selectors.EVENT_READ, "signal")
    # Death between this check and Popen is still protected by this subreaper;
    # the ready owner pidfd then takes us directly into cleanup.
    if monitor.select(0):
        os.write(proof_fd, b"D")
        return 125
    try:
        native = subprocess.Popen(argv, close_fds=True, start_new_session=True)
    except BaseException:
        # Popen failed before returning a live child; its exec-error handling
        # has already waited for that child. No native tree was admitted.
        os.write(proof_fd, b"D")
        raise
    try:
        leader_fd = os.pidfd_open(native.pid)
        monitor.register(leader_fd, selectors.EVENT_READ, "leader")
        done = False
        while not done:
            for key, _ in monitor.select():
                if key.data == "cancel":
                    request = os.read(cancel_fd, 64)
                    if request:
                        if b"T" in request:
                            try:
                                os.killpg(native.pid, signal.SIGTERM)
                            except ProcessLookupError:
                                pass
                        continue
                if key.data != "signal":
                    done = True
                    break
                signals = os.read(wake_read, 4096)
                if signal.SIGTERM in signals or signal.SIGINT in signals:
                    done = True
                    break
                if _reap_exited_except(native.pid):
                    done = True
                    break
    finally:
        for key in list(monitor.get_map().values()):
            if key.data != "signal":
                monitor.unregister(key.fd)
        # The native leader has never been reaped, so this PGID cannot have
        # been recycled. Escaped descendants are adopted by this subreaper.
        try:
            os.killpg(native.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        status = None
        while True:
            # No other thread/signal handler reaps children; each PID remains
            # our unreaped child while its pidfd is acquired and signalled.
            for pid in _children():
                try:
                    # This process is a direct child and only this thread can
                    # reap it. Its PID cannot be recycled during this call.
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            while True:
                try:
                    pid, observed = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    os.write(proof_fd, b"D")
                    return os.waitstatus_to_exitcode(status) if status is not None else 125
                if not pid:
                    break
                if pid == native.pid:
                    status = observed
            # Bounded wait between cleanup passes; no queries to the harness.
            # An unkillable child keeps this guardian alive rather than losing
            # ownership or fabricating cleanup success after a deadline.
            ready = monitor.select(.1)
            if any(key.data == "signal" for key, _ in ready):
                try:
                    os.read(wake_read, 4096)
                except BlockingIOError:
                    pass


if __name__ == "__main__":
    try:
        code = run(int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4:])
    except Exception as exc:
        print(f"Nexus Linux ownership failed: {type(exc).__name__}", file=sys.stderr, flush=True)
        code = 126
    sys.exit(code if code >= 0 else 128 - code)
