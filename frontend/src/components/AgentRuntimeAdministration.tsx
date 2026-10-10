import { useEffect, useRef, useState } from 'react';
import { RefreshCw, Square, Eye } from 'lucide-react';
import { api, type AgentRuntimeOverview } from '../api';
import { runtimeApi, type RuntimeSession, type RuntimeOperation } from '../runtimeApi';
import { SessionClosures, sessionReleased } from '../connectionSessions';
import { AgentActionModal, AgentModalFooter } from './AgentActionModal';
import { RuntimeHistory } from './RuntimeHistory';
import { RuntimeSessionTail } from './RuntimeSessionTail';
import { useConfirm } from './Confirm';
import './AgentRuntimeAdministration.css';

const short = (id: string) => id.length > 22 ? `${id.slice(0,12)}…${id.slice(-6)}` : id;
const key = (s: RuntimeSession) => `${s.scope.executor_id}:${s.scope.session_id}`;
const date = (value: string) => new Date(value).toLocaleString();

export function AgentRuntimeAdministration({agentId, onClose}: {agentId: string; onClose: () => void}) {
  const [view, setView] = useState<AgentRuntimeOverview | null>(null);
  const [after, setAfter] = useState(0);
  const [back, setBack] = useState<number[]>([]);
  const [reload, setReload] = useState(0);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<RuntimeSession | null>(null);
  const [operation, setOperation] = useState<RuntimeOperation | null>(null);
  const [inspectionError, setInspectionError] = useState('');
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<'tail' | 'history'>('tail');
  const [closing, setClosing] = useState<Record<string, string>>({});
  const [closeError, setCloseError] = useState('');
  const closures = useRef(new SessionClosures());
  const inspection = useRef<AbortController | null>(null);
  const live = useRef(true);
  const {confirm, dialog} = useConfirm({agentModal:true});
  useEffect(() => {live.current=true;return () => {live.current=false;inspection.current?.abort();};}, []);
  useEffect(() => {
    const controller = new AbortController(); let timer: number | undefined;
    const load = async () => {
      try {
        const value = await api.agentRuntimeOverview(agentId, after, controller.signal);
        if (controller.signal.aborted) return;
        if (value.agent_id !== agentId || value.active.some(s => s.scope.agent_id !== agentId)) throw new Error('The runtime list belongs to another agent.');
        setView(value);setError('');
      } catch (failure) {if (!controller.signal.aborted) setError(String(failure));}
      finally {if (!controller.signal.aborted) timer = window.setTimeout(() => void load(), 3000);}
    };
    void load();
    return () => {controller.abort();window.clearTimeout(timer);};
  }, [agentId, after, reload]);
  useEffect(() => {
    if (!Object.keys(closing).length) return;
    const controller = new AbortController();let timer: number | undefined;
    const check = async () => {
      const results = await Promise.allSettled(Object.entries(closing).map(async ([sessionKey, operationId]) => {
        const result = await runtimeApi.operation(operationId, controller.signal);
        return {sessionKey, result};
      }));
      if (controller.signal.aborted) return;
      for (const item of results) {
        if (item.status === 'rejected') {setCloseError('Could not confirm closure. Checking the same operation again.');continue;}
        const {sessionKey,result} = item.value;
        if (result.error || ['FAILED','CANCELLED','OUTCOME_UNKNOWN'].includes(result.executor_stage || ''))
          setCloseError(`Closure not confirmed: ${result.error?.message || result.executor_stage}. Inspect the session and runtime status.`);
        if (result.error || ['SUCCEEDED','FAILED','CANCELLED','OUTCOME_UNKNOWN'].includes(result.executor_stage || ''))
          setClosing(old => {const next={...old};delete next[sessionKey];return next;});
      }
      timer = window.setTimeout(() => void check(),2000);
    };
    void check();
    return () => {controller.abort();window.clearTimeout(timer);};
  }, [closing]);
  useEffect(() => {
    if (!selected || sessionReleased(selected)) return;
    const controller = new AbortController(); let timer: number | undefined;
    const refresh = async () => {
      try {
        const current = await runtimeApi.session(selected.scope.session_id, controller.signal, selected.scope.executor_id);
        if (controller.signal.aborted) return;
        if (key(current)!==key(selected) || current.scope.agent_id!==agentId) throw new Error('The session changed scope.');
        setSelected(current);
        if (!sessionReleased(current)) timer = window.setTimeout(() => void refresh(), 2000);
      } catch (failure) {if (!controller.signal.aborted) setInspectionError(String(failure));}
    };
    void refresh();
    return () => {controller.abort();window.clearTimeout(timer);};
  }, [selected?.scope.executor_id, selected?.scope.session_id]);
  const inspect = async (row: RuntimeSession | AgentRuntimeOverview['completed'][number]) => {
    inspection.current?.abort();const controller=new AbortController();inspection.current=controller;
    setLoading(true);setInspectionError('');setSelected(null);setOperation(null);
    try {
      const finished = 'operation_id' in row;
      const session = finished ? await runtimeApi.session(row.session_id, controller.signal, row.executor_id) : row;
      const result = finished ? await api.agentRuntimeExecution(agentId,row.operation_id,row.executor_id,controller.signal) : null;
      if (controller.signal.aborted) return;
      if (session.scope.agent_id!==agentId || result && (result.scope.agent_id!==agentId || result.scope.session_id!==session.scope.session_id))
        throw new Error('The inspection does not match this agent.');
      setSelected(session);setOperation(result);setTab(finished || sessionReleased(session) ? 'history' : 'tail');
    } catch (failure) {if (!controller.signal.aborted) setInspectionError(String(failure));}
    finally {if (!controller.signal.aborted) setLoading(false);}
  };
  const close = (session: RuntimeSession) => confirm({title:'End this runtime session?',
    body:<><p>Requests a graceful stop for <strong>{short(session.scope.session_id)}</strong>. Unfinished work may be interrupted.</p>
      <p className="mt-2">Other sessions are unaffected. A configured pool may create a replacement warm instance.</p></>,
    onConfirm:async () => {
      const result = await closures.current.close(runtimeApi,session);
      if (live.current) {setCloseError('');if (result) setClosing(old => ({...old,[key(session)]:result.operation_id}));setReload(n => n+1);}
    }});
  return <AgentActionModal title={`Runtime administration · ${agentId}`} wide guardChanges={false} onClose={onClose}>
    {dialog}
    <div className={`runtime-admin ${selected ? 'runtime-admin-has-selection' : ''}`}>
      <div className="runtime-admin-list space-y-5">
        <header className="flex justify-between items-center gap-2"><div><h3 className="font-semibold text-sm">Running instances <span className="text-surface-500">{view?.active_count ?? '…'}</span></h3>
          <p className="text-xs text-surface-500 mt-1">Local and remote runtimes · refreshes automatically</p></div>
          <button className="btn btn-secondary" aria-label="Refresh runtime instances" onClick={() => setReload(n=>n+1)}><RefreshCw size={14}/></button></header>
        {error && <p role="alert" className="text-xs">Could not refresh. Displayed data may be outdated. {error}</p>}
        {closeError && <p role="alert" className="text-xs">{closeError}</p>}
        {!view && !error && <p role="status">Loading instances…</p>}
        {view?.active.length===0 && <p className="text-sm text-surface-500">No open instances on this page.</p>}
        {view?.active.map(session => <article key={key(session)} className={`runtime-admin-row ${selected && key(selected)===key(session) ? 'runtime-admin-selected' : ''}`}>
          <div className="flex gap-2 items-center flex-wrap"><strong>{session.harness}</strong><span className="runtime-admin-badge">{closing[key(session)] || session.durable_release_pending ? 'Closing…' : session.pool_state || session.lifecycle_state}</span></div>
          <p className="text-surface-500">{session.host} · {session.location==='embedded' ? 'Local' : 'Remote'}</p>
          <p className="break-all" title={session.scope.session_id}>{short(session.scope.session_id)}</p>
          <div className="flex gap-2 mt-2"><button className="btn btn-secondary" aria-label={`Inspect session ${session.scope.session_id}`} onClick={() => void inspect(session)}><Eye size={13}/> Inspect</button>
            <button className="btn btn-secondary text-red-600" disabled={!session.control_available || session.durable_release_pending || !!closing[key(session)]}
              title={!session.control_available ? 'Runtime control is unavailable. Wait for reconnection or reconciliation.' : 'End this runtime session'} onClick={() => close(session)}><Square size={12}/> End session</button></div>
        </article>)}
        {(back.length>0 || view?.has_more) && <div className="flex gap-2"><button className="btn btn-secondary" disabled={!back.length} onClick={() => {setAfter(back.at(-1)!);setBack(v=>v.slice(0,-1));}}>Previous</button>
          <button className="btn btn-secondary" disabled={!view?.has_more} onClick={() => {setBack(v=>[...v,after]);setAfter(view!.next_after);}}>Next</button></div>}
        <section className="space-y-2" aria-label="Last 10 completed executions"><h3 className="font-semibold text-sm">Last 10 completed executions</h3>
          <p className="text-xs text-surface-500">Finished calls, including failures and cancellations. Shared sessions can appear more than once.</p>
          {view?.completed.length===0 && <p className="text-sm text-surface-500">No completed calls yet.</p>}
          {view?.completed.map(row => <button key={`${row.executor_id}:${row.operation_id}`} className="runtime-admin-row w-full text-left hover:bg-surface-50 dark:hover:bg-surface-800" onClick={() => void inspect(row)}>
            <div className="flex justify-between gap-2"><strong>{row.harness}</strong><span className="runtime-admin-badge">{row.outcome}</span></div>
            <p>{date(row.completed_at)}</p><p className="text-surface-500">{row.host} · {short(row.session_id)}</p>
          </button>)}
        </section>
      </div>
      <div className="runtime-admin-inspector space-y-4" aria-label="Session inspector">
        {selected && <button className="btn btn-secondary runtime-admin-back" onClick={() => {setSelected(null);setOperation(null);setInspectionError('');}}>← Instances and executions</button>}
        {loading && <p role="status">Loading session…</p>}
        {inspectionError && <p role="alert" className="text-xs">{inspectionError}</p>}
        {!selected && !loading && <p className="text-sm text-surface-500">Select an instance or a completed execution to inspect its session.</p>}
        {selected && <>
          <header className="space-y-2"><h3 className="font-semibold text-sm">Session inspector</h3><p className="text-xs break-all">{selected.scope.session_id}</p>
            <p className="text-xs text-surface-500">{selected.lifecycle_state} · Lease {selected.lease_state} · Workspace {selected.scope.workspace_id}</p>
            {selected.durable_release_pending && <p role="status" className="text-xs">Waiting for runtime confirmation of closure.</p>}
          </header>
          {operation && <details open className="text-xs space-y-2"><summary className="cursor-pointer font-semibold">Execution result · {operation.executor_stage || operation.admission_state}</summary>
            {operation.error && <p role="alert">{operation.error.code}: {operation.error.message}</p>}
            <pre className="whitespace-pre-wrap break-all max-h-64 overflow-y-auto">{operation.result?.output_text || 'No final output recorded.'}{operation.result?.output_truncated ? '\n[Output truncated]' : ''}</pre>
          </details>}
          <div className="flex gap-2" role="group" aria-label="Session inspection mode">
            <button className="btn btn-secondary" aria-pressed={tab==='tail'} onClick={() => setTab('tail')}>Live tail</button>
            <button className="btn btn-secondary" aria-pressed={tab==='history'} onClick={() => setTab('history')}>History</button>
          </div>
          {tab==='tail' ? <RuntimeSessionTail key={key(selected)} scope={selected.scope} active={!sessionReleased(selected)}/> : <RuntimeHistory key={key(selected)} scope={selected.scope}/>}
        </>}
      </div>
    </div>
    <AgentModalFooter><button className="btn btn-secondary" onClick={onClose}>Close</button></AgentModalFooter>
  </AgentActionModal>;
}
