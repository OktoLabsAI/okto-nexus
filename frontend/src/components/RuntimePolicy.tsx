import { useSettingsDraft } from './SettingsDrafts';
import { ConfigurationHelp } from './ConfigurationHelp';
import { useEffect, useState } from 'react';
import { api, type RuntimePolicy as Policy, type SessionPolicy } from '../api';
import { OneShotSettings } from './OneShotSettings';
import { BroadcastHandoffPolicy } from './BroadcastHandoffPolicy';

const fieldClass = 'mt-1.5 block w-full min-w-0 rounded-lg border border-surface-300 dark:border-surface-600 bg-white dark:bg-surface-800 px-3 py-2 text-sm font-normal text-surface-900 dark:text-surface-100 outline-none focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 disabled:opacity-50';
const labelClass = 'block min-w-0 text-xs font-medium text-surface-700 dark:text-surface-200';

export function RuntimePolicy({agentId, onUpdated, onPendingChange}: {agentId?: string; onUpdated?: (enabled: boolean) => void; onPendingChange?: (pending: boolean) => void}) {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [mcps, setMcps] = useState<boolean | null>(null);
  const [autoClaim, setAutoClaim] = useState<boolean | null>(null);
  const [recovery,setRecovery] = useState(true);
  const [sessions, setSessions] = useState<SessionPolicy | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [revision, setRevision] = useState(0);
  const accept = (value: Policy) => {
    setMcps(value.inherit_global_mcps ?? (agentId ? null : false)); setPolicy(value); setEnabled(value.runtime_enabled); setSessions(value.session_policy);
    setRecovery(value.automatic_recovery ?? true);
    setAutoClaim(value.broadcast_handoff_auto_claim ?? (agentId ? null : false));
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
  const changed = !!policy && (autoClaim !== policy.broadcast_handoff_auto_claim || mcps !== (policy.inherit_global_mcps ?? null) || enabled !== policy.runtime_enabled || sessions !== policy.session_policy || (!agentId && recovery !== policy.automatic_recovery));
  useEffect(() => {onPendingChange?.(busy || !policy || changed);}, [busy, policy, changed, onPendingChange]);
  const effectiveEnabled = enabled ?? policy?.defaults?.runtime_enabled ?? true;
  const effectiveSessions = sessions ?? policy?.defaults?.session_policy ?? 'shared';
  const save = async () => {
      if (!policy) return false;
      setBusy(true); setError(''); setNotice('');
      try {accept(await api.saveRuntimePolicy({expected_revision: policy.revision, broadcast_handoff_auto_claim: autoClaim, inherit_global_mcps: mcps, runtime_enabled: enabled, session_policy: sessions,...(!agentId ? {automatic_recovery:recovery} : {})}, agentId)); setNotice('Runtime policy saved.'); return true;}
      catch (failure) {setError(String(failure)); return false;}
      finally {setBusy(false);}
    };
  const managed = useSettingsDraft('runtime-policy', {dirty: changed, valid: !busy && !!policy, save});
  return <section className="space-y-4" aria-label={agentId ? 'Agent runtime override' : 'Global runtime defaults'}>
    <h3 className="font-display font-semibold text-sm">{agentId ? 'Runtime policy for this agent' : 'Global runtime defaults'}</h3>
    <p className="text-xs text-surface-500">{agentId ? 'Inherit the global settings or override each option for this agent, across all connections and workspaces.' : 'Defaults for all agents. An explicit agent override takes precedence.'}</p>
    {!agentId && <label className="flex items-center gap-2 text-xs font-medium text-surface-700 dark:text-surface-200"><input className="h-4 w-4 accent-accent-500" type="checkbox" checked={recovery} disabled={busy || !policy} onChange={e=>setRecovery(e.target.checked)} /> Automatic runtime recovery<ConfigurationHelp label="Automatic runtime recovery">Recover retained runtime state after restart using Core ownership proofs. New messages wait during recovery. Previously submitted work is never replayed. Recoverable failures retry automatically without abandoning queued messages.</ConfigurationHelp></label>}
    <div className="grid min-w-0 grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-2">
    <label className={labelClass}>Runtime connection <ConfigurationHelp label="Runtime connection">Runtime executes this harness through Nexus. MCP only keeps the existing MCP and inbox access. Disabling runtime blocks new work and closes existing sessions when their leases renew.</ConfigurationHelp>
      <select aria-label={agentId ? 'Agent runtime connection' : 'Global runtime connection'} className={fieldClass} value={enabled === null ? 'inherit' : enabled ? 'enabled' : 'disabled'} disabled={busy || !policy}
        onChange={event => {setEnabled(event.target.value === 'inherit' ? null : event.target.value === 'enabled'); setNotice('');}}>
        {agentId && <option value="inherit">Inherit global setting ({policy?.defaults?.runtime_enabled ? 'runtime enabled' : 'MCP only'})</option>}
        <option value="enabled">Runtime enabled</option><option value="disabled">MCP only — runtime disabled</option>
      </select>
    </label>
    <label className={labelClass}>Conversation sessions <ConfigurationHelp label="Conversation sessions">Shared uses one conversation for senders. Per sender shares history across sessions of the same agent. Per sender + source session isolates each verified source session. Senders without a verified session share a separate session per sender. Close sessions before changing this option, then authorize execution again.</ConfigurationHelp>
      <select aria-label={agentId ? 'Agent conversation sessions' : 'Global conversation sessions'} className={fieldClass} value={sessions ?? 'inherit'} disabled={busy || !policy}
        onChange={event => {setSessions(event.target.value === 'inherit' ? null : event.target.value as SessionPolicy); setNotice('');}}>
        {agentId && <option value="inherit">Inherit global setting ({policy?.defaults?.session_policy === 'one_shot' ? 'one shot' : policy?.defaults?.session_policy === 'per_sender_session' ? 'per sender + source session' : policy?.defaults?.session_policy === 'per_sender' ? 'per sender' : 'shared'})</option>}
        <option value="shared">Shared session</option><option value="per_sender">Separate session per sender</option><option value="per_sender_session">Separate session per sender + source session</option>
        <option value="one_shot">One shot — fresh session per call</option>
      </select>
    </label>
    <div className={labelClass}><BroadcastHandoffPolicy value={autoClaim} onChange={value => {setAutoClaim(value);setNotice('');}}
      inherited={agentId ? policy?.defaults?.broadcast_handoff_auto_claim ?? false : undefined}
      rolloutEnabled={policy?.handoff_auto_claim_rollout_enabled ?? false} disabled={busy || !policy} className={fieldClass} /></div>
    <label className={labelClass}>Include global harness MCPs <ConfigurationHelp label="Global harness MCPs">Include MCPs configured on the runtime host for Codex and Claude. Native project configuration precedence still applies. Nexus tools remain injected. This setting applies to new sessions; running sessions keep their configuration.</ConfigurationHelp>
      <select aria-label="Include global harness MCPs" className={fieldClass} disabled={busy || !policy}
        value={mcps === null ? 'inherit' : mcps ? 'enabled' : 'disabled'} onChange={e => {setMcps(e.target.value === 'inherit' ? null : e.target.value === 'enabled');setNotice('');}}>
        {agentId && <option value="inherit">Inherit global setting ({policy?.defaults?.inherit_global_mcps ? 'enabled' : 'disabled'})</option>}
        <option value="disabled">Disabled</option><option value="enabled">Enabled</option>
      </select>
    </label>
    </div>
    {(managed || effectiveSessions === 'one_shot') && <div className="border-t border-surface-200 dark:border-surface-700 pt-4" hidden={effectiveSessions !== 'one_shot'}><OneShotSettings agentId={agentId} /></div>}
    <p className="border-t border-surface-200 dark:border-surface-700 pt-3 text-xs text-surface-500">Effective selection: {effectiveEnabled ? 'runtime enabled' : 'MCP only'} · {effectiveSessions === 'one_shot' ? 'fresh session per call' : effectiveSessions === 'per_sender_session' ? 'separate session per sender + source session' : effectiveSessions === 'per_sender' ? 'separate session per sender' : 'shared session'}.</p>
    {!managed && <><button className="btn btn-primary" disabled={busy || !policy || !changed} onClick={save}>{agentId ? 'Save agent runtime policy' : 'Save global runtime defaults'}</button>
    <button className="btn btn-secondary ml-2" disabled={busy} onClick={() => setRevision(value => value + 1)}>Reload runtime policy</button></>}
    {notice && <p className="text-xs" role="status">{notice}</p>}{error && <p className="text-xs text-red-500" role="alert">{error}</p>}
  </section>;
}
