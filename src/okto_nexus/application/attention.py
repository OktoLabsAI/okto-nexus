"""Operator projection and independent seen/snooze controls."""
from copy import deepcopy
from datetime import timedelta

from ..domain.attention import (
    VERSION, decode_cursor, encode_cursor, identity, instant, invalid,
    normalize_filters, stamp,
)
from ..errors import ErrorCode, OktoNexusError


class AttentionService:
    def __init__(self, *, factory, access, queries, clock, config):
        self.factory, self.access, self.queries = factory, access, queries
        self.clock, self.config = clock, config

    def _authorize(self, uow, context):
        if context is None or not self.access.authenticate(context, uow=uow, require_feature=False):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'An authenticated operator is required for attention.', {})
        if not self.config.feature_attention:
            raise OktoNexusError('FEATURE_DISABLED', 'The attention view is disabled. Existing work controls remain available.', {})

    def _snapshot(self, *, context, filters, cursor=None, limit=50):
        filters = normalize_filters(filters)
        if type(limit) is not int or not 0 <= limit <= 200:
            invalid('Attention page size must be between 1 and 200.')
        after = decode_cursor(cursor, filters=filters) if cursor is not None else None
        with self.factory.unit_of_work(write=False) as uow:
            self._authorize(uow, context)
            now, config = stamp(self.clock.now_iso()), deepcopy(self.config)
            value = self.queries.snapshot(uow, filters=filters, now=now, config=config,
                                          access=self.access, context=context, after=after, limit=limit)
        items = value.pop('items')
        more = bool(limit and len(items) > limit)
        items = items[:limit]
        next_cursor = encode_cursor(filters=filters, snapshot_revision=value['snapshot_revision'], item=items[-1]) if more else None
        deadline = instant(now) + timedelta(seconds=15)
        if value['next_change_at'] is not None:
            deadline = min(deadline, instant(value['next_change_at']))
        value.pop('next_change_at')
        return dict(value, version=VERSION, filters=filters, items=items, next_cursor=next_cursor,
                    observed_at=now, next_refresh_at=deadline.isoformat(timespec='microseconds'),
                    refresh_after_seconds=max(0.0, (deadline - instant(now)).total_seconds()))

    def read(self, *, context, filters=None, cursor=None, limit=50):
        if type(limit) is not int or not 1 <= limit <= 200:
            invalid('Attention page size must be between 1 and 200.')
        return self._snapshot(context=context, filters=filters, cursor=cursor, limit=limit)

    def summary(self, *, context, filters=None):
        result = self._snapshot(context=context, filters=filters, limit=0)
        result.pop('items')
        result.pop('next_cursor')
        return result

    def _preference(self, *, context, attention_id, source_revision, preference_revision, seen=None, until=None, snooze=False):
        identity(attention_id)
        identity(source_revision)
        if type(preference_revision) is not int or preference_revision < 0:
            invalid('Use the viewing revision from the current occurrence.')
        if not snooze and type(seen) is not bool:
            invalid('Seen must be a boolean.')
        with self.factory.unit_of_work() as uow:
            self._authorize(uow, context)
            now, config = stamp(self.clock.now_iso()), deepcopy(self.config)
            item = self.queries.get(uow, attention_id=attention_id, now=now, config=config,
                                    access=self.access, context=context)
            if item is None:
                raise OktoNexusError(ErrorCode.NOT_FOUND, 'The attention episode is no longer available. Refresh the view.', {})
            prior = item['seen_state']
            if item['source_revision'] != source_revision or prior['revision'] != preference_revision:
                raise OktoNexusError(ErrorCode.CONFLICT, 'The occurrence or viewing state changed. Refresh before continuing.',
                                     {'reason': 'ATTENTION_REVISION_CHANGED'})
            seen_at, snoozed_until = prior['seen_at'], prior['snoozed_until']
            if snooze:
                if until is not None:
                    until = stamp(until)
                    if not instant(now) < instant(until) <= instant(now) + timedelta(days=30):
                        invalid('Snooze must end in the next 30 days, or be null to clear it.')
                snoozed_until = until
            else:
                seen_at = (seen_at or now) if seen else None
            if (seen_at, snoozed_until) != (prior['seen_at'], prior['snoozed_until']):
                self.queries.save_preference(uow, attention_id=attention_id, seen_at=seen_at,
                    snoozed_until=snoozed_until, expected_revision=preference_revision, now=now)
                # Reproject from source, so clearing snooze/seen can restore
                # visibility without treating the previous derived flag as truth.
                item = self.queries.get(uow, attention_id=attention_id, now=now, config=config,
                                        access=self.access, context=context)
            return dict(version=VERSION, item=item, observed_at=now)

    def mark_seen(self, *, context, attention_id, source_revision, preference_revision, seen=True):
        return self._preference(context=context, attention_id=attention_id, source_revision=source_revision,
                                preference_revision=preference_revision, seen=seen)

    def snooze(self, *, context, attention_id, source_revision, preference_revision, until):
        return self._preference(context=context, attention_id=attention_id, source_revision=source_revision,
                                preference_revision=preference_revision, until=until, snooze=True)
