"""Closed, bounded management grammar; errors never echo supplied contents."""
import json
import re

from ..errors import ErrorCode, OktoNexusError

_IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z')


def invalid(field='fields'):
    raise OktoNexusError(ErrorCode.VALIDATION_ERROR, f'Invalid observation {field}.', {'field': field})


def fields(value, required, optional=()):
    if (type(value) is not dict or not set(required) <= value.keys()
            or value.keys() - (set(required) | set(optional))):
        invalid()
    return value


def identity(value, field='identifier'):
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        invalid(field)
    return value


def number(value, field='revision', *, maximum=(1 << 63) - 1):
    if type(value) is not int or not 1 <= value <= maximum:
        invalid(field)
    return value


def opaque(value, field, maximum=256):
    if (type(value) is not str or not 1 <= len(value) <= maximum
            or not value.isprintable() or value.strip() != value):
        invalid(field)
    try:
        value.encode('utf-8')
    except UnicodeError:
        invalid(field)
    return value


def workspaces(value):
    if type(value) is not list or not 1 <= len(value) <= 100:
        invalid('workspace_ids')
    result = [identity(item, 'workspace_id') for item in value]
    if len(result) != len(set(result)):
        invalid('workspace_ids')
    return sorted(result)


def instance_grants(value):
    if type(value) is not list or not 1 <= len(value) <= 100:
        invalid('instance_grants')
    result = []
    for item in value:
        fields(item, ('observed_instance_id', 'generation'))
        result.append(dict(observed_instance_id=identity(item['observed_instance_id']),
                           generation=number(item['generation'], 'generation')))
    if len({item['observed_instance_id'] for item in result}) != len(result):
        invalid('instance_grants')
    return result


def reports(payload):
    values = payload
    if type(payload) is dict and 'reports' in payload:
        fields(payload, ('reports',))
        values = payload['reports']
        if type(values) is not list or not 1 <= len(values) <= 100:
            invalid('reports')
    else:
        values = [payload]
    for value in values:
        try:
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False,
                                 separators=(',', ':')).encode('utf-8')
        except (ValueError, TypeError, UnicodeError, RecursionError):
            invalid('report')
        if len(encoded) > 4096:
            raise OktoNexusError(ErrorCode.CONTENT_TOO_LARGE, 'An observation exceeds 4 KiB.', {})
    return values
