import { useEffect, useRef, useState } from "react";
import { ApiError } from "../api";
import { bindingRequestExists, discardExpiredBindingReview, durableBindingRequest, runtimeApi, type BindingProposal, type BindingView, type RuntimeChoice } from "../runtimeApi";

export function BindingConsent({agentId, executorId, hostLabel, workspaceId, workspaceLabel,
  inventoryRevision, choice, onApplied}: {
  agentId: string; executorId: string; hostLabel: string; workspaceId: string;
  workspaceLabel: string; inventoryRevision: string; choice: RuntimeChoice; onApplied: () => void;
}) {
  const mounted = useRef(true);
  const [alias, setAlias] = useState("");
  const [proposal, setProposal] = useState<BindingProposal | null>(null);
  const [binding, setBinding] = useState<BindingView | null>(choice.binding);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    mounted.current = true;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => { mounted.current = false; window.clearInterval(timer); };
  }, []);
  useEffect(() => { setBinding(choice.binding); }, [choice.binding]);
  const run = async (operation: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await operation(); }
    catch (failure) { if (mounted.current) setError(String(failure)); }
    finally { if (mounted.current) setBusy(false); }
  };
  const expired = proposal !== null && Date.parse(proposal.expires_at) <= now;
  const reviewKey = JSON.stringify(["prepare", agentId, executorId, inventoryRevision, choice.preparation?.realization_ref, workspaceId, alias.trim()]);
  const matches = (value: BindingView | BindingProposal) => value.agent_id === agentId &&
    value.executor_id === executorId && value.workspace_id === workspaceId &&
    value.adapter_id === choice.adapter_id && value.candidate_ref === choice.candidate_ref &&
    value.inventory_revision === inventoryRevision;

  if (binding) return <section aria-label="Connection status" className="space-y-2">
    <p>Connection: {binding.state}. Agent {agentId} · {hostLabel} · {workspaceLabel} · {choice.label}.</p>
    <p>{binding.state === "APPROVED" ? "This binding can be reused without issuing another connection key." : "This connection requires operator review before reuse."} Runtime start still requires current technical readiness and separate execution authority.</p>
    <button className="btn btn-secondary" disabled={busy} onClick={() => void run(async () => {
      const current = await runtimeApi.binding(binding.binding_id);
      if (mounted.current) { setBinding(current); onApplied(); }
    })}>Check connection</button>
    {error && <p role="alert">{error}</p>}
  </section>;

  if (!workspaceId) return <p>Select a workspace to review connection consent.</p>;
  if (!choice.preparation || !choice.can_bind) return <p>The execution host must publish a local preparation before connection review. For remote hosts, configure and realize the workspace through the Connector CLI. Review any selection or operator restrictions shown above.</p>;

  return <section aria-label="Connection consent" className="space-y-2">
    <p>Review access for {agentId} on {hostLabel}, workspace {workspaceLabel}, using {choice.label}.</p>
    {!proposal && <>
      <label className="block">Connection name <input aria-label="Connection name" className="rounded border p-1 dark:bg-surface-800"
        maxLength={120} value={alias} disabled={busy} onChange={event => setAlias(event.target.value)} /></label>
      <button className="btn btn-secondary" disabled={busy || !alias.trim() || /[\\/:]/.test(alias)} onClick={() => void run(async () => {
        const payload = {agent_id_hint: agentId, executor_id: executorId, adapter_id: choice.adapter_id,
          candidate_ref: choice.candidate_ref, inventory_revision: inventoryRevision,
          realization_ref: choice.preparation!.realization_ref, workspace_id: workspaceId, alias: alias.trim()};
        const result = await runtimeApi.prepareBinding(durableBindingRequest(reviewKey, payload));
        if (!matches(result) || result.realization_ref !== payload.realization_ref) throw new Error("The returned proposal does not match this selection.");
        if (mounted.current) {
          setProposal(result);
          setUncertain(bindingRequestExists(JSON.stringify(["apply", result.proposal_id])));
        }
      })}>Review connection</button>
    </>}
    {proposal && <>
      <p>Approve this connection for the selected agent, host, installation and workspace. Provider paths and credentials remain on the execution host. This does not authorize task execution or start a runtime.</p>
      <p>Changes: {proposal.diff.fields_changed.join(", ")}. Expires: {new Date(proposal.expires_at).toLocaleString()}.</p>
      <details><summary>Full approval scope</summary><p>{proposal.diff.summary}</p></details>
      {expired && <><p role="alert">This review expired. Check any uncertain approval before requesting a new review.</p>
        {!uncertain && <button className="btn btn-secondary" disabled={busy} onClick={() => { discardExpiredBindingReview(reviewKey); setProposal(null); }}>Request a new review</button>}</>}
      {!proposal.can_apply && <p role="alert">This proposal requires additional review before it can be applied.</p>}
      <button className="btn btn-primary" disabled={busy || expired || !proposal.can_apply} onClick={() => void run(async () => {
        const payload = {proposal_id: proposal.proposal_id, proposal_revision: proposal.proposal_revision,
          approved_diff_hash: proposal.diff.approved_diff_hash};
        const request = durableBindingRequest(JSON.stringify(["apply", proposal.proposal_id]), payload);
        setUncertain(true);
        let result: BindingView;
        try { result = await runtimeApi.applyBinding(request); }
        catch (failure) {
          if (mounted.current && failure instanceof ApiError && failure.status >= 400 && failure.status < 500) setUncertain(false);
          throw failure;
        }
        if (!matches(result)) throw new Error("The returned binding does not match this selection.");
        if (mounted.current) { setUncertain(false); setBinding(result); onApplied(); }
      })}>{uncertain ? "Retry the same approval request" : "Approve connection"}</button>
      {uncertain && <p role="status">The approval result is not confirmed. Keep the same request identity; check the binding before starting anything.</p>}
      {uncertain && <button className="btn btn-secondary" disabled={busy} onClick={() => void run(async () => {
        const current = await runtimeApi.binding(proposal.binding_id);
        if (!matches(current)) throw new Error("The current binding no longer matches this selection.");
        if (mounted.current) { setUncertain(false); setBinding(current); onApplied(); }
      })}>Check approval result</button>}
    </>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
