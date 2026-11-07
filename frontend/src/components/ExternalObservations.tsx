import { useEffect, useState } from 'react';
import { api } from '../api';
import type { AttentionTarget } from '../attentionNavigation';
import { readAttentionReference } from '../attentionNavigation';
import { useObservationRead } from '../hooks/useObservationRead';
import type { ObservationReadState } from '../observationReader';
import type { ExternalObservation, ObservationDetail, ObservationPageQuery, ObservationSummary } from '../observationTypes';
import { observationCountText, observationLimitation, observationRefreshSeconds, observationSourceLabels, observationStatus } from '../observationPresentation';
import { useWorkspaceName } from './WorkspaceNames';

const focus = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500';
const time = (value: string | null | undefined) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString() : 'Not recorded';

export function ExternalObservationMetadata({ item, currentView = true, compact = false }: {
  item: ExternalObservation; currentView?: boolean; compact?: boolean;
}) {
  const status = observationStatus(item, currentView);
  const workspaceName = useWorkspaceName(item.workspace_id);
  return <section aria-label={`External instance ${item.observed_instance_id}`} className="min-w-0 space-y-2 text-xs" data-testid={`external-instance-${item.observed_instance_id}`}>
    <div className="flex flex-wrap gap-2">
      <span className="rounded bg-surface-100 dark:bg-surface-800 px-2 py-1 font-medium">{status.activity}</span>
      <span>{status.freshness}</span>
      <span>{observationSourceLabels[item.source_kind] ?? 'External source'}</span>
      <span>{item.last_report?.evidence === 'inferred' ? 'Inferred evidence' : item.last_report ? 'Reported evidence' : 'No activity evidence'}</span>
    </div>
    <dl className="grid gap-2 sm:grid-cols-2">
      <div><dt className="text-surface-500">Source</dt><dd className="font-mono break-all">{item.source_id}</dd></div>
      <div><dt className="text-surface-500">Instance · generation {item.generation}</dt><dd className="font-mono break-all">{item.observed_instance_id}</dd></div>
      <div><dt className="text-surface-500">Workspace</dt><dd className="break-all">{workspaceName}<span className="block font-mono">{item.workspace_id}</span></dd></div>
      <div><dt className="text-surface-500">Source instance reference</dt><dd className="font-mono break-all whitespace-pre-wrap">{item.external_instance_ref}</dd></div>
      <div><dt className="text-surface-500">Observed at</dt><dd>{time(item.last_report?.observed_at)}</dd></div>
      <div><dt className="text-surface-500">Valid until</dt><dd>{time(item.last_report?.valid_until)}</dd></div>
    </dl>
    {!compact && <>
      <p className="break-all">Agent: <span className="font-mono">{item.agent_id}</span></p>
      <p>Received at: {time(item.last_report?.received_at)} · Sequence: {item.last_report?.sequence ?? 'No report'}</p>
      <p>Source contact: {item.source_continuity} · {time(item.source_last_received_at)}. Source contact does not establish this instance's current activity.</p>
      {item.last_report?.reason_code && <p className="break-all">Reported reason: {item.last_report.reason_code}</p>}
      {item.last_report?.reason_text && <p className="whitespace-pre-wrap break-all">{item.last_report.reason_text}</p>}
      {item.last_report?.last_completion_ref && <div>
        <p>Last observed completion reference · {time(item.last_report.last_completion_received_at)}</p>
        <p className="font-mono whitespace-pre-wrap break-all">{item.last_report.last_completion_ref}</p>
        <p>This external reference is not a Nexus result or handoff completion.</p>
      </div>}
      <p>No canonical session correlation is established.</p>
      <p className="text-surface-600 dark:text-surface-400">{observationLimitation}</p>
    </>}
  </section>;
}

export function ExternalObservationInspection({ target, refreshKey, completionEpisode }: {
  target: Extract<AttentionTarget, { kind: 'external_observation' }>; refreshKey?: string; completionEpisode?: ExternalObservation;
}) {
  const { state, refresh } = useObservationRead(target, async (selection, signal): Promise<ObservationDetail> => {
    const response = await readAttentionReference(api, selection, signal);
    if (response.kind !== 'external_observation') throw new Error('Unexpected observation reference.');
    return response.record;
  }, observationRefreshSeconds);
  useEffect(() => { if (refreshKey) refresh(); }, [refreshKey, refresh]);
  return <section aria-label="External observation inspection" className="space-y-4" data-testid="external-observation-inspection">
    <h3 className="font-semibold">Inspect in the source environment</h3>
    <p className="text-sm">Use the source and instance references below to locate the observed environment. Nexus only displays its reports here.</p>
    {state.loading && <p role="status" className="text-sm">Refreshing external observation…</p>}
    {state.error && <p role="alert" className="text-sm">{state.error}</p>}
    {state.value && <>
      {!state.value.feature_enabled && <p role="status">External observation publishing is disabled. Retained reports are unavailable as current activity.</p>}
      {completionEpisode?.last_report && <section aria-label="Selected external completion" className="rounded border border-surface-200 dark:border-surface-700 p-3 space-y-2 text-sm" data-testid="external-completion-episode">
        <h4 className="font-semibold">Selected observed completion</h4>
        <p className="font-mono break-all whitespace-pre-wrap">{completionEpisode.last_report.current_completion_ref ?? completionEpisode.last_report.last_completion_ref ?? 'Reference unavailable'}</p>
        <p>Observed: {time(completionEpisode.last_report.observed_at)} · Received: {time(completionEpisode.last_report.received_at)}</p>
        <p>This retained report belongs to the selected attention episode. A newer report below does not replace it or confirm a Nexus task result.</p>
      </section>}
      <h4 className="font-semibold">Latest instance report</h4>
      <ExternalObservationMetadata item={state.value.item} currentView={state.status === 'ready'} />
    </>}
    <button type="button" className={`btn btn-secondary ${focus}`} disabled={state.loading} onClick={refresh}>Refresh observation</button>
  </section>;
}

function AgentObservationInstances({ agentId, workspace }: { agentId: string; workspace: string }) {
  const [after, setAfter] = useState<string | undefined>();
  const query: ObservationPageQuery = { agent_id: agentId, ...(workspace !== 'all' ? { workspace_id: workspace } : {}),
    ...(after ? { after } : {}), limit: 20 };
  const { state, refresh } = useObservationRead(query, api.externalObservations, observationRefreshSeconds);
  return <div className="space-y-3 pt-2">
    {state.loading && <p role="status">Loading external instances…</p>}
    {state.error && <p role="alert">{state.error}</p>}
    {state.value && <>
      <p>{state.value.items.length} instance records on this page. These records do not define the complete agent total.</p>
      {state.value.items.length === 0 && <p>No instance records on this page.</p>}
      <ul className="space-y-3">{state.value.items.map(item => <li key={`${item.observed_instance_id}:${item.generation}`} className="rounded border border-surface-200 dark:border-surface-700 p-2">
        <ExternalObservationMetadata item={item} compact currentView={state.status === 'ready'} />
      </li>)}</ul>
    </>}
    <div className="flex flex-wrap gap-2">
      <button type="button" className={`btn btn-secondary ${focus}`} disabled={state.loading} onClick={refresh}>Refresh instances</button>
      {after && <button type="button" className={`btn btn-secondary ${focus}`} disabled={state.loading} onClick={() => setAfter(undefined)}>First page</button>}
      {state.value?.next_after && <button type="button" className={`btn btn-secondary ${focus}`} disabled={state.loading || state.status !== 'ready'}
        onClick={() => setAfter(state.value!.next_after!)}>Next instances</button>}
    </div>
  </div>;
}

/** Receives the single batched summary owned by AgentsView; reads details only after expansion. */
export function ExternalAgentActivity({ agentId, workspace, summary }: {
  agentId: string; workspace: string; summary: ObservationReadState<ObservationSummary>;
}) {
  const [open, setOpen] = useState(false);
  const counts = summary.value?.agents.find(row => row.agent_id === agentId);
  if (!counts || counts.total_instances === 0) return null;
  return <section className="border-t border-surface-200 dark:border-surface-700 pt-2 text-xs min-w-0" aria-label={`External activity for ${agentId}`} data-testid={`external-activity-${agentId}`}>
    <p className="font-medium">External activity</p>
    <p className="mt-1">{observationCountText(counts, summary.status === 'ready')}</p>
    {!summary.value!.feature_enabled && <p className="mt-1">Observation publishing disabled</p>}
    <p className="text-surface-500 mt-1">Activity reports only; presence and capacity are shown separately.</p>
    <button type="button" className={`rounded text-accent-700 dark:text-accent-300 py-1 underline ${focus}`} aria-expanded={open}
      onClick={() => setOpen(value => !value)}>{open ? 'Hide external instances' : 'Inspect external instances'}</button>
    {open && <AgentObservationInstances key={`${agentId}:${workspace}`} agentId={agentId} workspace={workspace} />}
  </section>;
}
