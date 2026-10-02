import { useEffect, useState } from "react";
import { api, type AgentExecutionPolicy } from "../api";
import { RuntimeSelection } from "./RuntimeSelection";

const fieldClass = "ml-2 rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5";

export function AgentConnectionsPanel({agentId, onClose}: {agentId: string; onClose: () => void}) {
  const [policy, setPolicy] = useState<AgentExecutionPolicy | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    let active = true;
    api.agentExecutionPolicy(agentId).then(value => {if (active) setPolicy(value);})
      .catch(failure => {if (active) setError(String(failure));});
    return () => {active = false;};
  }, [agentId]);
  return <section className="rounded-lg border p-3 space-y-3 text-xs" data-testid={`agent-connections-${agentId}`}>
    <div className="flex justify-between items-center"><h3>Connections · {agentId}</h3>
      <button className="btn btn-secondary" onClick={onClose}>Close</button></div>
    <p>MCP HTTP: <code>{window.location.origin}/mcp</code>. Authenticate with this agent's existing API key.</p>
    {policy && <>
      <label className="block">Execution access <select className={fieldClass} aria-label="Execution access" value={policy.execution_location} disabled={busy}
        onChange={event => {setDirty(true); setPolicy({...policy, execution_location: event.target.value as AgentExecutionPolicy['execution_location']});}}>
        <option value="local">Local</option><option value="remote">Remote</option><option value="all">All</option>
      </select></label>
      <p>Restricts where this agent may execute. All permits both local and authorized remote hosts.</p>
      {policy.execution_location !== 'remote' && <label className="block">Local runtime integration <select className={fieldClass} aria-label="Local runtime integration"
        disabled={busy} value={policy.local_adapter_id ?? ''} onChange={event => {setDirty(true); setPolicy({...policy, local_adapter_id: event.target.value || null});}}>
        <option value="">Select an integration</option>
        {policy.local_integrations.map(item => <option key={item.adapter_id} value={item.adapter_id}>{item.label}</option>)}
      </select></label>}
      {policy.execution_location !== 'local' && <p>Configure remote identity, installation and runtime integration in the Connector using this agent's ID and API key.</p>}
      <p>The workspace comes from the message or task. It is not part of the agent identity.</p>
      <button className="btn btn-primary" disabled={busy || (policy.execution_location !== 'remote' && !policy.local_adapter_id)} onClick={async () => {
        setBusy(true); setError(''); setNotice('');
        try {setPolicy(await api.saveAgentExecutionPolicy(agentId, {expected_revision: policy.revision,
          execution_location: policy.execution_location, local_adapter_id: policy.local_adapter_id})); setDirty(false); setNotice('Execution policy saved.');}
        catch (failure) {setError(String(failure));} finally {setBusy(false);}
      }}>Save execution policy</button>
    </>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {dirty && <p role="status">Save the execution policy before configuring the local integration.</p>}
    {policy && !dirty && policy.execution_location !== 'remote' && !policy.local_adapter_id &&
      <p>Select and save the local runtime integration to configure its installation and environment.</p>}
    {policy && !dirty && policy.execution_location !== 'remote' && policy.local_adapter_id &&
      <RuntimeSelection key={JSON.stringify([agentId, policy.revision])} agentId={agentId} configureLocal />}
  </section>;
}
