import { useEffect, useState } from 'react';
import { api, type RuntimePolicy as Policy } from '../api';

const fieldClass = 'block rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5';

export function RuntimePolicy({agentId, onUpdated}: {agentId?: string; onUpdated?: (enabled: boolean) => void}) {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [sessions, setSessions] = useState<'shared' | 'per_sender' | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [revision, setRevision] = useState(0);
  const accept = (value: Policy) => {
    setPolicy(value); setEnabled(value.runtime_enabled); setSessions(value.session_policy);
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
  const effectiveEnabled = enabled ?? policy?.defaults?.runtime_enabled ?? true;
  const effectiveSessions = sessions ?? policy?.defaults?.session_policy ?? 'shared';
  return <section className="panel p-4 space-y-3" aria-label={agentId ? 'Agent runtime override' : 'Global runtime defaults'}>
    <h3 className="font-semibold">{agentId ? 'Runtime policy for this agent' : 'Global runtime defaults'}</h3>
    <p>{agentId ? 'Inherit the global settings or override each option for this agent, across all connections and workspaces.' : 'Defaults for all agents. An explicit agent override takes precedence.'}</p>
    <label className="block">Runtime connection
      <select aria-label={agentId ? 'Agent runtime connection' : 'Global runtime connection'} className={fieldClass} value={enabled === null ? 'inherit' : enabled ? 'enabled' : 'disabled'} disabled={busy || !policy}
        onChange={event => {setEnabled(event.target.value === 'inherit' ? null : event.target.value === 'enabled'); setNotice('');}}>
        {agentId && <option value="inherit">Inherit global setting ({policy?.defaults?.runtime_enabled ? 'runtime enabled' : 'MCP only'})</option>}
        <option value="enabled">Runtime enabled</option><option value="disabled">MCP only — runtime disabled</option>
      </select>
    </label>
    <label className="block">Conversation sessions
      <select aria-label={agentId ? 'Agent conversation sessions' : 'Global conversation sessions'} className={fieldClass} value={sessions ?? 'inherit'} disabled={busy || !policy}
        onChange={event => {setSessions(event.target.value === 'inherit' ? null : event.target.value as 'shared' | 'per_sender'); setNotice('');}}>
        {agentId && <option value="inherit">Inherit global setting ({policy?.defaults?.session_policy === 'per_sender' ? 'per sender' : 'shared'})</option>}
        <option value="shared">Shared session</option><option value="per_sender">Separate session per sender</option>
      </select>
    </label>
    <p>Effective selection: {effectiveEnabled ? 'runtime enabled' : 'MCP only'} · {effectiveSessions === 'per_sender' ? 'separate session per sender' : 'shared session'}.</p>
    <p>MCP access and inbox delivery remain available under the existing agent permissions. Disabling runtime blocks new runtime work; existing sessions lose execution permission and close when their leases are renewed.</p>
    <p>Close affected sessions before changing conversation isolation. Policy changes affecting execution invalidate its permissions; authorize execution again after enabling runtime.</p>
    <button className="btn btn-primary" disabled={busy || !policy || (enabled === policy.runtime_enabled && sessions === policy.session_policy)} onClick={async () => {
      if (!policy) return;
      setBusy(true); setError(''); setNotice('');
      try {accept(await api.saveRuntimePolicy({expected_revision: policy.revision, runtime_enabled: enabled, session_policy: sessions}, agentId)); setNotice('Runtime policy saved.');}
      catch (failure) {setError(String(failure));}
      finally {setBusy(false);}
    }}>{agentId ? 'Save agent runtime policy' : 'Save global runtime defaults'}</button>
    <button className="btn btn-secondary ml-2" disabled={busy} onClick={() => setRevision(value => value + 1)}>Reload runtime policy</button>
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
