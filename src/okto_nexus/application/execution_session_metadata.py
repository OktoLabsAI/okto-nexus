"""Bounded, opaque session annotations; never merge them into runtime context."""
import json
from nexus_connector_core.protocol import canonical_json
from ..errors import ErrorCode, OktoNexusError


def normalize_metadata(value):
    try:
        if isinstance(value, str):
            if len(value.encode('utf-8')) > 16384:
                raise ValueError()
            value = json.loads(value)
        if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
            raise ValueError()
        encoded = canonical_json(value)
        if len(encoded) > 16384:
            raise ValueError()
        return json.loads(encoded)
    except (ValueError, TypeError, RecursionError) as exc:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
            'Session metadata must be a JSON object of at most 16384 bytes.', {}) from exc
