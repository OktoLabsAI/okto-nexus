"""Authenticated runtime command use cases shared by inbound surfaces."""
from collections.abc import Mapping

from ..domain.base import check_inline_size
from ..errors import ErrorCode, OktoNexusError


def validate_runtime_payload(value, *, required):
    if value is None and not required:
        return {}
    if (not isinstance(value, Mapping) or set(value) - {"text", "content"}
            or (required and len(value) != 1) or (not required and value)
            or any(not isinstance(v, str) or not v for v in value.values())):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                            "Use one text/content string for a conversational turn; native options are not accepted.", {})
    check_inline_size("runtime payload", value, 65536)
    return dict(value)


class RuntimeControlService:
    def __init__(self, *, access, supervisor):
        self.access, self.supervisor = access, supervisor

    def send(self, context, *, session_id, verb, payload):
        if verb not in {"send_turn", "steer", "interrupt"}:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Unsupported runtime control.", {})
        action = "send" if verb == "send_turn" else verb
        # Authorize before validation so unauthorized callers get opaque errors.
        self.access.authorize(context, action=action, session_id=session_id)
        payload = validate_runtime_payload(payload, required=verb != "interrupt")
        self.access.authorize(context, action=action, session_id=session_id, consume=True)
        return self.supervisor.send(session_id, verb, payload)

    def close(self, context, *, session_id):
        self.access.authorize(context, action="close", session_id=session_id)
        return self.supervisor.close(session_id)

    def replay(self, context, *, session_id, after_sequence=0, limit=200):
        self.access.authorize(context, action="events", session_id=session_id)
        return self.supervisor.replay_events(session_id, after_sequence=after_sequence, limit=limit)
