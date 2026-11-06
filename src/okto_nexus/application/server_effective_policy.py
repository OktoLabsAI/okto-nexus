"""Durable generations of policy actually applied by the active Server.

Publication belongs to the Server holding its ServeLock, or its bound settings
callback. This storage helper cannot establish process ownership: callers must
hold that fence and supply their existing writer unit of work. Reads, ordinary
MCP processes and persisted-settings changes must never publish inferred values.
"""
from datetime import datetime, timezone


POLICY_KEYS = frozenset({'feature_harness_integrations', 'feature_hitl'})


def read_effective_policy(uow):
    """Read metadata without initializing missing policy or changing history."""
    return {row['key']: dict(value=bool(row['value']), generation=row['generation'],
        changed_at=row['changed_at']) for row in uow.connection.execute(
            'SELECT key,value,generation,changed_at FROM server_effective_policy ORDER BY key')}


def publish_effective_policy(uow, *, values: dict[str, bool], now: str):
    """Publish changed values atomically within the caller's transaction.

    Equal values perform no UPDATE, including on restart or a later clock tick.
    A changed value always advances its generation, even at the same timestamp.
    This function neither commits nor obtains configuration, locks or a clock.
    """
    if (not isinstance(values, dict) or not values.keys() <= POLICY_KEYS
            or any(type(value) is not bool for value in values.values())):
        raise ValueError('Effective Server policy requires known keys and boolean values.')
    try:
        parsed = datetime.fromisoformat(now.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError
        timestamp = parsed.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')
    except (AttributeError, TypeError, ValueError):
        raise ValueError('Effective Server policy requires an ISO timestamp with timezone.') from None
    for key, value in sorted(values.items()):
        uow.connection.execute('''INSERT INTO server_effective_policy(key,value,generation,changed_at)
            VALUES(?,?,1,?) ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,generation=server_effective_policy.generation+1,
                changed_at=excluded.changed_at
            WHERE server_effective_policy.value<>excluded.value''', (key, int(value), timestamp))
    return read_effective_policy(uow)
