import {useEffect, useRef, useState, type ReactNode} from 'react';
import {api, ApiError} from '../../api';
import {ArrowUpRight, Eye} from 'lucide-react';
import type {HomeActivity, HomeResult, HomeSection, HomeTarget, HomeSummary, HomeAgent, HomeOverview} from '../../homeTypes';
import type {AttentionAction, AttentionOccurrence} from '../../attentionTypes';
import {homeCounterLabel, homeSectionLabel, homeStateLabel, homeResultLabel} from '../../homePresentation';
import {attentionActionLabels, attentionDescription, primaryAttentionAction} from '../../attentionPresentation';
import {useWorkspaceName} from '../WorkspaceNames';
import {formatTime} from '../../timeFormat';

export const homeFocus = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500';
export function isQuietHome(snapshot: HomeOverview | null, stale = false): boolean {
  if (!snapshot || stale) return false;
  const empty = (section: HomeSection<unknown>) => section.status === 'ready' && section.total_is_exact === true && section.total === 0 && section.items.length === 0;
  return empty(snapshot.work) && empty(snapshot.results) && empty(snapshot.attention)
    && (snapshot.external_activity.status === 'disabled' || empty(snapshot.external_activity))
    && snapshot.agents.status === 'ready' && snapshot.agents.total_is_exact === true && snapshot.agents.total !== null;
}
export function HomeWelcome({needsSetup, externalDisabled, onSetup, onRequest}: {
  needsSetup: boolean; externalDisabled: boolean; onSetup: () => void; onRequest: () => void;
}) {
  return <section className="panel p-5 sm:p-6" aria-label="Get started" data-testid="home-welcome">
    <h2 className="text-lg font-semibold">{needsSetup ? 'Set up your first agent' : 'What would you like to work on?'}</h2>
    <p className="text-sm text-surface-500 mt-2">{needsSetup ? 'Connect an agent to start work in this scope.' : 'Start a tracked handoff or a conversation. There is no pending work or result in this snapshot.'}</p>
    <button type="button" className={`btn btn-primary mt-4 ${homeFocus}`} onClick={needsSetup ? onSetup : onRequest}>{needsSetup ? 'Set up an agent' : 'New request'}</button>
    {externalDisabled && <p className="text-xs text-surface-500 mt-3">External reports are disabled.</p>}
  </section>;
}

export function HomeCounters({summary}: {summary: HomeSummary}) {
  return <dl aria-label="Operational summary" className="grid grid-cols-2 xl:grid-cols-4 gap-3">
    {(['running', 'waiting_start', 'needs_you', 'results'] as const).map(key => <div key={key} className="panel p-4 min-w-0">
      <dt className="text-xs text-surface-500">{summary[key].label}</dt>
      <dd className="text-2xl font-semibold mt-1">{homeCounterLabel(summary[key])}</dd>
      <p className="text-xs text-surface-500 mt-1">{summary[key].unit.replaceAll('_', ' ')}</p>
    </div>)}
  </dl>;
}
export function HomeBlock<T>({title, section, stale, children, empty, onMore, loadingMore}: {
  title: string; section: HomeSection<T>; stale?: boolean; children: ReactNode; empty: ReactNode;
  onMore?: () => void; loadingMore?: boolean;
}) {
  const readable = section.status === 'ready' || section.status === 'partial';
  return <section aria-label={title} className="panel p-4 sm:p-5 min-w-0">
    <header className="flex items-baseline justify-between gap-3"><h2 className="text-base font-semibold">{title}</h2>
      <span className="text-xs text-surface-500">{section.total === null ? 'Total unknown' : `${section.total_is_exact ? '' : 'At least '}${section.total}`}</span></header>
    <p className="text-xs text-surface-500 mt-1">{stale ? 'Out of date · last authorized snapshot' : homeSectionLabel(section)}{section.as_of ? ` · ${formatTime(section.as_of)}` : ''}</p>
    {!readable && <p role="status" className="text-sm text-surface-500 py-4">{homeSectionLabel(section)}. {section.reason_code?.replaceAll('_', ' ')}</p>}
    {readable && (section.items.length ? children : <div className="text-sm text-surface-500 py-5">{empty}</div>)}
    {readable && section.has_more && <div className="pt-3 border-t border-surface-200 dark:border-surface-700 mt-3">
      <p className="text-xs text-surface-500">Showing {section.items.length}{section.total !== null ? ` of ${section.total}` : ''}.</p>
      {onMore ? <button type="button" className={`btn btn-secondary mt-2 ${homeFocus}`} disabled={loadingMore || stale} onClick={onMore}>{loadingMore ? 'Loading…' : `Load more ${title.toLowerCase()}`}</button>
        : <p className="text-xs text-surface-500">More information is available after refining the scope.</p>}
    </div>}
  </section>;
}
function WorkspaceLabel({id}: {id: string | null}) {const name = useWorkspaceName(id);return <span title={id || undefined}>{id ? name : 'Server-wide'}</span>;}
export function WorkRow({item, onOpen}: {item: HomeActivity; onOpen: (target: HomeTarget) => void}) {
  return <li className="py-3 min-w-0" data-home-item={item.id}>
    <div className="flex justify-between gap-3"><h3 className="font-medium text-sm break-words min-w-0">{item.title}</h3>
      {item.detail_target && <button type="button" className={`btn btn-secondary shrink-0 ${homeFocus}`} aria-label={`Inspect ${item.title}`} onClick={() => onOpen(item.detail_target!)}><ArrowUpRight size={15}/></button>}</div>
    <p className="text-sm mt-1">{homeStateLabel(item.display_state)}{item.evidence_status === 'unknown' ? ' · Evidence unknown' : ''}</p>
    {item.reason && <p className="text-xs text-surface-500 mt-1 break-words">{item.reason}</p>}
    <p className="text-xs text-surface-500 mt-1 break-words">{item.agent_ids.join(', ') || 'Owner not assigned'} · <WorkspaceLabel id={item.workspace_id}/></p>
    {item.state_since && <p className="text-xs text-surface-500">In this state since {formatTime(item.state_since)}</p>}
    {!item.detail_target && <p className="text-xs text-surface-500">Exact detail unavailable.</p>}
  </li>;
}
export function AttentionRow({item, stale, pending, onOpen, onSeen, onSnooze}: {
  item: AttentionOccurrence; stale: boolean; pending: boolean;
  onOpen: (item: AttentionOccurrence, action: AttentionAction) => void;
  onSeen: (item: AttentionOccurrence, seen: boolean) => void; onSnooze: (item: AttentionOccurrence) => void;
}) {
  const description = attentionDescription(item), action = primaryAttentionAction(item);
  return <li className="py-3 min-w-0" data-home-item={item.attention_id}>
    <h3 className="text-sm font-medium break-words">{description.title}</h3><p className="text-sm mt-1 break-words">{description.reason}</p>
    <p className="text-xs text-surface-500 mt-1">{item.agent_id || 'Server'} · <WorkspaceLabel id={item.workspace_id}/>{item.seen_state.snoozed ? ' · Snoozed' : ''}</p>
    <div className="flex flex-wrap gap-2 mt-2">
      {action && <button type="button" className={`btn btn-primary ${homeFocus}`} onClick={() => onOpen(item, action)}>{attentionActionLabels[action]}</button>}
      <button type="button" className={`btn btn-secondary ${homeFocus}`} disabled={stale || pending} onClick={() => onSeen(item, !item.seen_state.seen)}><Eye size={14}/>{item.seen_state.seen ? 'Mark unseen' : 'Mark seen'}</button>
      <button type="button" className={`btn btn-secondary ${homeFocus}`} disabled={stale || pending} onClick={() => onSnooze(item)}>{item.seen_state.snoozed ? 'Show again' : 'Snooze 1 hour'}</button>
    </div>
  </li>;
}
export async function downloadCurrentArtifact(read: () => Promise<Blob>, current: () => boolean, publish: (blob: Blob) => void) {
  const blob = await read();
  if (!current()) return false;
  publish(blob);return true;
}
function ArtifactDownload({workspace, artifact}: {workspace: string; artifact: HomeResult['artifacts'][number]}) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const lock = useRef(false), access = useRef({active: true});
  useEffect(() => {
    const selected = {active: true};access.current = selected;
    const invalidate = () => {selected.active = false;};
    window.addEventListener('nexus-auth-expired', invalidate);
    window.addEventListener('nexus-operator-logout', invalidate);
    return () => {invalidate();window.removeEventListener('nexus-auth-expired', invalidate);window.removeEventListener('nexus-operator-logout', invalidate);};
  }, [workspace, artifact.artifact_id]);
  const download = async () => {
    if (lock.current || !access.current.active) return;lock.current = true;setBusy(true);setError('');
    const selected = access.current, current = () => selected.active && access.current === selected;
    try {
      // The canonical content API checks the selected workspace again. No filesystem or model-authored URL is opened.
      await downloadCurrentArtifact(() => api.artifactBlob(workspace, artifact.artifact_id), current, blob => {
      const url = URL.createObjectURL(blob), link = document.createElement('a');
      link.href = url;link.download = (artifact.filename || artifact.artifact_id).split(/[\\/]/).pop() || 'artifact';
      document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);
      });
    } catch (failure) {
      if (!current()) return;
      if (failure instanceof ApiError && [401,403].includes(failure.status)) window.dispatchEvent(new Event('nexus-auth-expired'));
      if (current()) setError('The artifact is unavailable or access has changed. No alternative path was opened.');
    } finally {lock.current = false;if (current()) setBusy(false);}
  };
  return <span className="block"><button type="button" className={`text-xs underline ${homeFocus}`} disabled={busy} onClick={() => void download()}>{busy ? 'Loading artifact…' : artifact.filename || artifact.artifact_id}</button>{error && <span role="alert" className="block text-xs">{error}</span>}</span>;
}
export function ResultRow({item, stale, onOpen, onSeen, onContinue}: {
  item: HomeResult; stale: boolean; onOpen: (target: HomeTarget) => void;
  onSeen: (item: AttentionOccurrence, seen: boolean) => void; onContinue: (target: HomeTarget) => void;
}) {
  return <li className="py-3 min-w-0" data-home-item={item.id}>
    <h3 className="font-medium text-sm break-words">{item.title}</h3>
    <p className="text-xs mt-1">{homeResultLabel(item)}{item.verification_state && item.cleanup_state ? ` · Verification: ${item.verification_state}` : ''} · {item.view_state === 'not_tracked' ? 'Recent · seen state not tracked' : item.view_state === 'seen' ? 'Seen' : 'Unseen'}</p>
    {item.preview && <p className="text-sm mt-2 whitespace-pre-wrap break-words line-clamp-4">{item.preview}</p>}
    {item.truncated && <p className="text-xs text-surface-500">Preview truncated. Open the original result.</p>}
    <p className="text-xs text-surface-500 mt-1">{item.agent_id || 'Author unknown'} · <WorkspaceLabel id={item.workspace_id}/>{item.created_at ? ` · ${formatTime(item.created_at)}` : ''}</p>
    {item.artifacts.length > 0 && <div className="mt-2 space-y-1" aria-label="Authorized artifact references">{item.artifacts.map(artifact => <ArtifactDownload key={artifact.artifact_id} workspace={item.workspace_id} artifact={artifact}/>)}</div>}
    <div className="flex flex-wrap gap-2 mt-2">
      {item.detail_target && <button type="button" className={`btn btn-secondary ${homeFocus}`} onClick={() => onOpen(item.detail_target!)}>Open result</button>}
      {item.attention && <button type="button" className={`btn btn-secondary ${homeFocus}`} disabled={stale} onClick={() => onSeen(item.attention!, !item.attention!.seen_state.seen)}>{item.view_state === 'seen' ? 'Mark unseen' : 'Mark seen'}</button>}
      {item.detail_target && ['execution', 'result'].includes(item.detail_target.kind) && <button type="button" className={`btn btn-secondary ${homeFocus}`} disabled={stale} onClick={() => onContinue(item.detail_target!)}>Continue this session</button>}
    </div>
  </li>;
}
export function AgentRow({item}: {item: HomeAgent}) {
  return <li className="py-3 text-sm"><strong className="break-words">{item.name || item.agent_id}</strong>
    <p className="text-xs text-surface-500 mt-1">Presence: {item.presence} · Connection: {item.connectivity}</p>
    <p className="text-xs text-surface-500">Activity not reported{item.capabilities?.length ? ` · ${item.capabilities.join(', ')}` : ''}</p></li>;
}
