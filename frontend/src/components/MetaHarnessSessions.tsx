import { useEffect, useState } from 'react';
import { PanelRightClose, RefreshCw, Terminal } from 'lucide-react';
import { api, type MetaHarnessSessions as SessionPage, type MetaHarnessSession, type WorkspaceListItem } from '../api';
import { workspaceDisplayName } from './WorkspaceNames';
import { SessionTerminalModal } from './SessionTerminalModal';
import './MetaHarnessSessions.css';

export function MetaHarnessSessions({workspace,agent,workspaces,onClose}: {
  workspace:string;agent:string;workspaces:WorkspaceListItem[];onClose:()=>void;
}) {
  const [view,setView]=useState<SessionPage|null>(null),[page,setPage]=useState(1);
  const [error,setError]=useState(''),[reload,setReload]=useState(0);
  const [selected,setSelected]=useState<MetaHarnessSession|null>(null);
  useEffect(()=>{
    const controller=new AbortController();let timer:number|undefined;
    setView(null);setError('');
    const poll=async()=>{
      try {
        const result=await api.metaHarnessSessions(workspace,agent,page,controller.signal);
        if(controller.signal.aborted)return;
        if(result.page!==page || result.items.some(s=>(workspace!=='all' && s.scope.workspace_id!==workspace) || (agent && s.scope.agent_id!==agent)))
          throw Error('The session list does not match this conversation.');
        if(!result.items.length && page>1 && result.total<=(page-1)*20){setPage(1);return;}
        setView(result);setError('');
      } catch(failure){if(!controller.signal.aborted)setError(String(failure));}
      finally {if(!controller.signal.aborted)timer=window.setTimeout(()=>void poll(),3000);}
    };
    void poll();return()=>{controller.abort();window.clearTimeout(timer);};
  },[workspace,agent,page,reload]);
  const names=Object.fromEntries(workspaces.map(item=>[item.workspace_id,workspaceDisplayName(item)]));
  return <aside id="meta-harness-sessions" className="meta-sessions-panel" aria-label="Conversation sessions">
    <header className="meta-sessions-header">
      <div><h3>Agent sessions</h3><p>{view?`${view.active_count} open · ${view.total} total`:'Operator conversations'}</p></div>
      <button className="meta-sessions-icon" aria-label="Refresh conversation sessions" title="Refresh" onClick={()=>setReload(v=>v+1)}><RefreshCw size={15}/></button>
      <button className="meta-sessions-icon" aria-label="Collapse conversation sessions" title="Collapse sessions" onClick={onClose}><PanelRightClose size={17}/></button>
    </header>
    <div className="meta-sessions-list">
      <p className="meta-sessions-caption">Runtime sessions used for the operator’s messages and handoffs.</p>
      {error && <p role="alert" className="text-xs text-red-600">Could not refresh sessions. {view?'Displayed data may be outdated. ':''}{error}</p>}
      {!view && !error && <p role="status" className="meta-sessions-caption">Loading sessions…</p>}
      {view?.items.length===0 && <div className="meta-sessions-empty"><Terminal size={24}/><p>No sessions in this conversation yet.</p><span>They appear when a runtime starts handling a request from the operator.</span></div>}
      {view?.items.map(session=><article key={`${session.scope.executor_id}:${session.scope.session_id}`} className="meta-session-card">
        <div className="meta-session-heading"><strong>{session.scope.agent_id}</strong><span className={session.is_open?'meta-session-open':''}>{session.is_open?'Open':'Ended'}</span></div>
        {!session.is_open && session.containment_reason && <p className="meta-sessions-caption" data-testid="session-end-reason">Ended: {session.containment_reason}</p>}
        <p className="meta-session-subject" title={session.subject || session.scope.session_id}>{session.subject || 'Conversation session'}</p>
        <p className="meta-sessions-caption">{session.harness==='codex_app_server'?'Codex':session.harness==='claude_stream'?'Claude':session.harness==='pi_rpc'?'Pi':session.harness} · {session.location==='embedded'?'Local':'Remote'}</p>
        {workspace==='all' && <p className="meta-sessions-caption">{names[session.scope.workspace_id] || session.scope.workspace_id}</p>}
        <p className="meta-sessions-caption" title={session.scope.session_id}>{session.scope.session_id.slice(0,14)}…{session.scope.session_id.slice(-5)}</p>
        <div className="meta-session-footer"><time title={session.last_interaction_at}>{new Date(session.last_interaction_at).toLocaleString()}</time>
          <button className="btn btn-secondary" aria-label={`View terminal ${session.scope.agent_id} ${session.scope.session_id}`} onClick={()=>setSelected(session)}><Terminal size={13}/> Terminal</button></div>
      </article>)}
    </div>
    {(page>1 || view?.has_more) && <footer className="meta-sessions-pagination"><button className="btn btn-secondary" disabled={page===1} onClick={()=>setPage(v=>v-1)}>Previous</button><span>{page}</span><button className="btn btn-secondary" disabled={!view?.has_more} onClick={()=>setPage(v=>v+1)}>Next</button></footer>}
    {selected && <SessionTerminalModal key={`${selected.scope.executor_id}:${selected.scope.session_id}`} session={selected} onClose={()=>setSelected(null)}/>}
  </aside>;
}
