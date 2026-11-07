"""Pure public projection of authenticated, batch-loaded correlation facts.

The caller supplies the authorized observation view and adapter-validated facts.
This module neither authenticates nor refreshes them. A matching relationship
can expose historical native facts; it never establishes present liveness,
capacity, or an effective activity state for the external observer.
"""
from datetime import datetime

from ..domain.observation_correlation import (
    EXTERNAL_PROVENANCE, MAX_INT64, NATIVE_PROVENANCE, normalize_selection,
)
from .observation_correlation_service import canonical_matches


_REFERENCE_FIELDS = (
    'server_id', 'executor_id', 'session_id', 'open_operation_id',
    'session_owner_generation', 'stream_epoch',
)
_LIFECYCLE_STATES = frozenset({'OPEN_PENDING', 'READY', 'CLOSED', 'FAILED'})
_PROVENANCE = dict(external_binding_provenance=EXTERNAL_PROVENANCE,
                   native_birth_provenance=NATIVE_PROVENANCE)
_RECEIPT_FIELDS = (
    'status', 'operation_id', 'action', 'stage', 'receipt_revision', 'received_at', 'provenance',
)


def _timestamp(value):
    return (type(value) is str and len(value) <= 64
            and datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is not None)


def _receipt(value):
    if value is None:
        return None
    unknown = dict(status='unknown', reason='receipt_provenance_unavailable')
    if type(value) is not dict or value.get('status') != 'verified' or value.get('provenance') != 'core_committed':
        return unknown
    try:
        if (any(type(value[key]) is not str or not 1 <= len(value[key]) <= 160
                or not value[key].isprintable() for key in ('operation_id', 'action', 'stage'))
                or type(value['receipt_revision']) is not int or not 1 <= value['receipt_revision'] <= MAX_INT64
                or not _timestamp(value['received_at'])):
            return unknown
        return {key: value[key] for key in _RECEIPT_FIELDS}
    except (KeyError, ValueError, TypeError, OverflowError):
        return unknown


def attach_canonical(view: dict, facts: dict | None) -> dict:
    """Return a new view with minimal native metadata, or two explicit nulls.

    External activity and report fields retain their existing meaning. Private
    proof, process identity, frame bodies and extra native fields never enter
    the newly attached objects. A stale external report alone does not erase a
    still-matching historical correlation; unavailability or changed fences do.
    """
    result = dict(view, canonical_session_ref=None, canonical_observation=None)
    if facts is None or view.get('freshness') == 'unavailable':
        return result
    try:
        correlation, native = facts['correlation'], facts['native']
        if correlation is None or correlation['state'] != 'selected':
            return result
        selected = normalize_selection(correlation['selection'])
        if (any(type(view[key]) is not type(selected[key]) or view[key] != selected[key] for key in (
                'observed_instance_id', 'source_id', 'source_revision', 'generation'))
                or correlation['observed_instance_id'] != view['observed_instance_id']
                or any(correlation[key] != view[key] for key in ('agent_id', 'workspace_id'))
                or type(correlation['revision']) is not int
                or correlation['revision'] != selected['expected_correlation_revision'] + 1
                or correlation['provenance'] != _PROVENANCE
                or not _timestamp(correlation['verified_at'])
                or not canonical_matches(native, selected, agent_id=view['agent_id'],
                                         workspace_id=view['workspace_id'], live=False)):
            return result
        lifecycle = native['lifecycle_state']
        result['canonical_session_ref'] = {key: selected[key] for key in _REFERENCE_FIELDS}
        result['canonical_observation'] = dict(
            correlation_revision=correlation['revision'], verified_at=correlation['verified_at'],
            provenance=dict(_PROVENANCE),
            session_lifecycle_state=lifecycle if type(lifecycle) is str and lifecycle in _LIFECYCLE_STATES else 'UNKNOWN',
            last_received_receipt=_receipt(facts['last_received_receipt']),
            precedence='canonical_core_facts',
        )
    except (KeyError, ValueError, TypeError, OverflowError):
        # Missing/corrupt private facts cannot make a previous enrichment current.
        result['canonical_session_ref'] = result['canonical_observation'] = None
    return result
