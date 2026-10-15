"""Verified creator affinity is provenance, never execution authority."""
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class HandoffOrigin:
    source_session_key: str = ''
    schema_version: int = 1

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError('Unsupported handoff origin version.')
        key = self.source_session_key
        if type(key) is not str or len(key) > 2048:
            raise ValueError('Invalid handoff origin.')
        if key:
            parts = json.loads(key)
            if (type(parts) is not list or not parts or
                    ((parts[0] == 'runtime' and len(parts) != 4) or
                     (parts[0] == 'mcp' and len(parts) != 2) or parts[0] not in ('runtime', 'mcp')) or
                    any(type(part) is not str or not 1 <= len(part) <= 160 or not part.isprintable() for part in parts)):
                raise ValueError('Invalid handoff origin.')
            if json.dumps(parts, separators=(',', ':')) != key:
                raise ValueError('Handoff origin must be canonical.')

    @property
    def kind(self):
        return json.loads(self.source_session_key)[0] if self.source_session_key else 'missing'
