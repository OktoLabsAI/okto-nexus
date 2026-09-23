"""An explicit pre-write fence failure is distinguishable from uncertain I/O."""
from ..errors import ErrorCode, OktoNexusError


class RuntimeCommandNotSent(OktoNexusError):
    def __init__(self, message):
        super().__init__(ErrorCode.CONFLICT, message, {})
