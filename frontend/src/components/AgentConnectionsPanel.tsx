import { ConnectionWorkflow } from "./ConnectionWorkflow";
import { ConfigurationHelp, ConfigurationSection } from './ConfigurationHelp';
import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { api, type AgentExecutionPolicy } from "../api";
import { RuntimeSelection } from "./RuntimeSelection";
import { RuntimePolicy } from "./RuntimePolicy";
import { RemoteConnectorCommand } from "./RemoteConnectorCommand";
import { runtimeApi, localRuntimeAvailability, type RuntimeOptions } from "../runtimeApi";

const fieldClass = "ml-2 rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5";

export function AgentConnectionsPanel({agentId, onClose}: {agentId: string; onClose: () => void}) {
  const [wizard, setWizard] = useState(false);
  const [wizardStarted, setWizardStarted] = useState(false);
  const [runtimePending, setRuntimePending] = useState(true);
  const [policy, setPolicy] = useState<AgentExecutionPolicy | null>(null);
  const [runtimeEnabled, setRuntimeEnabled] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [dirty, setDirty] = useState(false);
  const [inventory, setInventory] = useState<RuntimeOptions | null>(null);
  const [loadingInventory, setLoadingInventory] = useState(true);
  const [inventoryRevision, setInventoryRevision] = useState(0);
  const [inventoryError, setInventoryError] = useState('');
  useEffect(() => {
    if (!policy || policy.execution_location === 'remote') return;
    const controller = new AbortController();
    setLoadingInventory(true); setInventoryError('');
    void (async () => {
      try {
        const hosts = (await runtimeApi.executors(agentId, controller.signal)).filter(host => host.kind === 'embedded');
        if (hosts.length !== 1) throw new Error('The local runtime host is unavailable. Check the Server runtime service.');
        const current = await runtimeApi.options(agentId, hosts[0].executor_id, '', controller.signal);
        if (!controller.signal.aborted) setInventory(current);
      } catch (failure) {if (!controller.signal.aborted) {setInventory(null); setInventoryError(String(failure));}}
      finally {if (!controller.signal.aborted) setLoadingInventory(false);}
    })();
    return () => controller.abort();
  }, [agentId, inventoryRevision, policy?.execution_location]);
  useEffect(() => {
    const refresh = () => setInventoryRevision(value => value + 1);
    window.addEventListener('focus', refresh);
    const timer = window.setInterval(refresh, 30000);
    return () => {window.removeEventListener('focus', refresh); window.clearInterval(timer);};
  }, []);
  useEffect(() => {
    let active = true;
    api.agentExecutionPolicy(agentId).then(value => {if (active) setPolicy(value);})
      .catch(failure => {if (active) setError(String(failure));});
    return () => {active = false;};
  }, [agentId]);
  const savePolicy = async () => {
    if (!policy) throw new Error('Execution policy is unavailable.');
    const saved = await api.saveAgentExecutionPolicy(agentId, {expected_revision: policy.revision,
      execution_location: policy.execution_location, local_adapter_id: policy.local_adapter_id});
    setPolicy(saved); setDirty(false); setNotice('Execution policy saved.');
  };
  return <section className="rounded-lg border p-3 space-y-3 text-xs" data-testid={`agent-connections-${agentId}`}>
    <div className="flex justify-between items-center"><h3>Connections · {agentId}</h3>
      <button className="btn btn-secondary" onClick={onClose}>Close</button></div>
    {!wizard && <ConnectionWorkflow step={0} summaries={[runtimeEnabled ? `${policy?.execution_location || "Loading"} · ${policy?.local_adapter_id || "Select a harness"}` : "MCP only"]} onStep={() => {}} />}
    <div hidden={wizard} className="space-y-3">
    <details><summary className="cursor-pointer text-surface-500">MCP connection details</summary><p>MCP HTTP: <code>{window.location.origin}/mcp</code>. Authenticate with this agent's existing API key.</p></details>
    <ConfigurationSection title="Runtime behavior" status={runtimeEnabled ? "Runtime enabled · optional overrides" : "MCP only · runtime disabled"}><RuntimePolicy agentId={agentId} onPendingChange={setRuntimePending} onUpdated={enabled => {setRuntimeEnabled(enabled); setInventoryRevision(value => value + 1);}} /></ConfigurationSection>
    {policy && runtimeEnabled && <>
      <label className="block">Execution host <span className="text-surface-500">Required</span><ConfigurationHelp label="Execution host">Local runs on this Nexus server. Remote uses a Connector. All permits both, subject to authorization.</ConfigurationHelp><select className={fieldClass} aria-label="Execution access" value={policy.execution_location} disabled={busy}
        onChange={event => {setDirty(true); setNotice(''); setPolicy({...policy, execution_location: event.target.value as AgentExecutionPolicy['execution_location']});}}>
        <option value="local">Local</option><option value="remote">Remote</option><option value="all">All</option>
      </select></label>

      {policy.execution_location !== 'remote' && <div className="space-y-2">
        <h4 className="font-semibold">Harness <span className="text-xs font-normal text-surface-500">Required</span></h4>
        {loadingInventory && <p role="status">Detecting available runtimes…</p>}
        {inventoryError && <p role="alert">{inventoryError}</p>}
        <div role="group" aria-label="Local runtime" className="flex flex-wrap gap-2">
          {inventory?.catalog.runtimes.map(item => {
            const availability = localRuntimeAvailability(inventory, item.adapter_id);
            return <button key={item.adapter_id} type="button" data-testid={`local-runtime-${item.adapter_id}`}
              aria-pressed={policy.local_adapter_id === item.adapter_id} disabled={busy || !availability.available}
              title={availability.label} className={`rounded-lg border px-4 py-3 text-left disabled:opacity-40 disabled:cursor-not-allowed ${policy.local_adapter_id === item.adapter_id ? 'border-accent-500 bg-accent-100 text-accent-800 dark:bg-accent-900/40 dark:text-accent-200' : 'border-surface-300 dark:border-surface-700'}`}
              onClick={() => {setDirty(true); setNotice(''); setPolicy({...policy, local_adapter_id: item.adapter_id});}}>
              <span className="flex items-center gap-2 font-semibold">{policy.local_adapter_id === item.adapter_id && <Check size={14} aria-hidden="true" />}{item.display_name}</span><span className="block text-xs">{availability.label}</span>
            </button>;
          })}
        </div>
        <button className="btn btn-secondary" disabled={loadingInventory} onClick={() => {setError(''); setInventoryRevision(value => value + 1);}}>Reload runtime availability</button>
        {dirty && <p role="status">Next saves the selected host and harness.</p>}
        {!policy.local_adapter_id && <p>Select an available runtime to configure it.</p>}

      </div>}
      {policy.execution_location !== 'local' && <p>Configure remote identity, installation and runtime integration in the Connector using this agent's ID and API key.</p>}
      {policy.execution_location !== 'local' && <RemoteConnectorCommand agentId={agentId} />}

      <button className="btn btn-primary" disabled={busy || !dirty || (policy.execution_location !== 'remote' && (!policy.local_adapter_id || !inventory || !localRuntimeAvailability(inventory, policy.local_adapter_id).available))} onClick={async () => {
        setBusy(true); setError(''); setNotice('');
        try {await savePolicy();}
        catch (failure) {setError(String(failure));} finally {setBusy(false);}
      }}>Save execution policy</button>
      {policy.execution_location !== "remote" && <button className="btn btn-primary ml-2" disabled={busy || runtimePending || !policy.local_adapter_id || !inventory || !localRuntimeAvailability(inventory, policy.local_adapter_id).available} onClick={async () => {
        setBusy(true); setError("");
        try {if (dirty) await savePolicy(); setWizardStarted(true); setWizard(true);} catch (failure) {setError(String(failure));} finally {setBusy(false);}
      }}>Next →</button>}
      {runtimePending && <p role="status">Save the runtime behavior changes before continuing.</p>}
    </>}
    </div>
    {policy && runtimeEnabled && policy.execution_location !== "remote" && policy.local_adapter_id && <div hidden={!wizard}>
      {wizardStarted && <RuntimeSelection key={JSON.stringify([agentId, policy.local_adapter_id])} agentId={agentId} configureLocal
        localAdapterId={policy.local_adapter_id} configurationSaved={!dirty} onBackHost={() => setWizard(false)} onFinish={onClose}
        onInventoryUpdated={() => setInventoryRevision(value => value + 1)} />}
    </div>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
  </section>;
}
