import type { HomeActivity, HomeCounter, HomeDisplayState, HomeResult, HomeSection,HomeTarget } from './homeTypes';
import type { ExternalObservation } from './observationTypes';
import {deliveryPresentation} from './homeStatePresentation';

const labels: Record<HomeDisplayState, string> = {
  awaiting_owner: 'Awaiting owner', claimed: 'Claimed', queued: 'Queued', native_accepted: 'Accepted by runtime',
  running: 'Running', awaiting_dependency: 'Awaiting dependency', awaiting_operator: 'Needs your response',
  awaiting_agent: 'Awaiting agent response', awaiting_verification: 'Awaiting verification',
  outcome_unknown: 'Outcome unknown', completed: 'Completed', turn_completed: 'Turn completed',
  result_available_cleanup_pending: 'Result available · cleanup pending', failed: 'Failed', cancelled: 'Cancelled', unknown: 'Unknown',
};
export function homeStateLabel(state: string): string { return labels[state as HomeDisplayState] ?? 'Unknown'; }
/** A direct turn can have a private prompt and no public subject. */
export function isUntitledHomeWork(entry: {title: string; target?: HomeTarget | null}): boolean {
  return entry.target?.kind === 'execution' && entry.title === 'Work request';
}
export function homeTargetActionLabel(target:HomeTarget):string{
  return ({handoff:'View work',execution:'View work',result:'View delivery',session:'View session',
    connection:'View connection',message:'View message',approval:'Review request',external_observation:'View external signal'})[target.kind];
}
export function homeCounterLabel(counter: HomeCounter): string {
  return counter.value === null ? 'Not available' : `${counter.total_is_exact ? '' : 'At least '}${counter.value}`;
}
export function homeSectionLabel(section: HomeSection<unknown> | null): string {
  if (!section) return 'Loading';
  return ({ ready: 'Current snapshot', partial: 'Partial information', unavailable: 'Unavailable',
    disabled: 'Disabled', forbidden: 'Access unavailable' } as const)[section.status];
}
export function homeActivityKey(item: HomeActivity): string { return item.id; }
export function homeResultKey(item: HomeResult): string { return item.id; }
export function homeResultLabel(result: HomeResult): string {
  const meaning=deliveryPresentation(result.delivery_semantics,{outcome:result.outcome,evidence:'canonical'});
  const badges=[...meaning.badges];
  if(!result.delivery_semantics&&result.cleanup_state&&!['CLOSED','RELEASED','complete','completed'].includes(result.cleanup_state))badges.push('Cleanup pending');
  return [meaning.title,...badges].join(' · ');
}
export function homeExternalLabel(item: ExternalObservation): string {
  const evidence = item.last_report?.evidence ?? 'evidence unknown';
  return `External report · ${item.freshness === 'current' ? item.activity_state : 'state unknown'} · ${item.freshness} · ${evidence}`;
}
const feedLabels: Record<string, string> = {
  'handoff.created': 'Work requested', 'handoff.claimed': 'Work claimed', 'handoff.completed': 'Work completed',
  'handoff.cancelled': 'Work cancelled', 'handoff.rejected': 'Work rejected', 'handoff.expired': 'Work expired',
  'handoff.recovered': 'Work recovered', 'handoff.verification_requested': 'Verification requested',
  'handoff.verification_failed': 'Verification requires rework', 'handoff.unblocked': 'Dependency resolved',
  'handoff.dependency_failed': 'Dependency failed', 'handoff.execution_requested': 'Execution requested',
  'message.created': 'Coordination message', 'observation.activity': 'External activity reported',
  'observation.completion': 'External completion reported',
  'message.sent': 'Coordination message sent', 'handoff.verified': 'Work verified',
  'approval.created': 'Approval requested', 'approval.decided': 'Approval decision recorded',
};
/** No arbitrary event payload, native tokens or heartbeat text is rendered. */
export function homeFeedLabel(type: string): string | null { return feedLabels[type] ?? null; }
