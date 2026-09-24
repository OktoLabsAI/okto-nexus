import { useEffect, useRef, useState } from "react";
import { api, type AgentConnections } from "../api";
import { AgentEndpointSetup } from "./AgentEndpointSetup";

const fieldClass = "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs text-surface-700 dark:text-surface-200 focus:outline-none focus:ring-2 focus:ring-accent-500/40 disabled:opacity-50";

const labels: Record<string, string> = {mcp: "MCP", pi: "Pi · RPC", codex: "Codex · app-server", "claude_code.stream": "Claude Code · stream-json", "claude_code.attach": "Claude Code · attach (cc-socks)"};

export function AgentConnectionsPanel({agentId, onClose}: {agentId: string; onClose: () => void}) {
  const visibility = useRef(0);
  const [data, setData] = useState<AgentConnections | null>(null);
  const [methods, setMethods] = useState<Record<string, boolean>>({});
  const [mode, setMode] = useState("inherit");
  const [seconds, setSeconds] = useState(86400);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [snippet, setSnippet] = useState("");
  const [notice, setNotice] = useState("");
  const [setup, setSetup] = useState(false);
  const [format, setFormat] = useState("powershell");
  const [dirty, setDirty] = useState(false);
  const apply = (value: AgentConnections) => {
    setData(value); setMethods(Object.fromEntries(value.methods.map(m => [m.method, m.enabled])));
    setMode(value.key_ttl_seconds === null ? "inherit" : value.key_ttl_seconds === 0 ? "unlimited" : "custom");
    setSeconds(value.key_ttl_seconds || 86400); setDirty(false);
  };
  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setError(""); setNotice("");
    try { await fn(); } catch (e) { setError(String(e)); } finally { setBusy(false); }
  };
  useEffect(() => {
    visibility.current++;
    void run(async () => apply(await api.agentConnections(agentId)));
    return () => { visibility.current++; };
  }, [agentId]);
  const command = (() => {
    if (!snippet || format === "json") return snippet;
    const request = JSON.parse(snippet) as {url: string; headers: Record<string, string>; body: object};
    const quote = (value: string) => "'" + value.replace(/'/g, format === "powershell" ? "''" : "'\"'\"'") + "'";
    if (format === "powershell") return `Invoke-RestMethod -Method Post -Uri ${quote(request.url)} -Headers @{ Authorization = ${quote(request.headers.Authorization)} } -ContentType 'application/json' -Body ${quote(JSON.stringify(request.body))}`;
    return `curl --fail-with-body --request POST --url ${quote(request.url)} --header ${quote("Authorization: " + request.headers.Authorization)} --header 'Content-Type: application/json' --data-raw ${quote(JSON.stringify(request.body))}`;
  })();
  return <div className="rounded-lg border border-surface-200 dark:border-surface-700 p-3 text-xs"
    data-testid={`agent-connections-${agentId}`}>
    <div className="flex justify-between items-center"><h3 className="font-medium">Connection methods · {agentId}</h3><button className="btn btn-secondary" onClick={onClose}>Close</button></div>
    {error && <p role="alert" className="text-red-500 mt-2">{error}</p>}
    {data && <div className="space-y-3 mt-3">
      <p>Enable the connection methods this agent may use. Native methods also require an approved endpoint and runtime profile.</p>
      <div className="flex flex-wrap gap-4">{data.methods.map(m => <label key={m.method}>
        <input type="checkbox" checked={methods[m.method]} disabled={busy} onChange={e => {setMethods({...methods, [m.method]: e.target.checked}); setDirty(true); setSnippet("");}} /> {labels[m.method] || m.method}
      </label>)}</div>
      <label className="block">Connection key expiration <select aria-label="Connection key expiration" className={`${fieldClass} ml-2`} value={mode} disabled={busy} onChange={e => {setMode(e.target.value); setDirty(true);}}>
        <option value="inherit">Inherit global setting</option><option value="custom">Custom duration</option><option value="unlimited">No expiration</option>
      </select></label>
      {mode === "custom" && <label>Seconds <input aria-label="Connection key lifetime seconds" className={`${fieldClass} ml-2`} type="number" min={1} max={315360000} value={seconds} onChange={e => {setSeconds(Number(e.target.value)); setDirty(true);}} /></label>}
      <p>Current effective lifetime: {data.effective_key_ttl_seconds === 0 ? "unlimited" : `${data.effective_key_ttl_seconds} seconds`}. The global default is in Settings. Changes apply to newly issued keys.</p>
      <button className="btn btn-primary" disabled={busy || !dirty || mode === "custom" && (!Number.isInteger(seconds) || seconds < 1 || seconds > 315360000)} onClick={() => void run(async () => {
        apply(await api.saveAgentConnections(agentId, {expected_revision: data.revision, methods, key_ttl_seconds: mode === "inherit" ? null : mode === "unlimited" ? 0 : seconds})); setNotice("Connection policy saved.");
      })}>Save connection policy</button>
      <h4 className="font-semibold">Endpoints and connection commands</h4>
      <button className="btn btn-secondary" disabled={busy || dirty} onClick={() => setSetup(true)}>Configure endpoint</button>
      {dirty && <p>Save the connection policy before configuring an endpoint.</p>}
      {setup && <AgentEndpointSetup agentId={agentId} methods={data.methods} onCancel={() => setSetup(false)} onCreated={async () => {apply(await api.agentConnections(agentId)); setSetup(false); setNotice("Endpoint configured. Generate a command below, or authorize MCP opening for this agent.");}} />}
      <p>For a harness without MCP, generate a command and paste it into its terminal or give it to the harness to execute. Pi RPC, Codex app-server and Claude stream open a managed runtime; they do not adopt the caller’s existing conversation. Attach uses the approved external target. Managed runtimes run on the Nexus server; this command does not bridge a harness running on another machine.</p>
      {!data.endpoints.length && <p>No endpoints configured. Use Configure endpoint above to select the connector, project directory and runtime profile.</p>}
      <p>MCP clients use their own Nexus agent API key. Authorize MCP opening below grants discovery and opening for 1 hour, without task execution permission.</p>
      {!data.has_agent_key && <p>Generate an API key on this agent’s card before authorizing MCP opening. The copied command for a harness without MCP uses its own scoped connection key.</p>}
      {data.endpoints.map(ep => <div key={ep.endpoint_id} data-testid={`connection-endpoint-${ep.endpoint_id}`} className="flex flex-wrap items-center gap-2">
        <code>{ep.endpoint_id}</code><span>{labels[ep.adapter_id] || ep.adapter_id}</span>
        <button title={ep.can_issue ? "Issue a scoped connection key" : "Enable the integration and approve this endpoint first"} className="btn btn-secondary" disabled={busy || dirty || !methods[ep.adapter_id] || !ep.can_issue || !ep.enabled || ep.activation_state !== "approved"} onClick={() => void run(async () => {
          const generation = visibility.current;
          const issued = await api.issueConnectionKey(agentId, ep.endpoint_id);
          if (visibility.current !== generation) return;
          setSnippet(JSON.stringify({method: issued.request.method, url: window.location.origin + issued.request.path, headers: {...issued.request.headers, "Content-Type": "application/json"}, body: issued.request.body}, null, 2));
          apply(await api.agentConnections(agentId)); setNotice(`Key issued. Expiration: ${issued.expires_at || "none"}.`);
        })}>Generate connection command</button>
        <button className="btn btn-secondary" disabled={busy || dirty || !ep.can_issue || !data.has_agent_key} onClick={() => void run(async () => {await api.authorizeConnectionOpening(agentId, ep.endpoint_id); setNotice("MCP discovery and opening authorized for 1 hour. The agent must use its own Nexus API key.");})}>Authorize MCP opening (1 hour)</button>
      </div>)}
      {snippet && <div className="space-y-2">
        <p>This request contains a credential shown only now. Keep it private; closing this panel clears it.</p>
        <label className="block">Command format <select aria-label="Connection command format" className={fieldClass} value={format} onChange={e => setFormat(e.target.value)}><option value="powershell">PowerShell</option><option value="bash">Bash / cURL</option><option value="json">Request JSON</option></select></label>
        <textarea aria-label="Connection request" className={`${fieldClass} w-full font-mono`} rows={10} readOnly value={command} />
        <button className="btn btn-secondary" onClick={() => void run(async () => { await navigator.clipboard.writeText(command); setNotice("Connection command copied."); })}>Copy connection command</button>
      </div>}
      {data.keys.map(key => <div key={key.key_id} className="flex flex-wrap gap-2 items-center"><code>{key.key_id}</code><span>{key.endpoint_id} · {key.revoked_at ? "revoked" : key.expires_at || "no expiration"}</span>
        {!key.revoked_at && <button className="btn btn-secondary" disabled={busy} onClick={() => void run(async () => {await api.revokeConnectionKey(agentId, key.key_id); setSnippet(""); apply(await api.agentConnections(agentId));})}>Revoke</button>}
      </div>)}
    </div>}
    {notice && <p role="status" className="mt-2">{notice}</p>}
  </div>;
}
