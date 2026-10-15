"""Revisioned public MCP presets for runtime endpoints.

The caller supplies the operator-authorized transaction. Saving a preset does
not mutate a live session, the host's files, endpoint authority or secret vault.
New openings must capture snapshot() in their signed launch configuration.
"""
import json

from nexus_connector_core.mcp_presets import mcp_preset_digest, validate_mcp_preset
from nexus_connector_core.models import CoreError

from ..errors import ErrorCode, OktoNexusError


def _endpoint(conn, endpoint_id):
    row = conn.execute('SELECT protocol FROM agent_endpoints WHERE endpoint_id=?', (endpoint_id,)).fetchone()
    if row is None:
        raise OktoNexusError(ErrorCode.NOT_FOUND, 'Runtime endpoint not found.', {})
    if row[0] != 'nxl-r4':
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'MCP presets apply only to runtime connections.', {})


def snapshot(conn, endpoint_id):
    _endpoint(conn, endpoint_id)
    row = conn.execute('SELECT * FROM runtime_mcp_presets WHERE endpoint_id=?', (endpoint_id,)).fetchone()
    if row is None:
        return dict(revision=0, servers=[], configuration_digest=mcp_preset_digest([]))
    servers = validate_mcp_preset(json.loads(row['preset_json']))
    if mcp_preset_digest(servers) != row['configuration_digest']:
        raise OktoNexusError(ErrorCode.CONFLICT, 'MCP preset integrity check failed.', {})
    return dict(revision=row['revision'], servers=servers, configuration_digest=row['configuration_digest'])


def save(conn, *, endpoint_id, expected_revision, servers):
    if not conn.in_transaction:
        raise RuntimeError('MCP preset writes require the authorized write transaction.')
    if type(expected_revision) is not int or expected_revision < 0:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid MCP preset revision.', {})
    current = snapshot(conn, endpoint_id)
    if current['revision'] != expected_revision:
        raise OktoNexusError(ErrorCode.CONFLICT, 'MCP preset changed. Reload before saving.', {})
    try:
        normalized = validate_mcp_preset(servers)
    except CoreError as error:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, str(error), {}) from error
    if normalized == current['servers']:
        return current
    digest = mcp_preset_digest(normalized)
    conn.execute('INSERT INTO runtime_mcp_presets VALUES(?,?,?,?) ON CONFLICT(endpoint_id) DO UPDATE SET '
                 'revision=excluded.revision,preset_json=excluded.preset_json,configuration_digest=excluded.configuration_digest',
                 (endpoint_id, expected_revision + 1, json.dumps(normalized, sort_keys=True), digest))
    return snapshot(conn, endpoint_id)
