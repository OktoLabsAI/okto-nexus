import {useCallback, useEffect, useRef, useState} from 'react';
import {Pause, Play, Plus, RefreshCw} from 'lucide-react';
import type {WorkspaceListItem} from '../../api';
import type {AttentionAction, AttentionOccurrence} from '../../attentionTypes';
import type {HomeTarget,HomeEntryPage,HomeEntryGroup,HomeBoard,HomeHarnessBoard,HomeHarnessChild,HomeHarnessEvent} from '../../homeTypes';
import {primaryAttentionAction} from '../../attentionPresentation';
import {type HomeInvalidation,type HomeStreamStatus} from '../../homeController';
import {useHomeOverview} from '../../hooks/useHomeOverview';
import {decodeHomeTarget, encodeHomeTarget} from '../../homeNavigation';
import {homeStateLabel} from '../../homePresentation';
import {homeTargetActionLabel} from '../../homePresentation';
import type {HomeState} from '../../homeController';
import {AgentActionModal} from '../AgentActionModal';
import {PageContainer} from '../PageContainer';
import {HomeProjectCard,HomeSummaryCards} from './HomeContextCards';
import {HomeNewRequest, HomeInspection, HomeAttentionInspection} from './HomeInspection';
import {homeFocus,homeEntriesAnnouncementIds,isQuietEntries} from './HomeCards';
import {HomeBoardCards,isQuietBoard} from './HomeBoardCards';
import {HomeHarnessCard,HomeHarnessSignalCard} from './HomeHarnessCard';
import type {HomeEntrySelection} from '../../homeEntryInspection';

type Panel = {kind: 'request'} | {kind: 'target'; target: HomeTarget; continuation?: boolean;entrySelection?:HomeEntrySelection}
  | {kind: 'attention'; item: AttentionOccurrence; action: AttentionAction}
  | {kind:'harness';cardId:string|null};
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
function HarnessActivityPanel({cardId,state,onMore,onRefresh,onEntry}: {
  cardId:string|null;state:HomeState;onMore:()=>void;onRefresh:()=>void;onEntry:(entry:HomeHarnessChild)=>void;
}) {
  const root=state.harnessBoard;
  const card=root&&cardId!==null?Object.values(root.columns).flatMap(column=>column.items).filter(item=>item.kind==='harness').find(item=>item.id===cardId):null;
  const page=cardId===null?state.harnessUnlinked??root?.unlinked:state.harnessChildren[cardId];
  const items=page?.items??card?.children??[],total=page?.total??card?.children_total;
  const more=page?.has_more??card?.has_more_children;
  const denied=['forbidden','disabled'].includes(state.status);
  const changed=state.hasPendingUpdate||state.staleSections.length>0;
  return <section aria-label="Harness activity" className="space-y-4">
    <h3 className="font-semibold">{cardId===null?'Other activity':card?.connection.agent_label||'Harness activity'}</h3>
    <p className="text-sm text-surface-500">{total===null||total===undefined?'Activity total unknown':`${total} linked activities`}. Select an activity to review its canonical context.</p>
    {changed&&<p role="status">Updates are available. Opening an activity revalidates its exact context.</p>}
    <button type="button" className="btn btn-secondary" disabled={denied||state.harnessLoading!==null} onClick={onRefresh}>Refresh activity</button>
    <ul className="space-y-3">{items.map(entry=><li key={entry.id} className="border-b pb-3" data-home-activity={entry.id}>
      <p className="font-medium break-words">{entry.title}</p><p className="text-sm">{homeStateLabel(entry.display_state)}</p>
      {entry.shared_reference&&<p className="text-xs text-surface-500">Shared activity</p>}
      {entry.target?<button type="button" className={"underline "+homeFocus} disabled={denied} onClick={()=>onEntry(entry)}>{homeTargetActionLabel(entry.target)}</button>:
        <p className="text-sm text-surface-500">Exact context unavailable.</p>}
    </li>)}</ul>
    {more&&<button type="button" className="btn btn-secondary" disabled={denied||state.harnessLoading!==null} onClick={onMore}>{state.harnessLoading!==null?'Loading activity…':'Load more activity'}</button>}
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
  onAttentionChanged, onSetupAgent, onWorkspaceChange, registerLeaveGuard,presentationVersion=1}: {
  workspace: string; workspaces: WorkspaceListItem[]; identityKey: string; refreshTick: number;
  latestEvent: HomeInvalidation | null; streamStatus: HomeStreamStatus;
  onNavigate: (view: 'Agents' | 'Attention' | 'Graph' | 'Meta-harness') => void; onAttentionChanged: () => void; onSetupAgent: () => void;
  registerLeaveGuard: (guard: (() => boolean) | null) => void;
  onWorkspaceChange?:(id:string)=>void;
  presentationVersion?:1|2;
}) {
  const [listFocused,setListFocused]=useState(false);
  const home = useHomeOverview({family:'harness',workspace: workspace === 'all' ? null : workspace, identityKey,
    holdOrder:listFocused,latestEvent,streamStatus,presentationVersion});
  const {state,refresh,pause,apply,holdOrder,loadBoardColumn,loadHarnessChildren,refreshHarnessChildren}=home;
  const snapshot = state.harnessBoard;
  const [panel, setPanel] = useState<Panel | null>(null), [manualPause, setManualPause] = useState(false);
  const [notice, setNotice] = useState('');
  const heading = useRef<HTMLHeadingElement>(null), focusReturn = useRef<HTMLElement | null>(null);
  const focusEntry=useRef<string|null>(null);
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
  useEffect(() => {pause(manualPause || !!panel);}, [manualPause, !!panel, pause]);
  const close = useCallback(() => {
    setPanel(null);
    const url = new URL(window.location.href);url.searchParams.delete('home_target');window.history.replaceState(null, '', url);
    window.requestAnimationFrame(() => {
      const scroll = scrollReturn.current;if (scroll?.element.isConnected) scroll.element.scrollTop = scroll.top;
      const moved=focusEntry.current?Array.from(document.querySelectorAll<HTMLElement>('[data-home-entry]')).find(el=>el.dataset.homeEntry===focusEntry.current):null;
      const destination=focusReturn.current?.isConnected?focusReturn.current:moved?.querySelector<HTMLElement>('[data-home-entry-open]')??moved??heading.current;
      destination?.focus({preventScroll:true});
    });
  }, []);
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
  const open = (next: Panel) => {
    if (panel) {dismiss();return;}
    focusReturn.current = document.activeElement as HTMLElement | null;
    focusEntry.current=focusReturn.current?.closest<HTMLElement>('[data-home-entry]')?.dataset.homeEntry??null;
    const scroll = heading.current?.closest('main');if (scroll) scrollReturn.current = {element:scroll, top:scroll.scrollTop};
    if (next.kind === 'target') {
      const url = new URL(window.location.href);url.searchParams.set('home_target', encodeHomeTarget(next.target));window.history.pushState(null, '', url);
    }
    setPanel(next);
  };
  useEffect(() => {
    const pop = () => {
      if (panel) {dismiss();return;}
      const raw = new URL(window.location.href).searchParams.get('home_target');
      const target = raw && decodeHomeTarget(raw);if (target) setPanel({kind:'target', target});
    };
    window.addEventListener('popstate', pop);return () => window.removeEventListener('popstate', pop);
  }, [panel, dismiss]);
  useEffect(() => {
    if (initialTarget.current || !snapshot) return;initialTarget.current = true;
    const raw = new URL(window.location.href).searchParams.get('home_target');if (!raw) return;
    const target = decodeHomeTarget(raw);
    if (target) setPanel({kind:'target', target});else setNotice('The saved detail reference is invalid. No record was selected.');
  }, [snapshot]);
  useEffect(() => {if (state.status === 'forbidden' || state.status === 'disabled') {setPanel(null);setNotice('');}}, [state.status]);
  const changed = () => {refresh();onAttentionChanged();};
  const selectEntry=(entry:HomeHarnessChild,target:HomeTarget,attention?:HomeEntrySelection['attention'])=>{
    const selection:HomeEntrySelection={groupId:entry.group_id,revision:entry.entry_revision,entry,
      filters:{workspace_id:workspace==='all'?undefined:workspace,quick:'all'},attention};
    return {kind:'target' as const,target,entrySelection:selection};
  };
  const eventPanel=(event:HomeHarnessEvent):Panel|null=>{
    const action=event.attention?primaryAttentionAction(event.attention):null;
    if(event.attention&&action){
      return event.target?selectEntry(event.entry,event.target,{item:event.attention,action}):{kind:'attention',item:event.attention,action};
    }
    return event.target?selectEntry(event.entry,event.target):null;
  };
  const blocked=state.loading||!!state.entryLoading||!!state.boardLoading||state.paused||state.hasPendingUpdate||state.staleSections.length>0||!snapshot||
    !['ready','partial'].includes(snapshot.status)||['forbidden','disabled','error'].includes(state.status);
  const readBlocked=!snapshot||['forbidden','disabled'].includes(state.status);
  const quiet=isQuietBoard(snapshot,blocked);
  const filtered=false;
  const firstHarness=isFirstHarnessBoardEmpty(snapshot,blocked||state.status!=='ready',filtered);
  return <PageContainer testId="operational-home" className="space-y-5">
    <header className="flex flex-wrap justify-between items-start gap-3">
      <div><h1 ref={heading} tabIndex={-1} className="text-2xl font-semibold">Home</h1>
        <p className="text-sm text-surface-500 mt-1">Follow work, questions and deliveries.</p>
        <p className="text-sm text-surface-500 mt-2">Follow each harness below. Open an activity to see its exact context, or add a harness to this project.</p></div>
      <div className="flex flex-wrap gap-2">
        <button type="button" className={`btn btn-primary ${homeFocus}`} onClick={()=>open({kind:'request'})} disabled={firstHarness||!snapshot||['forbidden','disabled'].includes(state.status)}><Plus size={15}/> New request</button>
        <button type="button" className={`btn btn-secondary ${homeFocus}`} onClick={refresh} disabled={state.loading||!!state.entryLoading}><RefreshCw size={15}/> Refresh</button>
        <button type="button" className={`btn btn-secondary ${homeFocus}`} aria-pressed={manualPause} onClick={()=>setManualPause(value=>!value)}>{manualPause?<Play size={15}/>:<Pause size={15}/>} {manualPause?'Resume display':'Pause display'}</button>
      </div>
    </header>
    <HomeProjectCard workspace={workspace} workspaces={workspaces} onChange={onWorkspaceChange} onConnect={onSetupAgent} setupLabel="Add harness" connectDisabled={state.status==='forbidden'}/>
    {snapshot&&<HomeSummaryCards summary={snapshot.summary} stale={blocked}/>}
    {state.paused&&<p role="status" className="text-sm text-surface-500">Display updates paused. Agents keep running; decisions require a fresh canonical review.</p>}
    {state.hasPendingUpdate&&<div role="status" className="flex flex-wrap gap-3 items-center text-sm"><span>Updates are available.</span><button type="button" className="btn btn-secondary" disabled={!!panel} onClick={()=>{setManualPause(false);apply();}}>Apply updates</button></div>}
    {state.notice&&<p role="status" className="text-sm">{state.notice}</p>}
    <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{announcement}</p>
    {notice&&<p role="alert" className="text-sm">{notice}</p>}
    {state.error&&<p role="alert" className="text-sm">{/^[A-Z0-9_]+$/.test(state.error)?'Tracking information could not be refreshed. Try Refresh or narrow the filters.':state.error}</p>}
    <p className="text-xs text-surface-500">Active work, items needing you and retained results stay visible together. Each card keeps its linked sessions, questions and deliveries.</p>
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
        blocked={readBlocked} onActivity={()=>open({kind:'harness',cardId:card.id})}
        onEvent={event=>{const next=eventPanel(event);if(next)open(next);}}/>:
        <HomeHarnessSignalCard key={card.id} item={card} blocked={readBlocked} onOpen={()=>{
          if(card.kind==='request'){
            const action=primaryAttentionAction(card.request);if(!action)return;
            open(card.entry.target?selectEntry(card.entry,card.entry.target,{item:card.request,action}):{kind:'attention',item:card.request,action});
          }else if(card.result?.detail_target)open(selectEntry(card.entry,card.result.detail_target));
          else if(card.report){const action=primaryAttentionAction(card.report);if(action)open({kind:'attention',item:card.report,action});}
        }}/>}
      footer={snapshot&&(snapshot.unlinked.total===null||snapshot.unlinked.total>0)&&<div className="text-sm rounded-lg border p-3" data-testid="home-unlinked">
      <p>{snapshot.unlinked.total===null?'Some activity has incomplete connection tracking':`${snapshot.unlinked.total} activities without a proven registered connection`}. These are separate from harness cards.</p>
      <button type="button" className={"underline "+homeFocus} disabled={readBlocked} onClick={()=>open({kind:'harness',cardId:null})}>View other activity</button>
      </div>}/>
    {panel&&snapshot&&<AgentActionModal title={panel.kind==='request'?'New request':panel.kind==='attention'?'Canonical attention record':panel.kind==='target'&&panel.continuation?'Continue this exact session':'Activity detail'} onClose={close} presentation="drawer" wide testId="home-detail">
      {panel.kind==='request'?<HomeNewRequest workspace={workspace} workspaces={workspaces} onChanged={changed}/>
        :panel.kind==='harness'?<HarnessActivityPanel cardId={panel.cardId} state={state} onRefresh={()=>refreshHarnessChildren(panel.cardId)} onMore={()=>loadHarnessChildren(panel.cardId)} onEntry={entry=>{if(entry.target)setPanel(selectEntry(entry,entry.target));}}/>
        :panel.kind==='attention'?<HomeAttentionInspection item={panel.item} action={panel.action} onClose={close} onChanged={changed}/>
          :<HomeInspection target={panel.target} serverId={snapshot.server_id} workspace={workspace==='all'?null:workspace} continuation={panel.continuation} entrySelection={panel.entrySelection} onClose={close} onChanged={changed}/>}
    </AgentActionModal>}
  </PageContainer>;
}
