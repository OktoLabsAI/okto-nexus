"""External occurrences describe observations; they never authorize work."""
from ..domain.attention import instant, occurrence, stamp
from .observations import ObservationService


def _item(view, *, kind, episode, first, changed, active, resolution='open'):
    head = view['last_report']
    # A preference CAS follows the exact public metadata, including TTL and
    # provenance. The episode identity deliberately excludes heartbeat time.
    item = occurrence(kind=kind, source_type='external_observation',
        source_id=view['observed_instance_id'], episode=episode, source_revision=view,
        first_detected_at=first, last_changed_at=changed,
        agent_id=view['agent_id'], workspace_id=view['workspace_id'],
        severity='warning' if kind != 'external_completion_unseen' else 'info',
        priority=20 if kind == 'external_blocked' else 10,
        allowed_actions=['inspect_external_observation'],
        freshness=view['freshness'] if view['freshness'] != 'unknown' else 'unavailable',
        active=active, resolution=resolution,
        next_change_at=head['valid_until'] if head and view['freshness'] == 'current' else None)
    item['external_observation'] = view
    return item


def project(facts, now, policy):
    row = facts['current']
    config = policy['config']
    head, instance = row['head'], row['instance']
    kind = facts.get('kind')
    completion = facts.get('completion')
    if completion is not None:
        # Keep the current-head corruption check without constructing a second,
        # unused public DTO for every retained completion.
        ObservationService._head_expired(head, now)
        report = completion['report']
        reference = report.get('completion_ref')
        if not reference:
            return []
        historical = dict(row)
        # A current association does not prove that the native session was
        # associated at the time of this immutable completion event.
        historical.pop('correlation', None)
        # Immutable event provenance follows its own publishing authority, not
        # whichever token or report now occupies the instance's current head.
        historical['publisher_revoked'] = completion['publisher_revoked']
        historical['historical_unproven'] = completion['observed_at'] is None
        historical['head'] = dict(report, source_revision=completion['source_revision'],
            observed_at=completion['observed_at'], reason_text=None,
            current_completion_ref=reference, last_completion_ref=reference,
            last_completion_received_at=report['received_at'])
        old = ObservationService._project(historical, now, config)
        old['generation'] = report['generation']
        # Pre-upgrade events may lack their original publisher/observed time.
        # They remain explicitly unavailable historical facts, never invented
        # current observations or newly active notifications.
        proven = completion['source_revision'] is not None and completion['observed_at'] is not None
        if not proven:
            old['freshness'], old['activity_state'] = 'unavailable', 'unknown'
        return [_item(old, kind='external_completion_unseen',
            episode=[report['generation'], report['sequence'], completion['event_id']],
            first=report['received_at'], changed=report['received_at'],
            active=proven and old['freshness'] != 'unavailable', resolution='resolved')]
    if head is None:
        return []
    current = dict(row, correlation=policy['correlations'].get(instance['observed_instance_id']))
    view = ObservationService._project(current, now, config)
    result = []
    anchor = facts.get('anchor')
    if kind in (None, 'external_blocked') and head['state'] == 'blocked' and anchor and anchor['blocked_sequence'] is not None:
        first = anchor['blocked_started_at']
        result.append(_item(view, kind='external_blocked',
            episode=[instance['generation'], anchor['blocked_sequence']], first=first,
            changed=max(stamp(first), stamp(head['received_at'])),
            active=view['freshness'] == 'current',
            resolution='open' if view['freshness'] == 'current' else 'expired'))
    expired = instant(head['valid_until']) <= instant(now)
    if kind in (None, 'external_observation_stale') and expired:
        result.append(_item(view, kind='external_observation_stale',
            episode=[instance['generation'], head['sequence']], first=head['valid_until'],
            changed=head['valid_until'], active=view['freshness'] == 'stale',
            resolution='open' if view['freshness'] == 'stale' else 'expired'))
    return result
