"""Compare the published R4 preview shape across two separately installed wheels."""

import json
import sys
from hashlib import sha256
from pathlib import Path

from nexus_connector_core import (
    R4_PREVIEW_REVISION,
    CoreError,
    decode_control_frame,
    encode_r4_frame,
    r4_submit_intent_hash,
)
from nexus_connector_core.protocol import canonical_json

old = sys.argv[1] == "baseline"
frame = {
    "protocol_major": 1,
    "contract_revision": R4_PREVIEW_REVISION,
    "type": "operation.submit",
    "server_id": "server",
    "executor_id": "executor",
    "binding_id": "binding",
    "agent_id": "agent",
    "workspace_id": "workspace",
    "workspace_binding_id": "workspace-binding",
    "session_id": "session",
    "session_owner_generation": 1,
    "authorization_revision": 1,
    "configuration_revision": 1,
    "binding_revision": 1,
    "credential_epoch": 1,
    "connection_id": "connection",
    "connection_generation": 1,
    "grant_id": "grant",
    "operation_id": "operation",
    "action": "turn.submit",
    "payload": {"text": "/skill:reported ß  "},
}
frame["intent_hash"] = r4_submit_intent_hash(frame)
ordinary = encode_r4_frame(frame)
assert decode_control_frame(ordinary) == frame
literal = frame | {"payload": frame["payload"] | {"literal": True}}
literal["intent_hash"] = r4_submit_intent_hash(literal)
raw = canonical_json(literal)
try:
    decode_control_frame(raw)
except CoreError as error:
    assert error.code == ("VALIDATION_ERROR" if old else "VERSION_INCOMPATIBLE")
    code = error.code
else:
    raise AssertionError("Unnegotiated literal input entered an operation lane")
if not old:
    from nexus_connector_core.turn_operation import (
        PI_LITERAL_INPUT_REVISION,
        r4_turn_operation,
    )

    accepted = r4_turn_operation(
        decode_control_frame(raw, capabilities=(PI_LITERAL_INPUT_REVISION,))
    )
    assert accepted.literal is True and accepted.text == frame["payload"]["text"]
    omitted = frame | {"intent_hash": literal["intent_hash"]}
    try:
        decode_control_frame(
            canonical_json(omitted), capabilities=(PI_LITERAL_INPUT_REVISION,)
        )
    except CoreError as error:
        assert error.code == "VALIDATION_ERROR" and error.stage == "r4_intent_hash"
    else:
        raise AssertionError("Discarding literal intent retained the hash")
result = {
    "ordinary_frame_sha256": sha256(ordinary).hexdigest(),
    "ordinary_intent_hash": frame["intent_hash"],
    "literal_intent_hash": literal["intent_hash"],
    "unnegotiated_literal": code,
    "negotiated_literal_validated": not old,
}
Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
