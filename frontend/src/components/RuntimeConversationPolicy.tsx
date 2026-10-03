import { useEffect, useState } from "react";
import { api } from "../api";
import type { BindingView } from "../runtimeApi";

export function RuntimeConversationPolicy({binding, onUpdated}: {binding: BindingView; onUpdated: () => void}) {
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
  return <section aria-label="Message execution policy" className="space-y-2 rounded border p-3">
    <h5 className="font-semibold">Automatic message replies</h5>
    <p>Run this harness when a message arrives for this agent in this workspace, including from Meta-harness. Execution still requires a current permission and available budget.</p>
    <label className="block"><input type="checkbox" checked={enabled} disabled={busy || !policy}
      onChange={event => {setEnabled(event.target.checked); setNotice("");}} /> Reply automatically to messages in this workspace</label>
    <p>Changing this policy invalidates existing execution permissions. Authorize execution again after saving.</p>
    <p>Conversation isolation follows the agent runtime policy, which can inherit the global defaults. Files and tools still share the workspace.</p>
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
