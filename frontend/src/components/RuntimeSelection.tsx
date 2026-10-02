import { useEffect, useState } from "react";
import { api, type AgentExecutionPolicy, type WorkspaceListItem } from "../api";
import { runtimeApi, type ExecutorChoice, type RuntimeOptions } from "../runtimeApi";
import { BindingConsent } from "./BindingConsent";
import { InventoryRefresh } from "./InventoryRefresh";
import { EmbeddedPreparation } from "./EmbeddedPreparation";
import { LocalInstallationCheck } from "./LocalInstallationCheck";
import { RuntimeOperations } from "./RuntimeOperations";
import { RuntimeSessions } from "./RuntimeSessions";
import { LocalExecutionPermission } from "./LocalExecutionPermission";

const fieldClass = "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs";
type Selection = {executorId: string; adapterId: string; candidateRef: string; inventoryRevision: string};

export function RuntimeSelection({agentId, contextWorkspaceId = "", configureLocal = false}: {
  agentId: string; contextWorkspaceId?: string; configureLocal?: boolean;
}) {
  const [hosts, setHosts] = useState<ExecutorChoice[]>([]);
  const [policy, setPolicy] = useState<AgentExecutionPolicy | null>(null);
  const [workspaces, setWorkspaces] = useState<WorkspaceListItem[]>([]);
  const [executorId, setExecutorId] = useState("");
  const [mappingWorkspaceId, setMappingWorkspaceId] = useState("");
  const workspaceId = configureLocal ? mappingWorkspaceId : contextWorkspaceId;
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
        const [directory, projects, currentPolicy] = await Promise.all([
          runtimeApi.executors(agentId, controller.signal), api.workspaces(), api.agentExecutionPolicy(agentId),
        ]);
        if (controller.signal.aborted) return;
        const visibleHosts = configureLocal ? directory.filter(host => host.kind === "embedded") : directory;
        setHosts(visibleHosts); setWorkspaces(projects.workspaces); setPolicy(currentPolicy);
        if (executorId && !directory.some(host => host.executor_id === executorId)) {
          setExecutorId(""); setSelection(null); setNotice("The selected host is no longer available. Select a host again.");
          return;
        }
        if (workspaceId && !projects.workspaces.some(project => project.workspace_id === workspaceId)) {
          setSelection(null); setNotice("The message workspace is no longer available.");
          return;
        }
        if (!executorId) { setOptions(null); return; }
        const next = await runtimeApi.options(agentId, executorId, workspaceId, controller.signal);
        if (controller.signal.aborted) return;
        setOptions(next);
        setSelection(previous => {
          if (!previous) return null;
          const exists = next.options.some(item => item.adapter_id === previous.adapterId && item.candidate_ref === previous.candidateRef);
          if (previous.executorId !== next.executor_id || previous.inventoryRevision !== next.inventory_revision || !exists) {
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
  }, [agentId, executorId, workspaceId, revision, configureLocal]);

  // Re-read on focus and periodically. This only reads the published inventory;
  // it does not claim to trigger a provider scan or renew execution authority.
  useEffect(() => {
    const refresh = () => setRevision(value => value + 1);
    window.addEventListener("focus", refresh);
    const timer = window.setInterval(refresh, 30000);
    return () => { window.removeEventListener("focus", refresh); window.clearInterval(timer); };
  }, []);

  const candidate = options?.options.find(item => item.adapter_id === selection?.adapterId && item.candidate_ref === selection?.candidateRef);
  const local = hosts.find(host => host.executor_id === executorId)?.kind === "embedded";
  const choices = options?.options.filter(item => configureLocal
    ? item.adapter_id === policy?.local_adapter_id : !!item.binding) || [];
  const selected = candidate && options?.freshness !== "FRESH"
    ? {...candidate, can_prepare: false, can_bind: false, can_start: false} : candidate;
  return <section className="space-y-3 mt-3" aria-label="Runtime selection" data-testid="runtime-selection">
    <h4 className="font-semibold">{configureLocal ? "Local harness configuration" : "Message execution"}</h4>
    <p>{configureLocal ? "Select a local installation and configure its environment here. Workspace mappings authorize folders for work; they do not set a default workspace for this agent." : "Workspace comes from this message. Choose an authorized host for this work."}</p>
    <label className="block">Execution host <select className={fieldClass} aria-label="Execution host" value={executorId} disabled={busy} onChange={event => {
      setSelection(null); setNotice(""); setExecutorId(event.target.value);
    }}><option value="">Select a host</option>{hosts.map(host => <option key={host.executor_id} value={host.executor_id}>
      {host.kind === "embedded" ? "This Nexus Server · Local" : `${host.label || host.executor_id} · Remote`} · {host.control_state}
    </option>)}</select></label>
    {configureLocal ? <label className="block">Workspace mapping <select className={fieldClass} aria-label="Runtime workspace" value={workspaceId} disabled={busy}
      onChange={event => {setMappingWorkspaceId(event.target.value); setSelection(null);}}>
      <option value="">Register a workspace mapping</option>
      {workspaces.map(project => <option key={project.workspace_id} value={project.workspace_id}>{project.display_name || project.workspace_id}</option>)}
    </select></label> : <p>Message workspace: {workspaces.find(project => project.workspace_id === workspaceId)?.display_name || workspaceId}</p>}
    {!configureLocal && local && <p>Configure local installations and workspace mappings in Agents → Connections.</p>}
    <button className="btn btn-secondary" disabled={busy} onClick={() => setRevision(value => value + 1)}>Reload published inventory</button>
    {executorId && local && configureLocal && <InventoryRefresh key={JSON.stringify([agentId, executorId])} executorId={executorId}
      onUpdated={() => { setSelection(null); setRevision(value => value + 1); }} />}
    {busy && <p role="status">Loading current choices…</p>}
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {options && <>
      <p>Inventory: {options.freshness}</p>
      {options.freshness !== "FRESH" && <p role="status">Published inventory is not current. Select a recorded connection to inspect its history or recover an existing request. Preparation, binding and runtime start remain unavailable.</p>}
      <fieldset disabled={busy} className="space-y-2">
        <legend>{local ? "Local installation" : "Connector connections"}</legend>
        {!local && <p>The Connector selects the remote runtime integration. Select a configured connection for this message's workspace.</p>}
        {!choices.length && <p>{local ? "No installation is available for the selected local integration." : "No Connector connection is configured for this agent and workspace."}</p>}
        {choices.map(item => <label key={JSON.stringify([item.adapter_id, item.candidate_ref])} data-testid={`runtime-candidate-${item.candidate_ref}`} className="block rounded border border-surface-200 dark:border-surface-700 p-2">
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
      {configureLocal && local &&
        selected.can_prepare && selected.technical_state === "NOT_PROBED" && selected.candidate_ref &&
        <LocalInstallationCheck key={JSON.stringify([agentId, executorId, selected.candidate_ref, options!.inventory_revision])}
          agentId={agentId} executorId={executorId} adapterId={selected.adapter_id}
          candidateRef={selected.candidate_ref} inventoryRevision={options!.inventory_revision}
          onChecked={() => { setNotice("Version checked. Review the refreshed installation before preparing its workspace.");
            setSelection(null); setRevision(value => value + 1); }} />}
      {configureLocal && local &&
        selected.can_prepare && !selected.preparation && !selected.binding &&
        !selected.policy_reasons.includes("REALIZATION_SELECTION_REQUIRED") &&
        <EmbeddedPreparation key={JSON.stringify([agentId, executorId, workspaceId, selection?.candidateRef, selection?.inventoryRevision])}
          agentId={agentId} executorId={executorId} hostLabel={hosts.find(host => host.executor_id === executorId)?.label || executorId}
          workspaceId={workspaceId} workspaceLabel={workspaces.find(project => project.workspace_id === workspaceId)?.display_name || ""}
          inventoryRevision={options!.inventory_revision} choice={selected}
          onPrepared={id => { setMappingWorkspaceId(id); setRevision(value => value + 1); }} />}
      {configureLocal && local && <BindingConsent key={JSON.stringify([agentId, executorId, workspaceId, selection?.candidateRef, selection?.inventoryRevision, selected.preparation?.realization_ref])}
        agentId={agentId} executorId={executorId} hostLabel={hosts.find(host => host.executor_id === executorId)?.label || executorId}
        workspaceId={workspaceId} workspaceLabel={workspaces.find(project => project.workspace_id === workspaceId)?.display_name || workspaceId}
        inventoryRevision={options!.inventory_revision} choice={selected} onApplied={() => setRevision(value => value + 1)} />}
      {!configureLocal && selected.binding && <RuntimeOperations key={JSON.stringify([agentId, selected.binding.binding_id])}
        agentId={agentId} binding={selected.binding} canStart={selected.can_start} />}
      {configureLocal && local && selected.binding?.state === "APPROVED" && selected.policy_reasons.includes("AUTHORIZATION_REQUIRED") &&
        <LocalExecutionPermission key={selected.binding.binding_id} agentId={agentId} binding={selected.binding}
          onUpdated={() => setRevision(value => value + 1)} />}
      {!configureLocal && selected.binding && <RuntimeSessions key={JSON.stringify([agentId, executorId, selected.binding.binding_id])}
        agentId={agentId} binding={selected.binding} />}
    </fieldset>}
  </section>;
}
