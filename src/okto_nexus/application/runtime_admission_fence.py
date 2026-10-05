"""Process-local shutdown fence shared by canonical runtime entry points."""
import threading

from ..errors import ErrorCode, OktoNexusError


class RuntimeAdmissionFence:
    def __init__(self):
        self._closed = threading.Event()

    def close(self):
        # No database/native wait may postpone the admission fence.
        self._closed.set()

    @property
    def closed(self):
        return self._closed.is_set()

    def require(self, action, *, returning_external_work=False):
        productive = action in {
            "open", "send", "steer", "execute_work",
            "runtime.open", "turn.submit", "turn.steer",
        }
        if productive and not (returning_external_work and action == "execute_work") and self.closed:
            raise OktoNexusError(ErrorCode.CONFLICT,
                "Runtime shutdown is in progress; new work is not accepted.",
                {"reason": "RUNTIME_DRAINING"})
