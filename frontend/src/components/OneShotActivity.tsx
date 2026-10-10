import { useEffect, useState } from 'react';
import { api, type OneShotState } from '../api';

export function OneShotActivity({agentId, showCalls = true, revision}: {agentId: string; showCalls?: boolean; revision?: number}) {
  const [state, setState] = useState<OneShotState | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    let active = true, timer: ReturnType<typeof setTimeout>;
    setState(null); setError('');
    const refresh = async () => {
      try {
        const policy = await api.runtimePolicy(agentId);
        const pooled = policy.effective?.runtime_enabled && policy.effective.session_policy === 'one_shot';
        if (active) setEnabled(!!pooled);
        if (pooled) {const value = await api.oneShotState(agentId); if (active) {setState(value); setError('');}}
      }
      catch (e) {if (active) setError(String(e));}
      finally {if (active) timer = setTimeout(refresh, 5000);}
    };
    void refresh();
    return () => {active = false; clearTimeout(timer);};
  }, [agentId, revision]);
  const limit = (value: number) => value === 0 ? 'Unlimited' : String(value);
  if (!enabled) return null;
  const segments = state ? [
    {label: 'Available', count: state.available, color: 'bg-emerald-500'},
    {label: 'Warming', count: state.slots.STARTING ?? 0, color: 'bg-amber-400'},
    {label: 'Assigned', count: state.slots.CLAIMED ?? 0, color: 'bg-violet-400'},
    {label: 'Running', count: state.slots.RUNNING ?? 0, color: 'bg-blue-500'},
    {label: 'Closing', count: state.slots.CLOSING ?? 0, color: 'bg-slate-400'},
  ] : [];
  const scale = state ? Math.max(state.max_pool_instances, state.occupied, 1) : 1;
  return <section aria-label={`Instance pool for ${agentId}`} className="space-y-2 min-w-0 border-t pt-3 mt-1">
    <h5 className="font-semibold">Live instance pool</h5>
    {!state && !error && <p role="status" className="text-sm">Loading pool status…</p>}
    {state && <>
      <div role="img" aria-label={segments.map(s => `${s.label}: ${s.count}`).join(', ')} className="flex h-3 overflow-hidden rounded-full bg-surface-100 dark:bg-surface-700">
        {segments.map(segment => <span key={segment.label} title={`${segment.label}: ${segment.count}`} className={segment.color}
          style={{width: `${segment.count / scale * 100}%`}} />)}
      </div>
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 rounded border p-3 text-sm">
        <div className="min-w-0"><dt className="text-surface-500">Available / maximum pool instances</dt>
          <dd className="font-semibold text-lg tabular-nums">{state.available} / {limit(state.max_pool_instances)}</dd></div>
        <div className="min-w-0"><dt className="text-surface-500">Maximum parallel executions</dt>
          <dd className="font-semibold text-lg tabular-nums">{limit(state.max_parallel)}</dd></div>
      </dl>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs">{segments.map(segment => <span key={segment.label} className="inline-flex items-center gap-1">
        <span className={`h-2 w-2 rounded-full ${segment.color}`} />{segment.count} {segment.label.toLowerCase()}
      </span>)}<span>{state.queued} queued</span></div>
      <p className="text-xs text-surface-500">Warm target: {state.warm_target}. All instance states count toward the pool limit.</p>
    </>}
    {showCalls && <p className="text-xs text-surface-500">Cancellation stops the call and requests session closure. Work already performed may have side effects.</p>}
    {showCalls && state?.calls.slice(0, 10).map(call => <div key={call.call_id} className="border rounded p-2 text-xs min-w-0 break-words">
      <p>{call.state} · Caller: {call.caller_id}</p><p className="font-mono break-all">{call.call_id}</p>
      {call.error && <p>{call.error.code}: {call.error.message}{call.error.possible_effect ? ' Work may already have taken effect.' : ''}</p>}
      {['QUEUED', 'ADMITTED', 'RUNNING'].includes(call.state) && <button className="btn btn-secondary" disabled={busy} onClick={async () => {
        setBusy(true); setError('');
        try {setState(await api.cancelOneShot(agentId, call.call_id));}
        catch (e) {setError(String(e));} finally {setBusy(false);}
      }}>Cancel call</button>}
    </div>)}
    {error && <p role="alert">{error}</p>}
  </section>;
}
