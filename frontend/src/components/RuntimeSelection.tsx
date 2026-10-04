import { useEffect, useState } from "react";
import { api, type AgentExecutionPolicy, type WorkspaceListItem } from "../api";
import { runtimeApi, localInstallationAvailable, type ExecutorChoice, type RuntimeOptions } from "../runtimeApi";
import { BindingConsent } from "./BindingConsent";
import { InventoryRefresh } from "./InventoryRefresh";
import { EmbeddedPreparation } from "./EmbeddedPreparation";
import { LocalInstallationCheck } from "./LocalInstallationCheck";
import { RuntimeOperations } from "./RuntimeOperations";
import { RuntimeSessions } from "./RuntimeSessions";
import { LocalExecutionPermission } from "./LocalExecutionPermission";
import { RuntimeConversationPolicy } from "./RuntimeConversationPolicy";
import { RuntimeToolPermission } from "./RuntimeToolPermission";
import { HarnessConfigurationDiscovery } from "./HarnessConfigurationDiscovery";
import { RuntimeHarnessSettings } from "./RuntimeHarnessSettings";

const fieldClass = "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs";
type Selection = {executorId: string; adapterId: string; candidateRef: string; inventoryRevision: string};

export function RuntimeSelection({agentId, contextWorkspaceId = "", configureLocal = false, localAdapterId, configurationSaved = true, beforeConfigure, onInventoryUpdated}: {
  agentId: string; contextWorkspaceId?: string; configureLocal?: boolean; localAdapterId?: string; configurationSaved?: boolean; beforeConfigure?: () => Promise<void>;
  onInventoryUpdated?: () => void;
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
  const [reconfigure, setReconfigure] = useState(false);
  useEffect(() => {setReconfigure(false);}, [agentId, executorId, workspaceId, selection?.candidateRef]);

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
        if (configureLocal && !executorId && visibleHosts.length === 1) {
          setExecutorId(visibleHosts[0].executor_id); return;
        }
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
          if (!previous) {
            const candidates = next.options.filter(item => item.adapter_id === (localAdapterId || currentPolicy.local_adapter_id) && item.candidate_ref);
            return configureLocal && candidates.length === 1 ? {executorId, adapterId: candidates[0].adapter_id,
              candidateRef: candidates[0].candidate_ref!, inventoryRevision: next.inventory_revision} : null;
          }
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
  }, [agentId, executorId, workspaceId, revision, configureLocal, localAdapterId]);

  // Re-read on focus and periodically. This only reads the published inventory;
  // it does not claim to trigger a provider scan or renew execution authority.
  useEffect(() => {
    const refresh = () => setRevision(value => value + 1);
    window.addEventListener("focus", refresh);
    const timer = window.setInterval(refresh, 30000);
    return () => { window.removeEventListener("focus", refresh); window.clearInterval(timer); };
  }, []);

  const candidate = options?.options.find(item => item.adapter_id === selection?.adapterId && item.candidate_ref === selection?.candidateRef
    && (!configureLocal || item.adapter_id === (localAdapterId || policy?.local_adapter_id)));
  const local = hosts.find(host => host.executor_id === executorId)?.kind === "embedded";
  const choices = options?.options.filter(item => configureLocal
    ? item.adapter_id === (localAdapterId || policy?.local_adapter_id) : !!item.binding) || [];
  const selected = candidate && (options?.freshness !== "FRESH" || (configureLocal && !localInstallationAvailable(candidate)))
    ? {...candidate, can_prepare: false, can_configure: false, can_bind: false, can_start: false} : candidate;
  const usableChoices = choices.filter(item => localInstallationAvailable(item));
  const configuredChoices = usableChoices.filter(item => item.binding?.state === 'APPROVED');
  const recommended = options?.freshness === 'FRESH'
    ? (configuredChoices.length === 1 ? configuredChoices[0] :
      choices.every(item => !item.binding) && usableChoices.length === 1 && usableChoices[0].technical_state === 'READY_FOR_RUNTIME' ? usableChoices[0] : null)
    : null;
  return <section className="space-y-3 mt-3" aria-label="Runtime selection" data-testid="runtime-selection">
    <h4 className="font-semibold">{configureLocal ? "Local harness configuration" : "Message execution"}</h4>
    <p>{configureLocal ? "Select a local installation and configure its environment here. Workspace mappings authorize folders for work; they do not set a default workspace for this agent." : "Workspace comes from this message. Choose an authorized host for this work."}</p>
    {!configureLocal && <label className="block">Execution host <select className={fieldClass} aria-label="Execution host" value={executorId} disabled={busy} onChange={event => {
      setSelection(null); setNotice(""); setExecutorId(event.target.value);
    }}><option value="">Select a host</option>{hosts.map(host => <option key={host.executor_id} value={host.executor_id}>
      {host.kind === "embedded" ? "This Nexus Server · Local" : `${host.label || host.executor_id} · Remote`} · {host.control_state}
    </option>)}</select></label>}
    {configureLocal ? <label className="block">Workspace mapping <select className={fieldClass} aria-label="Runtime workspace" value={workspaceId} disabled={busy}
      onChange={event => {setMappingWorkspaceId(event.target.value); setSelection(null);}}>
      <option value="">Register a workspace mapping</option>
      {workspaces.map(project => <option key={project.workspace_id} value={project.workspace_id}>{project.display_name || project.workspace_id}</option>)}
    </select></label> : <p>Message workspace: {workspaces.find(project => project.workspace_id === workspaceId)?.display_name || workspaceId}</p>}
    {!configureLocal && local && <p>Configure local installations and workspace mappings in Agents → Connections.</p>}
    <button className="btn btn-secondary" disabled={busy} onClick={() => setRevision(value => value + 1)}>Reload published inventory</button>
    {executorId && local && configureLocal && <InventoryRefresh key={JSON.stringify([agentId, executorId])} executorId={executorId}
      onUpdated={() => { setSelection(null); setRevision(value => value + 1); onInventoryUpdated?.(); }} />}
    {busy && <p role="status">Loading current choices…</p>}
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {options && <>
      {!configureLocal && <p>Inventory: {options.freshness}</p>}
      {options.freshness !== "FRESH" && <p role="status">Published inventory is not current. Select a recorded connection to inspect its history or recover an existing request. Preparation, binding and runtime start remain unavailable.</p>}
      <fieldset disabled={busy} className="space-y-2">
        <legend>{local ? "Local installation" : "Connector connections"}</legend>
        {local && <p className="text-sm text-surface-600 dark:text-surface-300">Cada opção representa uma instalação encontrada neste computador. Prefira a conexão já configurada para este agente e workspace. Uma instalação disponível ainda precisa de autorização para executar.</p>}
        {local && !workspaceId && choices.length > 1 && <p className="text-sm">Selecione o workspace acima para identificar a conexão já configurada.</p>}
        {local && choices.length > 1 && !recommended && <p className="text-sm">Compare a versão e a origem. Não há uma recomendação única para esta seleção.</p>}
        {!local && <p>The Connector selects the remote runtime integration. Select a configured connection for this message's workspace.</p>}
        {!choices.length && <p>{local ? "No installation is available for the selected local integration." : "No Connector connection is configured for this agent and workspace."}</p>}
        {choices.map(item => {
          const installation = options.availability.availability?.find(row => row.adapter_id === item.adapter_id && row.candidate_ref === item.candidate_ref);
          const source = ({path:'PATH do sistema',trusted_root:'Diretório configurado',explicit:'Selecionada explicitamente',pi_release:'Instalação gerenciada do Pi',pi_releases:'Instalação gerenciada do Pi'} as Record<string,string>)[installation?.source || ''] || installation?.source || 'Não informada';
          const status = ({READY_FOR_RUNTIME:'Disponível para configuração',NOT_PROBED:'Verificação de versão necessária',PREPARATION_REQUIRED:'Preparação necessária',UNQUALIFIED_BUILD:'Instalação não homologada para runtime',NOT_INSTALLED:'Não instalado',UNSUPPORTED_PLATFORM:'Sistema não suportado',CONTAINMENT_UNAVAILABLE:'Execução indisponível neste ambiente'} as Record<string,string>)[item.technical_state] || 'Instalação indisponível';
          return <label key={JSON.stringify([item.adapter_id, item.candidate_ref])} data-testid={`runtime-candidate-${item.candidate_ref}`} className="block rounded border border-surface-200 dark:border-surface-700 p-3 space-y-1">
          <input type="radio" name={`runtime-installation-${agentId}`} disabled={!item.candidate_ref || (configureLocal && !localInstallationAvailable(item))}
            checked={!!selection && selection.adapterId === item.adapter_id && selection.candidateRef === item.candidate_ref}
            onChange={() => { if (item.candidate_ref) { setNotice(""); setSelection({executorId, adapterId: item.adapter_id, candidateRef: item.candidate_ref, inventoryRevision: options.inventory_revision}); } }} />
          {" "}<span className="font-medium">{local ? (installation?.display_name || options.catalog.runtimes.find(row => row.adapter_id === item.adapter_id)?.display_name || item.label) : item.label}</span>
          {local && <>
            <span className="ml-2 text-sm">{installation?.version ? `Versão ${installation.version}` : 'Versão ainda não verificada'}</span>
            {recommended === item && <span className="chip ml-2">Recomendada{item.binding ? ' · conexão configurada' : ' · única instalação pronta'}</span>}
            {item.binding && <p className="text-sm">{item.binding.state === 'APPROVED' ? 'Conexão configurada para este agente e workspace.' : 'Conexão existente — precisa de revisão antes de executar.'}</p>}
            <p className="text-sm">{status}</p>
            <p className="text-xs text-surface-500">Origem: {source}{installation?.architecture ? ` · ${installation.architecture}` : ''} · Identificação: {item.label}</p>
            {!localInstallationAvailable(item) && <p className="text-sm">Esta instalação não pode ser selecionada. Use uma opção disponível ou atualize a instalação.</p>}
          </>}
          <details className="mt-1 text-surface-500"><summary>Technical details</summary>
            <span className="block">{item.technical_state} · {[...item.technical_reasons, ...item.policy_reasons].join(" · ")}</span>
          </details>
        </label>})}
      </fieldset>
    </>}
    {selected && <fieldset disabled={busy} data-testid="runtime-selection-summary">
      {configureLocal && selected.harness_configuration && <HarnessConfigurationDiscovery value={selected.harness_configuration} />}
      {configureLocal && selected.binding && selected.harness_configuration && <RuntimeHarnessSettings
        key={`settings:${selected.binding.binding_id}`} endpoint={selected.binding.endpoint_id} schema={selected.harness_configuration}
        onUpdated={() => setRevision(value => value + 1)} />}
      {!configureLocal && <p>Selected: {selected.label}. Start: {selected.can_start ? "available" : "unavailable"}.</p>}
      {configureLocal && local &&
        selected.can_configure && selected.technical_state === "NOT_PROBED" && selected.candidate_ref &&
        <LocalInstallationCheck key={JSON.stringify(["installation-check", agentId, executorId, selected.candidate_ref, options!.inventory_revision])}
          agentId={agentId} executorId={executorId} adapterId={selected.adapter_id}
          candidateRef={selected.candidate_ref} inventoryRevision={options!.inventory_revision}
          beforeCheck={beforeConfigure}
          onChecked={() => { setNotice("Version checked. Review the refreshed installation before preparing its workspace.");
            setSelection(null); setRevision(value => value + 1); onInventoryUpdated?.(); }} />}
      {configureLocal && local && selected.can_configure && selected.binding && !selected.preparation && !reconfigure &&
        <button className="btn btn-secondary" onClick={() => setReconfigure(true)}>Reconfigure local environment</button>}
      {configureLocal && local &&
        selected.can_configure && !selected.preparation && (!selected.binding || selected.binding.state === "STALE" || reconfigure) &&
        !selected.policy_reasons.includes("REALIZATION_SELECTION_REQUIRED") &&
        <EmbeddedPreparation key={JSON.stringify(["preparation", agentId, executorId, workspaceId, selection?.candidateRef, selection?.inventoryRevision, selected.binding?.binding_revision])}
          agentId={agentId} executorId={executorId} hostLabel={hosts.find(host => host.executor_id === executorId)?.label || executorId}
          workspaceId={workspaceId} workspaceLabel={workspaces.find(project => project.workspace_id === workspaceId)?.display_name || ""}
          inventoryRevision={options!.inventory_revision} choice={selected}
          beforePrepare={beforeConfigure}
          onPrepared={id => { setReconfigure(false); setMappingWorkspaceId(id); setRevision(value => value + 1); }} />}
      {configureLocal && local && configurationSaved && <BindingConsent key={JSON.stringify(["binding-consent", agentId, executorId, workspaceId, selection?.candidateRef, selection?.inventoryRevision, selected.preparation?.realization_ref])}
        agentId={agentId} executorId={executorId} hostLabel={hosts.find(host => host.executor_id === executorId)?.label || executorId}
        workspaceId={workspaceId} workspaceLabel={workspaces.find(project => project.workspace_id === workspaceId)?.display_name || workspaceId}
        inventoryRevision={options!.inventory_revision} choice={selected} onApplied={() => setRevision(value => value + 1)} />}
      {!configureLocal && selected.binding && <RuntimeOperations key={JSON.stringify(["operations", agentId, selected.binding.binding_id, selected.binding.workspace_binding_id])}
        agentId={agentId} binding={selected.binding} canStart={selected.can_start} />}
      {configureLocal && local && configurationSaved && selected.binding?.state === "APPROVED" &&
        <RuntimeConversationPolicy key={"messages:" + selected.binding.binding_id} binding={selected.binding} onUpdated={() => setRevision(value => value + 1)} />}
      {configureLocal && local && selected.binding &&
        <RuntimeToolPermission key={"tools:" + selected.binding.binding_id} endpoint={selected.binding.endpoint_id} onUpdated={() => setRevision(value => value + 1)} />}
      {configureLocal && local && configurationSaved && selected.binding?.state === "APPROVED" &&
        <LocalExecutionPermission key={"permission:" + selected.binding.binding_id} agentId={agentId} binding={selected.binding}
          onUpdated={() => setRevision(value => value + 1)} />}
      {!configureLocal && selected.binding && <RuntimeSessions key={JSON.stringify(["sessions", agentId, executorId, selected.binding.binding_id])}
        agentId={agentId} binding={selected.binding} />}
    </fieldset>}
  </section>;
}
