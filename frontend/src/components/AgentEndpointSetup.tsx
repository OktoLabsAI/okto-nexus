import { useEffect, useState } from "react";
import { api, type AgentConnections } from "../api";

const fieldClass = "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs text-surface-700 dark:text-surface-200 focus:outline-none focus:ring-2 focus:ring-accent-500/40 disabled:opacity-50";

export function AgentEndpointSetup({agentId, methods, onCreated, onCancel}: {
  agentId: string; methods: AgentConnections["methods"]; onCreated: () => Promise<void>; onCancel: () => void;
}) {
  const native = methods.filter(m => m.method !== "mcp");
  const [adapter, setAdapter] = useState(native.find(m => m.enabled && m.platform_compatible !== false)?.method || native.find(m => m.platform_compatible !== false)?.method || "");
  const [endpoint, setEndpoint] = useState("");
  const [root, setRoot] = useState("");
  const [profile, setProfile] = useState("");
  const [profiles, setProfiles] = useState<Array<{profile_id: string; adapter_id: string; enabled: boolean}>>([]);
  const [binary, setBinary] = useState("");
  const [configuration, setConfiguration] = useState("{}");
  const [pid, setPid] = useState("");
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const selected = native.find(m => m.method === adapter);
  const attach = selected?.substrate === "attach";
  useEffect(() => { void api.runtimeProfiles().then(r => setProfiles(r.items)).catch(e => setError(String(e))); }, []);
  const create = async () => {
    setBusy(true); setError("");
    let selectedProfile = profile || `${endpoint}-profile`;
    try {
      if (!attach && !profile) {
        const config: unknown = JSON.parse(configuration);
        if (!config || typeof config !== "object" || Array.isArray(config)) throw new Error("Runtime configuration must be a JSON object.");
        const parameters = {...config as Record<string, unknown>};
        if (binary.trim()) parameters.command = [binary.trim()];
        await api.createRuntimeProfile({profile_id: selectedProfile, adapter_id: adapter, config: parameters, enabled: true, inherit_ambient: false});
        // Keep a successfully created profile selectable if endpoint creation fails.
        setProfiles(current => [...current, {profile_id: selectedProfile, adapter_id: adapter, enabled: true}]);
        setProfile(selectedProfile);
      }
      await api.createRuntimeEndpoint({endpoint_id: endpoint, agent_id: agentId, adapter_id: adapter,
        project_root: root, profile_id: attach ? null : selectedProfile, enabled: true,
        public_config: attach ? {target_pid: Number(pid)} : {}});
      await onCreated();
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  };
  return <div className="rounded-lg border border-surface-300 dark:border-surface-600 p-3 space-y-3" data-testid="endpoint-setup">
    <h4 className="font-semibold">Configure an endpoint for {agentId}</h4>
    <p>This saves an approved connection. It does not start a runtime or enable automatic startup.</p>
    {error && <p role="alert" className="text-red-500">{error}</p>}
    <label className="block">Connection method <select aria-label="Endpoint connection method" className={fieldClass} value={adapter} disabled={busy} onChange={e => {setAdapter(e.target.value); setProfile(""); setBinary(""); setConfiguration("{}"); setApproved(false);}}>
      {native.map(m => <option key={m.method} value={m.method}>{m.method}{m.platform_compatible === false ? " (unsupported on this server)" : ""}</option>)}
    </select></label>
    <label className="block">Endpoint name <input aria-label="Endpoint name" className={fieldClass} maxLength={100} value={endpoint} disabled={busy} onChange={e => setEndpoint(e.target.value)} placeholder="worker-codex" /></label>
    <label className="block">Project directory on the Nexus server <input aria-label="Endpoint project directory" className={`${fieldClass} w-full`} value={root} disabled={busy} onChange={e => setRoot(e.target.value)} placeholder="Absolute project path" /></label>
    {attach ? <label className="block">Approved Claude session PID <input aria-label="Attach process ID" className={fieldClass} type="number" min={1} value={pid} disabled={busy} onChange={e => setPid(e.target.value)} /></label> : <>
      <label className="block">Runtime profile <select aria-label="Runtime profile" className={fieldClass} value={profile} disabled={busy} onChange={e => setProfile(e.target.value)}>
        <option value="">Create an isolated profile</option>
        {profiles.filter(p => p.adapter_id === adapter && p.enabled).map(p => <option key={p.profile_id} value={p.profile_id}>{p.profile_id}</option>)}
      </select></label>
      {!profile && <>
        <label className="block">Executable (optional) <input aria-label="Runtime executable" className={`${fieldClass} w-full`} value={binary} disabled={busy} onChange={e => setBinary(e.target.value)} placeholder="Use the installed connector executable" /></label>
        <p>New profiles use isolated tool homes and do not inherit the operator environment. Configure the intended provider/model or tool home explicitly when required.</p>
        <details><summary>Advanced runtime configuration</summary>
          <label className="block">Configuration JSON <textarea aria-label="Runtime configuration JSON" className={`${fieldClass} w-full font-mono`} rows={5} value={configuration} disabled={busy} onChange={e => setConfiguration(e.target.value)} /></label>
          <p>Use supported profile options (for example Pi provider/model or an approved env mapping). Do not put tokens here. Existing sandbox and approval defaults remain in effect.</p>
        </details>
      </>}
    </>}
    <label className="flex gap-2"><input type="checkbox" checked={approved} disabled={busy} onChange={e => setApproved(e.target.checked)} /> I approve this endpoint and the selected runtime configuration for this agent.</label>
    {selected?.platform_compatible === false && <p>This connection method is not supported on the Nexus server platform.</p>}
    <div className="flex gap-2"><button className="btn btn-primary" disabled={busy || !approved || !endpoint.trim() || !root.trim() || !adapter || selected?.platform_compatible === false || attach && (!Number.isInteger(Number(pid)) || Number(pid) <= 0)} onClick={() => void create()}>Create approved endpoint</button>
      <button className="btn btn-secondary" disabled={busy} onClick={onCancel}>Cancel setup</button></div>
  </div>;
}
