"""Read-only projections. Canonical handoff decisions outrank native output."""
from datetime import datetime
from typing import Protocol
from .handoff_runtime_scheduler import SCHEDULE_REASONS


def public_reason(value):
    return value if value is None or value in SCHEDULE_REASONS | {'RELEASED', 'EXPIRED_UNCONSUMED', 'CANCELLED'} else 'UNKNOWN'


class HandoffRuntimeViewRepository(Protocol):
    def handoffs(self, uow, handoff_ids: list[str]) -> dict[str, dict]: ...
    def agent_attempts(self, uow, agent_id: str, *, limit: int) -> list[dict]: ...
    def sample_attempts(self, uow, *, limit: int) -> list[dict]: ...
    def sample_handoff_ids(self, uow, *, limit: int) -> list[str]: ...


def elapsed_ms(start, end):
    if not start or not end:
        return None
    try:
        delta = (datetime.fromisoformat(end.replace('Z', '+00:00')) -
                 datetime.fromisoformat(start.replace('Z', '+00:00'))).total_seconds()
        return round(delta * 1000) if delta >= 0 else None
    except (ValueError, TypeError):
        return None


def progress(facts, *, automation_enabled=True):
    """Never infer a business outcome from transport, reserve or native final."""
    canonical = facts['status']
    state = {'COMPLETED': 'COMPLETED', 'VERIFYING': 'AWAITING_VERIFICATION',
             'REJECTED': 'REJECTED', 'CANCELLED': 'CANCELLED'}.get(canonical)
    if state is None:
        if canonical == 'OPEN':
            state = 'WAITING_EXECUTOR' if automation_enabled else 'AWAITING_EXPLICIT_CLAIM'
        elif (facts.get('capacity_state') == 'NEEDS_RECONCILIATION'
              or facts.get('native_stage') == 'OUTCOME_UNKNOWN'
              or facts.get('delivery_state') in {'OUTCOME_UNKNOWN', 'SENT_UNCONFIRMED'}):
            state = 'NEEDS_RECONCILIATION'
        elif facts.get('native_stage') in {'FAILED', 'CANCELLED'} or facts.get('delivery_state') in {'REJECTED', 'FAILED_FINAL'}:
            state = 'EXECUTION_FAILED'
        elif facts.get('native_stage') == 'SUCCEEDED' and facts.get('native_action') in {'turn.submit', 'turn.steer'}:
            state = 'AWAITING_DECISION'
        elif facts.get('native_stage') == 'RUNNING':
            state = 'RUNNING'
        elif facts.get('native_stage') == 'WAITING_INPUT':
            state = 'WAITING_INPUT'
        elif facts.get('native_stage') in {'SUBMITTED', 'ACCEPTED'}:
            state = 'DISPATCHED'
        else:
            state = 'CLAIMED' if canonical == 'CLAIMED' else 'UNKNOWN'
    return dict(state=state, canonical_status=canonical, claimed_by=facts.get('claimed_by'),
        winner_channel=('runtime' if facts.get('domain_operation_id') else 'explicit') if facts.get('claimed_by') else None,
        origin=facts.get('source_kind') or 'missing',
        reason=('AUTOMATION_DISABLED' if not automation_enabled else public_reason(facts.get('schedule_reason'))) if canonical == 'OPEN' else None,
        native_stage=facts.get('native_stage'),
        claim_latency_ms=elapsed_ms(facts.get('created_at'), facts.get('claimed_at')),
        execution_delay_ms=elapsed_ms(facts.get('claimed_at'), facts.get('started_at')))


class HandoffRuntimeViews:
    def __init__(self, repository: HandoffRuntimeViewRepository, *, automation_enabled):
        self.repository = repository
        self.automation_enabled = automation_enabled

    def handoffs(self, uow, handoff_ids):
        return {key: progress(value, automation_enabled=self.automation_enabled)
                for key, value in self.repository.handoffs(uow, handoff_ids).items()}

    def agent(self, uow, agent_id):
        rows = self.repository.agent_attempts(uow, agent_id, limit=21)
        items = rows[:20]
        facts = self.repository.handoffs(uow, list({r['handoff_id'] for r in items}))
        for row in items:
            row['reason'] = public_reason(row['reason'])
            current = facts.get(row['handoff_id'])
            row['current_claim'] = bool(current and current['status'] in {'CLAIMED', 'VERIFYING'} and row['operation_id'] and
                                        row['operation_id'] == current['domain_operation_id'])
            row['handoff_progress'] = progress(current, automation_enabled=self.automation_enabled) if current else None
        return dict(items=items, has_more=len(rows) > 20)

    def metrics(self, uow):
        """Bounded historical samples with fixed-cardinality labels, no IDs."""
        limit = 1000
        attempts = self.repository.sample_attempts(uow, limit=limit+1)
        ids = self.repository.sample_handoff_ids(uow, limit=limit+1)
        facts = self.repository.handoffs(uow, ids[:limit])
        states = dict.fromkeys(('WAITING','RESERVING','RESERVED','NOT_AVAILABLE','RELEASE_PENDING',
                               'NEEDS_RECONCILIATION','CLAIM_COMMITTED','CANCELLED_NO_EFFECT','UNKNOWN'), 0)
        reasons = dict.fromkeys(sorted(SCHEDULE_REASONS | {'RELEASED','EXPIRED_UNCONSUMED','CANCELLED','UNKNOWN'}), 0)
        reservations = dict.fromkeys(('HELD','CONSUMED','RELEASE_PENDING','RELEASED','EXPIRED_UNCONSUMED',
                                     'NEEDS_RECONCILIATION','UNKNOWN'), 0)
        for row in attempts[:limit]:
            states[row['state'] if row['state'] in states else 'UNKNOWN'] += 1
            if row['reason'] is not None:
                reasons[public_reason(row['reason'])] += 1
            if row['reservation_state'] is not None:
                reservations[row['reservation_state'] if row['reservation_state'] in reservations else 'UNKNOWN'] += 1
        winners = dict(runtime=0, explicit=0, unclaimed=0)
        claim_times, dispatch_times = [], []
        for row in facts.values():
            view = progress(row, automation_enabled=self.automation_enabled)
            winners[view['winner_channel'] or 'unclaimed'] += 1
            if view['claim_latency_ms'] is not None:
                claim_times.append(view['claim_latency_ms'])
            if view['execution_delay_ms'] is not None:
                dispatch_times.append(view['execution_delay_ms'])
        def latency(values):
            return dict(count=len(values), min_ms=min(values) if values else None,
                max_ms=max(values) if values else None,
                mean_ms=round(sum(values)/len(values)) if values else None)
        return dict(status='available', sample_limit=limit,
            attempt_sample=dict(size=min(len(attempts),limit), truncated=len(attempts)>limit),
            handoff_sample=dict(size=len(facts), truncated=len(ids)>limit),
            recorded_attempt_states=states, recorded_reasons=reasons, recorded_reservation_states=reservations,
            winner_channels=winners, claim_latency=latency(claim_times), execution_delay=latency(dispatch_times))
