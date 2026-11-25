import {useCallback, useEffect, useRef, useState,type ReactNode} from 'react';
import {Pause, Play, Plus, RefreshCw} from 'lucide-react';
import type {WorkspaceListItem} from '../../api';
import type {AttentionAction, AttentionOccurrence} from '../../attentionTypes';
import type {HomeTarget,HomeEntryPage,HomeEntryGroup,HomeBoard,HomeHarnessBoard,HomeHarnessChild,HomeHarnessEvent,HomeSessionRef,HomeHarnessRequest,HomeHarnessCard as HarnessCard,HomeHarnessConnection,HomeSessionContext} from '../../homeTypes';
import {primaryAttentionAction} from '../../attentionPresentation';
import {type HomeInvalidation,type HomeStreamStatus} from '../../homeController';
import {useHomeOverview} from '../../hooks/useHomeOverview';
import {decodeHomeTarget, encodeHomeTarget,resolveHomeTarget} from '../../homeNavigation';
import {homeApi} from '../../homeApi';
import {homeStateLabel,homeTargetActionLabel,isUntitledHomeWork} from '../../homePresentation';
import type {HomeState} from '../../homeController';
import {AgentActionModal,useAgentModalTransition} from '../AgentActionModal';
import {PageContainer} from '../PageContainer';
import {HomeProjectCard,HomeSummaryCards} from './HomeContextCards';
import {workspaceDisplayName} from '../WorkspaceNames';
import {HomeNewRequest, HomeInspection, HomeAttentionInspection, HomeRestoredAttention} from './HomeInspection';
import {homeFocus,homeEntriesAnnouncementIds,isQuietEntries} from './HomeCards';
import {HomeBoardCards,isQuietBoard} from './HomeBoardCards';
import {HomeHarnessCard,HomeHarnessSignalCard} from './HomeHarnessCard';
import type {HomeAttentionReturn, HomeEntrySelection} from '../../homeEntryInspection';
import {initialHarnessSession,homeConsoleTarget,homeWorkConsoleTarget,homeSessionRefKey,homeSessionOptionLabel,homeSessionTarget,assertHarnessSessionContext} from '../../homeEntryInspection';
import {HomeSessionInspection} from './HomeSessionInspection';

type Panel = {kind: 'request'} | {kind: 'target'; target: HomeTarget; continuation?: boolean;entrySelection?:HomeEntrySelection;connection?:HomeHarnessConnection;console?:boolean}
  | {kind: 'attention'; item: AttentionOccurrence; action: AttentionAction}
  | {kind: 'restored_attention'; selection: HomeAttentionReturn}
  | {kind:'console-choice';cardId:string}
  | {kind:'harness';cardId:string|null;requests?:boolean};
/** Only the authorized pre-filter inventory can prove the first-connection case. */
export function isFirstHarnessEmpty(page:HomeEntryPage<HomeEntryGroup>|null,stale=false,filtered=false):boolean {
  if(!page||stale||filtered||!isQuietEntries(page)||page.partition!=='groups')return false;
  const scope=page.scope,count=page.inventory?.connections;
  return page.source_status.connections==='ready'&&
    ['work','results','attention','connections','sessions','correlations','external'].every(key=>['ready','disabled'].includes(page.source_status[key]))&&
    scope.quick==='active'&&scope.include_recent_results===true&&
    !scope.agent_id&&!scope.state&&!scope.harness&&!scope.host&&
    count?.unit==='connections'&&count.total_is_exact===true&&count.value===0;
}

/** Contextual activity page, never a second inventory or a synthesized harness. */
function HarnessSessionInspection({sessionRef,connection,serverId,workspace}:{sessionRef:HomeSessionRef;connection?:HomeHarnessConnection;serverId:string;workspace:string|null}) {
  const key=JSON.stringify([homeSessionRefKey(sessionRef),connection?.binding_id,connection?.workspace_binding_id,connection?.agent_id,serverId,workspace]);
  const [read,setRead]=useState<{key:string;context:HomeSessionContext|null;error:string}>({key,context:null,error:''});
  useEffect(()=>{
    const abort=new AbortController();setRead({key,context:null,error:''});
    void resolveHomeTarget(homeApi,homeSessionTarget(sessionRef),{server_id:serverId,workspace_id:workspace},abort.signal)
      .then(value=>{
        if(abort.signal.aborted)return;
        if(!value.available||!value.session_context)throw new Error('Unavailable');
        if(connection)assertHarnessSessionContext(value.session_context,connection,sessionRef);
        setRead({key,context:value.session_context,error:''});
      }).catch(()=>{if(!abort.signal.aborted)setRead({key,context:null,error:'This exact session is unavailable. No replacement was selected.'});});
    return()=>abort.abort();
  },[key]);
  if(read.key!==key||!read.context)return <p role={read.key===key&&read.error?'alert':'status'}>{read.key===key&&read.error?read.error:'Revalidating session…'}</p>;
  return <HomeSessionInspection context={read.context} nativeTerminal/>;
}

function HarnessConsoleChoice({card,state,onOpen,onMore}: {card:HarnessCard;state:HomeState;onOpen:(ref:HomeSessionRef)=>void;onMore:()=>void}) {
  const page=state.harnessSessions[card.id];
  const sessions=page?.items??card.sessions??[];
  const live=sessions.filter(ref=>ref.lifecycle_state==='READY');
  const loading=state.harnessLoading!==null;
  const unique=initialHarnessSession({...card,sessions,sessions_total:page?.total??card.sessions_total,
    has_more_sessions:page?.has_more??card.has_more_sessions,sessions_cursor:page?page.next_cursor:card.sessions_cursor});
  useEffect(()=>{if(unique?.lifecycle_state==='READY')onOpen(unique);},[unique,onOpen]);
  if(loading&&!page||unique?.lifecycle_state==='READY') return <p role="status">Opening console…</p>;
  return <>
    {!live.length&&<p role="status">No active console is available.</p>}
    {live.length>0&&<ul className="space-y-2">{live.map((ref,index)=><li key={homeSessionRefKey(ref)}>
      <button type="button" className="btn btn-secondary w-full justify-start" onClick={()=>onOpen(ref)}>
        {ref.title||`Session ${index+1}`}
      </button>
    </li>)}</ul>}
    {(page?.has_more??card.has_more_sessions)&&<button type="button" className="btn btn-secondary mt-3" disabled={loading} onClick={onMore}>Show more sessions</button>}
  </>;
}


function HarnessActivityPanel({cardId,state,onMore,onRefresh,onEntry,onSessions,onRefreshSessions,onRequests,onRefreshRequests,onRequest,renderSession,onConnection,requestsIntent=false}: {
  cardId:string|null;state:HomeState;onMore:()=>void;onRefresh:()=>void;onEntry:(entry:HomeHarnessChild)=>void;
  onSessions:()=>void;onRefreshSessions:()=>void;onRequests:()=>void;onRefreshRequests:()=>void;onRequest:(item:HomeHarnessRequest)=>void;requestsIntent?:boolean;
  renderSession:(ref:HomeSessionRef)=>ReactNode;onConnection:(target:HomeTarget)=>void;
}) {
  const transition=useAgentModalTransition();
  const [selected,setSelected]=useState<HomeSessionRef|null>(null),touched=useRef(false);
  const root=state.harnessBoard;
  const card=root&&cardId!==null?Object.values(root.columns).flatMap(column=>column.items).filter(item=>item.kind==='harness').find(item=>item.id===cardId):null;
  const page=cardId===null?state.harnessUnlinked??root?.unlinked:state.harnessChildren[cardId];
  const items=page?.items??card?.children??[],total=page?.total??card?.children_total;
  const more=page?.has_more??card?.has_more_children;
  const denied=['forbidden','disabled'].includes(state.status);
  const changed=state.hasPendingUpdate||state.staleSections.length>0;
  const sessionsPage=cardId?state.harnessSessions[cardId]:null;
  const refs=sessionsPage?.items??card?.sessions??[];
  const sessionsTotal=sessionsPage?.total??card?.sessions_total;
  const moreSessions=sessionsPage?.has_more??card?.has_more_sessions;
  const requestsPage=cardId?state.harnessRequests[cardId]:null;
  const requests=requestsPage?.items??card?.requests_preview??card?.blocking_requests??[];
  const optionRefs=selected&&!refs.some(ref=>homeSessionRefKey(ref)===homeSessionRefKey(selected))?[selected,...refs]:refs;
  useEffect(()=>{
    if(touched.current||!card)return;
    const unique=initialHarnessSession({...card,sessions:refs,sessions_total:sessionsTotal??null,
      has_more_sessions:moreSessions??true,sessions_cursor:sessionsPage?.next_cursor??card.sessions_cursor});
    if(unique){setSelected(unique);touched.current=true;}
  },[card,refs,sessionsTotal,moreSessions,sessionsPage]);
  return <section aria-label="Harness activity" className="space-y-4">
    <h3 className="font-semibold">{cardId===null?'Other activity':card?.connection.agent_label||'Harness activity'}</h3>
    <p className="text-sm text-surface-500">{requestsIntent?'Choose an action to review its current canonical context.':`${total===null||total===undefined?'Activity total unknown':`${total} linked activities`}. Select an activity to review its canonical context.`}</p>
    {changed&&<p role="status">Updates are available. Opening an activity revalidates its exact context.</p>}
    {!requestsIntent&&card&&root?.presentation_version===2&&<section aria-label="Session context" className="space-y-2">
      {sessionsTotal!==0&&<label className="block text-sm">Choose a session
        <select data-modal-passive className="block border rounded p-2 w-full bg-transparent" value={selected?homeSessionRefKey(selected):''} disabled={denied}
          onChange={event=>{const ref=optionRefs.find(r=>homeSessionRefKey(r)===event.target.value)??null;
            transition(()=>{touched.current=true;setSelected(ref);});}}>
          <option value="">Choose a session</option>{optionRefs.map((ref,index)=><option key={homeSessionRefKey(ref)} value={homeSessionRefKey(ref)}>{homeSessionOptionLabel(ref,index)}</option>)}
        </select></label>}
      {sessionsTotal===0&&<p>No session is currently available. Connection context and retained activity are still available.</p>}
      {sessionsTotal===null||sessionsTotal===undefined?<p className="text-sm">Session coverage is unknown. No session was selected automatically.</p>:null}
      <button type="button" className="underline" disabled={denied||state.harnessLoading!==null} onClick={onRefreshSessions}>Refresh sessions</button>
      {moreSessions&&<button type="button" className="btn btn-secondary" disabled={denied||state.harnessLoading!==null} onClick={onSessions}>Load more sessions</button>}
      <button type="button" className="underline" disabled={denied} onClick={()=>transition(()=>onConnection(card.target))}>View connection</button>
      {selected&&renderSession(selected)}
    </section>}
    {(requestsIntent||requests.length>0)&&<section aria-label="Pending actions" className="space-y-2">
      <h4 className="font-medium">Pending actions</h4>
      {!requests.length&&<p role="status">{state.harnessLoading!==null?'Revalidating actions…':requestsPage?.total===0?'No pending actions.':'Action coverage is unavailable. Refresh to try again.'}</p>}
      <button type="button" className="underline" disabled={denied||state.harnessLoading!==null} onClick={onRefreshRequests}>Refresh actions</button>
      {requests.map(item=><HomeHarnessSignalCard key={item.id} item={item} blocked={denied} onOpen={()=>transition(()=>onRequest(item))}/>)}
      {(requestsPage?requestsPage.has_more:card?.operational_status?.has_more_pending_requests)&&<button type="button" className="btn btn-secondary" disabled={denied||state.harnessLoading!==null} onClick={onRequests}>Load more actions</button>}
    </section>}
    {!requestsIntent&&<><button type="button" className="btn btn-secondary" disabled={denied||state.harnessLoading!==null} onClick={onRefresh}>Refresh activity</button>
    <ul className="space-y-3">{items.map(entry=><li key={entry.id} className="border-b pb-3" data-home-activity={entry.id}>
      {!isUntitledHomeWork(entry)&&<p className="font-medium break-words">{entry.title}</p>}<p className="text-sm">{homeStateLabel(entry.display_state)}</p>
      {entry.shared_reference&&<p className="text-xs text-surface-500">Shared activity</p>}
      {entry.target?<button type="button" className={"underline "+homeFocus} disabled={denied} onClick={()=>transition(()=>onEntry(entry))}>{homeTargetActionLabel(entry.target)}</button>:
        <p className="text-sm text-surface-500">Exact context unavailable.</p>}
    </li>)}</ul>
    {more&&<button type="button" className="btn btn-secondary" disabled={denied||state.harnessLoading!==null} onClick={onMore}>{state.harnessLoading!==null?'Loading activity…':'Load more activity'}</button>}</>}
  </section>;
}
export function isFirstHarnessBoardEmpty(page:HomeBoard|HomeHarnessBoard|null,stale=false,filtered=false):boolean{
  if(!page||stale||filtered||!isQuietBoard(page))return false;
  const count=page.inventory?.connections;
  return ['work','results','attention','connections','sessions','correlations','external'].every(key=>['ready','disabled'].includes(page.source_status[key]))&&
    page.source_status.connections==='ready'&&!page.scope.agent_id&&!page.scope.state&&!page.scope.harness&&!page.scope.host&&
    count?.unit==='connections'&&count.total_is_exact===true&&count.value===0;
}
export function OperationalHome({workspace, workspaces, identityKey, refreshTick, latestEvent, streamStatus, onNavigate,
  onAttentionChanged, onSetupAgent, onWorkspaceChange, registerLeaveGuard, attentionReturn, presentationVersion:offeredPresentationVersion=1}: {
  workspace: string; workspaces: WorkspaceListItem[]; identityKey: string; refreshTick: number;
  latestEvent: HomeInvalidation | null; streamStatus: HomeStreamStatus;
  onNavigate: (view: 'Agents' | 'Attention' | 'Graph' | 'Meta-harness') => void; onAttentionChanged: () => void; onSetupAgent: () => void;
  registerLeaveGuard: (guard: (() => boolean) | null) => void;
  attentionReturn: {current: HomeAttentionReturn | null};
  onWorkspaceChange?:(id:string)=>void;
  presentationVersion?:1|2;
}) {
  const [listFocused,setListFocused]=useState(false);
  const [panel, setPanel] = useState<Panel | null>(null);
  const [manualPause, setManualPause] = useState(false);
  const [restoringFocus,setRestoringFocus]=useState(false);
  const [presentationVersion,setPresentationVersion]=useState(offeredPresentationVersion);
  // A late capability reply must not unmount a canonical form or replace a
  // board being read. Adopt it after the context, manual pause and focus release.
  // Identity, workspace and authority changes still clear the controller normally.
  useEffect(()=>{if(!panel&&!manualPause&&!listFocused&&!restoringFocus)setPresentationVersion(offeredPresentationVersion);},
    [panel,manualPause,listFocused,restoringFocus,offeredPresentationVersion]);
  const home = useHomeOverview({family:'harness',workspace: workspace === 'all' ? null : workspace, identityKey,
    holdOrder:listFocused,latestEvent,streamStatus,presentationVersion});
  const {state,refresh,pause,apply,holdOrder,loadBoardColumn,loadHarnessChildren,refreshHarnessChildren,loadHarnessRequests,loadHarnessSessions,refreshHarnessSessions,refreshHarnessRequests}=home;
  const snapshot = state.harnessBoard;
  const [notice, setNotice] = useState('');
  const heading = useRef<HTMLHeadingElement>(null), focusReturn = useRef<HTMLElement | null>(null);
  const focusEntry=useRef<{attribute:string;id:string}|null>(null);
  const scrollReturn = useRef<{element: HTMLElement; top: number} | null>(null);
  const initialTarget = useRef(false);
  const [announcement, setAnnouncement] = useState('');
  const announced = useRef<{generation: number; ids: Set<string>}>({generation:-1, ids:new Set()});
  const announceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (announced.current.generation !== state.generation) {
      if (announceTimer.current !== null) {clearTimeout(announceTimer.current);announceTimer.current = null;}
      setAnnouncement('');
    }
    if (!snapshot) return;
    const ids = homeEntriesAnnouncementIds(state);
    const previous = announced.current;
    announced.current = {generation:state.generation,ids};
    if (previous.generation !== state.generation) {setAnnouncement('');return;}
    if ([...ids].some(id => !previous.ids.has(id)) && announceTimer.current === null) {
      // A separate mutation makes the next coalesced batch audible even when
      // its business summary is the same as the preceding batch.
      setAnnouncement('');
      announceTimer.current = setTimeout(() => {announceTimer.current=null;setAnnouncement('Home updated. New work, attention or results are available.');}, 2000);
    }
  }, [snapshot,state.entryChildren, state.generation]);
  useEffect(() => () => {if (announceTimer.current) clearTimeout(announceTimer.current);}, []);
  useEffect(()=>{setListFocused(false);},[state.generation]);
  useEffect(() => {if (refreshTick) refresh();}, [refreshTick, refresh]);
  useEffect(() => {pause(manualPause || !!panel);}, [manualPause, !!panel, pause, presentationVersion]);
  const close = useCallback(() => {
    setRestoringFocus(true);
    // Commit the cached board with the closing panel before restoring focus.
    // Otherwise a later pause effect can remove the refocused old card.
    pause(manualPause);
    setPanel(null);
    attentionReturn.current = null;
    const url = new URL(window.location.href);url.searchParams.delete('home_target');window.history.replaceState(null, '', url);
    window.requestAnimationFrame(() => {
      const scroll = scrollReturn.current;if (scroll?.element.isConnected) scroll.element.scrollTop = scroll.top;
      const identity=focusEntry.current;
      const moved=identity?Array.from(document.querySelectorAll<HTMLElement>(`[${identity.attribute}]`)).find(el=>el.getAttribute(identity.attribute)===identity.id):null;
      const destination=focusReturn.current?.isConnected?focusReturn.current:moved?.querySelector<HTMLElement>('[data-home-entry-open],button:not(:disabled),a[href]')??heading.current;
      try {destination?.focus({preventScroll:true});} finally {setRestoringFocus(false);}
    });
  }, [manualPause,pause,attentionReturn]);
  const dismiss = useCallback(() => {
    const dialog = document.querySelector<HTMLDialogElement>('[data-testid="home-detail"]');
    dialog?.dispatchEvent(new Event('cancel', {cancelable:true}));
    return !dialog;
  }, []);
  useEffect(() => {
    registerLeaveGuard(panel ? dismiss : null);
    const beforeUnload = (event: BeforeUnloadEvent) => {event.preventDefault();event.returnValue = '';};
    if (panel) window.addEventListener('beforeunload', beforeUnload);
    return () => {registerLeaveGuard(null);window.removeEventListener('beforeunload', beforeUnload);};
  }, [panel, dismiss, registerLeaveGuard]);
  const rememberAttention = (selection: HomeEntrySelection['attention'], target?: HomeTarget) => {
    attentionReturn.current = selection && snapshot ? {
      attentionId: selection.item.attention_id, action: selection.action, serverId: snapshot.server_id,
      workspace: selection.item.workspace_id, viewWorkspace: workspace, identityKey, target,
    } : null;
  };
  const selectPanel = (next: Panel) => {
    const selection = next.kind === 'attention' ? next : next.kind === 'target' ? next.entrySelection?.attention : undefined;
    rememberAttention(selection, next.kind === 'target' ? next.target : undefined);
    setPanel(next);
  };
  const open = (next: Panel) => {
    if (panel) {dismiss();return;}
    focusReturn.current = document.activeElement as HTMLElement | null;
    const row=focusReturn.current?.closest<HTMLElement>('[data-home-entry],[data-home-harness],[data-home-signal]');
    const attribute=['data-home-entry','data-home-harness','data-home-signal'].find(name=>row?.hasAttribute(name));
    focusEntry.current=attribute?{attribute,id:row!.getAttribute(attribute)!}:null;
    const scroll = heading.current?.closest('main');if (scroll) scrollReturn.current = {element:scroll, top:scroll.scrollTop};
    if (next.kind === 'target') {
      const url = new URL(window.location.href);url.searchParams.set('home_target', encodeHomeTarget(next.target));window.history.pushState(null, '', url);
    }
    selectPanel(next);
  };
  useEffect(() => {
    const pop = () => {
      if (panel) {dismiss();return;}
      const raw = new URL(window.location.href).searchParams.get('home_target');
      const target = raw && decodeHomeTarget(raw);if (target) setPanel({kind:'target', target, console:target.kind==='session'});
    };
    window.addEventListener('popstate', pop);return () => window.removeEventListener('popstate', pop);
  }, [panel, dismiss]);
  useEffect(() => {
    if (initialTarget.current || !snapshot) return;initialTarget.current = true;
    const selection = attentionReturn.current;
    attentionReturn.current = null;
    if (selection && selection.identityKey !== identityKey && selection.serverId === snapshot.server_id && selection.viewWorkspace === workspace) {
      setPanel({kind:'restored_attention', selection});
      return;
    }
    const raw = new URL(window.location.href).searchParams.get('home_target');if (!raw) return;
    const target = decodeHomeTarget(raw);
    if (target) setPanel({kind:'target', target, console:target.kind==='session'});else setNotice('The saved detail reference is invalid. No record was selected.');
  }, [snapshot, attentionReturn, identityKey, workspace]);
  useEffect(() => {
    if (state.status === 'forbidden' || state.status === 'disabled') {
      attentionReturn.current = null;setPanel(null);setNotice('');
    }
  }, [state.status, attentionReturn]);
  const changed = () => {refresh();onAttentionChanged();};
  const selectEntry=(entry:HomeHarnessChild,target:HomeTarget,attention?:HomeEntrySelection['attention'])=>{
    const selection:HomeEntrySelection={groupId:entry.group_id,revision:entry.entry_revision,entry,
      filters:{workspace_id:workspace==='all'?undefined:workspace,quick:'all'},attention,presentationVersion};
    return {kind:'target' as const,target,entrySelection:selection};
  };
  const eventPanel=(event:HomeHarnessEvent,connection?:HomeHarnessConnection):Panel|null=>{
    const action=event.attention?primaryAttentionAction(event.attention):null;
    if(event.attention&&action){
      return event.target?selectEntry(event.entry,event.target,{item:event.attention,action}):{kind:'attention',item:event.attention,action};
    }
    const session=event.kind==='work'?homeWorkConsoleTarget(event.entry,event.target):homeConsoleTarget(event.target);
    if(session&&(event.kind==='work'||event.kind==='session'))return {kind:'target',target:session,connection,console:true};
    return event.target?selectEntry(event.entry,event.target):null;
  };
  const requestPanel=(item:HomeHarnessRequest):Panel|null=>{
    const action=primaryAttentionAction(item.request);if(!action)return null;
    return item.entry.target?selectEntry(item.entry,item.entry.target,{item:item.request,action}):{kind:'attention',item:item.request,action};
  };
  const openHarness=(card:HarnessCard)=>{
    const ref=presentationVersion===2?initialHarnessSession(card):null;
    if(ref?.lifecycle_state==='READY'){open({kind:'target',target:homeSessionTarget(ref),connection:card.connection,console:true});return;}
    if(presentationVersion===2){open({kind:'console-choice',cardId:card.id});loadHarnessSessions(card.id);return;}
    open({kind:'harness',cardId:card.id});
  };
  const consoleTarget=panel?.kind==='target'&&panel.console&&panel.target.kind==='session'?panel.target:null;
  const consoleCard=panel?.kind==='console-choice'&&snapshot?Object.values(snapshot.columns).flatMap(column=>column.items)
    .find((card):card is HarnessCard=>card.kind==='harness'&&card.id===panel.cardId):null;
  const blocked=state.loading||!!state.entryLoading||!!state.boardLoading||state.paused||state.hasPendingUpdate||state.staleSections.length>0||!snapshot||
    !['ready','partial'].includes(snapshot.status)||['forbidden','disabled','error'].includes(state.status);
  const readBlocked=!snapshot||['forbidden','disabled'].includes(state.status);
  const snapshotStale=state.hasPendingUpdate||state.staleSections.length>0||state.status==='stale'||state.status==='error';
  const projectLabel=(id:string)=>{const index=workspaces.findIndex(item=>item.workspace_id===id);return index>=0?workspaceDisplayName(workspaces[index],index):id;};
  const quiet=isQuietBoard(snapshot,blocked);
  const filtered=false;
  const firstHarness=isFirstHarnessBoardEmpty(snapshot,blocked||state.status!=='ready',filtered);
  return <PageContainer testId="operational-home" className="space-y-5">
    <header className="flex flex-wrap justify-between items-start gap-3">
      <div><h1 ref={heading} tabIndex={-1} className="text-2xl font-semibold">Home</h1>
        {presentationVersion===1&&<p className="text-sm text-surface-500 mt-1">Follow work, questions and deliveries.</p>}
        <p className="text-sm text-surface-500 mt-2">Follow each harness below. Open an activity to see its exact context, or add a harness to this project.</p></div>
      <div className="flex flex-wrap gap-2">
        <button type="button" className={`btn btn-primary ${homeFocus}`} onClick={()=>open({kind:'request'})} disabled={firstHarness||!snapshot||['forbidden','disabled'].includes(state.status)}><Plus size={15}/> {presentationVersion===2?'Ask for work or chat':'New request'}</button>
        <button type="button" className={`btn btn-secondary ${homeFocus}`} onClick={refresh} disabled={state.loading||!!state.entryLoading}><RefreshCw size={15}/> Refresh</button>
        <button type="button" className={`btn btn-secondary ${homeFocus}`} aria-pressed={manualPause} onClick={()=>setManualPause(value=>!value)}>{manualPause?<Play size={15}/>:<Pause size={15}/>} {manualPause?'Resume display':'Pause display'}</button>
      </div>
    </header>
    <HomeProjectCard workspace={workspace} workspaces={workspaces} onChange={onWorkspaceChange} onConnect={onSetupAgent} setupLabel="Add harness" connectDisabled={state.status==='forbidden'} compact={presentationVersion===2}/>
    {snapshot&&<HomeSummaryCards summary={snapshot.summary} stale={snapshotStale} operationalSummary={presentationVersion===2?snapshot.operational_summary:undefined}/>}
    {state.paused&&<p role="status" className="text-sm text-surface-500">Display updates paused. Agents keep running; decisions require a fresh canonical review.</p>}
    {state.hasPendingUpdate&&<div role="status" className="flex flex-wrap gap-3 items-center text-sm"><span>Updates are available.</span><button type="button" className="btn btn-secondary" disabled={!!panel} onClick={()=>{setManualPause(false);apply();}}>Apply updates</button></div>}
    {state.notice&&<p role="status" className="text-sm">{state.notice}</p>}
    <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{announcement}</p>
    {notice&&<p role="alert" className="text-sm">{notice}</p>}
    {state.error&&<p role="alert" className="text-sm">{/^[A-Z0-9_]+$/.test(state.error)?'Tracking information could not be refreshed. Try Refresh or narrow the filters.':state.error}</p>}
    {presentationVersion===1&&<p className="text-xs text-surface-500">Active work, items needing you and retained results stay visible together. Each card keeps its linked sessions, questions and deliveries.</p>}
    {!snapshot&&<p role="status" className="panel p-5">{state.status==='forbidden'?'Operator access is required. Protected Home data has been cleared.':state.status==='disabled'?'Operational Home is disabled.':state.status==='error'?'Home information is unavailable. Refresh to try again.':'Loading follow-up…'}</p>}
    {snapshot&&<>
      {(snapshot.server_attention.total===null||snapshot.server_attention.total>0)&&<div role="status" className="rounded-lg border border-surface-200 dark:border-surface-700 p-3 text-sm">
        <button type="button" className={`underline ${homeFocus}`} onClick={()=>onNavigate('Attention')}>{snapshot.server_attention.total===null?'Server attention unavailable':`${snapshot.server_attention.total} Server attention ${snapshot.server_attention.total===1?'item':'items'}`}. Open Needs attention</button>
        <p className="text-xs text-surface-500 mt-1">All projects and Server. These incidents are separate from project work.</p>
      </div>}
        {snapshot.status!=='ready'&&<p role="status" className="text-sm text-surface-500">Some information is incomplete or unavailable. Totals may be unknown; refresh before acting.</p>}
        {snapshot.coverage.result_tracking!=='ready'&&<p className="text-xs text-surface-500">Some result viewing states are untracked. Those deliveries are labeled recent.</p>}
        {quiet&&<div className="panel p-5">{firstHarness?<>
          <p className="font-medium">Connect a collaborator</p>
          <p className="text-sm text-surface-500 mt-2">Connect a collaborator to start work in this project.</p>
        </>:<><p className="font-medium">No matching activity{filtered?' for these filters':''}.</p><p className="text-sm text-surface-500 mt-2">Use New request to ask for work, or Connect or resume to find an existing connection or add a collaborator.</p></>}</div>}
    </>}
    <HomeBoardCards board={snapshot} blocked={blocked} loading={state.boardLoading} initialLoading={state.status==='loading'||state.loading} onMore={loadBoardColumn} countLabel={{active:'harnesses',needs_you:'items',results:'deliveries'}}
      onFocus={()=>{holdOrder(true);setListFocused(true);}} onBlur={inside=>{if(!inside){holdOrder(false);setListFocused(false);}}}
      renderEntry={card=>card.kind==='harness'?<HomeHarnessCard key={card.id} card={card} column={snapshot!.columns.needs_you.items.some(item=>item.id===card.id)?'needs_you':'active'}
        blocked={readBlocked} onActivity={()=>openHarness(card)} showProject={workspace==='all'} projectLabel={card.connection.workspace_label||projectLabel(card.connection.workspace_id)} stale={snapshotStale}
        onRequest={item=>{const next=requestPanel(item);if(next)open(next);}}
        onRequests={()=>{open({kind:'harness',cardId:card.id,requests:true});loadHarnessRequests(card.id);}}
        onEvent={event=>{const next=eventPanel(event,card.connection);if(next)open(next);}}/>:
        <HomeHarnessSignalCard key={card.id} item={card} blocked={readBlocked} showProject={workspace==='all'} projectLabel={projectLabel(card.entry.workspace_id)} onOpen={()=>{
          if(card.kind==='request'){
            const next=requestPanel(card);if(next)open(next);
          }else if(card.result?.detail_target)open(selectEntry(card.entry,card.result.detail_target));
          else if(card.report){const action=primaryAttentionAction(card.report);if(action)open({kind:'attention',item:card.report,action});}
        }}/>}
      footer={snapshot&&(snapshot.unlinked.total===null||snapshot.unlinked.total>0)&&<div className="text-sm rounded-lg border p-3" data-testid="home-unlinked">
      <p>{snapshot.unlinked.total===null?'Some activity has incomplete connection tracking':`${snapshot.unlinked.total} activities without a proven registered connection`}. These are separate from harness cards.</p>
      <button type="button" className={"underline "+homeFocus} disabled={readBlocked} onClick={()=>open({kind:'harness',cardId:null})}>View other activity</button>
      </div>}/>
    {panel&&snapshot&&<AgentActionModal title={consoleTarget?'Harness console':panel.kind==='console-choice'?'Open console':panel.kind==='request'?'New request':panel.kind==='attention'?'Canonical attention record':panel.kind==='target'&&panel.continuation?'Continue this exact session':'Activity detail'} onClose={close} presentation={consoleTarget?'terminal':'drawer'} wide testId="home-detail">
      {panel.kind==='request'?<HomeNewRequest workspace={workspace} workspaces={workspaces} onChanged={changed}/>
        :panel.kind==='console-choice'?consoleCard?<HarnessConsoleChoice card={consoleCard} state={state}
          onMore={()=>loadHarnessSessions(consoleCard.id)} onOpen={ref=>{
            const target=homeSessionTarget(ref),url=new URL(window.location.href);
            url.searchParams.set('home_target',encodeHomeTarget(target));window.history.pushState(null,'',url);
            selectPanel({kind:'target',target,connection:consoleCard.connection,console:true});
          }}/>:<p role="status">This console is unavailable.</p>
        :panel.kind==='harness'?<HarnessActivityPanel key={panel.cardId??'unlinked'} cardId={panel.cardId} state={state}
          requestsIntent={panel.requests}
          onRefresh={()=>refreshHarnessChildren(panel.cardId)} onMore={()=>loadHarnessChildren(panel.cardId)}
          onSessions={()=>{if(panel.cardId)loadHarnessSessions(panel.cardId);}} onRequests={()=>{if(panel.cardId)loadHarnessRequests(panel.cardId);}}
          onRefreshSessions={()=>{if(panel.cardId)refreshHarnessSessions(panel.cardId);}}
          onRefreshRequests={()=>{if(panel.cardId)refreshHarnessRequests(panel.cardId);}}
          onRequest={item=>{const next=requestPanel(item);if(next)selectPanel(next);}}
          onConnection={target=>selectPanel({kind:'target',target})}
          renderSession={ref=>{const card=Object.values(snapshot.columns).flatMap(c=>c.items).find((c):c is HarnessCard=>c.kind==='harness'&&c.id===panel.cardId);
            return card?<HarnessSessionInspection key={homeSessionRefKey(ref)} sessionRef={ref} connection={card.connection} serverId={snapshot.server_id} workspace={card.connection.workspace_id}/>:<p>Connection context unavailable.</p>;}}
          onEntry={entry=>{if(entry.target){const target=entry.kind==='work'?homeWorkConsoleTarget(entry,entry.target):homeConsoleTarget(entry.target);
            selectPanel(target?{kind:'target',target,console:true}:selectEntry(entry,entry.target));}}}/>
        :panel.kind==='attention'?<HomeAttentionInspection item={panel.item} action={panel.action} onClose={close} onChanged={changed}/>
          :panel.kind==='restored_attention'?<HomeRestoredAttention selection={panel.selection} onClose={close} onChanged={changed}/>
          :panel.kind==='target'&&consoleTarget?<HarnessSessionInspection key={homeSessionRefKey(consoleTarget)} sessionRef={consoleTarget}
            connection={panel.connection} serverId={snapshot.server_id} workspace={workspace==='all'?null:workspace}/>:
            <HomeInspection target={panel.target} serverId={snapshot.server_id} workspace={workspace==='all'?null:workspace} continuation={panel.continuation} entrySelection={panel.entrySelection}
              onAttentionSelected={selection=>rememberAttention(selection,panel.target)} onClose={close} onChanged={changed}/>}
    </AgentActionModal>}
  </PageContainer>;
}
