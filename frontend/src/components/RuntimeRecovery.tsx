import { useState } from 'react';
import { runtimeApi, type RecoveryPlan } from '../runtimeApi';

export function RuntimeRecovery({agentId, onChanged}: {agentId: string; onChanged: () => void}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [plan, setPlan] = useState<RecoveryPlan | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const act = async (work: () => Promise<void>) => {
    setBusy(true);
    try { await work(); }
    catch (e) { setMessage(e instanceof Error ? e.message : String(e)); setPlan(null); setConfirmed(false); }
    finally { setBusy(false); }
  };
  return <div className="m-4 rounded-lg border border-amber-500/30 p-3 text-sm space-y-2">
    <p>Nexus is automatically restoring {agentId}. Other agents remain available.</p>
    <button className="btn btn-secondary text-xs disabled:opacity-50" disabled={busy} onClick={() => act(async () => {
      setPlan(null); setConfirmed(false);
      const result = await runtimeApi.retryRecovery(agentId);
      setMessage(result.message); setBlocked(result.state !== 'READY'); onChanged();
    })}>{busy ? 'Recovering…' : 'Retry recovery'}</button>
    {message && <p role="status" className="break-words">{message}</p>}
    {blocked && !plan && <button className="btn btn-secondary text-xs disabled:opacity-50" disabled={busy} onClick={() => act(async () => {
      setPlan(await runtimeApi.recoveryPlan(agentId)); setConfirmed(false);
    })}>Review last-resort recovery</button>}
    {plan && <div className="space-y-2">
      <p>Automatic recovery could not establish that the previous runtimes stopped.
        This concerns only the {plan.sessions.length} sessions listed below for this agent.</p>
      <p>Stop the previous runtime processes before continuing. If you cannot identify them, restart this computer and return here. History is preserved; interrupted work is not replayed.</p>
      <ul className="max-h-36 overflow-y-auto break-all font-mono text-xs">
        {plan.sessions.map(s => <li key={s.session_id}>{s.agent_id}: {s.session_id}</li>)}
      </ul>
      <label className="flex gap-2 items-start"><input type="checkbox" checked={confirmed}
        onChange={e => setConfirmed(e.target.checked)} disabled={busy} />
        I have verified that the previous runtime processes for these sessions have stopped.</label>
      <button className="btn btn-secondary text-xs disabled:opacity-50" disabled={busy || !confirmed || !plan.sessions.length}
        onClick={() => act(async () => {
          const result = await runtimeApi.confirmStopped(plan);
          setMessage(result.message); setPlan(null); setConfirmed(false);
          setBlocked(result.state !== 'READY'); onChanged();
        })}>Restore local runtime</button>
    </div>}
  </div>;
}
