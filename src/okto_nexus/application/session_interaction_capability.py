"""Derive next-turn support from the current owner and exact Core build."""

import json
from dataclasses import asdict

from nexus_connector_core import CAPACITY_CONTRACT_REVISION

from ..adapters.outbound.sqlite.execution_leases import SqliteExecutionLeaseRepository
from ..adapters.outbound.sqlite.session_interaction import (
    _current_session,
    _scope_params,
)
from ..adapters.outbound.sqlite.session_interaction_queue_controls import (
    has_unresolved_interrupt,
)
from ..domain.attention import digest
from ..domain.session_interaction import InputScope
from .execution_inventory_freshness import inventory_is_fresh
from .execution_inventory_revalidation import accepts_binding, selection
from .executor_inventory import load_current_executor_inventory


def queue_pause_revision(uow, scope: InputScope, paused: bool, *, current_next_turn_revision) -> str | None:
    if not _current_session(uow.connection, _scope_params(scope), require_active_lease=not paused):
        return None
    next_turn = None
    if not paused:
        if has_unresolved_interrupt(uow.connection, scope.session):
            return None
        next_turn = current_next_turn_revision(uow, scope)
        if next_turn is None:
            return None
    return 'sha256:' + digest({'action': 'queue.pause.v1' if paused else 'queue.resume.v1',
                              'scope': _scope_params(scope), 'next_turn': next_turn})


def next_turn_revision(uow, scope: InputScope, *, availability, fresh_publications) -> str | None:
    """Return a technical revision only. Human and grant authority are separate."""
    session = asdict(scope.session)
    key = (scope.session.server_id, scope.session.executor_id)
    host = availability.current_host(*key)
    if host is None or not host.boot_id:
        return None
    observation = host.observations.get(scope.binding_id)
    if observation is None or observation[2] <= availability.monotonic():
        return None

    conn = uow.connection
    if not _current_session(conn, _scope_params(scope), require_active_lease=True):
        return None
    leases = SqliteExecutionLeaseRepository()
    owner = leases.authority(uow, session)
    if (owner is None or owner['control_state'] != 'CONTROL_READY' or owner['revoked_at'] is not None
            or (owner['owner_instance_id'], owner['generation']) != (
                host.channel.connection_id, host.channel.connection_generation
            )):
        return None
    if owner['kind'] == 'remote' and not host.channel.supports_work_containment:
        return None

    opening = json.loads(owner['semantic_payload'])
    payload = opening.get('payload', {})
    adapter, candidate = owner['adapter_id'], owner['candidate_ref']
    if (opening.get('action') != 'runtime.open' or payload.get('mode') != 'managed'
            or (payload.get('adapter_id'), payload.get('candidate_ref')) != (adapter, candidate)):
        return None

    inventory = leases.inventory(uow, session)
    if (not inventory_is_fresh(inventory, fresh_publications.get(key), adapter)
            or not accepts_binding(conn, owner, inventory['inventory_revision'], *key)):
        return None
    snapshot = load_current_executor_inventory(inventory['canonical_projection'])
    selected = selection(snapshot, adapter, candidate)
    if selected is None or selected['runtime']['connection_mode'] != 'managed':
        return None
    evidence = selected['evidence']
    if (evidence['state'] != 'READY_FOR_RUNTIME' or evidence['trust'] != 'selected'
            or evidence['qualification'] != 'qualified'):
        return None

    opening_revision = payload.get('inventory_revision')
    if opening_revision != inventory['inventory_revision']:
        launched = conn.execute("""
            SELECT canonical_projection FROM execution_inventory_snapshots
            WHERE server_id=? AND executor_id=? AND inventory_revision=?
            ORDER BY publication_sequence DESC LIMIT 1
        """, (*key, opening_revision)).fetchone()
        if launched is None:
            return None
        original = selection(json.loads(launched['canonical_projection']), adapter, candidate)
        if original is None or _build(original['evidence']) != _build(evidence):
            return None

    # Lease renewal and publication heartbeats preserve the revision. Exact
    # capacity requests independently carry the current boot and connection.
    return 'sha256:' + digest({
        'scope': _scope_params(scope),
        'binding_revision': owner['binding_revision'],
        'contract': CAPACITY_CONTRACT_REVISION,
        'candidate': candidate,
        'adapter': adapter,
        'build': _build(evidence),
    })


def _build(evidence):
    return {field: evidence.get(field) for field in (
        'content_fingerprint', 'build_identity', 'version', 'platform', 'architecture', 'qualification',
    )}
