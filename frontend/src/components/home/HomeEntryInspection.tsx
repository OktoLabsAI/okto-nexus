import {useEffect,useRef,useState,type ReactNode} from 'react';
import {api} from '../../api';
import {homeApi} from '../../homeApi';
import {isUntitledHomeWork} from '../../homePresentation';
import {resolveHomeTarget} from '../../homeNavigation';
import {attentionTarget} from '../../attentionNavigation';
import {readEntryInspectionPage,entryInspectionQuery,homeSessionRefKey,homeSessionTarget,homeSessionOptionLabel,initialEntrySession,occurrenceSession,type HomeEntrySelection} from '../../homeEntryInspection';
import type {HomeEntryPage,HomeResult,HomeSessionRef,HomeTarget} from '../../homeTypes';
import type {AttentionAction,AttentionOccurrence} from '../../attentionTypes';
import {CanonicalInspection} from '../AttentionInspection';
import {useAgentModalTransition} from '../AgentActionModal';
import {HomeSessionInspection} from './HomeSessionInspection';
import {AttentionRow,ResultRow} from './HomeCards';

export function HomeEntryInspection({selection,target,serverId,workspace,onClose,onChanged,renderRecord,onAttentionSelected}: {
  selection:HomeEntrySelection;target:HomeTarget;serverId:string;workspace:string|null;onClose:()=>void;onChanged:()=>void;
  renderRecord:(target:HomeTarget,continuation:boolean)=>ReactNode;
  onAttentionSelected?: (selection: HomeEntrySelection['attention']) => void;
}) {
  const {entry}=selection;
  const transition=useAgentModalTransition();
  const [session,setSession]=useState<HomeSessionRef|null>(()=>selection.attention?occurrenceSession(selection.attention.item,serverId):initialEntrySession(entry,target));
  const [active,setActive]=useState<{item:AttentionOccurrence;action:AttentionAction}|null>(selection.attention??null);
  const selectAttention = (value: typeof active) => {
    setActive(value);
    onAttentionSelected?.(value ?? undefined);
  };
  const [record,setRecord]=useState({target,continuation:false});
  const [sessions,setSessions]=useState(entry.sessions),[attention,setAttention]=useState(entry.attention_preview),[results,setResults]=useState(entry.results_preview);
  const [cursors,setCursors]=useState({sessions:entry.sessions_cursor,attention:entry.attention_cursor,results:entry.results_cursor});
  const [error,setError]=useState(''),[busy,setBusy]=useState(false),[lost,setLost]=useState(false);
  const [notice,setNotice]=useState('');
  const revisions=useRef({sessions:selection.revision,attention:selection.revision,results:selection.revision});
  const [pending,setPending]=useState<string[]>([]),[preferencesStale,setPreferencesStale]=useState(false);
  const lock=useRef(false),preferenceLocks=useRef(new Set<string>()),abort=useRef(new AbortController());
  const revoke=()=>{abort.current.abort();setLost(true);setSessions([]);setAttention([]);setResults([]);setActive(null);setSession(null);};
  useEffect(()=>{
    const controller=new AbortController();abort.current=controller;
    window.addEventListener('nexus-auth-expired',revoke);window.addEventListener('nexus-operator-logout',revoke);
    return()=>{controller.abort();window.removeEventListener('nexus-auth-expired',revoke);window.removeEventListener('nexus-operator-logout',revoke);};
  },[]);
  const more=async(partition:'sessions'|'attention'|'results')=>{
    if(lock.current||abort.current.signal.aborted||!cursors[partition])return;
    lock.current=true;setBusy(true);setError('');
    try {
      const read=(cursor:string|null)=>{
        const query=entryInspectionQuery(selection,cursor);
        return partition==='sessions'?homeApi.entrySessions(selection.groupId,entry.id,query,abort.current.signal):
          partition==='attention'?homeApi.entryAttention(selection.groupId,entry.id,query,abort.current.signal):homeApi.entryResults(selection.groupId,entry.id,query,abort.current.signal);
      };
      const {page,replaced}=await readEntryInspectionPage<unknown>(read,cursors[partition],selection,serverId,partition,revisions.current[partition],abort.current.signal);
      if(abort.current.signal.aborted)return;
      const append=<T,>(before:T[],next:T[],key:(item:T)=>string)=>{const ids=new Set(before.map(key));return [...before,...next.filter(item=>!ids.has(key(item)))];};
      if(partition==='sessions')setSessions(before=>append(replaced?[]:before,page.items as HomeSessionRef[],homeSessionRefKey));
      if(partition==='attention')setAttention(before=>append(replaced?[]:before,page.items as AttentionOccurrence[],item=>item.attention_id));
      if(partition==='results')setResults(before=>append(replaced?[]:before,page.items as HomeResult[],item=>item.id));
      revisions.current[partition]=page.revision;
      if(replaced)setNotice('Related information was refreshed. Your selected context is unchanged.');
      setCursors(before=>({...before,[partition]:page.next_cursor}));
    }catch(failure){if(!abort.current.signal.aborted){if([401,403].includes((failure as {status?:number}).status??0)){revoke();return;}
      setError('This exact context could not be refreshed. No replacement was selected.');setCursors({sessions:null,attention:null,results:null});}}
    finally{lock.current=false;if(!abort.current.signal.aborted)setBusy(false);}
  };
  const preference=async(item:AttentionOccurrence,seen?:boolean)=>{
    if(abort.current.signal.aborted||preferencesStale||preferenceLocks.current.has(item.attention_id))return;
    preferenceLocks.current.add(item.attention_id);setPending([...preferenceLocks.current]);
    try {
      const revisions={source_revision:item.source_revision,preference_revision:item.seen_state.revision};
      if(seen!==undefined)await api.attentionSeen(item.attention_id,{...revisions,seen},abort.current.signal);
      else await api.attentionSnooze(item.attention_id,{...revisions,until:item.seen_state.snoozed?null:new Date(Date.now()+3600000).toISOString()},abort.current.signal);
      if(!abort.current.signal.aborted){setPreferencesStale(true);setError('Viewing preference recorded. Reopen the row for its current viewing state.');onChanged();}
    }catch(failure){if(!abort.current.signal.aborted){if([401,403].includes((failure as {status?:number}).status??0)){revoke();return;}
      setPreferencesStale(true);setError('The viewing preference could not be confirmed. Reopen to inspect it; no replay was attempted.');onChanged();}}
    finally{preferenceLocks.current.delete(item.attention_id);if(!abort.current.signal.aborted)setPending([...preferenceLocks.current]);}
  };
  if(lost)return <p role="alert">Operator access is required. Protected context has been cleared.</p>;
  const sessionOptions=session&&!sessions.some(ref=>homeSessionRefKey(ref)===homeSessionRefKey(session))?[session,...sessions]:sessions;
  return <section className="space-y-4" aria-label="Activity context">
    {notice&&<p role="status">{notice}</p>}
    <header><h3 className="font-semibold break-words">{isUntitledHomeWork(entry)?'Work activity':entry.title}</h3>
      {(entry.agent_label||entry.host_label)&&<p className="text-xs text-surface-500">{[entry.agent_label,entry.host_label].filter(Boolean).join(' · ')}</p>}</header>
    {error&&<p role="status">{error}</p>}
    <section aria-label="Session in this activity" className="space-y-2">
      <h4 className="font-medium">Session</h4>
      {(sessions.length>1||entry.sessions_total===null||entry.has_more_sessions)&&<label className="block text-sm">Choose the exact session<select data-modal-passive className="block border rounded p-2 w-full bg-transparent" value={session?homeSessionRefKey(session):''}
        onChange={event=>{const value=sessionOptions.find(ref=>homeSessionRefKey(ref)===event.target.value)??null;transition(()=>{setSession(value);selectAttention(null);setRecord({target:value?homeSessionTarget(value):target,continuation:false});});}}>
        <option value="">Choose a session</option>{sessionOptions.map((ref,index)=><option key={homeSessionRefKey(ref)} value={homeSessionRefKey(ref)}>{homeSessionOptionLabel(ref,index)}</option>)}</select></label>}
      {!session&&<p className="text-sm text-surface-500">{entry.sessions_total===0?'No canonical session is linked to this activity.':'Select a session to inspect its exact output. No recent session is selected automatically.'}</p>}
      {session&&<ExactEntrySession key={homeSessionRefKey(session)} session={session} serverId={serverId} workspace={workspace}/>}
      {session&&<button type="button" className="btn btn-secondary" onClick={()=>transition(()=>{selectAttention(null);setRecord({target:homeSessionTarget(session),continuation:true});})}>Continue this exact session</button>}
      {cursors.sessions&&<button type="button" className="btn btn-secondary" disabled={busy} onClick={()=>void more('sessions')}>Load more linked sessions</button>}
    </section>
    {entry.external.length>0&&<p className="text-sm">External reports do not provide native terminal capture. Open the retained source below for its evidence and limitations.</p>}
    {(attention.length>0||cursors.attention)&&<section aria-label="Questions and decisions in this activity"><h4 className="font-medium">Questions and decisions</h4>
      <ul>{attention.map(item=><AttentionRow key={item.attention_id} level={5} item={item} stale={preferencesStale} pending={pending.includes(item.attention_id)}
        onOpen={(item,action)=>transition(()=>{setSession(occurrenceSession(item,serverId));selectAttention({item,action});})} onSeen={(item,seen)=>void preference(item,seen)} onSnooze={item=>void preference(item)}/>)}</ul>
      {cursors.attention&&<button type="button" className="btn btn-secondary" disabled={busy} onClick={()=>void more('attention')}>Load more related attention</button>}
      {active&&<CanonicalInspection key={active.item.attention_id} target={attentionTarget(active.item,active.action)} item={active.item} action={active.action} onClose={onClose} onChanged={onChanged}/>}
    </section>}
    {(results.length>0||cursors.results)&&<section aria-label="Deliveries in this activity"><h4 className="font-medium">Deliveries and artifacts</h4>
      <ul>{results.map(item=><ResultRow key={item.id} level={5} item={item} stale={preferencesStale||!!item.attention&&pending.includes(item.attention.attention_id)}
        onOpen={next=>transition(()=>{selectAttention(null);setSession(initialEntrySession(entry,next));setRecord({target:next,continuation:false});})}
        onContinue={next=>transition(()=>{selectAttention(null);setSession(initialEntrySession(entry,next));setRecord({target:next,continuation:true});})} onSeen={(item,seen)=>void preference(item,seen)}/>)}</ul>
      {cursors.results&&<button type="button" className="btn btn-secondary" disabled={busy} onClick={()=>void more('results')}>Load more related results</button>}
    </section>}
    {active?<button type="button" className="btn btn-secondary" onClick={()=>transition(()=>{selectAttention(null);setSession(initialEntrySession(entry,record.target));})}>Show work details</button>:
      <section aria-label="Original record and canonical controls"><h4 className="font-medium mb-2">{record.continuation?'Continue this session':'Work details'}</h4>
        {renderRecord(record.target,record.continuation)}</section>}
  </section>;
}

function ExactEntrySession({session,serverId,workspace}: {session:HomeSessionRef;serverId:string;workspace:string|null}) {
  const [resolved,setResolved]=useState<Awaited<ReturnType<typeof resolveHomeTarget>>|null>(null),[error,setError]=useState('');
  useEffect(()=>{const abort=new AbortController();void resolveHomeTarget(homeApi,homeSessionTarget(session),{server_id:serverId,workspace_id:workspace},abort.signal)
    .then(value=>{if(!abort.signal.aborted)setResolved(value);}).catch(()=>{if(!abort.signal.aborted)setError('This exact session is unavailable. No replacement was selected.');});return()=>abort.abort();},[]);
  return error?<p role="alert">{error}</p>:resolved?.session_context?<HomeSessionInspection context={resolved.session_context}/>:<p role="status">Revalidating the exact session…</p>;
}
