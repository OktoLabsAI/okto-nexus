import {useEffect, useMemo, useRef, useState, useSyncExternalStore} from 'react';
import {runtimeApi, type ConnectionCatalogItem, type SetupFinishResult} from '../../runtimeApi';
import {ProjectConnectModel, connectorDraftCommand, type ConnectWorkspace, type ProjectConnectApi} from '../../projectConnectFlowModel';
import {ConnectionWorkflow} from '../ConnectionWorkflow';
import {HarnessPreferenceFields} from '../HarnessPreferenceFields';
import {ModalCancelButton, useAgentModalGuard, useAgentModalChanges, useAgentModalTransition} from '../AgentActionModal';

const input='block w-full rounded-lg border border-surface-300 dark:border-surface-700 bg-transparent p-2';
const browserStorage={getItem:(key:string)=>window.sessionStorage.getItem(key),setItem:(key:string,value:string)=>window.sessionStorage.setItem(key,value),removeItem:(key:string)=>window.sessionStorage.removeItem(key)};
export interface ProjectConnectFlowProps {
  identityKey:string; workspace:ConnectWorkspace|null; serverOrigin:string;
  onClose:()=>void; onResume:(connection:ConnectionCatalogItem)=>void; onComplete:(result:SetupFinishResult)=>void;
  api?:ProjectConnectApi; storage?:Pick<Storage,'getItem'|'setItem'|'removeItem'>;
}

/** An inline body for the existing contextual panel; never another modal. */
export function ProjectConnectFlow({identityKey,workspace,serverOrigin,onClose,onResume,onComplete,api=runtimeApi,storage=browserStorage}:ProjectConnectFlowProps) {
  const model=useMemo(()=>new ProjectConnectModel(api,storage,identityKey,workspace),[api,storage,identityKey,workspace?.workspace_id]);
  const lifetime=useMemo(()=>({active:false,started:false}),[model]);
  const state=useSyncExternalStore(model.subscribe,model.getSnapshot,model.getSnapshot);
  const changes=useAgentModalChanges(), transition=useAgentModalTransition();
  const dirty=!!state.agentId&&!state.retained&&!['choose','remote','complete','loading'].includes(state.phase);
  useAgentModalGuard(dirty,state.busy);
  useEffect(()=>{if(state.retained||state.phase==='complete')changes?.reset(changes.checkpoint());},[changes,state.retained,state.phase]);
  const [consent,setConsent]=useState(false),[customize,setCustomize]=useState(false),[error,setError]=useState('');
  const [finishConsent,setFinishConsent]=useState(false);
  const [remoteOrigin,setRemoteOrigin]=useState(serverOrigin),[shell,setShell]=useState<'powershell'|'posix'>('powershell');
  const completed=useRef<ProjectConnectModel|null>(null);
  const [resumeTarget,setResumeTarget]=useState<ConnectionCatalogItem|null>(null);
  useEffect(()=>{if(resumeTarget&&!state.busy){setResumeTarget(null);transition(()=>onResume(resumeTarget));}},[resumeTarget,state.busy,transition,onResume]);
  useEffect(()=>{
    lifetime.active=true;
    if(!lifetime.started){lifetime.started=true;void model.initialize();}
    // StrictMode's effect rehearsal must not dispose a still-mounted model or
    // load twice. A real identity/workspace change disposes the old lifetime.
    return()=>{lifetime.active=false;queueMicrotask(()=>{if(!lifetime.active)model.dispose();});};
  },[model,lifetime]);
  useEffect(()=>{setConsent(false);setFinishConsent(false);},[state.request]);
  useEffect(()=>{
    if(state.phase==='complete'&&state.result&&completed.current!==model){completed.current=model;onComplete(state.result);}
  },[state.phase,state.result,model,onComplete]);
  useEffect(()=>{
    if(state.phase!=='testing'||state.busy)return;
    const timer=setInterval(()=>void model.checkTest(),1500);
    return()=>clearInterval(timer);
  },[model,state.phase,state.busy]);
  const act=(action:()=>unknown)=>{setError('');void Promise.resolve().then(action).catch(e=>setError(e instanceof Error?e.message:String(e)));};
  const phase=state.phase;
  const step=phase==='choose'||phase==='remote'||phase==='loading'?0:phase==='configure'||phase==='checking'?1:phase==='review'?2:3;
  const choice=state.options?.options.find(item=>item.candidate_ref===state.candidateRef);
  let remoteCommand='';let remoteError='';
  if(phase==='remote')try{remoteCommand=connectorDraftCommand(remoteOrigin,shell);}catch(e){remoteError=e instanceof Error?e.message:String(e);}
  const request=state.request;
  const identity=state.reviewIdentity;
  const allowed=Object.entries(identity?.permissions||{}).flatMap(([group,value])=>
    value&&typeof value==='object'&&!Array.isArray(value)?Object.entries(value).filter(([,enabled])=>enabled===true).map(([flag])=>`${group}.${flag}`):[]);
  const policyLimits=identity?.permissions.limits;
  const limits=policyLimits&&typeof policyLimits==='object'&&!Array.isArray(policyLimits)?Object.entries(policyLimits).filter(([,value])=>typeof value==='number'||value===null):[];
  const reviewDetails=request&&<div className="space-y-3">
    <dl><dt>Server execution host</dt><dd>{state.executorLabel||'Nexus Server — retained host reference'}</dd><dt>Logical project</dt><dd>{request.configuration.workspace_label}</dd>
      <dt>Server folder</dt><dd className="break-all">{request.configuration.workspace_root}</dd><dt>Harness</dt><dd>{request.configuration.adapter_id}</dd>
      <dt>New collaborator</dt><dd>{request.agent_creation?.display_name}</dd><dt>Provider login directory</dt><dd>{request.configuration.provider_home||'Harness default on the Server'}</dd>
      <dt>Execution authorization applied at Finish</dt><dd>{request.configuration.authorization.minutes??'Unlimited'} minutes · {request.configuration.authorization.actions??'Unlimited'} actions</dd>
      <dt>Identity role</dt><dd>{identity?.role||'Retained canonical defaults reference'}</dd></dl>
    <div><h4 className="font-semibold">Coordination permissions for the new identity</h4><ul className="list-disc pl-5">{allowed.map(permission=><li key={permission}>{permission.replaceAll('_',' ').replace('.',' → ')}</li>)}</ul>
      <h4 className="font-semibold">Coordination rate and recipient limits</h4><dl>{limits.map(([key,value])=><div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{value===null?'Unlimited':String(value)}</dd></div>)}</dl>
      {!limits.length&&<p>No rate values were supplied by this identity review.</p>}</div>
    {request.native_decision_policy?.initialize?<p role="note" className="rounded border border-amber-400 p-3"><strong>Server-wide change at Finish:</strong> enable native human-decision handling for every connection on this Nexus Server. This is a global Server policy change, separate from this connection's execution limits.</p>:
      <p>The existing Server-wide native decision policy is preserved.</p>}
    <details><summary>Canonical identity, host and policy references</summary><p className="break-all">Agent: {request.agent_id}</p><p className="break-all">Server: {state.serverId} · Host: {request.executor_id}</p>
      <p className="break-all">Project: {request.workspace_id||'Created canonically from the Server folder at Finish'}</p><p>Preset: {request.project_preset?.id} revision {request.project_preset?.revision}</p>
      <p className="break-all">Identity defaults: {request.agent_creation?.defaults_hash}</p><p className="break-all">Native policy: {state.nativePolicySource} · {request.native_decision_policy?.expected_revision}</p>
      <pre className="whitespace-pre-wrap break-all">{JSON.stringify(identity?.permissions,null,2)}</pre></details>
  </div>;
  return <section aria-label="Connect a project agent" data-testid="project-connect-flow" className="space-y-4">
    <header className="flex items-start justify-between gap-3"><div><h2 className="text-xl font-semibold">Connect agent</h2>
      <p className="text-sm text-surface-500">{state.workspace?.display_name||'Choose a project'} · Nexus Server</p></div>
      <ModalCancelButton onClose={onClose}>{state.retained?'Close and keep attempt':'Close'}</ModalCancelButton></header>
    <ConnectionWorkflow steps={['Choose connection','Project and harness','Review','Test and finish']} step={step}
      summaries={[state.workspace?.display_name||'Project connection',state.displayName||'Choose a harness',request?'Exact selection ready':'Review before effects',state.test?.stage||'No model test started']}
      available={step} locked onStep={()=>{}} />
    {(error||state.error)&&<p role="alert">{error||state.error}</p>}
    {phase==='loading'&&<div role="status"><p>{state.busy?'Loading authorized project connections…':'The connection flow could not be loaded.'}</p>
      {!state.busy&&<button className="btn btn-secondary" onClick={()=>act(()=>model.initialize())}>Retry loading</button>}</div>}
    {(phase==='choose'||phase==='configure')&&<label className="block">Project
      <select aria-label="Project" data-modal-passive className={input} disabled={state.busy} value={state.workspace?.workspace_id||''}
        onChange={event=>{const id=event.target.value;const selected=state.workspaces.find(item=>item.workspace_id===id)||null;transition(()=>act(()=>model.selectWorkspace(selected)));}}>
        <option value="">New project on the Server</option>{state.workspaces.map(item=><option key={item.workspace_id} value={item.workspace_id}>{item.display_name||'Unnamed project'}</option>)}
      </select></label>}
    {phase==='choose'&&<>
      {state.catalogStatus==='loading'&&<p role="status">Checking the complete authorized connection catalog…</p>}
      {state.catalogStatus==='unavailable'&&<p>Connection coverage is unavailable; this is not an empty project. <button className="btn btn-secondary" disabled={state.busy} onClick={()=>act(()=>model.refreshCatalog())}>Reload connections</button></p>}
      {state.catalog.length>0&&<section aria-label="Existing project connections" className="space-y-2"><h3 className="font-semibold">Open an existing connection</h3>
        <p>Selecting opens its context. It does not start a session, renew authorization or change its configuration.</p>
        {state.catalog.map(item=><div key={item.server_id+':'+item.executor_id+':'+item.binding_id} className="rounded border p-3">
          <p className="font-medium">{item.agent_label||'Agent name unavailable'} · {item.adapter_id}</p>
          <p className="text-sm">{item.workspace_label||'Project'} · {item.host_label||(item.execution_location==='local'?'Nexus Server':'Connector host')}</p>
          <button className="btn btn-secondary" disabled={state.busy} onClick={()=>act(async()=>{const result=await model.resume(item);if(result)setResumeTarget(result);})}>Open connection</button>
          <details><summary>Connection reference</summary><p className="break-all">{item.binding_id}</p><p>Canonical access and state are checked when opened.</p></details>
        </div>)}</section>}
      {state.catalogStatus==='ready'&&!state.catalog.length&&<p>No recorded connections match this project. You can add a collaborator.</p>}
      <div className="flex flex-wrap gap-2"><button className="btn btn-primary" disabled={state.busy||state.catalogStatus!=='ready'} onClick={()=>act(()=>model.add())}>Add another harness on this Server</button>
        <button className="btn btn-secondary" disabled={state.busy} onClick={()=>act(()=>model.remote())}>Use a Connector on another host</button></div>
    </>}
    {phase==='remote'&&<section aria-label="Connect on another host" data-modal-passive className="space-y-3">
      <h3 className="font-semibold">Run the Connector on the execution host</h3>
      <p>The browser cannot discover that host's programs, login or folders. This command creates a host draft without an agent key or operator credential.</p>
      <label className="block">Reachable Nexus Server address<input className={input} aria-label="Reachable Nexus Server address" value={remoteOrigin} onChange={e=>setRemoteOrigin(e.target.value)} /></label>
      <label className="block">Terminal<select className={input} aria-label="Connector terminal" value={shell} onChange={e=>setShell(e.target.value as 'powershell'|'posix')}><option value="powershell">PowerShell</option><option value="posix">Bash / zsh</option></select></label>
      {remoteCommand?<pre className="whitespace-pre-wrap break-all rounded bg-surface-100 dark:bg-surface-900 p-3">{remoteCommand}</pre>:<p role="status">{remoteError}</p>}
      <p>Keep the setup request ID printed by the Connector. An authenticated operator reviews the same draft, logical project and identity, then returns its protected handoff. Resume with the Connector's setup receipt; waiting for approval is not a ready connection.</p>
      {state.workspace&&<details><summary>Project reference for the operator review</summary><p className="break-all">{state.workspace.workspace_id}</p><p>Use this canonical project in the operator review. A folder name alone does not select the project.</p></details>}
      <button className="btn btn-secondary" onClick={()=>act(()=>model.choose())}>Back to project connections</button>
    </section>}
    {phase==='configure'&&state.configuration&&<section className="space-y-3" aria-label="Project connection selection">
      <p>Execution host: {state.executorLabel}. Folders and login belong to this Nexus Server, which may be a different computer from your browser.</p>
      <div role="group" aria-label="Observed harness installations" className="space-y-2">
        {state.options?.options.filter(item=>item.candidate_ref).map(item=><label key={item.adapter_id+':'+item.candidate_ref} className="block rounded border p-3">
          <input type="radio" name="project-harness" checked={state.candidateRef===item.candidate_ref} disabled={state.busy||!item.can_configure}
            onChange={()=>act(()=>model.selectInstallation(item.candidate_ref!))} />{' '}
          {state.options?.catalog.runtimes.find(row=>row.adapter_id===item.adapter_id)?.display_name||item.adapter_id}
          <span className="block text-sm text-surface-500">{item.technical_state==='READY_FOR_RUNTIME'?'Installation verified':item.technical_state==='NOT_PROBED'?'Version check required':'Review installation availability'}</span>
        </label>)}
        {!state.options?.options.some(item=>item.candidate_ref)&&<p>No eligible installation is currently published by this Server. Install and authenticate a supported harness on this host, then reopen this flow.</p>}
      </div>
      {choice&&choice.technical_state!=='READY_FOR_RUNTIME'&&<div><p>A version check runs the selected program on this Server without authorizing a model session.</p>
        <button className="btn btn-secondary" disabled={state.busy} onClick={()=>act(()=>model.verifyInstallation())}>Verify selected installation</button></div>}
      <label className="block">Collaborator name<input className={input} aria-label="Collaborator name" maxLength={120} value={state.displayName} disabled={state.busy}
        onChange={e=>{const value=e.target.value;act(()=>model.customize({},value));}} /></label>
      <label className="block">Project name<input className={input} aria-label="Project name" value={state.configuration.workspace_label} disabled={state.busy}
        onChange={e=>{const value=e.target.value;act(()=>model.customize({workspace_label:value}));}} /></label>
      {state.workspacePaths.length>1&&<label className="block">Previously used Server folder<select className={input} aria-label="Previously used Server folder" value={state.configuration.workspace_root}
        onChange={e=>{const value=e.target.value;act(()=>model.customize({workspace_root:value}));}}><option value="">Choose a folder</option>{state.workspacePaths.map(path=><option key={path} value={path}>{path}</option>)}</select></label>}
      <label className="block">Project folder on the Nexus Server<input className={input} aria-label="Project folder on the Nexus Server" value={state.configuration.workspace_root} disabled={state.busy}
        onChange={e=>{const value=e.target.value;act(()=>model.customize({workspace_root:value}));}} /></label>
      <p>Recommended project preset: {state.preset?.origin.id}, revision {state.preset?.origin.revision}. The proposed identity is created only at Finish.</p>
      <button className="btn btn-secondary" aria-expanded={customize} onClick={()=>setCustomize(value=>!value)}>Customize</button>
      {customize&&<div className="space-y-3"><label className="block">Provider login directory on the Server<input className={input} aria-label="Provider login directory on the Server"
        value={state.configuration.provider_home||''} onChange={e=>{const value=e.target.value;act(()=>model.customize({provider_home:value||null}));}} /></label>
        {choice?.harness_configuration&&<HarnessPreferenceFields schema={choice.harness_configuration} values={state.configuration.harness_settings}
          onChange={harness_settings=>act(()=>model.customize({harness_settings}))} />}
        <label className="block">Nexus tool access<select className={input} aria-label="Nexus tool access" value={state.configuration.tool_access} onChange={e=>{const value=e.target.value as 'ask'|'always_allow';act(()=>model.customize({tool_access:value}));}}><option value="ask">Ask for approval</option><option value="always_allow">Always allow</option></select></label>
      </div>}
      <button className="btn btn-primary" disabled={state.busy||!state.candidateRef} onClick={()=>act(()=>model.review())}>Review this connection</button>
    </section>}
    {phase==='review'&&request&&<section aria-label="Exact connection review" className="space-y-3">
      <h3 className="font-semibold">Review before any model test</h3>
      {reviewDetails}
      <ul className="list-disc pl-5">{state.reviewEffects.map(effect=><li key={effect}>{effect}</li>)}</ul>
      <label className="block"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)} /> I approve this exact identity, permissions, limits and {request.native_decision_policy?.initialize?'Server-wide policy change, applied only at Finish, and':'configuration, applied only at Finish, and'} a temporary real model test now, which may use the provider account and incur usage.</label>
      <div className="flex gap-2"><button className="btn btn-secondary" onClick={()=>act(()=>model.editReview())}>Edit review</button>
        <button className="btn btn-primary" disabled={!consent||state.busy} onClick={()=>act(()=>model.test(consent))}>Test reviewed connection</button></div>
    </section>}
    {(phase==='checking'||phase==='testing')&&<div role="status"><p>{phase==='checking'?'Checking the selected installation…':state.test?.stage||'Checking the retained model test…'}</p>
      <p>Closing this panel does not resubmit or cancel the retained request.</p></div>}
    {phase==='finish'&&<section aria-label="Finish project connection" className="space-y-3"><h3 className="font-semibold">Test completed and its temporary session closed</h3>
      {reviewDetails}
      <p>Finish creates the reviewed collaborator, saves this project connection and its authorization. It does not submit a project task.</p>
      <label className="block"><input type="checkbox" checked={finishConsent} onChange={e=>setFinishConsent(e.target.checked)} /> Apply this exact reviewed identity, permissions, authorization and {request?.native_decision_policy?.initialize?'Server-wide native decision policy change':'preserved native decision policy'} now.</label>
      <button className="btn btn-primary" disabled={state.busy||!finishConsent} onClick={()=>act(()=>model.finish())}>Finish</button></section>}
    {phase==='uncertain'&&<section aria-label="Recover retained connection attempt" className="space-y-3"><h3 className="font-semibold">Check the retained attempt</h3>
      <p>Its result is not yet confirmed. Selection is locked. Recovery checks the same request; it does not start a new model test, create another identity or renew a grant.</p>
      <button className="btn btn-primary" disabled={state.busy} onClick={()=>act(()=>model.recover())}>Recover existing attempt</button>
      {state.testRejected&&<><p>The Server definitively rejected this test before execution. You can preserve this attempt and explicitly edit a new review; no test is repeated automatically.</p>
        <button className="btn btn-secondary" disabled={state.busy} onClick={()=>act(()=>model.editRejectedReview())}>Edit rejected review</button></>}
      {state.test?.status==='failed'&&state.test.retryable_failure&&<button className="btn btn-secondary" disabled={state.busy} onClick={()=>act(()=>model.retryReview())}>Review a new test after confirmed cleanup</button>}
      {request&&<details><summary>Retained setup reference</summary><p className="break-all">{request.client_intent_id}</p></details>}</section>}
  </section>;
}
