"""Revisioned one-shot defaults and independent per-agent overrides.

Called inside an operator-authorized unit of work. Policy changes affect new
admission limits; an admitted call keeps its timeout snapshot.
"""
import json

from nexus_connector_core.models import CoreError
from nexus_connector_core.one_shot import OneShotPolicy, validate_one_shot_policy

from ..errors import ErrorCode, OktoNexusError


def _scope(agent_id):
    return 'agent:' + agent_id if agent_id is not None else 'global'


def read(conn, agent_id=None):
    if agent_id is not None and not conn.execute('SELECT 1 FROM agents WHERE agent_id=?', (agent_id,)).fetchone():
        raise OktoNexusError(ErrorCode.NOT_FOUND, 'Agent not found.', {})
    base = conn.execute("SELECT * FROM one_shot_policy_settings WHERE scope='global'").fetchone()
    defaults = validate_one_shot_policy(json.loads(base['policy_json'])).to_dict()
    row = conn.execute('SELECT * FROM one_shot_policy_settings WHERE scope=?', (_scope(agent_id),)).fetchone()
    overrides = json.loads(row['policy_json']) if row else {}
    return dict(revision=row['revision'] if row else 0, settings=overrides,
                defaults=defaults, effective=validate_one_shot_policy(defaults | overrides).to_dict())


def save(conn, *, expected_revision, settings, agent_id=None):
    if not conn.in_transaction:
        raise RuntimeError('Policy writes require the authorized write transaction.')
    fields = set(OneShotPolicy.__dataclass_fields__)
    if (type(expected_revision) is not int or expected_revision < 0 or type(settings) is not dict
            or set(settings) - fields or (agent_id is None and set(settings) != fields)):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid one-shot settings.', {})
    current = read(conn, agent_id)
    if current['revision'] != expected_revision:
        raise OktoNexusError(ErrorCode.CONFLICT, 'One-shot settings changed. Reload before saving.', {})
    # An omitted/null agent field inherits; global settings must be complete.
    values = {k: v for k, v in settings.items() if v is not None} if agent_id else dict(settings)
    try:
        validate_one_shot_policy(current['defaults'] | values)
        if agent_id is None:
            for row in conn.execute("SELECT policy_json FROM one_shot_policy_settings WHERE scope<>'global'"):
                validate_one_shot_policy(values | json.loads(row[0]))
    except CoreError as error:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                            'One-shot limits must remain valid for global settings and every agent override.', {}) from error
    if current['settings'] == values:
        return current
    conn.execute('INSERT INTO one_shot_policy_settings(scope,revision,policy_json) VALUES(?,?,?) '
                 'ON CONFLICT(scope) DO UPDATE SET revision=excluded.revision,policy_json=excluded.policy_json',
                 (_scope(agent_id), expected_revision + 1, json.dumps(values, sort_keys=True)))
    return read(conn, agent_id)
