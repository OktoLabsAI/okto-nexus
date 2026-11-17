"""Public Harness ID metadata; deliberately separate from Core configuration."""
from dataclasses import asdict, dataclass
import re

from ..errors import ErrorCode, OktoNexusError


REFERENCE_FIELDS = ('server_id', 'executor_id', 'binding_id', 'endpoint_id',
                    'agent_id', 'workspace_id', 'workspace_binding_id')


def invalid(message='Invalid Harness ID metadata.'):
    raise OktoNexusError(ErrorCode.VALIDATION_ERROR, message, {'reason': 'CONNECT_ID_INVALID'})


def connect_id(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', value) is None:
        invalid('Harness ID must start with an ASCII letter and contain at most 64 letters, digits, underscores or hyphens.')
    return value.lower()


@dataclass(frozen=True)
class PublicConnection:
    version: int
    connect_id: str
    reservation_ref: str
    project_revision: str


def normalize(value):
    if type(value) is not dict or set(value) != {'version', 'connect_id', 'reservation_ref', 'project_revision'}:
        invalid()
    if type(value['version']) is not int or value['version'] != 1:
        invalid()
    if type(value['reservation_ref']) is not str or not re.fullmatch(r'pcr_[a-f0-9]{32}', value['reservation_ref']):
        invalid('Use the stable public ID reservation reference from this review.')
    if type(value['project_revision']) is not str or not re.fullmatch(r'sha256:[a-f0-9]{64}', value['project_revision']):
        invalid('Use the current canonical project revision.')
    return asdict(PublicConnection(1, connect_id(value['connect_id']), value['reservation_ref'], value['project_revision']))


def canonical_reference(value):
    if type(value) is not dict or set(value) != set(REFERENCE_FIELDS) or any(
            type(value[name]) is not str or not 1 <= len(value[name]) <= 160 or not value[name].isprintable()
            for name in REFERENCE_FIELDS):
        invalid('Use the complete canonical binding reference.')
    return {name: value[name] for name in REFERENCE_FIELDS}
