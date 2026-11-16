import {useEffect, useState} from 'react';
import type {HomeSessionContext} from '../../homeTypes';
import {runtimeApi, type RuntimeSession} from '../../runtimeApi';
import {readHomeSessionInspection} from '../../homeSessionInspection';
import {SessionExecutionPanel} from '../SessionExecutionPanel';

/** Revalidate admission identity before exposing only the existing passive event viewer. */
export function HomeSessionInspection({context}: {context: HomeSessionContext}) {
  const key=JSON.stringify(context);
  const [read,setRead]=useState<{key:string;session:RuntimeSession|null;error:string}>({key,session:null,error:''});
  useEffect(()=>{
    const controller=new AbortController();setRead({key,session:null,error:''});
    const revoke=()=>{controller.abort();setRead({key,session:null,error:'Operator access is required. Protected session output has been cleared.'});};
    window.addEventListener('nexus-auth-expired',revoke);window.addEventListener('nexus-operator-logout',revoke);
    void readHomeSessionInspection(runtimeApi,context,controller.signal).then(session=>{
      if(!controller.signal.aborted)setRead({key,session,error:''});
    }).catch(()=>{if(!controller.signal.aborted)setRead({key,session:null,error:'This exact session is unavailable. No replacement was selected.'});});
    return()=>{controller.abort();window.removeEventListener('nexus-auth-expired',revoke);window.removeEventListener('nexus-operator-logout',revoke);};
  },[key]);
  if(read.key!==key||!read.session)return <p role={read.key===key&&read.error?'alert':'status'}>{read.key===key&&read.error?read.error:'Revalidating the exact session…'}</p>;
  return <SessionExecutionPanel session={read.session} embedded/>;
}
