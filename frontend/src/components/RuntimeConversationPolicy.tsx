import { ConfigurationHelp } from './ConfigurationHelp';
import { useEffect, useState } from "react";
import { api } from "../api";
import type { BindingView } from "../runtimeApi";

export function RuntimeConversationPolicy({binding, onUpdated, onPendingChange, onSummaryChange}: {binding: BindingView; onUpdated: () => void; onSummaryChange?: (summary: string) => void; onPendingChange?: (pending: boolean) => void}) {
  const [policy, setPolicy] = useState<{revision: number; enabled: boolean; session_policy: "shared" | "per_sender"} | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    setPolicy(null); setBusy(true); setError("");
    api.runtimeConversationPolicy(binding.endpoint_id).then(value => {
      if (value.agent_id !== binding.agent_id || value.workspace_id !== binding.workspace_id) throw new Error("Connection scope changed.");
      if (active) { setPolicy(value); setEnabled(value.enabled); }
    }).catch(failure => {if (active) setError(String(failure));})
      .finally(() => {if (active) setBusy(false);});
    return () => {active = false;};
  }, [binding.endpoint_id, binding.agent_id, binding.workspace_id, refresh]);
  useEffect(() => {onPendingChange?.(busy || !policy || enabled !== policy.enabled);}, [busy, policy, enabled, onPendingChange]);
  useEffect(() => {onSummaryChange?.(policy ? policy.enabled ? "Automatic replies on" : "Automatic replies off" : "Loading replies");}, [policy, onSummaryChange]);
  return <section aria-label="Message execution policy" className="space-y-2 border-t pt-3">
    <h5 className="font-semibold">Automatic replies <ConfigurationHelp label="Automatic replies">Run the harness when this agent receives a message in this workspace. Requires execution permission and budget. Save changes before authorizing execution. Conversation isolation follows the agent policy; files and tools still share the workspace.</ConfigurationHelp></h5>
    <label className="block"><input type="checkbox" checked={enabled} disabled={busy || !policy}
      onChange={event => {setEnabled(event.target.checked); setNotice("");}} /> Reply automatically to messages in this workspace</label>
    <button className="btn btn-secondary" disabled={busy || !policy || enabled === policy.enabled} onClick={async () => {
      if (!policy) return;
      setBusy(true); setError(""); setNotice("");
      try {
        const result = await api.saveRuntimeConversationPolicy(binding.endpoint_id, {expected_revision: policy.revision, enabled});
        setPolicy(result); setEnabled(result.enabled); setNotice("Message policy saved. Review execution permission below.");
        onUpdated();
      } catch (failure) {
        setError(String(failure)); setPolicy(null);
      } finally {setBusy(false);}
    }}>Save message policy</button>
    <button className="btn btn-secondary" disabled={busy} onClick={() => setRefresh(value => value + 1)}>Reload message policy</button>
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
