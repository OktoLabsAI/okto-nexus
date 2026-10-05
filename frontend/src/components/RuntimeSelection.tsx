import { ConnectionWorkflow, connectionSteps } from "./ConnectionWorkflow";
import { ConfigurationHelp } from './ConfigurationHelp';
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

export function RuntimeSelection({agentId, contextWorkspaceId = "", configureLocal = false, localAdapterId, configurationSaved = true, beforeConfigure, onInventoryUpdated, onBackHost, onFinish}: {
  agentId: string; contextWorkspaceId?: string; configureLocal?: boolean; localAdapterId?: string; configurationSaved?: boolean; beforeConfigure?: () => Promise<void>;
  onInventoryUpdated?: () => void; onBackHost?: () => void; onFinish?: () => void;
}) {
  const [testState, setTestState] = useState("Not tested");
  const [step, setStep] = useState(1);
  const [visited, setVisited] = useState(1);
  const [settingsSummary, setSettingsSummary] = useState("");
  const [conversationSummary, setConversationSummary] = useState("");
  const [toolsSummary, setToolsSummary] = useState("");
  const [settingsPending, setSettingsPending] = useState(false);
  const [conversationPending, setConversationPending] = useState(false);
  const [toolsPending, setToolsPending] = useState(false);
  const preferencesPending = settingsPending || conversationPending || toolsPending;
  const go = (value: number) => {setStep(value); setVisited(previous => Math.max(previous, value));};
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
          if (previous.executorId !== next.executor_id || !exists) {
            setNotice("The inventory changed or became unavailable. Review the current options and select the installation again.");
            return null;
          }
          if (previous.inventoryRevision !== next.inventory_revision) {
            setNotice("Installations refreshed. The selected installation was retained; review any updated setup details.");
            return {...previous, inventoryRevision: next.inventory_revision};
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

  // Configuration refreshes are explicit so background scans cannot reset drafts.
  // Re-read on focus and periodically. This only reads the published inventory;
  // it does not claim to trigger a provider scan or renew execution authority.
  useEffect(() => {
    if (configureLocal) return;
    const refresh = () => setRevision(value => value + 1);
    window.addEventListener("focus", refresh);
    const timer = window.setInterval(refresh, 30000);
    return () => { window.removeEventListener("focus", refresh); window.clearInterval(timer); };
  }, [configureLocal]);

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
  const approved = selected?.binding?.state === 'APPROVED' && !selected.preparation && !reconfigure;
  const ready = !!selected?.can_start && configurationSaved;
  const needsInstallationCheck = selected?.technical_state === 'NOT_PROBED' || !!selected?.technical_reasons.includes('selection_required');
  const canNext = !busy && !error && (step === 1 ? !!selected && options?.freshness === 'FRESH' && selected.technical_state === 'READY_FOR_RUNTIME' :
    step === 2 ? !!selected?.preparation || approved : step === 3 ? approved : step === 4 ? approved && !preferencesPending : step === 5 ? ready : false);
  const hint = step === 1 ? 'Select an installation and complete its version check.' : step === 2 ? 'Save the folders and login before continuing.' :
    step === 3 ? 'Review and approve this connection before continuing.' : step === 4 ? 'Save your preference changes before continuing.' :
    step === 5 ? 'Authorize execution, then refresh readiness if needed.' : '';
  const summaries = ['Local · ' + (options?.catalog.runtimes.find(row => row.adapter_id === localAdapterId)?.display_name || localAdapterId || ''),
    selected?.label || 'Select an installation', workspaces.find(row => row.workspace_id === workspaceId)?.display_name || (workspaceId || 'Choose folders'),
    approved ? 'Approved' : selected?.preparation ? 'Ready for review' : 'Not approved',
    preferencesPending ? 'Unsaved changes' : [settingsSummary, conversationSummary, toolsSummary].filter(Boolean).join(' · ') || 'Optional',
    ready ? 'Ready to run' : 'Authorization required', testState];
  return <section className="space-y-4 mt-3" aria-label="Runtime selection" data-testid="runtime-selection">
    {configureLocal && <><ConnectionWorkflow step={step} summaries={summaries} available={Math.min(visited, step + (canNext ? 1 : 0))} locked={step === 4 && preferencesPending}
      onStep={value => {if (preferencesPending && step === 4) return; if (value === 0) onBackHost?.(); else if (value <= step) go(value); else if (canNext) go(Math.min(value, step + 1));}} />
      <h4 className="font-semibold">Step {step + 1} of {connectionSteps.length} · {connectionSteps[step]}</h4></>}
    <div hidden={configureLocal && step !== 1} className="space-y-3">
    {!configureLocal && <h4 className="font-semibold">Message execution</h4>}
    <p className="text-xs text-surface-500">{configureLocal ? "Select a workspace and installation." : "Choose an authorized host for this message."}
      <ConfigurationHelp label="Connection">Workspace mappings authorize directories on the execution host. They do not set a default workspace for the agent.</ConfigurationHelp></p>
    {!configureLocal && <label className="block">Execution host <select className={fieldClass} aria-label="Execution host" value={executorId} disabled={busy} onChange={event => {
      setSelection(null); setNotice(""); setExecutorId(event.target.value);
    }}><option value="">Select a host</option>{hosts.map(host => <option key={host.executor_id} value={host.executor_id}>
      {host.kind === "embedded" ? "This Nexus Server · Local" : `${host.label || host.executor_id} · Remote`} · {host.control_state}
    </option>)}</select></label>}
    {configureLocal ? <label className="block">Workspace <span className="text-surface-500 text-xs">Required</span><ConfigurationHelp label="Workspace">Choose an existing workspace or register a new one during local setup.</ConfigurationHelp><select className={fieldClass} aria-label="Runtime workspace" value={workspaceId} disabled={busy}
      onChange={event => {setMappingWorkspaceId(event.target.value); setSelection(null); setVisited(1);}}>
      <option value="">Register a workspace mapping</option>
      {workspaces.map(project => <option key={project.workspace_id} value={project.workspace_id}>{project.display_name || project.workspace_id}</option>)}
    </select></label> : <p>Message workspace: {workspaces.find(project => project.workspace_id === workspaceId)?.display_name || workspaceId}</p>}
    {!configureLocal && local && <p>Configure local installations and workspace mappings in Agents → Connections.</p>}
    <details open={options?.freshness !== 'FRESH' || undefined}><summary className="cursor-pointer text-xs text-surface-500">Refresh installations</summary><div className="space-y-2 mt-2">
    <button className="btn btn-secondary" disabled={busy} onClick={() => setRevision(value => value + 1)}>Reload published inventory</button>
    {executorId && local && configureLocal && <InventoryRefresh key={JSON.stringify([agentId, executorId])} executorId={executorId}
      onUpdated={() => { setRevision(value => value + 1); onInventoryUpdated?.(); }} />}
    </div></details>
    {busy && <p role="status">Loading current choices…</p>}
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {options && <>
      {!configureLocal && <p>Inventory: {options.freshness}</p>}
      {options.freshness !== "FRESH" && <p role="status">Published inventory is not current. Select a recorded connection to inspect its history or recover an existing request. Preparation, binding and runtime start remain unavailable.</p>}
      <fieldset disabled={busy} className="space-y-2">
        <legend>{local ? "Local installation" : "Connector connections"}</legend>
        {local && <ConfigurationHelp label="Local installation">Each option is a separate installation. Prefer the configured connection for this workspace. Availability does not grant execution permission.</ConfigurationHelp>}
        {local && !workspaceId && choices.length > 1 && <p className="text-sm">Select a workspace to identify its configured connection.</p>}

        {!local && <p>The Connector selects the remote runtime integration. Select a configured connection for this message's workspace.</p>}
        {!choices.length && <p>{local ? "No installation is available for the selected local integration." : "No Connector connection is configured for this agent and workspace."}</p>}
        {choices.map(item => {
          const installation = options.availability.availability?.find(row => row.adapter_id === item.adapter_id && row.candidate_ref === item.candidate_ref);
          const source = ({path:'System PATH',trusted_root:'Configured directory',explicit:'Explicit selection',pi_release:'Managed Pi installation',pi_releases:'Managed Pi installation'} as Record<string,string>)[installation?.source || ''] || installation?.source || 'Not reported';
          const status = ({READY_FOR_RUNTIME:'Available for setup',NOT_PROBED:'Version check required',PREPARATION_REQUIRED:'Setup required',UNQUALIFIED_BUILD:'Installation not qualified for runtime',NOT_INSTALLED:'Not installed',UNSUPPORTED_PLATFORM:'Unsupported platform',CONTAINMENT_UNAVAILABLE:'Execution unavailable in this environment'} as Record<string,string>)[item.technical_state] || 'Installation unavailable';
          return <label key={JSON.stringify([item.adapter_id, item.candidate_ref])} data-testid={`runtime-candidate-${item.candidate_ref}`} className="block rounded border border-surface-200 dark:border-surface-700 p-3 space-y-1">
          <input type="radio" name={`runtime-installation-${agentId}`} disabled={!item.candidate_ref || (configureLocal && !localInstallationAvailable(item))}
            checked={!!selection && selection.adapterId === item.adapter_id && selection.candidateRef === item.candidate_ref}
            onChange={() => { if (item.candidate_ref) { setNotice(""); setVisited(1); setSelection({executorId, adapterId: item.adapter_id, candidateRef: item.candidate_ref, inventoryRevision: options.inventory_revision}); } }} />
          {" "}<span className="font-medium">{local ? (installation?.display_name || options.catalog.runtimes.find(row => row.adapter_id === item.adapter_id)?.display_name || item.label) : item.label}</span>
          {local && <>
            <span className="ml-2 text-sm">{installation?.version ? `Version ${installation.version}` : 'Version not checked'}</span>
            {recommended === item && <span className="chip ml-2">Recommended{item.binding ? ' · configured connection' : ' · only ready installation'}</span>}
            {item.binding && <p className="text-sm">{item.binding.state === 'APPROVED' ? 'Configured for this agent and workspace.' : 'Existing connection — review required.'}</p>}
            <p className="text-sm">{status}</p>
            <p className="text-xs text-surface-500">Source: {source}{installation?.architecture ? ` · ${installation.architecture}` : ''} · Installation: {item.label}</p>
            {!localInstallationAvailable(item) && <p className="text-sm">Unavailable. Choose another installation or update this one.</p>}
          </>}
          <details className="mt-1 text-surface-500"><summary>Technical details</summary>
            <span className="block">{item.technical_state} · {[...item.technical_reasons, ...item.policy_reasons].join(" · ")}</span>
          </details>
        </label>})}
      </fieldset>
    </>}
    </div>
    {selected && <fieldset disabled={busy} data-testid="runtime-selection-summary" className="space-y-4">
      <div hidden={configureLocal && step !== 1}>
      {!configureLocal && <p>Selected: {selected.label}. Start: {selected.can_start ? "available" : "unavailable"}.</p>}
      {configureLocal && local &&
        selected.can_configure && needsInstallationCheck && selected.candidate_ref &&
        <LocalInstallationCheck key={JSON.stringify(["installation-check", agentId, executorId, selected.candidate_ref, options!.inventory_revision])}
          agentId={agentId} executorId={executorId} adapterId={selected.adapter_id}
          candidateRef={selected.candidate_ref} inventoryRevision={options!.inventory_revision}
          beforeCheck={beforeConfigure}
          onChecked={() => { setNotice("Version checked. Review the refreshed installation before preparing its workspace.");
            setRevision(value => value + 1); onInventoryUpdated?.(); }} />}
      </div>
      <div hidden={configureLocal && step !== 2} className="space-y-3">
      {configureLocal && approved && <p role="status">Folders and login are already configured for this connection. Continue or edit the environment below.</p>}
      {configureLocal && local && selected.can_configure && selected.binding?.state === 'APPROVED' && !selected.preparation && !reconfigure &&
        <button className="btn btn-secondary" onClick={() => setReconfigure(true)}>Reconfigure local environment</button>}
      {configureLocal && local &&
        selected.can_configure && !selected.preparation && (!selected.binding || selected.binding.state === "STALE" || reconfigure) &&
        !selected.policy_reasons.includes("REALIZATION_SELECTION_REQUIRED") &&
        <EmbeddedPreparation key={JSON.stringify(["preparation", agentId, executorId, workspaceId, selection?.candidateRef, selection?.inventoryRevision, selected.binding?.binding_revision])}
          agentId={agentId} executorId={executorId} hostLabel={hosts.find(host => host.executor_id === executorId)?.label || executorId}
          workspaceId={workspaceId} workspaceLabel={workspaces.find(project => project.workspace_id === workspaceId)?.display_name || ""}
          inventoryRevision={options!.inventory_revision} choice={selected}
          beforePrepare={beforeConfigure}
          onPrepared={id => { setReconfigure(false); setMappingWorkspaceId(id); setRevision(value => value + 1); go(3); }} />}
      {configureLocal && selected.preparation && <p role="status">Folders saved. Continue to review the connection.</p>}
      </div>
      <div hidden={configureLocal && step !== 3}>
      {configureLocal && local && configurationSaved && <BindingConsent key={JSON.stringify(["binding-consent", agentId, executorId, workspaceId, selection?.candidateRef, selection?.inventoryRevision, selected.preparation?.realization_ref])}
        agentId={agentId} executorId={executorId} hostLabel={hosts.find(host => host.executor_id === executorId)?.label || executorId}
        workspaceId={workspaceId} workspaceLabel={workspaces.find(project => project.workspace_id === workspaceId)?.display_name || workspaceId}
        inventoryRevision={options!.inventory_revision} choice={selected} onApplied={() => {setRevision(value => value + 1); go(4);}} />}
      </div>
      {!configureLocal && selected.binding && <RuntimeOperations key={JSON.stringify(["operations", agentId, selected.binding.binding_id, selected.binding.workspace_binding_id])}
        agentId={agentId} binding={selected.binding} canStart={selected.can_start} />}
      {configureLocal && selected.binding && <div hidden={step !== 4} className="space-y-4">
        <p className="text-xs text-surface-500">Save any changes before authorizing execution.</p>
      {configureLocal && selected.harness_configuration && <HarnessConfigurationDiscovery value={selected.harness_configuration} />}
      {configureLocal && selected.binding && selected.harness_configuration && <RuntimeHarnessSettings
        key={`settings:${selected.binding.binding_id}`} endpoint={selected.binding.endpoint_id} schema={selected.harness_configuration} onPendingChange={setSettingsPending} onSummaryChange={setSettingsSummary}
        onUpdated={() => setRevision(value => value + 1)} />}
      {configureLocal && local && configurationSaved && selected.binding?.state === "APPROVED" &&
        <RuntimeConversationPolicy key={"messages:" + selected.binding.binding_id} binding={selected.binding} onPendingChange={setConversationPending} onSummaryChange={setConversationSummary} onUpdated={() => setRevision(value => value + 1)} />}
      {configureLocal && local && selected.binding &&
        <RuntimeToolPermission key={"tools:" + selected.binding.binding_id} endpoint={selected.binding.endpoint_id} onPendingChange={setToolsPending} onSummaryChange={setToolsSummary} onUpdated={() => setRevision(value => value + 1)} />}
      </div>}
      {configureLocal && local && configurationSaved && selected.binding?.state === "APPROVED" &&
        <div hidden={step !== 5} className="space-y-3">
        {selected.technical_state !== 'READY_FOR_RUNTIME' && <p role="alert">The installation is not ready. Return to Installation to confirm the selected installation and check its version.</p>}
        {ready && <p role="status">Execution is authorized for this connection. Continue to test it, or replace the limits below.</p>}<LocalExecutionPermission key={"permission:" + selected.binding.binding_id} agentId={agentId} binding={selected.binding}
          onUpdated={() => setRevision(value => value + 1)} /></div>}
      {configureLocal && step === 5 && local && (!configurationSaved || selected.binding?.state !== 'APPROVED') &&
        <div className="rounded-xl border border-surface-200 dark:border-surface-700 px-4 py-3 text-surface-500">
          <h5 className="font-semibold">3. Execution authorization <span className="text-xs font-normal">Required to run</span></h5>
          <p className="text-xs mt-1">Complete connection setup and save the execution policy to unlock authorization.</p>
        </div>}
      {configureLocal && step === 6 && selected.binding && <div className="space-y-3">
        <h5 className="font-semibold">Configuration saved</h5>
        <dl className="grid grid-cols-2 gap-2 rounded-lg border p-3">{summaries.slice(0, 6).map((value, index) => <div key={index}><dt className="text-surface-500">{connectionSteps[index]}</dt><dd>{value}</dd></div>)}</dl>
        <RuntimeOperations key={`test:${selected.binding.binding_id}:${selected.binding.binding_revision}`} agentId={agentId}
          binding={selected.binding} canStart={ready} connectionTest onTestStateChange={setTestState} testConfigurationKey={JSON.stringify([settingsSummary, conversationSummary, toolsSummary, selected.binding.inventory_revision])} />
      </div>}
      {!configureLocal && selected.binding && <RuntimeSessions key={JSON.stringify(["sessions", agentId, executorId, selected.binding.binding_id])}
        agentId={agentId} binding={selected.binding} />}
    </fieldset>}
    {configureLocal && <footer className="sticky bottom-0 bg-white dark:bg-surface-800 border-t pt-3 pb-2 flex flex-wrap items-center gap-3">
      <button className="btn btn-secondary" disabled={busy || (step === 4 && preferencesPending)} onClick={() => step === 1 ? onBackHost?.() : go(step - 1)}>← Back</button>
      {step === 6 && testState === "Verified · test session closed" && <button className="btn btn-primary" onClick={onFinish}>Finish setup</button>}
      {step < 6 && <button className="btn btn-primary" disabled={!canNext} onClick={() => go(step + 1)}>Next →</button>}
      <button className="btn btn-secondary" disabled={busy} onClick={() => setRevision(value => value + 1)}>Refresh readiness</button>
      {step < 6 && !canNext && <p role="status" className="text-xs text-surface-500">{hint}</p>}
      {error && <p role="alert">{error}</p>}
      {!selected && step !== 1 && <button className="btn btn-secondary" onClick={() => go(1)}>Select an installation</button>}
    </footer>}
  </section>;
}
