import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Loader2 } from 'lucide-react';
import { api, type WorkspaceListItem, type SessionPolicy } from '../api';
import { runtimeApi, localInstallationAvailable, type RuntimeOptions } from '../runtimeApi';
import { emptyConnection, parseConnectionConfiguration, exportConnectionConfiguration, policyOnlySetup, sameConnectionConfiguration, type ConnectionConfiguration, type SetupBaseline, type SetupRequest, type SetupTest } from '../connectionConfiguration';
import { ConnectionWorkflow, connectionSteps } from './ConnectionWorkflow';
import { ConfigurationHelp } from './ConfigurationHelp';
import { HarnessPreferenceFields } from './HarnessPreferenceFields';
import { harnessSelectionError } from '../harnessConfiguration';
import { InventoryRefresh } from './InventoryRefresh';
import { RemoteConnectorCommand } from './RemoteConnectorCommand';
import { OneShotSettings, type OneShotSettingsHandle } from './OneShotSettings';
import { MCPPresetFields, parseMCPPreset } from './MCPPresetFields';

const input = 'block w-full rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 p-2';
export function AgentConnectionsPanel({agentId,onClose}: {agentId: string; onClose: () => void}) {
  const [draft,setDraft] = useState(emptyConnection);
  const [runtimeDefault,setRuntimeDefault] = useState(true);
  const [sessionDefault,setSessionDefault] = useState<SessionPolicy>('shared');
  const [capacityPending,setCapacityPending] = useState(false);
  const capacity = useRef<OneShotSettingsHandle>(null);
  const [savedConnection,setSavedConnection] = useState<{configuration: ConnectionConfiguration; bindingId: string; executor: string; workspace: string; candidate: string} | null>(null);
  const runtimeEnabled = draft.runtime_enabled ?? runtimeDefault;
  const [step,setStep] = useState(0);
  const [visited,setVisited] = useState(0);
  const [authorized,setAuthorized] = useState(false);
  const [busy,setBusy] = useState(true);
  const [error,setError] = useState('');
  const [notice,setNotice] = useState('');
  const [executor,setExecutor] = useState('');
  const [options,setOptions] = useState<RuntimeOptions | null>(null);
  const [workspaces,setWorkspaces] = useState<WorkspaceListItem[]>([]);
  const [workspace,setWorkspace] = useState('');
  const [workspacePaths,setWorkspacePaths] = useState<{path: string}[]>([]);
  const [workspacePathsLoading,setWorkspacePathsLoading] = useState(false);
  const [candidateRef,setCandidateRef] = useState('');
  const [baseline,setBaseline] = useState<SetupBaseline | null>(null);
  const [bindingId,setBindingId] = useState<string | null>(null);
  const [connections,setConnections] = useState<Awaited<ReturnType<typeof runtimeApi.setup>>['connections']>([]);
  const [test,setTest] = useState<SetupTest | null>(null);
  const [request,setRequest] = useState<SetupRequest | null>(null);
  const [details,setDetails] = useState(false);
  const [inheritedMcps,setInheritedMcps] = useState(false);
  const [mcpText,setMcpText] = useState('[]');
  const [savedMcp,setSavedMcp] = useState({revision:0, text:'[]'});
  const loadMcp = (preset?: {revision: number; servers: unknown[]}) => {
    const text = JSON.stringify(preset?.servers || [], null, 2);
    setMcpText(text); setSavedMcp({revision:preset?.revision || 0, text});
  };
  let mcpError = '';
  try {parseMCPPreset(mcpText);} catch (reason) {mcpError = String(reason);}
  const presetChanged = mcpText !== savedMcp.text;
  const [reload,setReload] = useState(0);
  const [installationBusy,setInstallationBusy] = useState(false);
  const [installationError,setInstallationError] = useState('');
  const installationAttempt = useRef('');
  const fileInput = useRef<HTMLInputElement>(null);
  const imported = useRef(false);
  const live = useRef(true);
  const testing = test?.status === 'running';
  const selected = options?.options.find(row => row.adapter_id === draft.adapter_id && row.candidate_ref === candidateRef);
  const patch = (values: Partial<ConnectionConfiguration>) => {
    setDraft(previous => ({...previous,...values})); setTest(null); setRequest(null); setAuthorized(false);setError('');
  };
  useEffect(() => {
    live.current = true;
    const controller = new AbortController();
    void Promise.all([api.agentExecutionPolicy(agentId),api.runtimePolicy(agentId),api.workspaces(),
      runtimeApi.executors(agentId,controller.signal),runtimeApi.setup(agentId,undefined,controller.signal)])
      .then(async ([policy,runtime,projects,hosts,initial]) => {
        const matches = initial.connections.filter(c => c.execution_location === policy.execution_location && c.adapter_id === policy.local_adapter_id);
        const saved = matches.length === 1 ? matches[0] : null;
        const setup = saved ? await runtimeApi.setup(agentId,saved.binding_id,controller.signal) : initial;
        if (controller.signal.aborted) return;
        setConnections(initial.connections);
        loadMcp(setup.mcp_preset);
        const loaded: ConnectionConfiguration = {...emptyConnection(),execution_location:policy.execution_location,adapter_id:policy.local_adapter_id || '',
          runtime_enabled:runtime.runtime_enabled,session_policy:runtime.session_policy,
          ...(setup.folders || {}),alias:setup.public_config?.alias || '',
          harness_settings:setup.public_config?.harness_settings || {},
          tool_access:setup.public_config?.nexus_tool_permission || 'ask',automatic_reply:true,
          authorization:setup.authorization || emptyConnection().authorization,
          workspace_label:projects.workspaces.find(w => w.workspace_id === saved?.workspace_id)?.display_name || ''};
        setDraft(loaded);
        setSavedConnection(saved ? {configuration:loaded,bindingId:saved.binding_id,executor:saved.executor_id,
          workspace:saved.workspace_id,candidate:saved.candidate_ref} : null);
        setRuntimeDefault(runtime.defaults?.runtime_enabled ?? true);
        setSessionDefault(runtime.defaults?.session_policy ?? 'shared');
        setInheritedMcps(runtime.effective?.inherit_global_mcps ?? false);
        setBaseline(setup.baseline); setWorkspaces(projects.workspaces);
        const local = hosts.filter(h => h.kind === 'embedded');
        if (saved) {setExecutor(saved.executor_id);setWorkspace(saved.workspace_id);setCandidateRef(saved.candidate_ref);setBindingId(saved.binding_id);}
        else if (local.length === 1) setExecutor(local[0].executor_id);
      }).catch(e => {if (!controller.signal.aborted) setError(String(e));})
      .finally(() => {if (!controller.signal.aborted) setBusy(false);});
    return () => {live.current=false;controller.abort();};
  },[agentId]);
  useEffect(() => {
    if (!executor) return;
    const controller = new AbortController(); setBusy(true);
    runtimeApi.options(agentId,executor,workspace,controller.signal).then(value => {
      if (!controller.signal.aborted) setOptions(value);
    }).catch(e => {if (!controller.signal.aborted) setError(String(e));})
      .finally(() => {if (!controller.signal.aborted) setBusy(false);});
    return () => controller.abort();
  },[agentId,executor,workspace,reload]);
  useEffect(() => {
    setWorkspacePaths([]);
    setWorkspacePathsLoading(false);
    if (!workspace || !executor || draft.execution_location !== 'local') return;
    const controller = new AbortController();
    setWorkspacePathsLoading(true);
    runtimeApi.workspacePaths(workspace, executor, controller.signal)
      .then(({items}) => {
        if (controller.signal.aborted) return;
        setWorkspacePaths(items);
        if (items.length === 1) {
          setDraft(current => current.workspace_root ? current : {...current, workspace_root: items[0].path});
        }
      })
      .catch(() => { /* The folder can still be entered manually. */ })
      .finally(() => { if (!controller.signal.aborted) setWorkspacePathsLoading(false); });
    return () => controller.abort();
  }, [workspace, executor, draft.execution_location]);
  useEffect(() => {
    if (!testing || !test) return;
    const controller = new AbortController();
    let reading = false;
    const timer = window.setInterval(async () => {
      if (reading) return; reading=true;
      try {const result = await runtimeApi.setupTest(test.test_id,controller.signal); if (!controller.signal.aborted) {setTest(result);setError('');}}
      catch(e) {if (!controller.signal.aborted) setError(`${String(e)} Checking the same test again…`);}
      finally {reading=false;}
    },1500);
    return () => {controller.abort();window.clearInterval(timer);};
  },[testing,test?.test_id]);
  const selectInstallation = async (ref: string) => {
    if (!options) return;
    setBusy(true);setError('');setTest(null);setRequest(null);setCandidateRef(ref);
    const choice = options.options.find(row => row.candidate_ref === ref && row.adapter_id === draft.adapter_id);
    const binding = choice?.binding?.binding_id || null;
    try {
      const setup = await runtimeApi.setup(agentId,binding || undefined);
      if (!live.current) return;
      setBaseline(setup.baseline);setBindingId(binding);
      loadMcp(setup.mcp_preset);
      if (!imported.current) setDraft(old => ({...old,...(setup.folders || {}),
        provider_home:setup.folders?.provider_home ?? choice?.provider_home_suggestion ?? null,
        alias:setup.public_config?.alias || old.alias || `${agentId}-${old.adapter_id}`,
        harness_settings:setup.public_config?.harness_settings || {},
        tool_access:setup.public_config?.nexus_tool_permission || 'ask',automatic_reply:true,
        authorization:setup.authorization || old.authorization,
        workspace_label:workspaces.find(w => w.workspace_id === workspace)?.display_name || old.workspace_label}));
    } catch(e) {setError(String(e));} finally {if (live.current) setBusy(false);}
  };
  const portableOnly = !runtimeEnabled || draft.execution_location === 'remote';
  const workflowSteps = !runtimeEnabled ? ['Runtime connection'] : draft.execution_location === 'remote' ? ['Host & Connector'] : connectionSteps;
  useEffect(() => {
    if (portableOnly) {setStep(0);setVisited(0);}
  }, [portableOnly]);
  useEffect(() => {
    if (step !== 1 || busy || !options || installationBusy) return;
    const choices = options.options.filter(row => row.adapter_id === draft.adapter_id && localInstallationAvailable(row));
    if (!selected) {
      if (choices.length === 1) void selectInstallation(choices[0].candidate_ref!);
      return;
    }
    const key = `${executor}:${workspace}:${draft.adapter_id}:${candidateRef}:${reload}`;
    if (installationAttempt.current === key) return;
    installationAttempt.current = key;
    setInstallationBusy(true);setInstallationError('');
    void (async () => {
      try {
        let latest = await runtimeApi.options(agentId,executor,workspace,new AbortController().signal);
        const choice = latest.options.find(row => row.adapter_id === draft.adapter_id && row.candidate_ref === candidateRef);
        if (!choice) throw new Error('This installation is no longer available. Refresh installations.');
        if (choice.technical_state === 'NOT_PROBED' || choice.technical_reasons.includes('selection_required')) {
          await runtimeApi.checkLocalInstallation(executor, {agent_id:agentId,adapter_id:draft.adapter_id,
            candidate_ref:candidateRef,inventory_revision:latest.inventory_revision,approved:true});
          latest = await runtimeApi.options(agentId,executor,workspace,new AbortController().signal);
        }
        const checked = latest.options.find(row => row.adapter_id === draft.adapter_id && row.candidate_ref === candidateRef);
        if (live.current) setOptions(latest);
        if (latest.freshness !== 'FRESH' || checked?.technical_state !== 'READY_FOR_RUNTIME')
          throw new Error(checked?.technical_reasons.join(', ') || 'Installation is not ready. Refresh installations.');
      } catch (failure) { if (live.current) setInstallationError(String(failure)); }
      finally { if (live.current) setInstallationBusy(false); }
    })();
  },[step,busy,options,executor,workspace,draft.adapter_id,candidateRef,reload,installationBusy]);
  const validation = step === 0 ? (!portableOnly && !draft.adapter_id ? 'Select a harness.' : '') :
    step === 1 ? (installationBusy || installationError || !selected || options?.freshness !== 'FRESH' || selected.technical_state !== 'READY_FOR_RUNTIME' ? 'Choose a verified installation to continue.' : '') :
    step === 2 ? (!draft.workspace_root.trim() || !draft.workspace_label.trim() ? 'Enter the workspace folder and name.' : '') :
    step === 3 ? (!draft.alias.trim() ? 'Enter a connection name.' : '') :
    step === 4 ? (mcpError || (selected?.harness_configuration ? harnessSelectionError(selected.harness_configuration,draft.harness_settings) : '')) :
    step === 5 ? (Object.entries(draft.authorization).some(([key,v]) => v !== null && (!Number.isInteger(v) || v < 1 || v > (key === 'minutes' ? 1440 : 1000))) ? 'Enter valid authorization limits.' : '') : '';
  const go = (value: number) => {setStep(value);setVisited(old => Math.max(old,value));setError('');};
  const buildRequest = (): SetupRequest => {
    if (!baseline) throw new Error('Configuration is still loading.');
    const intent = `setup_${Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2,'0')).join('')}`;
    const value = {client_intent_id:intent,agent_id:agentId,executor_id:executor,candidate_ref:candidateRef,
      inventory_revision:options?.inventory_revision || '',workspace_id:workspace || null,binding_id:bindingId,
      baseline,configuration:draft,
      ...(runtimeEnabled ? {mcp_preset:{expected_revision:savedMcp.revision,servers:parseMCPPreset(mcpText)}} : {})};
    const remoteBinding = connections.find(c => c.binding_id === bindingId && c.execution_location === 'remote');
    return portableOnly && !(runtimeEnabled && draft.execution_location === 'remote' && remoteBinding) ? policyOnlySetup(value) : value;
  };
  const connectionUnchanged = !!savedConnection && bindingId === savedConnection.bindingId && executor === savedConnection.executor
    && workspace === savedConnection.workspace && candidateRef === savedConnection.candidate && !presetChanged && sameConnectionConfiguration(draft, savedConnection.configuration);
  const finish = async () => {
    if (capacity.current && !await capacity.current.save()) return;
    if (connectionUnchanged) {if (!capacityPending) onClose(); return;}
    setBusy(true);setError('');
    try {
      const value = request || buildRequest();
      setRequest(value);
      await runtimeApi.finishSetup(value);
      window.dispatchEvent(new Event('nexus-workspaces-changed'));
      onClose();
    }
    catch(e) {setError(String(e));} finally {if(live.current)setBusy(false);}
  };
  const summaries = [!runtimeEnabled ? 'MCP only' : draft.execution_location === 'remote' ? 'Remote · Configure on the Connector computer' : `Local · ${draft.adapter_id || 'Choose a harness'}`,
    selected?.label || 'Choose an installation',draft.workspace_label || 'Choose folders',draft.alias || 'Name the connection',
    Object.values(draft.harness_settings).join(' · ') || 'Harness defaults',
    `${draft.authorization.minutes ?? 'Unlimited'} minutes · ${draft.authorization.actions ?? 'Unlimited'} actions`,test?.stage || 'Not tested'];
  const statuses = [
    portableOnly || !!draft.adapter_id && visited > 0 ? 'complete' : draft.adapter_id ? 'partial' : 'pending',
    selected?.technical_state === 'READY_FOR_RUNTIME' ? 'complete' : candidateRef ? 'partial' : 'pending',
    draft.workspace_root.trim() && draft.workspace_label.trim() ? 'complete' : draft.workspace_root || draft.workspace_label || draft.provider_home ? 'partial' : 'pending',
    draft.alias.trim() ? 'complete' : 'pending',
    selected?.harness_configuration && !harnessSelectionError(selected.harness_configuration,draft.harness_settings) ? 'complete' : Object.keys(draft.harness_settings).length ? 'partial' : 'pending',
    authorized ? 'complete' : 'partial',
    test?.status === 'succeeded' ? 'complete' : test ? 'partial' : 'pending',
  ] as ('complete' | 'partial' | 'pending')[];
  return <section className="rounded-lg border p-3 space-y-4 text-xs" data-testid={`agent-connections-${agentId}`}>
    <header className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
      <div className="flex gap-2 flex-wrap">{step === 0 && <>
        <button className="btn btn-secondary" disabled={busy} onClick={() => fileInput.current?.click()}>Import JSON</button>
        <button className="btn btn-secondary" disabled={busy} onClick={() => {
          const url=URL.createObjectURL(new Blob([exportConnectionConfiguration(draft)],{type:'application/json'}));
          const a=document.createElement('a');a.href=url;a.download=`${agentId}.connection.json`;a.click();setTimeout(() => URL.revokeObjectURL(url),1000);
        }}>Export JSON</button>
        <ConfigurationHelp label="Connection JSON">Reuse harness preferences and connection policies in Nexus or the Connector CLI. Identity, credentials, installation, workspace and login paths stay on the destination host.</ConfigurationHelp>
      </>}</div>
      <h3 className="text-center font-semibold">Connections · {agentId}</h3>
      <button className="btn btn-secondary justify-self-end" disabled={busy && !!request} onClick={onClose}>Close</button>
    </header>
    <input ref={fileInput} type="file" accept=".json,application/json" className="hidden" aria-label="Import connection JSON" onChange={async e => {
      const file=e.currentTarget.files?.[0];e.currentTarget.value='';if(!file)return;
      try {if(file.size>65536)throw new Error('The file must be 64 KiB or smaller.');const config=parseConnectionConfiguration(await file.text());
        const setup=await runtimeApi.setup(agentId);setBaseline(setup.baseline);
        imported.current=true;patch(config);setCandidateRef('');setBindingId(null);setWorkspace('');setVisited(0);setNotice('Configuration imported. Review the host, installation and folders.');
      }catch(e){setError(String(e));}
    }} />
    <ConnectionWorkflow steps={workflowSteps} step={step} summaries={summaries} statuses={statuses} available={visited} locked={busy || installationBusy || !!testing || (step===0 && capacityPending)}
      onStep={async value => {if (value <= visited && !busy && !testing) {if (step===0 && value!==0 && capacity.current && !await capacity.current.save()) return; go(value);}}} />
    <h4 className="font-semibold">Step {step+1} of {workflowSteps.length} · {workflowSteps[step]}</h4>
    {connectionUnchanged && <p className="text-xs text-surface-500">Next or Done saves capacity changes and preserves the existing connection and its sessions.</p>}
    <fieldset disabled={busy || installationBusy || !!testing} className="space-y-4">
    {step === 0 && <>
      {runtimeEnabled && connections.some(c => c.execution_location === draft.execution_location) && <label className="block">Existing connection <span className="text-surface-500">Select to authorize and configure this connection</span><select aria-label="Existing connection" className={input} value={bindingId || ''} onChange={async e => {
        const saved=connections.find(c => c.binding_id===e.target.value);if(!saved)return;
        setBusy(true);setError('');
        try {const setup=await runtimeApi.setup(agentId,saved.binding_id);setBaseline(setup.baseline);setBindingId(saved.binding_id);
          loadMcp(setup.mcp_preset);
          setExecutor(saved.executor_id);setWorkspace(saved.workspace_id);setCandidateRef(saved.candidate_ref);imported.current=false;
          patch({...setup.folders,adapter_id:saved.adapter_id,alias:setup.public_config?.alias || '',
            harness_settings:setup.public_config?.harness_settings || {},tool_access:setup.public_config?.nexus_tool_permission || 'ask',
            automatic_reply:true,authorization:setup.authorization || emptyConnection().authorization,
            workspace_label:workspaces.find(w => w.workspace_id===saved.workspace_id)?.display_name || ''});
        }catch(e){setError(String(e));}finally{setBusy(false);}
      }}><option value="">Select a connection to edit or export</option>{connections.filter(c => c.execution_location === draft.execution_location).map(c => <option key={c.binding_id} value={c.binding_id}>{c.adapter_id} · {workspaces.find(w => w.workspace_id===c.workspace_id)?.display_name || c.workspace_id}</option>)}</select></label>}
      <label className="block">Runtime connection <ConfigurationHelp label="Runtime connection">Use the global setting or override it for this agent. This change is applied when you finish.</ConfigurationHelp>
        <select className={input} aria-label="Runtime connection" value={draft.runtime_enabled === null ? 'inherit' : String(draft.runtime_enabled)} onChange={e => patch({runtime_enabled:e.target.value === 'inherit' ? null : e.target.value === 'true'})}>
          <option value="inherit">Use global setting ({runtimeDefault ? 'Enabled' : 'MCP only'})</option><option value="true">Enabled</option><option value="false">MCP only</option>
        </select>
      </label>
      {runtimeEnabled && <>
        <label className="block">Execution host <span className="text-surface-500">Required</span><select aria-label="Execution access" className={input} value={draft.execution_location} onChange={e => patch({execution_location:e.target.value as ConnectionConfiguration['execution_location']})}>
          <option value="local">Local</option><option value="remote">Remote</option></select></label>
        {draft.execution_location !== 'remote' && <div role="group" aria-label="Local runtime" className="flex gap-2 flex-wrap">
          {options?.catalog.runtimes.filter(r => r.support_status === 'managed_supported').map(r => <button key={r.adapter_id} className={`btn ${draft.adapter_id === r.adapter_id ? 'btn-primary':'btn-secondary'}`}
            aria-pressed={draft.adapter_id === r.adapter_id} data-testid={`local-runtime-${r.adapter_id}`}
            onClick={() => {patch({adapter_id:r.adapter_id,harness_settings:{}});loadMcp();setCandidateRef('');setBindingId(null);setVisited(0);}}>{r.display_name}</button>)}
        </div>}
        <label>Session context <span className="text-surface-500">Optional</span><ConfigurationHelp label="Session context">Shared keeps all senders together. Per sender shares history across sessions of the same agent. Per sender + source session isolates each verified source session. Messages without a verified session, including the operator UI, share a separate session per sender.</ConfigurationHelp>
          <select aria-label="Session context" className={input} value={draft.session_policy || ''} onChange={e => patch({session_policy:e.target.value as 'shared' | 'per_sender' | 'per_sender_session' | 'one_shot' || null})}>
            <option value="">Use global setting ({sessionDefault === 'one_shot' ? 'One shot' : sessionDefault.replaceAll('_', ' ')})</option><option value="shared">Shared</option><option value="per_sender">One session per sender</option><option value="per_sender_session">One session per sender + source session</option><option value="one_shot">One shot — fresh session per call</option></select></label>
        {(draft.session_policy ?? sessionDefault) === 'one_shot' && <OneShotSettings ref={capacity} agentId={agentId} showActivity={false} saveOnNext onPendingChange={setCapacityPending} />}
        {draft.execution_location === 'remote' && <RemoteConnectorCommand agentId={agentId} />}
        {draft.execution_location === 'remote' && connections.some(c => c.binding_id === bindingId && c.execution_location === 'remote') &&
          <MCPPresetFields remote value={mcpText} onChange={text => {setMcpText(text);setTest(null);setRequest(null);setAuthorized(false);setError('');}} />}
      </>}
    </>}
    {step === 1 && <fieldset disabled={installationBusy || busy} className="space-y-3">
      <label>Workspace <span className="text-surface-500">Required</span><select aria-label="Runtime workspace" className={input} value={workspace} onChange={e => {setWorkspace(e.target.value);setCandidateRef('');setBindingId(null);setVisited(1);patch({workspace_label:workspaces.find(w => w.workspace_id === e.target.value)?.display_name || '',workspace_root:''});}}>
        <option value="">Register a new workspace</option>{workspaces.map(w => <option key={w.workspace_id} value={w.workspace_id}>{w.display_name || w.workspace_id}</option>)}</select></label>
      <div role="group" aria-label="Local installation" className="space-y-2">{options?.options.filter(row => row.adapter_id === draft.adapter_id && row.candidate_ref).map(row => {
        const info=options.availability.availability?.find(i => i.candidate_ref === row.candidate_ref);
        return <label key={row.candidate_ref} className="block border rounded-lg p-3"><input type="radio" name="installation" checked={row.candidate_ref===candidateRef} disabled={!localInstallationAvailable(row)} onChange={() => void selectInstallation(row.candidate_ref!)} />{' '}
          <span className="font-medium">{info?.display_name || row.adapter_id}{info?.version ? ` · ${info.version}` : ''}</span>
          {row.binding && <span className="chip ml-2">Recommended · Configured for this workspace</span>}
          <span className="block mt-1 text-surface-500">{info?.source}</span>
          <details className="mt-1"><summary>Details</summary><span className="break-all">{row.label}</span></details>
        </label>;
      })}</div>
      {(installationBusy || busy) ? <p role="status" className="flex items-center gap-2"><Loader2 className="animate-spin" size={16} />Checking installation…</p> : installationError ? <div role="alert">
        <p>Could not verify this installation.</p><button className="btn btn-secondary" onClick={() => setReload(v => v+1)}>Retry</button>
        <details><summary>Details</summary><p>{installationError}</p></details>
      </div> : selected?.technical_state === 'READY_FOR_RUNTIME' && <p role="status" className="flex items-center gap-2 text-green-600"><CheckCircle2 size={16} />Installation verified</p>}
      <InventoryRefresh compact executorId={executor} onUpdated={() => {setTest(null);setRequest(null);setReload(v => v+1);}} />
    </fieldset>}
    {step === 2 && <>
      <label className="block">Workspace name <span className="text-surface-500">Required</span><input aria-label="Workspace name" className={input} value={draft.workspace_label} onChange={e => patch({workspace_label:e.target.value})} /></label>
      {workspace && draft.execution_location === 'local' && workspacePaths.length > 0 && <label className="block">Previously used folders on this execution host
        <select aria-label="Saved workspace folder" className={input}
          value={workspacePaths.some(item => item.path === draft.workspace_root) ? draft.workspace_root : ''}
          onChange={e => patch({workspace_root:e.target.value})}>
          <option value="">Enter a new folder</option>
          {workspacePaths.map(item => <option key={item.path} value={item.path}>{item.path}</option>)}
        </select>
      </label>}
      {workspace && workspacePathsLoading && <p className="text-xs text-surface-500">Loading saved workspace folders…</p>}
      <label className="block">Workspace folder <span className="text-surface-500">Required</span><ConfigurationHelp label="Workspace folder">Existing absolute folder on the execution host. Folders previously used for this workspace on the same host are suggested above. The harness operates in the selected directory.</ConfigurationHelp><input aria-label="Workspace folder" className={input} value={draft.workspace_root} onChange={e => patch({workspace_root:e.target.value})} /></label>
      <label className="block">Login directory <span className="text-surface-500">Optional</span><ConfigurationHelp label="Login directory">The account directory suggested by Core discovery. Continuing authorizes the harness to use this login for the test and this connection.</ConfigurationHelp><input aria-label="Login directory" className={input} value={draft.provider_home || ''} onChange={e => patch({provider_home:e.target.value || null})} /></label>
    </>}
    {step === 3 && <>
      <label className="block">Connection name <span className="text-surface-500">Required</span><input aria-label="Connection name" className={input} maxLength={160} value={draft.alias} onChange={e => patch({alias:e.target.value})} /></label>
      <p className="text-surface-500">{bindingId ? 'The existing connection will be updated when you finish.' : 'The new connection will be created when you finish.'}</p>
    </>}
    {step === 4 && <>
      {selected?.harness_configuration && <HarnessPreferenceFields inheritedGlobalMcps={inheritedMcps} schema={selected.harness_configuration} values={draft.harness_settings} onChange={harness_settings => patch({harness_settings})} />}
      <MCPPresetFields value={mcpText} onChange={text => {setMcpText(text);setTest(null);setRequest(null);setAuthorized(false);setError('');}} />
      <label className="block">Nexus tool access <span className="text-surface-500">Required</span><ConfigurationHelp label="Nexus tool access">Always allow skips approval requests for Nexus tools. Native harness approval settings remain separate.</ConfigurationHelp><select aria-label="Nexus tool access" className={input} value={draft.tool_access} onChange={e => patch({tool_access:e.target.value as 'ask' | 'always_allow'})}><option value="ask">Ask for approval</option><option value="always_allow">Always allow</option></select></label>
    </>}
    {(step === 5 || (step === 0 && runtimeEnabled && draft.execution_location === 'remote' && connections.some(c => c.binding_id === bindingId && c.execution_location === 'remote'))) && <>
      <p>Next authorizes the connection test and the execution limits below. The connection is saved only after Finish.</p>
      {(['minutes','actions'] as const).map(key => <div key={key} className="space-y-2"><label className="block">{key==='minutes'?'Authorization duration (minutes)':'Action limit'} <span className="text-surface-500">Required</span>
        <ConfigurationHelp label={key==='minutes'?'Authorization duration':'Action limit'}>{key==='minutes'?'Duration starts at Finish. The temporary test has a separate four-minute limit.':'Maximum runtime actions after Finish. Select Unlimited for no action limit.'}</ConfigurationHelp>
        <input className={input} aria-label={key==='minutes'?'Authorization duration':'Action limit'} type="number" min={1} max={key==='minutes'?1440:1000} disabled={draft.authorization[key]===null} value={draft.authorization[key] ?? ''} onChange={e => patch({authorization:{...draft.authorization,[key]:Number(e.target.value)}})} /></label>
        <label><input type="checkbox" checked={draft.authorization[key]===null} onChange={e => patch({authorization:{...draft.authorization,[key]:e.target.checked?null:key==='minutes'?60:20}})} /> Unlimited</label></div>)}
    </>}
    </fieldset>
    {step === 6 && <div className="rounded-xl border p-6 text-center space-y-3" aria-busy={testing}>
      <div role="status" aria-live="polite" className="flex items-center justify-center gap-2 text-sm font-medium">
        {testing && <Loader2 className="animate-spin motion-reduce:animate-none" size={22} aria-hidden="true" />}
        {test?.status==='succeeded' && <CheckCircle2 className="text-green-600" size={22} aria-hidden="true" />}
        {test?.stage || 'Ready to test your connection'}
      </div>
      {test?.status==='succeeded' && <p className="text-surface-500">The harness responded and the test session is closed. Finish to save.</p>}
      {!testing && test?.status!=='succeeded' && <button className="btn btn-primary" disabled={busy} onClick={async () => {
        setBusy(true);setError('');
        try {const value=test?.status === 'failed' ? buildRequest() : request || buildRequest();setRequest(value);setTest(await runtimeApi.testSetup(value));}
        catch(e){setError(String(e));}finally{if(live.current)setBusy(false);}
      }}>{test?.status === 'failed' ? 'Retry test' : request && !test ? 'Check test submission' : 'Test connection'}</button>}
      <button type="button" className="btn btn-secondary" aria-expanded={details} onClick={() => setDetails(v => !v)}>Details</button>
      {details && <div className="text-left text-xs space-y-2"><p>Checks installation, provider login and a real model response using a temporary Core session. Does not test Nexus message routing.</p>
        <ol className="list-decimal pl-5">{test?.details.map((line,i) => <li key={i}>{line}</li>)}</ol>
      </div>}
    </div>}
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
    <footer className="sticky bottom-0 bg-white dark:bg-surface-800 border-t pt-3 flex items-center gap-3">
      {connectionUnchanged && <button className="btn btn-primary" disabled={busy || installationBusy || !!testing || capacityPending} onClick={() => void finish()}>Done</button>}
      {step>0 && <button className="btn btn-secondary" disabled={busy || installationBusy || !!testing} onClick={() => go(step-1)}>← Back</button>}
      {(portableOnly && step===0 || step===6 && test?.status==='succeeded') ? <button className="btn btn-primary" disabled={busy || capacityPending} onClick={() => void finish()}>{busy?'Saving…':'Finish'}</button> : step<6 && <button className="btn btn-primary" disabled={busy || !!validation || !!error || (step===0 && capacityPending)} onClick={async () => {if (step===0 && capacity.current && !await capacity.current.save()) return; if(step===5)setAuthorized(true);go(step+1);}}>Next →</button>}
      {busy && <Loader2 size={16} className="animate-spin" aria-label="Loading" />}
      {validation && <span className="text-surface-500">{validation}</span>}
    </footer>
  </section>;
}
