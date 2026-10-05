"""An explicit pre-write fence failure is distinguishable from uncertain I/O."""
from ..errors import ErrorCode, OktoNexusError


class RuntimeCommandNotSent(OktoNexusError):
    def __init__(self, message):
        super().__init__(ErrorCode.CONFLICT, message, {})


class RuntimeLaneBusyBeforeWrite(RuntimeCommandNotSent):
    """The local adapter refused a new turn before invoking native transport.

    This typed, transient proof permits a bounded retry of the same delivery.
    It grants neither endpoint transfer nor retry of control/continuation commands.
    """
