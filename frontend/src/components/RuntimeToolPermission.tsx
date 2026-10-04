import { ConfigurationHelp } from './ConfigurationHelp';
import { useEffect, useState } from "react";
import { api } from "../api";

export function RuntimeToolPermission({endpoint, onUpdated, onPendingChange, onSummaryChange}: {endpoint: string; onUpdated: () => void; onSummaryChange?: (summary: string) => void; onPendingChange?: (pending: boolean) => void}) {
  const [policy, setPolicy] = useState<{revision: number; mode: "ask" | "always_allow"} | null>(null);
  const [mode, setMode] = useState<"ask" | "always_allow">("ask");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setPolicy(null); setError("");
    api.runtimeToolPermission(endpoint).then(result => {
      if (active) {setPolicy(result); setMode(result.mode);}
    }).catch(failure => {if (active) setError(String(failure));});
    return () => {active = false;};
  }, [endpoint, revision]);
  useEffect(() => {onPendingChange?.(busy || !policy || mode !== policy.mode);}, [busy, policy, mode, onPendingChange]);
  useEffect(() => {onSummaryChange?.(policy ? policy.mode === "always_allow" ? "Nexus tools: always allow" : "Nexus tools: ask" : "Loading permissions");}, [policy, onSummaryChange]);
  return <section aria-label="Nexus tool permissions" className="space-y-2 border-t pt-3">
    <h5 className="font-semibold">Nexus tool access</h5>
    <label className="block">Tool approval <span className="text-xs text-surface-500">Optional</span><ConfigurationHelp label="Nexus tool approval">Always allow skips harness approval for Nexus calls. Agent permissions and Nexus policies still apply. Pi native tools do not request harness approval. Close sessions before saving, then authorize execution again.</ConfigurationHelp>
      <select className="block rounded border p-2 bg-white dark:bg-surface-800" value={mode} disabled={busy || !policy}
        onChange={event => {setMode(event.target.value as typeof mode); setNotice("");}}>
        <option value="ask">Ask for approval</option>
        <option value="always_allow">Always allow</option>
      </select>
    </label>


    <button className="btn btn-secondary" disabled={busy || !policy || mode === policy.mode} onClick={async () => {
      if (!policy) return;
      setBusy(true); setError(""); setNotice("");
      try {
        const result = await api.saveRuntimeToolPermission(endpoint, {expected_revision: policy.revision, mode});
        setPolicy(result); setNotice("Tool access saved. Authorize execution before starting a new session."); onUpdated();
      } catch (failure) {setError(String(failure));}
      finally {setBusy(false);}
    }}>Save tool access</button>
    <button className="btn btn-secondary" disabled={busy} onClick={() => setRevision(value => value + 1)}>Reload</button>
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
