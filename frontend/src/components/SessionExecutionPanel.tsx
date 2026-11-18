import {useEffect, useRef, useState, type ReactNode} from 'react';
import {runtimeApi, type InteractionScope, type RuntimeSession} from '../runtimeApi';
import {sessionReleased} from '../connectionSessions';
import {assertHomeSessionContext} from '../homeSessionInspection';
import {RuntimeEventStream} from './RuntimeEventStream';
import {CopyMessageButton} from './CopyMessageButton';
import {SessionConversation} from './SessionConversation';

export interface SessionExecutionPanelProps {
  session: RuntimeSession; harness?: string; host?: string; embedded?: boolean; interactive?: boolean;
  technicalControls?: ReactNode;
}

/** Build a shell-safe invocation of the Nexus CLI's existing-session prompt. */
function terminalSessionCommand(session: RuntimeSession): string | null {
  const id = session.scope.session_id;
  if (!session.control_available || session.durable_release_pending || !['READY','ACTIVE'].includes(session.lifecycle_state) ||
      !/^ses_[a-zA-Z0-9_-]+$/.test(id)) return null;
  return `okto-nexus work chat --session-id ${id}`;
}
/** Shared exact-session body used in the Home context and the terminal viewer. */
export function SessionExecutionPanel(props: SessionExecutionPanelProps) {
  const s = props.session.scope;
  const identity = JSON.stringify([s.server_id,s.executor_id,s.workspace_id,s.session_id,s.binding_id,s.workspace_binding_id,
    s.agent_id,s.session_owner_generation]);
  return <ExecutionBody key={identity} {...props}/>;
}

function ExecutionBody({session,harness,host,embedded=false,interactive=false,technicalControls}: SessionExecutionPanelProps) {
  const [current,setCurrent] = useState<RuntimeSession|null>(session);
  const [tab,setTab] = useState<'tail'|'history'>(sessionReleased(session)?'history':'tail');
  const [presentation,setPresentation] = useState<'conversation'|'activity'>('conversation');
  const [error,setError] = useState('');
  const [blocked,setBlocked] = useState(false);
  const stopObserving=useRef<()=>void>(()=>{});
  const clear = () => {stopObserving.current();setCurrent(null);setBlocked(true);setError('Operator access is required. Protected session output has been cleared.');};
  useEffect(()=>{
    const controller=new AbortController();let timer:number|undefined;
    stopObserving.current=()=>{controller.abort();window.clearTimeout(timer);};
    const revoke=()=>clear();
    window.addEventListener('nexus-auth-expired',revoke);window.addEventListener('nexus-operator-logout',revoke);
    const poll=async()=>{
      try {
        const next=await runtimeApi.session(session.scope.session_id,controller.signal,session.scope.executor_id);
        if(controller.signal.aborted)return;
        try {assertHomeSessionContext(next,{...session.scope,lifecycle_state:session.lifecycle_state});}
        catch {stopObserving.current();setCurrent(null);setBlocked(true);setError('The session changed scope. Reopen its exact context.');return;}
        if (interactive && next.scope.session_owner_generation !== session.scope.session_owner_generation) {
          stopObserving.current();setCurrent(null);setBlocked(true);setError('The session owner changed. Reopen this session.');
          return;
        }
        setCurrent(next);setError('');
        if(sessionReleased(next))setTab('history');
        else timer=window.setTimeout(()=>void poll(),2000);
      }catch(failure){
        if(controller.signal.aborted)return;
        if([401,403].includes((failure as {status?:number}).status ?? 0)){revoke();return;}
        setError('Session status could not be refreshed. Displayed status may be out of date.');
        timer=window.setTimeout(()=>void poll(),3000);
      }
    };
    if(!sessionReleased(session))void poll();
    return()=>{controller.abort();window.clearTimeout(timer);window.removeEventListener('nexus-auth-expired',revoke);window.removeEventListener('nexus-operator-logout',revoke);};
  },[]);
  if(blocked||!current)return <p role="alert">{error}</p>;
  const command = embedded && !error ? terminalSessionCommand(current) : null;
  const activity = <section aria-label="Session execution output" data-modal-passive className="space-y-3 min-w-0">
    <p className="text-xs text-surface-500 break-words">{[harness,host,current.lifecycle_state].filter(Boolean).join(' · ')} · Read only</p>
    {!embedded&&<p className="text-xs text-surface-500 break-all">{session.scope.session_id}</p>}
    {error&&<p role="alert" className="text-xs text-red-600">{error}</p>}
    <div className="flex gap-2" role="group" aria-label="Terminal mode">
      <button type="button" className="btn btn-secondary" aria-pressed={tab==='tail'} disabled={sessionReleased(current)} onClick={()=>setTab('tail')}>Live tail</button>
      <button type="button" className="btn btn-secondary" aria-pressed={tab==='history'} onClick={()=>setTab('history')}>History</button>
    </div>
    <RuntimeEventStream scope={current.scope} harness={harness} history={tab==='history'}
      active={tab==='tail'&&!sessionReleased(current)} allowMaximize={!embedded} onAccessLost={clear}/>
    {command&&<details className="text-sm">
      <summary className="cursor-pointer">Open this session in a terminal</summary>
      <p className="mt-2 text-surface-500">Run from the project folder to open the Nexus prompt for this session. If you use a saved profile for this connection, include its name with <code>--profile</code>.</p>
      <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md bg-surface-100 p-2 dark:bg-surface-800">
        <code className="min-w-0 break-all text-xs">{command}</code>
        <CopyMessageButton text={command} item="command"/>
      </div>
    </details>}
  </section>;
  const generation = current.scope.session_owner_generation;
  if (!interactive || generation === undefined || !Number.isSafeInteger(generation) || generation <= 0) {
    return technicalControls ? <>{activity}{technicalControls}</> : activity;
  }
  const scope: InteractionScope = {...current.scope, session_owner_generation: generation};
  return <section aria-label="Session" className="space-y-3 min-w-0">
    <div role="group" aria-label="Session view" className="flex flex-wrap gap-2">
      <button type="button" className="btn btn-secondary" aria-pressed={presentation === 'conversation'}
        onClick={() => setPresentation('conversation')}>Conversation</button>
      <button type="button" className="btn btn-secondary" aria-pressed={presentation === 'activity'}
        onClick={() => setPresentation('activity')}>Technical activity</button>
    </div>
    {presentation === 'conversation'
      ? <SessionConversation scope={scope} active={!sessionReleased(current) && !error} onAccessLost={clear}/>
      : <>{activity}{technicalControls}</>}
  </section>;
}
