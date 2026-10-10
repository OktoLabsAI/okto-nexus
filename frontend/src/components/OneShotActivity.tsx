import { useEffect, useState } from 'react';
import { api, type OneShotState } from '../api';

export function OneShotActivity({agentId, showCalls = true, revision}: {agentId: string; showCalls?: boolean; revision?: number}) {
  const [state, setState] = useState<OneShotState | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true, timer: ReturnType<typeof setTimeout>;
    setState(null); setError('');
    const refresh = async () => {
      try {const value = await api.oneShotState(agentId); if (active) {setState(value); setError('');}}
      catch (e) {if (active) setError(String(e));}
      finally {if (active) timer = setTimeout(refresh, 5000);}
    };
    void refresh();
    return () => {active = false; clearTimeout(timer);};
  }, [agentId, revision]);
  const limit = (value: number) => value === 0 ? 'Unlimited' : String(value);
  return <section aria-label="One-shot activity" className="space-y-2 min-w-0">
    <h5 className="font-semibold">Live instance pool</h5>
    <p className="text-xs text-surface-500">Uses saved settings. Updates every 5 seconds. Only ready, unused sessions are available; host capacity still applies.</p>
    {!state && !error && <p role="status" className="text-sm">Loading pool status…</p>}
    {state && <>
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 rounded border p-3 text-sm">
        <div className="min-w-0"><dt className="text-surface-500">Available / maximum pool instances</dt>
          <dd className="font-semibold text-lg tabular-nums">{state.available} / {limit(state.max_pool_instances)}</dd></div>
        <div className="min-w-0"><dt className="text-surface-500">Maximum parallel executions</dt>
          <dd className="font-semibold text-lg tabular-nums">{limit(state.max_parallel)}</dd></div>
      </dl>
      <p className="text-sm break-words">{state.occupied} total · {state.slots.STARTING ?? 0} warming · {state.slots.CLAIMED ?? 0} assigned · {state.slots.RUNNING ?? 0} running · {state.slots.CLOSING ?? 0} closing · {state.queued} queued</p>
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
