import { useEffect, useState } from 'react';
import type { MetaHarnessSession } from '../api';
import { runtimeApi, type RuntimeSession } from '../runtimeApi';
import { sessionReleased } from '../connectionSessions';
import { AgentActionModal } from './AgentActionModal';
import { RuntimeSessionTail } from './RuntimeSessionTail';
import { RuntimeHistory } from './RuntimeHistory';

export function SessionTerminalModal({session, onClose}: {session: MetaHarnessSession; onClose: () => void}) {
  const [current,setCurrent]=useState<RuntimeSession>(session);
  const [tab,setTab]=useState<'tail'|'history'>(sessionReleased(session)?'history':'tail');
  const [error,setError]=useState('');
  useEffect(()=>{
    if(sessionReleased(session)) return;
    const controller=new AbortController();let timer:number|undefined;
    const poll=async()=>{
      try {
        const next=await runtimeApi.session(session.scope.session_id,controller.signal,session.scope.executor_id);
        if(controller.signal.aborted)return;
        if((['server_id','executor_id','binding_id','agent_id','workspace_id','workspace_binding_id','session_id']).some(key=>next.scope[key as keyof typeof next.scope]!==session.scope[key as keyof typeof session.scope]))
          throw Error('The session changed scope. Reopen its terminal.');
        setCurrent(next);setError('');
        if(!sessionReleased(next))timer=window.setTimeout(()=>void poll(),2000);
      } catch(failure) {
        if(!controller.signal.aborted){setError(String(failure));timer=window.setTimeout(()=>void poll(),3000);}
      }
    };
    void poll();return()=>{controller.abort();window.clearTimeout(timer);};
  },[session.scope.server_id,session.scope.executor_id,session.scope.session_id]);
  return <AgentActionModal title={`Terminal · ${session.scope.agent_id}`} wide guardChanges={false} onClose={onClose}>
    <div className="space-y-3 min-w-0">
      <p className="text-xs text-surface-500 break-words">{session.harness} · {session.host} · {current.lifecycle_state}</p>
      <p className="text-xs text-surface-500 break-all">{session.scope.session_id}</p>
      {error && <p role="alert" className="text-xs text-red-600">Session status could not be refreshed. {error}</p>}
      <div className="flex gap-2" role="group" aria-label="Terminal mode">
        <button className="btn btn-secondary" aria-pressed={tab==='tail'} onClick={()=>setTab('tail')}>Live tail</button>
        <button className="btn btn-secondary" aria-pressed={tab==='history'} onClick={()=>setTab('history')}>History</button>
      </div>
      {tab==='tail'?<RuntimeSessionTail scope={current.scope} harness={session.harness} active={!sessionReleased(current)}/>
        :<RuntimeHistory scope={current.scope} harness={session.harness}/>}
    </div>
  </AgentActionModal>;
}
