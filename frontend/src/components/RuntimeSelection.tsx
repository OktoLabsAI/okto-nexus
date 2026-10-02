import { useEffect, useState } from "react";
import { api, type WorkspaceListItem } from "../api";
import { runtimeApi, type ExecutorChoice, type RuntimeOptions } from "../runtimeApi";
import { BindingConsent } from "./BindingConsent";
import { InventoryRefresh } from "./InventoryRefresh";
import { EmbeddedPreparation } from "./EmbeddedPreparation";
import { LocalInstallationCheck } from "./LocalInstallationCheck";
import { RuntimeOperations } from "./RuntimeOperations";
import { RuntimeSessions } from "./RuntimeSessions";

const fieldClass = "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs";
type Selection = {executorId: string; adapterId: string; candidateRef: string; inventoryRevision: string};

export function RuntimeSelection({agentId}: {agentId: string}) {
  const [hosts, setHosts] = useState<ExecutorChoice[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceListItem[]>([]);
  const [executorId, setExecutorId] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [options, setOptions] = useState<RuntimeOptions | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setBusy(true); setError("");
    void (async () => {
      try {
        const [directory, projects] = await Promise.all([
          runtimeApi.executors(agentId, controller.signal), api.workspaces(),
        ]);
        if (controller.signal.aborted) return;
        setHosts(directory); setWorkspaces(projects.workspaces);
        if (executorId && !directory.some(host => host.executor_id === executorId)) {
          setExecutorId(""); setSelection(null); setNotice("The selected host is no longer available. Select a host again.");
          return;
        }
        if (workspaceId && !projects.workspaces.some(project => project.workspace_id === workspaceId)) {
          setWorkspaceId(""); setSelection(null); setNotice("The selected workspace is no longer available. Select a workspace again.");
          return;
        }
        if (!executorId) { setOptions(null); return; }
        const next = await runtimeApi.options(agentId, executorId, workspaceId, controller.signal);
        if (controller.signal.aborted) return;
        setOptions(next);
        setSelection(previous => {
          if (!previous) return null;
          const exists = next.options.some(item => item.adapter_id === previous.adapterId && item.candidate_ref === previous.candidateRef);
          if (previous.executorId !== next.executor_id || previous.inventoryRevision !== next.inventory_revision || !exists || next.freshness !== "FRESH") {
            setNotice("The inventory changed or became unavailable. Review the current options and select the installation again.");
            return null;
          }
          return previous;
        });
      } catch (failure) {
        if (!controller.signal.aborted) { setError(String(failure)); setSelection(null); }
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    })();
    return () => controller.abort();
  }, [agentId, executorId, workspaceId, revision]);

  // Re-read on focus and periodically. This only reads the published inventory;
  // it does not claim to trigger a provider scan or renew execution authority.
  useEffect(() => {
    const refresh = () => setRevision(value => value + 1);
    window.addEventListener("focus", refresh);
    const timer = window.setInterval(refresh, 30000);
    return () => { window.removeEventListener("focus", refresh); window.clearInterval(timer); };
  }, []);

  const selected = options?.options.find(item => item.adapter_id === selection?.adapterId && item.candidate_ref === selection?.candidateRef);
  return <section className="space-y-3 mt-3" aria-label="Runtime selection" data-testid="runtime-selection">
    <h4 className="font-semibold">Execution host and installation</h4>
    <p>Choose where this agent runs. Installation discovery and workspace selection do not approve or start a runtime.</p>
    <label className="block">Execution host <select className={fieldClass} aria-label="Execution host" value={executorId} disabled={busy} onChange={event => {
      setSelection(null); setNotice(""); setExecutorId(event.target.value);
    }}><option value="">Select a host</option>{hosts.map(host => <option key={host.executor_id} value={host.executor_id}>
      {host.label || host.executor_id} · {host.kind} · {host.control_state}
    </option>)}</select></label>
    <label className="block">Workspace <select className={fieldClass} aria-label="Runtime workspace" value={workspaceId} disabled={busy || !executorId} onChange={event => {
      setSelection(null); setNotice(""); setWorkspaceId(event.target.value);
    }}><option value="">Select a workspace</option>{workspaces.map(project => <option key={project.workspace_id} value={project.workspace_id}>
      {project.display_name || project.workspace_id}
    </option>)}</select></label>
    <button className="btn btn-secondary" disabled={busy} onClick={() => setRevision(value => value + 1)}>Reload published inventory</button>
    {executorId && <InventoryRefresh key={JSON.stringify([agentId, executorId])} executorId={executorId}
      onUpdated={() => { setSelection(null); setRevision(value => value + 1); }} />}
    {busy && <p role="status">Loading current choices…</p>}
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {options && <>
      <p>Inventory: {options.freshness}</p>
      <fieldset disabled={busy || options.freshness !== "FRESH"} className="space-y-2">
        <legend>Provider installation</legend>
        {options.options.map(item => <label key={JSON.stringify([item.adapter_id, item.candidate_ref])} data-testid={`runtime-candidate-${item.candidate_ref}`} className="block rounded border border-surface-200 dark:border-surface-700 p-2">
          <input type="radio" name={`runtime-installation-${agentId}`} disabled={!item.candidate_ref}
            checked={!!selection && selection.adapterId === item.adapter_id && selection.candidateRef === item.candidate_ref}
            onChange={() => { if (item.candidate_ref) { setNotice(""); setSelection({executorId, adapterId: item.adapter_id, candidateRef: item.candidate_ref, inventoryRevision: options.inventory_revision}); } }} />
          {" "}{item.label} · {item.technical_state}
          <span className="block">{[...item.technical_reasons, ...item.policy_reasons].join(" · ")}</span>
        </label>)}
      </fieldset>
    </>}
    {selected && <fieldset disabled={busy} data-testid="runtime-selection-summary">
      <p>Selected: {selected.label}. Preparation: {selected.can_prepare ? "available" : "unavailable"}; binding approval: {selected.can_bind ? "available" : "unavailable"}; start: {selected.can_start ? "available" : "unavailable"}.</p>
      {hosts.find(host => host.executor_id === executorId)?.kind === "embedded" &&
        selected.can_prepare && selected.technical_state === "NOT_PROBED" && selected.candidate_ref &&
        <LocalInstallationCheck key={JSON.stringify([agentId, executorId, selected.candidate_ref, options!.inventory_revision])}
          agentId={agentId} executorId={executorId} adapterId={selected.adapter_id}
          candidateRef={selected.candidate_ref} inventoryRevision={options!.inventory_revision}
          onChecked={() => { setNotice("Version checked. Review the refreshed installation before preparing its workspace.");
            setSelection(null); setRevision(value => value + 1); }} />}
      {hosts.find(host => host.executor_id === executorId)?.kind === "embedded" &&
        selected.can_prepare && !selected.preparation && !selected.binding &&
        !selected.policy_reasons.includes("REALIZATION_SELECTION_REQUIRED") &&
        <EmbeddedPreparation key={JSON.stringify([agentId, executorId, workspaceId, selection?.candidateRef, selection?.inventoryRevision])}
          agentId={agentId} executorId={executorId} hostLabel={hosts.find(host => host.executor_id === executorId)?.label || executorId}
          workspaceId={workspaceId} workspaceLabel={workspaces.find(project => project.workspace_id === workspaceId)?.display_name || ""}
          inventoryRevision={options!.inventory_revision} choice={selected}
          onPrepared={id => { setWorkspaceId(id); setRevision(value => value + 1); }} />}
      <BindingConsent key={JSON.stringify([agentId, executorId, workspaceId, selection?.candidateRef, selection?.inventoryRevision, selected.preparation?.realization_ref])}
        agentId={agentId} executorId={executorId} hostLabel={hosts.find(host => host.executor_id === executorId)?.label || executorId}
        workspaceId={workspaceId} workspaceLabel={workspaces.find(project => project.workspace_id === workspaceId)?.display_name || workspaceId}
        inventoryRevision={options!.inventory_revision} choice={selected} onApplied={() => setRevision(value => value + 1)} />
      {selected.binding && <RuntimeOperations key={JSON.stringify([agentId, selected.binding.binding_id])}
        agentId={agentId} binding={selected.binding} canStart={selected.can_start} />}
      {selected.binding && <RuntimeSessions key={JSON.stringify([agentId, executorId, selected.binding.binding_id])}
        agentId={agentId} binding={selected.binding} />}
    </fieldset>}
  </section>;
}
