"""Shared deterministic selection after each intent's own authorization checks."""
from ..errors import ErrorCode, OktoNexusError


def select_runtime_endpoint(candidates):
    """Choose an existing affinity first, then priority and approved group.

    Tuples contain (endpoint, intent-specific context, existing session ID).
    Capacity is deliberately not a tie-breaker: a busy selected affinity must
    not silently redirect work to a different binding.
    """
    if not candidates:
        return None
    ready = [candidate for candidate in candidates if candidate[2]]
    candidates = ready or candidates
    priority = max(candidate[0]['priority'] for candidate in candidates)
    candidates = [candidate for candidate in candidates if candidate[0]['priority'] == priority]
    groups = {candidate[0]['selection_group'] for candidate in candidates}
    if len(candidates) > 1 and (len(groups) != 1 or None in groups):
        raise OktoNexusError(ErrorCode.CONFLICT, 'AMBIGUOUS_BINDING', {'reason': 'AMBIGUOUS_BINDING'})
    return min(candidates, key=lambda candidate: candidate[0]['endpoint_id'])
