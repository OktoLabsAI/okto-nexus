import type { ExternalObservation, ObservationCounts, ObservationDetail, ObservationPage, ObservationSummary } from './observationTypes';

export const observationLimitation = 'External activity does not confirm task success, presence or available capacity. Inspect this instance in its source environment.';
export const observationSourceLabels = { herdr: 'Herdr', hook: 'Hook', custom: 'Custom integration' };
export const observationActivityLabels = { working: 'Working', idle: 'Idle', blocked: 'Awaiting input', unknown: 'Activity unknown' };
export const observationFreshnessLabels = { current: 'Current report', stale: 'Report expired', unknown: 'No report received', unavailable: 'Observation unavailable' };

export function observationStatus(item: ExternalObservation, currentView: boolean) {
  if (!currentView) return { activity: 'Activity unknown', freshness: 'Snapshot out of date' };
  return { activity: observationActivityLabels[item.freshness === 'current' ? item.activity_state : 'unknown'],
    freshness: observationFreshnessLabels[item.freshness] };
}

/** Counts come from the complete authorized Server projection, never a loaded page. */
export function observationCountText(counts: ObservationCounts, currentView: boolean): string {
  if (!currentView) return `${counts.total_instances} external instances · snapshot out of date`;
  const parts = [
    [counts.activity.working, 'working'], [counts.activity.idle, 'idle'],
    [counts.activity.blocked, 'awaiting input'], [counts.activity.unknown, 'activity unknown'],
  ].filter(([count]) => Number(count) > 0).map(([count, label]) => `${count} ${label}`);
  const unavailable = [[counts.freshness.stale, 'expired'], [counts.freshness.unavailable, 'unavailable'],
    [counts.freshness.unknown, 'without a report']].filter(([count]) => Number(count) > 0)
    .map(([count, label]) => `${count} ${label}`);
  return (parts.join('; ') || 'No external instances in this scope') + (unavailable.length ? ` (${unavailable.join('; ')})` : '');
}

/** The Server clock establishes TTL; browser wall-clock changes cannot extend it. */
export function observationRefreshSeconds(value: ObservationDetail | ObservationPage | ObservationSummary): number {
  const observed = Date.parse(value.observed_at);
  if (!Number.isFinite(observed)) return 0;
  let seconds = 15;
  if ('refresh_after_seconds' in value) {
    if (!Number.isFinite(value.refresh_after_seconds) || value.refresh_after_seconds < 0) return 0;
    seconds = Math.min(seconds, value.refresh_after_seconds);
  }
  const items = 'items' in value ? value.items : 'item' in value ? [value.item] : [];
  for (const item of items) {
    if (item.freshness === 'current') {
      const until = Date.parse(item.last_report?.valid_until ?? '');
      if (!Number.isFinite(until)) return 0;
      seconds = Math.min(seconds, Math.max(0, (until - observed) / 1000));
    }
  }
  return seconds;
}
