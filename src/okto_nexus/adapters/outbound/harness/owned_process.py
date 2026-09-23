"""Launch only processes owned by this connector; never used for attach."""
import os
import sys

from ....application.runtime_lifecycle import current_lifecycle
from ....errors import ErrorCode, OktoNexusError


def observe_owned_process(process):
    exit_code = process.poll() if process is not None else None
    confirmed = getattr(process, "tree_stopped", True)
    return {"stop_observed": exit_code is not None and confirmed, "exit_code": exit_code}


def spawn_owned_process(argv, **kwargs):
    scope = current_lifecycle.get()
    if scope is not None:
        scope.check()
    if os.name == "nt":
        from .windows_process import OwnedWindowsPopen
        process = OwnedWindowsPopen(argv, **kwargs)
        stop = process.kill
    elif sys.platform == "linux":
        from .linux_process import OwnedLinuxPopen
        process = OwnedLinuxPopen(argv, **kwargs)
        stop = process.kill
    else:
        raise OktoNexusError(ErrorCode.CONFIG_ERROR,
            "Managed process birth ownership is supported on Windows and Linux only.",
            {"reason": "platform_unsupported"})

    if scope is not None:
        scope.register(stop)
    return process
