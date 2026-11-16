import {useEffect,useState} from 'react';
import {api,ApiError} from '../../api';
import type {AttentionTarget} from '../../attentionNavigation';
import {runtimeApi} from '../../runtimeApi';
import type {HomeSessionContext} from '../../homeTypes';
import {RuntimeOperations} from '../RuntimeOperations';
import {SessionExecutionPanel} from '../SessionExecutionPanel';
import {clearExactRuntimeRequests,exactScopeKey,readExactExecutionContext,readExactSessionContext} from './exactRuntimeOperations';

type Target=Extract<AttentionTarget,{kind:'execution'}>;
type Context=Awaited<ReturnType<typeof readExactExecutionContext>>;

/** An operation reference is never replaced by an agent's runtime inventory. */
export function HomeExecutionInspection({target,refreshKey,suppressOutput=true}: {
  target:Target;refreshKey?:string;suppressOutput?:boolean;
}) {
  const key=JSON.stringify(target);
  const [read,setRead]=useState<{key:string;context:Context|null;error:string}>({key,context:null,error:''});
  const [reload,setReload]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();setRead(before=>before.key===key?{...before,error:''}:{key,context:null,error:''});
    const revoke=()=>{controller.abort();clearExactRuntimeRequests(sessionStorage);setRead({key,context:null,error:'Operator access is required. Protected execution context has been cleared.'});};
    window.addEventListener('nexus-auth-expired',revoke);window.addEventListener('nexus-operator-logout',revoke);
    void readExactExecutionContext(api,runtimeApi,target,controller.signal).then(context=>{
      if(!controller.signal.aborted)setRead({key,context,error:''});
    }).catch(failure=>{
      if(controller.signal.aborted)return;
      if([401,403].includes((failure as {status?:number}).status??0)){revoke();return;}
      if(failure instanceof TypeError||failure instanceof ApiError&&failure.status>=500){
        setRead(before=>before.key===key?{...before,error:'The exact execution could not be refreshed. Displayed facts may be out of date; actions revalidate their own scope.'}:
          {key,context:null,error:'The exact execution could not be read.'});return;
      }
      setRead({key,context:null,error:'This exact execution is unavailable. No other operation or session was selected.'});
    });
    return()=>{controller.abort();window.removeEventListener('nexus-auth-expired',revoke);window.removeEventListener('nexus-operator-logout',revoke);};
  },[key,refreshKey,reload]);
  if(read.key!==key||!read.context)return <section aria-label="Exact execution context" className="space-y-2">
    <p role={read.key===key&&read.error?'alert':'status'}>{read.key===key&&read.error?read.error:'Loading the exact execution…'}</p>
    {read.key===key&&read.error&&<button type="button" className="btn btn-secondary" onClick={()=>setReload(value=>value+1)}>Refresh this exact execution</button>}
  </section>;
  return <>{read.error&&<p role="status">{read.error}</p>}<HomeExecutionDetails context={read.context} suppressOutput={suppressOutput}
    onAccessLost={()=>setRead({key,context:null,error:'Operator access is required. Protected execution context has been cleared.'})}/></>;
}

/** Presentation receives only already verified operation/session/binding facts. */
export function HomeExecutionDetails({context,suppressOutput=true,onAccessLost}: {context:Context;suppressOutput?:boolean;onAccessLost?:()=>void}) {
  const {operation,session,binding}=context;
  const uncertain=operation.executor_stage==='OUTCOME_UNKNOWN'||operation.admission_state==='RECONCILING';
  return <section aria-label="Exact execution context" className="space-y-3 min-w-0">
    <h3 className="font-semibold">Execution · {operation.executor_stage||operation.admission_state}</h3>
    <p className="text-xs break-all">{operation.operation_id}</p>
    <p className="text-sm">{operation.possible_effect?'The operation may have reached the runtime.':'No possible effect is reported for this operation.'}</p>
    {operation.executor_stage==='OUTCOME_UNKNOWN'&&<p role="status">The recorded outcome is unknown. Inspect the same request before considering another action.</p>}
    {operation.error&&<p role="alert">{operation.error.code}: {operation.error.message}</p>}
    <details className="text-xs"><summary>Exact context details</summary><dl>
      {Object.entries(operation.scope).map(([key,value])=><div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd className="break-all">{String(value)}</dd></div>)}
    </dl></details>
    {!suppressOutput&&<><SessionExecutionPanel session={session} harness={binding.adapter_id} embedded/>
      {operation.result&&<section aria-label="Retained execution result"><h4 className="font-medium">Retained result</h4>
        <pre className="whitespace-pre-wrap break-words">{operation.result.output_text}{operation.result.output_truncated?'\n[Output truncated]':''}</pre>
      </section>}</>}
    {!uncertain?<ExactSessionControls session={session} binding={binding} onAccessLost={onAccessLost}/>:
      <p role="status">Controls are unavailable for this exact session. Its history does not authorize a new context or renew execution permission.</p>}
  </section>;
}

export function ExactSessionControls({session,binding,onAccessLost}:Awaited<ReturnType<typeof readExactSessionContext>>&{onAccessLost?:()=>void}) {
  const available=session.control_available&&!session.durable_release_pending&&binding.state==='APPROVED'&&
    !['CLOSED','FAILED','CLOSING','DRAINING'].includes(session.lifecycle_state)&&session.lease_state!=='CLOSED';
  return available?<RuntimeOperations key={exactScopeKey(session.scope)} agentId={session.scope.agent_id} binding={binding}
    canStart={false} exactContext={{scope:session.scope}} allowedIntents={['turn.submit','turn.interrupt','runtime.close']} suppressOutput onAccessLost={onAccessLost}/>:
    <p role="status">Controls are unavailable for this exact session. Opening another session requires a separate explicit intention.</p>;
}

/** A session without an operation still has an exact canonical control target. */
export function HomeSessionControls({context}:{context:HomeSessionContext}) {
  const key=exactScopeKey(context);
  const [read,setRead]=useState<{key:string;value:Awaited<ReturnType<typeof readExactSessionContext>>|null;error:string}>({key,value:null,error:''});
  useEffect(()=>{
    const controller=new AbortController();setRead({key,value:null,error:''});
    const revoke=()=>{controller.abort();clearExactRuntimeRequests(sessionStorage);setRead({key,value:null,error:'Operator access is required. Protected session controls were cleared.'});};
    window.addEventListener('nexus-auth-expired',revoke);window.addEventListener('nexus-operator-logout',revoke);
    void readExactSessionContext(runtimeApi,context,controller.signal).then(value=>{if(!controller.signal.aborted)setRead({key,value,error:''});})
      .catch(failure=>{if(controller.signal.aborted)return;if([401,403].includes((failure as {status?:number}).status??0)){revoke();return;}
        setRead({key,value:null,error:'This exact session is unavailable. No replacement was selected.'});});
    return()=>{controller.abort();window.removeEventListener('nexus-auth-expired',revoke);window.removeEventListener('nexus-operator-logout',revoke);};
  },[key]);
  if(read.key!==key||!read.value)return <p role={read.error?'alert':'status'}>{read.key===key&&read.error||'Revalidating controls for the exact session…'}</p>;
  return <ExactSessionControls {...read.value} onAccessLost={()=>setRead({key,value:null,error:'Operator access is required. Reopen this exact session.'})}/>;
}
