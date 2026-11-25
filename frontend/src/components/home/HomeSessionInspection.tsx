import {lazy, Suspense, useEffect, useState, type ReactNode} from 'react';
import type {HomeSessionContext} from '../../homeTypes';
import {runtimeApi, type RuntimeSession} from '../../runtimeApi';
import {readHomeSessionInspection} from '../../homeSessionInspection';
import {SessionExecutionPanel} from '../SessionExecutionPanel';

const PiNativeTerminal = lazy(() => import('./PiNativeTerminal').then(module => ({default: module.PiNativeTerminal})));

/** Revalidate identity before opening the exact session context. */
export function HomeSessionInspection({context, technicalControls, onContinue, nativeTerminal=false}: {
  context: HomeSessionContext; technicalControls?: ReactNode; onContinue?: () => void; nativeTerminal?: boolean;
}) {
  const key=JSON.stringify([context.server_id,context.executor_id,context.workspace_id,context.session_id,
    context.binding_id,context.workspace_binding_id,context.agent_id]);
  const [read,setRead]=useState<{key:string;session:RuntimeSession|null;nativePi?:boolean;error:string}>({key,session:null,error:''});
  useEffect(()=>{
    const controller=new AbortController();setRead({key,session:null,error:''});
    const revoke=()=>{controller.abort();setRead({key,session:null,error:'Operator access is required. Protected session output has been cleared.'});};
    window.addEventListener('nexus-auth-expired',revoke);window.addEventListener('nexus-operator-logout',revoke);
    void readHomeSessionInspection(runtimeApi,context,controller.signal).then(async session=>{
      let nativePi=false;
      if(nativeTerminal&&session.lifecycle_state==='READY'&&session.scope.session_owner_generation){
        const binding=await runtimeApi.binding(context.binding_id,controller.signal).catch(()=>null);
        nativePi=binding?.adapter_id==='pi_rpc'&&
          (['binding_id','executor_id','workspace_id','workspace_binding_id','agent_id'] as const)
          .every(name=>binding[name]===session.scope[name]);
      }
      if(!controller.signal.aborted)setRead({key,session,nativePi,error:''});
    }).catch(()=>{if(!controller.signal.aborted)setRead({key,session:null,error:'This exact session is unavailable. No replacement was selected.'});});
    return()=>{controller.abort();window.removeEventListener('nexus-auth-expired',revoke);window.removeEventListener('nexus-operator-logout',revoke);};
  },[key,nativeTerminal]);
  if(read.key!==key||!read.session)return <p role={read.key===key&&read.error?'alert':'status'}>{read.key===key&&read.error?read.error:'Revalidating the exact session…'}</p>;
  const generation=read.session.scope.session_owner_generation;
  if(read.nativePi&&generation)return <Suspense fallback={<p role="status">Loading terminal…</p>}>
    <PiNativeTerminal scope={{...read.session.scope,session_owner_generation:generation}}/>
  </Suspense>;
  return <SessionExecutionPanel session={read.session} embedded interactive technicalControls={technicalControls} onContinue={onContinue}/>;
}
