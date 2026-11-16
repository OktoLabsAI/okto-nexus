import {useEffect, useState} from 'react';
import {api, type AgentRow, type WorkspaceListItem} from '../../api';
import type {AttentionAction, AttentionOccurrence} from '../../attentionTypes';
import {attentionTarget} from '../../attentionNavigation';
import {homeApi} from '../../homeApi';
import {homeInspectionTarget, resolveHomeTarget} from '../../homeNavigation';
import type {HomeTarget} from '../../homeTypes';
import {runtimeApi, type RuntimeSession, type BindingView} from '../../runtimeApi';
import {CanonicalInspection} from '../AttentionInspection';
import {MetaHarnessComposer} from '../MetaHarnessComposer';
import {RuntimeOperations} from '../RuntimeOperations';
import {readContinuationContext} from './continuation';
import type {HomeEntrySelection} from '../../homeEntryInspection';
import {HomeEntryInspection} from './HomeEntryInspection';

export function HomeNewRequest({workspace, workspaces, onChanged}: {workspace: string; workspaces: WorkspaceListItem[]; onChanged: () => void}) {
  const [agents, setAgents] = useState<AgentRow[]>([]), [error, setError] = useState('');
  useEffect(() => {let active = true;void api.agents().then(value => {if (active) setAgents(value.items);}).catch(failure => {if (active) setError(String(failure));});return () => {active=false;};}, []);
  return <div className="space-y-3"><p className="text-sm text-surface-500">Choose Handoff for tracked work or Message for a conversation. You send as the operator; permissions are checked again on submission.</p>
    {error && <p role="alert">{error}</p>}
    <MetaHarnessComposer workspace={workspace} workspaces={workspaces} agents={agents} onSent={onChanged}/></div>;
}
export function HomeAttentionInspection({item, action, onClose, onChanged, refreshKey}: {
  item: AttentionOccurrence; action: AttentionAction; onClose: () => void; onChanged: () => void; refreshKey?: string;
}) {
  return <CanonicalInspection target={attentionTarget(item, action)} item={item} action={action} onClose={onClose} onChanged={onChanged} refreshKey={refreshKey}/>;
}

/** Opening is read-only. The original canonical inspector retains ownership of commands. */
export function HomeInspection({target, serverId, workspace, continuation, onClose, onChanged,entrySelection,suppressOutput=false}: {
  target: HomeTarget; serverId: string; workspace: string | null; continuation?: boolean;
  entrySelection?:HomeEntrySelection;
  suppressOutput?:boolean;
  onClose: () => void; onChanged: () => void;
}) {
  const [resolved, setResolved] = useState<Awaited<ReturnType<typeof resolveHomeTarget>> | null>(null);
  const [context, setContext] = useState<{session: RuntimeSession; binding: BindingView} | null>(null);
  const [error, setError] = useState('');
  const key = JSON.stringify(target);
  useEffect(() => {
    const controller = new AbortController();setResolved(null);setContext(null);setError('');
    void (async () => {
      try {
        const result = await resolveHomeTarget(homeApi, target, {server_id: serverId, workspace_id: workspace}, controller.signal);
        if (!result.available) throw new Error('This exact record is unavailable. No replacement was selected.');
        if (controller.signal.aborted) return;
        if (continuation) {
          const exact = await readContinuationContext(runtimeApi, target, result.agent_id ?? undefined, controller.signal);
          if (!controller.signal.aborted) setContext(exact);
        }
        if (!controller.signal.aborted) setResolved(result);
      } catch (failure) {if (!controller.signal.aborted) setError((failure as Error).message);}
    })();
    return () => controller.abort();
  }, [key, serverId, workspace, continuation]);
  return <div className="space-y-4">
    {error ? <p role="alert">{error}</p> : !resolved && <p role="status">Revalidating the exact canonical record…</p>}
    {resolved && !continuation && (entrySelection?<HomeEntryInspection selection={entrySelection} target={target} serverId={serverId} workspace={workspace} onClose={onClose} onChanged={onChanged}
      renderRecord={(related,continuing)=><HomeInspection key={JSON.stringify([related,continuing])} target={related} continuation={continuing} suppressOutput serverId={serverId} workspace={workspace} onClose={onClose} onChanged={onChanged}/>}/>
      :<CanonicalInspection target={homeInspectionTarget(resolved)} contextual suppressOutput={suppressOutput} onClose={onClose} onChanged={onChanged}/>)}
    {resolved && continuation && context && <RuntimeOperations agentId={context.session.scope.agent_id} binding={context.binding} canStart={false} continuationScope={context.session.scope}/>}
  </div>;
}
