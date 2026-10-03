import { useState } from "react";
import { api, ApiError } from "../api";
import type { BindingView } from "../runtimeApi";

export function LocalExecutionPermission({agentId, binding, onUpdated}: {
  agentId: string; binding: BindingView; onUpdated: () => void;
}) {
  const [minutes, setMinutes] = useState(60);
  const [budget, setBudget] = useState(20);
  const [noExpiry, setNoExpiry] = useState(false);
  const [unlimitedActions, setUnlimitedActions] = useState(false);
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  return <section aria-label="Local execution permission" className="space-y-2 rounded border p-3">
    <h5 className="font-semibold">Authorize local execution</h5>
    <p>Allow this agent to open, send, steer, interrupt and close runtimes for this connection and workspace, using its existing API key.</p>
    <fieldset disabled={busy || uncertain} className="space-y-2">
      <label className="block"><input type="checkbox" checked={noExpiry} onChange={event => {setNoExpiry(event.target.checked); setApproved(false);}} /> No expiration</label>
      <label className="block">Valid for (minutes) <input disabled={noExpiry} aria-label="Permission duration" type="number" min={1} max={1440}
        className="rounded border p-1 dark:bg-surface-800" value={minutes} onChange={event => {setMinutes(Number(event.target.value)); setApproved(false);}} /></label>
      <label className="block"><input type="checkbox" checked={unlimitedActions} onChange={event => {setUnlimitedActions(event.target.checked); setApproved(false);}} /> Unlimited actions</label>
      <label className="block">Action budget <input disabled={unlimitedActions} aria-label="Permission action budget" type="number" min={1} max={1000}
        className="rounded border p-1 dark:bg-surface-800" value={budget} onChange={event => {setBudget(Number(event.target.value)); setApproved(false);}} /></label>
      <p>{noExpiry ? "Valid until revoked." : `Valid for ${minutes} minutes.`} {unlimitedActions ? "No action limit." : `Up to ${budget} actions.`} Agent, connection and workspace restrictions still apply.</p>
      <label className="block"><input type="checkbox" checked={approved} onChange={event => setApproved(event.target.checked)} /> I authorize execution with these settings.</label>
    </fieldset>
    <button className="btn btn-primary" disabled={busy || uncertain || !approved || (!noExpiry && (!Number.isInteger(minutes) || minutes < 1 || minutes > 1440)) || (!unlimitedActions && (!Number.isInteger(budget) || budget < 1 || budget > 1000))}
      onClick={async () => {
        setBusy(true); setError(""); setSaved(false);
        try {
          await api.authorizeRuntimeExecution({actor_agent_id: agentId, endpoint_id: binding.endpoint_id,
            actions: ["open", "send", "steer", "interrupt", "close"], max_executions: unlimitedActions ? null : budget,
            expires_at: noExpiry ? null : new Date(Date.now() + minutes * 60000).toISOString()});
          setSaved(true); setApproved(false);
          onUpdated();
        } catch (failure) {
          setError(String(failure));
          if (!(failure instanceof ApiError && failure.status >= 400 && failure.status < 500)) setUncertain(true);
          onUpdated();
        } finally {setBusy(false);}
      }}>Authorize local execution</button>
    {uncertain && <p role="status">The result was not confirmed. Reload the connection status before issuing another permission.</p>}
    {saved && <p role="status">Execution permission issued.</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
