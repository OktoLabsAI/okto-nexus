import { ConfigurationHelp } from './ConfigurationHelp';
import { useEffect, useState } from 'react';
import { api, type RuntimePolicy as Policy, type SessionPolicy } from '../api';
import { OneShotSettings } from './OneShotSettings';

const fieldClass = 'block rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5';

export function RuntimePolicy({agentId, onUpdated, onPendingChange}: {agentId?: string; onUpdated?: (enabled: boolean) => void; onPendingChange?: (pending: boolean) => void}) {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [mcps, setMcps] = useState<boolean | null>(null);
  const [recovery,setRecovery] = useState(true);
  const [sessions, setSessions] = useState<SessionPolicy | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [revision, setRevision] = useState(0);
  const accept = (value: Policy) => {
    setMcps(value.inherit_global_mcps ?? (agentId ? null : false)); setPolicy(value); setEnabled(value.runtime_enabled); setSessions(value.session_policy);
    setRecovery(value.automatic_recovery ?? true);
    onUpdated?.(value.effective?.runtime_enabled ?? value.runtime_enabled ?? true);
  };
  useEffect(() => {
    let active = true;
    setBusy(true); setError('');
    api.runtimePolicy(agentId).then(value => {if (active) accept(value);})
      .catch(failure => {if (active) setError(String(failure));})
      .finally(() => {if (active) setBusy(false);});
    return () => {active = false;};
  }, [agentId, revision]);
  useEffect(() => {onPendingChange?.(busy || !policy || mcps !== (policy.inherit_global_mcps ?? null) || enabled !== policy.runtime_enabled || sessions !== policy.session_policy || (!agentId && recovery !== policy.automatic_recovery));}, [busy, policy, enabled, sessions, recovery, mcps, agentId, onPendingChange]);
  const effectiveEnabled = enabled ?? policy?.defaults?.runtime_enabled ?? true;
  const effectiveSessions = sessions ?? policy?.defaults?.session_policy ?? 'shared';
  return <section className="space-y-3" aria-label={agentId ? 'Agent runtime override' : 'Global runtime defaults'}>
    <h3 className="font-semibold">{agentId ? 'Runtime policy for this agent' : 'Global runtime defaults'}</h3>
    {!agentId && <label className="block"><input type="checkbox" checked={recovery} disabled={busy} onChange={e=>setRecovery(e.target.checked)} /> Automatic runtime recovery<ConfigurationHelp label="Automatic runtime recovery">Recover retained runtime state after restart using Core ownership proofs. New messages wait during recovery. Previously submitted work is never replayed. Recoverable failures retry automatically without abandoning queued messages.</ConfigurationHelp></label>}
    <p className="text-xs text-surface-500">{agentId ? 'Inherit the global settings or override each option for this agent, across all connections and workspaces.' : 'Defaults for all agents. An explicit agent override takes precedence.'}</p>
    <label className="block">Runtime connection <ConfigurationHelp label="Runtime connection">Runtime executes this harness through Nexus. MCP only keeps the existing MCP and inbox access. Disabling runtime blocks new work and closes existing sessions when their leases renew.</ConfigurationHelp>
      <select aria-label={agentId ? 'Agent runtime connection' : 'Global runtime connection'} className={fieldClass} value={enabled === null ? 'inherit' : enabled ? 'enabled' : 'disabled'} disabled={busy || !policy}
        onChange={event => {setEnabled(event.target.value === 'inherit' ? null : event.target.value === 'enabled'); setNotice('');}}>
        {agentId && <option value="inherit">Inherit global setting ({policy?.defaults?.runtime_enabled ? 'runtime enabled' : 'MCP only'})</option>}
        <option value="enabled">Runtime enabled</option><option value="disabled">MCP only — runtime disabled</option>
      </select>
    </label>
    <label className="block">Conversation sessions <ConfigurationHelp label="Conversation sessions">Shared uses one conversation for senders. Per sender shares history across sessions of the same agent. Per sender + source session isolates each verified source session. Senders without a verified session share a separate session per sender. Close sessions before changing this option, then authorize execution again.</ConfigurationHelp>
      <select aria-label={agentId ? 'Agent conversation sessions' : 'Global conversation sessions'} className={fieldClass} value={sessions ?? 'inherit'} disabled={busy || !policy}
        onChange={event => {setSessions(event.target.value === 'inherit' ? null : event.target.value as SessionPolicy); setNotice('');}}>
        {agentId && <option value="inherit">Inherit global setting ({policy?.defaults?.session_policy === 'one_shot' ? 'one shot' : policy?.defaults?.session_policy === 'per_sender_session' ? 'per sender + source session' : policy?.defaults?.session_policy === 'per_sender' ? 'per sender' : 'shared'})</option>}
        <option value="shared">Shared session</option><option value="per_sender">Separate session per sender</option><option value="per_sender_session">Separate session per sender + source session</option>
        <option value="one_shot">One shot — fresh session per call</option>
      </select>
    </label>
    {effectiveSessions === 'one_shot' && <OneShotSettings agentId={agentId} />}
    <label className="block">Include global harness MCPs <ConfigurationHelp label="Global harness MCPs">Include MCPs configured on the runtime host for Codex and Claude. Native project configuration precedence still applies. Nexus tools remain injected. This setting applies to new sessions; running sessions keep their configuration.</ConfigurationHelp>
      <select aria-label="Include global harness MCPs" className={fieldClass} disabled={busy || !policy}
        value={mcps === null ? 'inherit' : mcps ? 'enabled' : 'disabled'} onChange={e => {setMcps(e.target.value === 'inherit' ? null : e.target.value === 'enabled');setNotice('');}}>
        {agentId && <option value="inherit">Inherit global setting ({policy?.defaults?.inherit_global_mcps ? 'enabled' : 'disabled'})</option>}
        <option value="disabled">Disabled</option><option value="enabled">Enabled</option>
      </select>
    </label>
    <p>Effective selection: {effectiveEnabled ? 'runtime enabled' : 'MCP only'} · {effectiveSessions === 'one_shot' ? 'fresh session per call' : effectiveSessions === 'per_sender_session' ? 'separate session per sender + source session' : effectiveSessions === 'per_sender' ? 'separate session per sender' : 'shared session'}.</p>
    <button className="btn btn-primary" disabled={busy || !policy || (mcps === (policy.inherit_global_mcps ?? null) && enabled === policy.runtime_enabled && sessions === policy.session_policy && (!!agentId || recovery === policy.automatic_recovery))} onClick={async () => {
      if (!policy) return;
      setBusy(true); setError(''); setNotice('');
      try {accept(await api.saveRuntimePolicy({expected_revision: policy.revision, inherit_global_mcps: mcps, runtime_enabled: enabled, session_policy: sessions,...(!agentId ? {automatic_recovery:recovery} : {})}, agentId)); setNotice('Runtime policy saved.');}
      catch (failure) {setError(String(failure));}
      finally {setBusy(false);}
    }}>{agentId ? 'Save agent runtime policy' : 'Save global runtime defaults'}</button>
    <button className="btn btn-secondary ml-2" disabled={busy} onClick={() => setRevision(value => value + 1)}>Reload runtime policy</button>
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
