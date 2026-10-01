"""Historical adapter error identities retained for safe diagnostic redaction."""
MAX_FRAME_CHARS = 262_144


class NativeEventOverflow(RuntimeError):
    def __init__(self):
        super().__init__("native event buffer overflow; outcome unknown")


class NativeReplayExpired(RuntimeError):
    def __init__(self):
        super().__init__("native event replay expired; use canonical durable replay")


class NativeSubscriptionLimit(RuntimeError):
    pass


class FrameLimitExceeded(ValueError):
    def __init__(self):
        super().__init__(f"frame_limit_exceeded: maximum {MAX_FRAME_CHARS} characters")
