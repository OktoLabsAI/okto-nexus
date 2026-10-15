import { useEffect, useState } from 'react';
import { ChevronDown } from 'lucide-react';
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
  return <section aria-label={`Instance pool for ${agentId}`} className="min-w-0 border-t border-surface-200 dark:border-surface-700 pt-2 mt-1 text-xs">
    <details className="group">
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded py-1 text-surface-600 dark:text-surface-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500/40 [&::-webkit-details-marker]:hidden">
        <ChevronDown aria-hidden="true" size={13} className="shrink-0 -rotate-90 transition-transform group-open:rotate-0" />
        <span className="font-medium">Live instance pool</span>
        {state && <span className="ml-auto text-[11px] tabular-nums text-surface-500">{state.available}/{limit(state.max_pool_instances)} available</span>}
      </summary>
      <div className="space-y-2 pt-2">
    {!state && !error && <p role="status">Loading pool status…</p>}
    {state && <>
      <div role="img" aria-label={segments.map(s => `${s.label}: ${s.count}`).join(', ')} className="flex h-1.5 overflow-hidden rounded-full bg-surface-100 dark:bg-surface-700">
        {segments.map(segment => <span key={segment.label} title={`${segment.label}: ${segment.count}`} className={segment.color}
          style={{width: `${segment.count / scale * 100}%`}} />)}
      </div>
      <dl className="space-y-1 text-xs">
        <div className="flex items-baseline justify-between gap-3"><dt className="text-surface-500">Available / pool limit</dt>
          <dd className="font-medium tabular-nums">{state.available} / {limit(state.max_pool_instances)}</dd></div>
        <div className="flex items-baseline justify-between gap-3"><dt className="text-surface-500">Maximum parallel executions</dt>
          <dd className="font-medium tabular-nums">{limit(state.max_parallel)}</dd></div>
      </dl>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-surface-500">{segments.map(segment => <span key={segment.label} className="inline-flex items-center gap-1">
        <span className={`h-2 w-2 rounded-full ${segment.color}`} />{segment.count} {segment.label.toLowerCase()}
      </span>)}<span>{state.queued} queued</span></div>
      <p className="text-[11px] text-surface-500" title="All instance states count toward the pool limit.">Warm target: {state.warm_target}</p>
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
      </div>
    </details>
  </section>;
}
