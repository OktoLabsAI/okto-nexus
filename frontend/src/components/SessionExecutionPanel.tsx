import {useEffect, useRef, useState} from 'react';
import {runtimeApi, type RuntimeSession} from '../runtimeApi';
import {sessionReleased} from '../connectionSessions';
import {assertHomeSessionContext} from '../homeSessionInspection';
import {RuntimeEventStream} from './RuntimeEventStream';

export interface SessionExecutionPanelProps {
  session: RuntimeSession; harness?: string; host?: string; embedded?: boolean;
}
/** Shared output body: no dialog, command input, session selection or execution controls. */
export function SessionExecutionPanel(props: SessionExecutionPanelProps) {
  const s = props.session.scope;
  const identity = JSON.stringify([s.server_id,s.executor_id,s.workspace_id,s.session_id,s.binding_id,s.workspace_binding_id,s.agent_id]);
  return <ExecutionBody key={identity} {...props}/>;
}

function ExecutionBody({session,harness,host,embedded=false}: SessionExecutionPanelProps) {
  const [current,setCurrent] = useState<RuntimeSession|null>(session);
  const [tab,setTab] = useState<'tail'|'history'>(sessionReleased(session)?'history':'tail');
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
  return <section aria-label="Session execution output" data-modal-passive className="space-y-3 min-w-0">
    <p className="text-xs text-surface-500 break-words">{[harness,host,current.lifecycle_state].filter(Boolean).join(' · ')} · Read only</p>
    <p className="text-xs text-surface-500 break-all">{session.scope.session_id}</p>
    {error&&<p role="alert" className="text-xs text-red-600">{error}</p>}
    <div className="flex gap-2" role="group" aria-label="Terminal mode">
      <button type="button" className="btn btn-secondary" aria-pressed={tab==='tail'} disabled={sessionReleased(current)} onClick={()=>setTab('tail')}>Live tail</button>
      <button type="button" className="btn btn-secondary" aria-pressed={tab==='history'} onClick={()=>setTab('history')}>History</button>
    </div>
    <RuntimeEventStream scope={current.scope} harness={harness} history={tab==='history'}
      active={tab==='tail'&&!sessionReleased(current)} allowMaximize={!embedded} onAccessLost={clear}/>
  </section>;
}
