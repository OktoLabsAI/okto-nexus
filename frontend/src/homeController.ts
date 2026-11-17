import type { HomeApi } from './homeApi';
import type { HomeActivity, HomeAgent, HomeFeedEvent, HomeFilters, HomeOverview, HomePage, HomePageSection,
  HomeResult, HomeSection, HomeSectionName, HomeQuickFilter, HomeEntryQuery, HomeEntryPage, HomeEntryGroup,
  HomeEntry, HomeSessionRef, HomeEntryPartition,HomeBoard,HomeBoardPage,HomeBoardColumn,HomeBoardMetadata,HomeBoardSlice,HomeBoardEntry } from './homeTypes';
import type { ExternalObservation } from './observationTypes';
import type { AttentionOccurrence } from './attentionTypes';
import type {HomeHarnessBoard,HomeHarnessBoardPage,HomeHarnessCard,HomeHarnessChild,HomeHarnessChildrenPage,HomeHarnessSlice,HomeHarnessConnection} from './homeTypes';
import {validHomeOperationalStatus,validHomeOperationalSummary,validHomePlacement,validHomeDeliverySemantics} from './homeStateContracts';

export interface HomeContext {
  workspace: string | null; identityKey: string; origin?: string; enabled?: boolean; visible?: boolean;
  agent_id?: string; state?: string;
  family?: 'legacy'|'entries'|'board'|'harness'; quick?:HomeQuickFilter; harness?:string; host?:string;
  holdOrder?:boolean;
  presentationVersion?:1|2;
}
export interface HomeEntryJob {partition:HomeEntryPartition;groupId?:string;entryId?:string;boardRevision?:string|null;entryRevision?:string|null}
interface HomeBoardJob {column:HomeBoardColumn;revision:string;entryRevision:string|null;cursor:string}
interface HomeHarnessJob {cardId:string|null;revision:string;entryRevision:string|null;cursor:string|null;reset?:boolean;retry?:number}
export const homeBoardColumns:readonly HomeBoardColumn[]=['active','needs_you','results'];
export const homeEntryPageKey=(groupId:string,entryId:string)=>JSON.stringify([groupId,entryId]);
interface HomeEntryCache {
  entries:HomeEntryPage<HomeEntryGroup>|null;
  board:HomeBoard|null;
  harnessBoard:HomeHarnessBoard|null;
  harnessChildren:Record<string,HomeHarnessChildrenPage>;
  harnessUnlinked:HomeHarnessChildrenPage|null;
  entryChildren:Record<string,HomeEntryPage<HomeEntry>>;
  entrySessions:Record<string,HomeEntryPage<HomeSessionRef>>;
  entryAttention:Record<string,HomeEntryPage<AttentionOccurrence>>;
  entryResults:Record<string,HomeEntryPage<HomeResult>>;
}
export interface HomeInvalidation { type: string; event_id?: number; id?: string | number }
export type HomeStreamStatus = 'live' | 'connecting' | 'reconnecting' | 'off';
export interface HomeState extends HomeEntryCache {
  snapshot: HomeOverview | null; activity: HomeSection<HomeFeedEvent> | null;
  status: 'loading' | 'ready' | 'stale' | 'error' | 'forbidden' | 'disabled';
  loading: boolean; loadingMore: HomePageSection | null; paused: boolean; hasPendingUpdate: boolean;
  error: string | null; notice?:string|null; staleSections: HomeSectionName[]; generation: number;
  scopeKey: string | null;
  entryLoading:HomeEntryJob|null;
  boardLoading:HomeBoardColumn|null;
  harnessLoading:string|null;
}
export interface HomeDependencies {
  api: HomeApi; now(): number; setTimeout(callback: () => void, milliseconds: number): unknown;
  clearTimeout(handle: unknown): void; onChange?(state: HomeState): void;
}
const emptyEntryCache=():HomeEntryCache=>({entries:null,board:null,harnessBoard:null,harnessChildren:{},harnessUnlinked:null,entryChildren:{},entrySessions:{},entryAttention:{},entryResults:{}});
export const initialHomeState = (): HomeState => ({ ...emptyEntryCache(),entryLoading:null,boardLoading:null,harnessLoading:null,snapshot: null, activity: null, status: 'loading',
  loading: false, loadingMore: null, paused: false, hasPendingUpdate: false, error: null, notice:null, staleSections: [], generation: 0, scopeKey: null });
/** Observation timestamps/cursors are not a visible change. Validity and source
 * states remain in the signature; the Server must revise those on expiry. */
export function homeSnapshotSignature(value:unknown):string {
  const clean=(item:unknown,root=false):unknown=>{
    if(Array.isArray(item))return item.map(value=>clean(value));
    if(!item||typeof item!=='object')return item;
    const object=item as Record<string,unknown>;
    const metadata=root||('id'in object&&'group_id'in object)||('items'in object&&('status'in object||'partition'in object));
    return Object.fromEntries(Object.keys(object).sort().filter(key=>!(metadata&&
      ['generated_at','as_of','next_refresh_at','event_cursor','event_low_watermark','snapshot_id'].includes(key)))
      .map(key=>[key,clean(object[key])]));
  };
  return JSON.stringify(clean(value,true));
}
const sections = ['work', 'attention', 'results', 'agents', 'external_activity', 'server_attention'] as const;
/** Hints only. The fallback/TTL still covers sources without a workspace event. */
export function homeInvalidatedSections(type: string): HomeSectionName[] {
  if (/^observation[.:-]/.test(type)) return ['external_activity', 'agents', 'attention', 'server_attention', 'activity'];
  if (/^attention[.:-]/.test(type)) return ['attention', 'server_attention', 'results', 'work'];
  if (/^message[.:-]/.test(type)) return ['work', 'agents', 'activity'];
  if (/^handoff[.:-]/.test(type)) return ['work', 'results', 'attention', 'server_attention', 'agents', 'activity'];
  if (/^(execution|runtime|native|approval)[.:-]/.test(type)) return ['work', 'results', 'attention', 'server_attention', 'agents', 'activity'];
  if (/^(agent|session|authorization|operator|stream)[.:-]/.test(type) || ['reset', 'gap', 'reconnect'].includes(type))
    return [...sections, 'activity'];
  return [];
}
const info = (value: unknown): { status?: number; code?: string; name?: string } =>
  value && typeof value === 'object' ? value : {};
export const homeContextKey = (c: HomeContext): string => JSON.stringify([c.origin ?? '', c.identityKey,
  c.workspace === 'all' ? null : c.workspace || null, c.agent_id ?? '', c.state ?? '',c.family??'legacy',c.quick??'',c.harness??'',c.host??'',c.presentationVersion??1]);
const usable = (s: HomeSection<unknown>) => s.status === 'ready' || s.status === 'partial';
function retained<T>(next: HomeSection<T>, previous?: HomeSection<T>): HomeSection<T> {
  if (next.status === 'unavailable' && previous) return { ...next, items: previous.items,
    as_of: previous.as_of, next_cursor: null, has_more: false };
  if (next.status === 'ready' && previous?.status === 'ready' && next.revision &&
      next.revision === previous.revision && previous.items.length > next.items.length)
    return { ...next, items: [...next.items, ...previous.items.slice(next.items.length)],
      next_cursor: previous.next_cursor, has_more: previous.has_more };
  return next;
}
function append<T>(previous: HomeSection<T>, next: HomeSection<T>, key: (item: T) => string): HomeSection<T> {
  const seen = new Set(previous.items.map(key));
  return { ...next, items: [...previous.items, ...next.items.filter(item => !seen.has(key(item)))] };
}

/** No stream, effects or credentials: one serialized, generation-bound GET queue. */
export class HomeController {
  private state = initialHomeState();
  private context: HomeContext = { workspace: null, identityKey: '', enabled: false, visible: false };
  private generation = 0;
  private active: { generation: number; abort: AbortController } | null = null;
  private disposed = false;
  private blocked = false;
  private refreshPending = false;
  private morePending: HomePageSection | null = null;
  private entryPending:HomeEntryJob|null=null;
  private boardPending:HomeBoardJob|null=null;
  private harnessPending:HomeHarnessJob|null=null;
  private harnessReadPending:{cardId:string|null;retry:number}|null=null;
  private entryCache=emptyEntryCache();
  private timer: unknown;
  private poll: unknown;
  private lastStarted = -Infinity;
  private snapshotStarted = 0;
  private dirtySince: number | null = null;
  private latest: HomeOverview | null = null;
  private latestActivity: HomeSection<HomeFeedEvent> | null = null;
  private activityDirty = false;
  private resetPages = false;
  private stream: HomeStreamStatus = 'off';
  private eventId: string | null = null;
  constructor(private deps: HomeDependencies) {}
  getState(): HomeState { return this.state; }
  private emit(patch: Partial<HomeState> = {}): void {
    this.state = { ...this.state, ...patch, generation: this.generation, scopeKey: homeContextKey(this.context) };
    if (!this.disposed) this.deps.onChange?.(this.state);
  }
  private cancel(name: 'timer' | 'poll'): void {
    if (this[name] !== undefined) this.deps.clearTimeout(this[name]);
    this[name] = undefined;
  }
  private allowed(): boolean { return !this.disposed && !this.blocked && this.context.enabled !== false && !!this.context.identityKey; }
  private filters(): HomeFilters {
    return { ...(this.context.workspace && this.context.workspace !== 'all' ? { workspace_id: this.context.workspace } : {}),
      ...(this.context.agent_id ? { agent_id: this.context.agent_id } : {}), ...(this.context.state ? { state: this.context.state } : {}) };
  }
  private entriesFamily():boolean{return this.context.family==='entries';}
  private boardFamily():boolean{return this.context.family==='board';}
  private harnessFamily():boolean{return this.context.family==='harness';}
  private trackingFamily():boolean{return this.entriesFamily()||this.boardFamily()||this.harnessFamily();}
  private hasSnapshot():boolean{return this.harnessFamily()?!!this.state.harnessBoard:this.boardFamily()?!!this.state.board:this.entriesFamily()?!!this.state.entries:!!this.state.snapshot;}
  private entryFilters():HomeEntryQuery{return {...this.filters(),...(this.context.quick?{quick:this.context.quick}:{}),
    ...(this.context.harness?{harness:this.context.harness}:{}),...(this.context.host?{host:this.context.host}:{})};}
  configure(next: HomeContext): void {
    if (this.disposed) return;
    const normalized = { ...next, workspace: next.workspace === 'all' ? null : next.workspace };
    const changed = homeContextKey(normalized) !== homeContextKey(this.context) || next.enabled !== this.context.enabled;
    const becameVisible = next.visible !== false && this.context.visible === false;
    this.context = normalized;
    if (changed || next.enabled === false || !next.identityKey) {
      this.generation++;
      this.active?.abort.abort(); // Keep it owned until finally; no concurrent replacement.
      this.cancel('timer'); this.cancel('poll');
      this.latest = null; this.latestActivity = null; this.activityDirty = false; this.eventId = null;
      this.entryCache=emptyEntryCache();this.entryPending=null;this.boardPending=null;this.harnessPending=null;this.harnessReadPending=null;
      this.resetPages = false;
      this.refreshPending = false; this.morePending = null; this.dirtySince = null;
      this.blocked = false;
      this.emit({ ...initialHomeState(), status: this.allowed() ? 'loading' : 'disabled' });
      if (this.allowed()) this.refresh();
    } else if (becameVisible && this.allowed()) {
      if (this.active) {
        this.generation++;
        this.active.abort.abort(); // Retain ownership until finally, then read after wake.
      }
      this.emit({ status: this.hasSnapshot() ? 'stale' : 'loading', staleSections: [...sections, 'activity'] });
      this.refresh();
    }
    else this.schedulePoll();
  }
  clear(): void {
    this.generation++; this.blocked = true; this.active?.abort.abort();
    this.cancel('timer'); this.cancel('poll'); this.refreshPending = false; this.morePending = null;
    this.latest = null; this.latestActivity = null; this.activityDirty = false;
    this.entryCache=emptyEntryCache();this.entryPending=null;this.boardPending=null;this.harnessPending=null;this.harnessReadPending=null;
    this.resetPages = false;
    this.emit({ ...initialHomeState(), status: 'forbidden' });
  }
  dispose(): void { this.clear(); this.disposed = true; }
  refresh(): void {
    if (!this.allowed()) return;
    this.refreshPending = true; this.morePending = null;this.entryPending=null;this.boardPending=null;this.harnessPending=null; this.dirtySince = null;
    this.cancel('poll'); this.schedule(0);
  }
  pause(paused = !this.state.paused): void {
    this.emit({ paused });
    if (!paused) this.apply();
  }
  holdOrder(holding:boolean):void{this.context={...this.context,holdOrder:holding};}
  apply(): void {
    if(!this.allowed())return;
    if(this.trackingFamily()){this.emit({...this.entryCache,hasPendingUpdate:false,
      status:(this.harnessFamily()?this.entryCache.harnessBoard:this.boardFamily()?this.entryCache.board:this.entryCache.entries)?.status==='ready'&&!this.refreshPending?'ready':'stale',staleSections:this.refreshPending?[...sections]:[]});return;}
    this.emit({ snapshot: this.latest, activity: this.latestActivity, hasPendingUpdate: false });
  }
  onStreamStatus(status: HomeStreamStatus): void {
    if (status === this.stream) return;
    this.stream = status;
    if (!this.allowed()) return;
    if (this.context.visible === false) { this.refreshPending = true; this.schedulePoll(); }
    else this.refresh(); // Reconnect/error never constitutes data freshness.
  }
  invalidate(event?: HomeInvalidation): void {
    if (!this.allowed()) return;
    const affected = event ? this.trackingFamily()&&/^(connection|binding|executor|workspace|policy|guardrail|settings)[.:-]/.test(event.type)
      ? [...sections] : homeInvalidatedSections(event.type) : [...sections];
    if (event) {
      const id = event.event_id ?? event.id;
      const key = id === undefined ? null : `${id}:${event.type}`;
      if (key && key === this.eventId) return;
      this.eventId = key;
      if (!affected.length) return;
    }
    this.emit({ status: this.hasSnapshot() ? 'stale' : 'loading',
      staleSections: [...new Set([...this.state.staleSections, ...affected])] });
    this.refreshPending = true; this.morePending = null;this.entryPending=null;this.boardPending=null;this.harnessPending=null;
    if (this.context.visible === false) { this.schedulePoll(); return; }
    this.dirtySince ??= this.deps.now();
    this.schedule(Math.max(0, Math.min(350, this.dirtySince + 500 - this.deps.now())));
  }
  loadMore(section: HomePageSection): void {
    if(this.trackingFamily())return;
    if (!this.allowed() || this.context.visible === false || this.state.paused || this.refreshPending || this.active) return;
    const current = section === 'activity' ? this.latestActivity : this.latest?.[section === 'external' ? 'external_activity' : section];
    if (current && !(section === 'activity' && this.activityDirty) && (!usable(current) || !current.next_cursor)) return;
    if (!current && section !== 'activity') return;
    this.morePending = section; this.schedule(0);
  }
  loadEntries():void{this.loadEntryPage({partition:'groups'});}
  loadGroupChildren(groupId:string):void{this.loadEntryPage({partition:'children',groupId});}
  loadEntrySessions(groupId:string,entryId:string):void{this.loadEntryPage({partition:'sessions',groupId,entryId});}
  loadEntryAttention(groupId:string,entryId:string):void{this.loadEntryPage({partition:'attention',groupId,entryId});}
  loadEntryResults(groupId:string,entryId:string):void{this.loadEntryPage({partition:'results',groupId,entryId});}
  loadBoardColumn(column:HomeBoardColumn):void{
    const root=this.harnessFamily()?this.entryCache.harnessBoard:this.entryCache.board;
    if(!(this.boardFamily()||this.harnessFamily())||!root?.revision||!this.allowed()||this.context.visible===false||this.state.paused||
      this.state.hasPendingUpdate||this.state.staleSections.length||this.refreshPending||this.active)return;
    const page=root.columns[column];
    if(!['ready','partial'].includes(root.status)||!page.has_more||!page.next_cursor)return;
    this.entryPending=null;this.harnessPending=null;this.boardPending={column,revision:root.revision,entryRevision:root.entry_revision,cursor:page.next_cursor};this.schedule(0);
  }
  loadHarnessChildren(cardId:string|null):void{
    const root=this.entryCache.harnessBoard;
    if(!this.harnessFamily()||!root?.revision||!this.allowed()||this.context.visible===false)return;
    const currentPage=cardId===null?this.entryCache.harnessUnlinked:this.entryCache.harnessChildren[cardId];
    if(this.refreshPending||this.active||!currentPage&&(this.state.hasPendingUpdate||this.state.staleSections.length)){
      this.refreshHarnessChildren(cardId);return;
    }
    const card=cardId===null?null:homeBoardColumns.flatMap(name=>root.columns[name].items).filter(item=>item.kind==='harness').find(item=>item.id===cardId);
    const page=cardId===null?this.entryCache.harnessUnlinked??root.unlinked:this.entryCache.harnessChildren[cardId]??
      (card?{next_cursor:card.children_cursor,has_more:card.has_more_children}:null);
    if(!page?.has_more||!page.next_cursor)return;
    this.entryPending=null;this.boardPending=null;
    this.harnessPending={cardId,revision:currentPage?.revision??root.revision,entryRevision:currentPage?.entry_revision??root.entry_revision,cursor:page.next_cursor};this.schedule(0);
  }
  /** Revalidate this relation, not the displayed board or another session. */
  refreshHarnessChildren(cardId:string|null):void{
    if(!this.harnessFamily()||!this.allowed()||this.context.visible===false)return;
    this.harnessReadPending={cardId,retry:0};this.schedule(0);
  }
  private loadEntryPage(job:HomeEntryJob):void{
    if(this.harnessFamily()||!this.trackingFamily()||!this.allowed()||this.context.visible===false||this.state.paused||this.state.hasPendingUpdate||this.refreshPending||this.active)return;
    if(this.boardFamily()&&(job.partition==='groups'||job.partition==='children'))return;
    const previous=this.previousEntryPage(job);
    if(!previous||!['ready','partial'].includes(previous.status)||!previous.next_cursor)return;
    this.boardPending=null;this.entryPending=this.boardFamily()?{...job,boardRevision:this.entryCache.board?.revision,entryRevision:this.entryCache.board?.entry_revision}:job;this.schedule(0);
  }
  private schedule(delay: number): void {
    this.cancel('timer');
    if (!this.allowed() || this.active) return;
    const wait = Math.max(delay, this.lastStarted + 1000 - this.deps.now());
    this.timer = this.deps.setTimeout(() => { this.timer = undefined; void this.pump(); }, Math.max(0, wait));
  }
  private schedulePoll(): void {
    this.cancel('poll');
    if (!this.allowed()) return;
    let delay = this.context.visible === false ? 60000 : 15000;
    const entries=this.harnessFamily()?this.entryCache.harnessBoard:this.boardFamily()?this.entryCache.board:this.entryCache.entries;
    if(this.trackingFamily()&&entries&&this.context.visible!==false&&entries.next_refresh_at){
      const interval=Date.parse(entries.next_refresh_at)-Date.parse(entries.generated_at);
      if(Number.isFinite(interval))delay=Math.min(delay,Math.max(1000,this.snapshotStarted+interval-this.deps.now()));
    }
    if (this.latest && this.context.visible !== false) {
      for (const name of sections) {
        const section = this.latest[name];
        if (section.next_refresh_at && section.as_of) {
          const interval = Date.parse(section.next_refresh_at) - Date.parse(this.latest.generated_at);
          if (Number.isFinite(interval)) delay = Math.min(delay, Math.max(1000, this.snapshotStarted + interval - this.deps.now()));
        }
      }
    }
    this.poll = this.deps.setTimeout(() => this.refresh(), delay);
  }
  private validScope(value: { scope: HomeOverview['scope']; server_id: string }): boolean {
    const filters = this.filters();
    return value.scope.workspace_id === (filters.workspace_id ?? null) &&
      (value.scope.agent_id ?? '') === (filters.agent_id ?? '') && (value.scope.state ?? '') === (filters.state ?? '') &&
      (!this.latest || value.server_id === this.latest.server_id);
  }
  private previousEntryPage(job:HomeEntryJob):HomeEntryPage<unknown>|null{
    if(this.boardFamily()){
      const root=this.entryCache.board;if(!root)return null;
      const entry=homeBoardColumns.flatMap(name=>root.columns[name].items).find(item=>item.group_id===job.groupId&&item.id===job.entryId);
      if(!entry)return null;
      const base:Omit<HomeEntryPage<unknown>,'items'|'total'|'total_is_exact'|'has_more'|'next_cursor'>={
        version:1,scope:root.scope,server_id:root.server_id,generated_at:root.generated_at,snapshot_id:root.entry_revision,
        revision:root.entry_revision,partition:job.partition,group_id:entry.group_id,entry_id:entry.id,
        event_cursor:root.event_cursor,event_low_watermark:root.event_low_watermark,source_status:root.source_status,
        coverage:root.coverage,summary:root.summary,inventory:root.inventory,server_attention:root.server_attention,
        status:root.status,as_of:root.as_of,next_refresh_at:root.next_refresh_at};
      const key=homeEntryPageKey(entry.group_id,entry.id);
      if(job.partition==='sessions')return this.entryCache.entrySessions[key]??{...base,items:entry.sessions,total:entry.sessions_total,
        total_is_exact:entry.sessions_total!==null,has_more:entry.has_more_sessions,next_cursor:entry.sessions_cursor};
      if(job.partition==='attention')return this.entryCache.entryAttention[key]??{...base,items:entry.attention_preview,total:entry.attention_total,
        total_is_exact:entry.attention_total!==null,has_more:entry.has_more_attention,next_cursor:entry.attention_cursor};
      if(job.partition==='results')return this.entryCache.entryResults[key]??{...base,items:entry.results_preview,total:entry.results_total,
        total_is_exact:entry.results_total!==null,has_more:entry.has_more_results,next_cursor:entry.results_cursor};
      return null;
    }
    const root=this.entryCache.entries;if(!root)return null;
    if(job.partition==='groups')return root;
    const group=root.items.find(item=>item.id===job.groupId);if(!group)return null;
    const base={...root,partition:job.partition,group_id:group.id,entry_id:job.entryId??null};
    if(job.partition==='children')return this.entryCache.entryChildren[group.id]??{...base,items:group.children,
      total:group.children_total,total_is_exact:group.children_total!==null,has_more:group.has_more_children,next_cursor:group.children_cursor};
    const entry=(this.entryCache.entryChildren[group.id]?.items??group.children).find(item=>item.id===job.entryId);if(!entry)return null;
    const key=homeEntryPageKey(group.id,entry.id);
    if(job.partition==='sessions')return this.entryCache.entrySessions[key]??{...base,items:entry.sessions,total:entry.sessions_total,
      total_is_exact:entry.sessions_total!==null,has_more:entry.has_more_sessions,next_cursor:entry.sessions_cursor};
    if(job.partition==='attention')return this.entryCache.entryAttention[key]??{...base,items:entry.attention_preview??[],total:entry.attention_total,
      total_is_exact:entry.attention_total!==null,has_more:entry.has_more_attention,next_cursor:entry.attention_cursor};
    return this.entryCache.entryResults[key]??{...base,items:entry.results_preview??[],total:entry.results_total,
      total_is_exact:entry.results_total!==null,has_more:entry.has_more_results,next_cursor:entry.results_cursor};
  }
  private validEntryScope(value:HomeEntryPage<unknown>,job:HomeEntryJob):boolean{
    const expected={...this.entryFilters(),...(this.boardFamily()?{quick:'all' as const}:{})},scope=value.scope,
      root=this.boardFamily()?this.entryCache.board:this.entryCache.entries;
    return value.version===1&&scope.workspace_id===(expected.workspace_id??null)&&
      (scope.agent_id??'')===(expected.agent_id??'')&&(scope.state??'')===(expected.state??'')&&
      scope.quick===(expected.quick??'active')&&scope.include_recent_results===(expected.quick===undefined)&&
      (scope.harness??'')===(expected.harness??'')&&(scope.host??'')===(expected.host??'')&&
      value.partition===job.partition&&value.group_id===(job.groupId??null)&&value.entry_id===(job.entryId??null)&&
      (!root||root.server_id===value.server_id);
  }
  private publishEntries(notice:string|null=null):void{
    const value=this.entryCache.entries;
    const prior=this.state.entries;
    const order=(page:HomeEntryPage<HomeEntryGroup>)=>JSON.stringify(page.items.map(group=>[group.id,group.children.map(entry=>entry.id)]));
    const loaded=Object.keys(this.state.entryChildren).length+Object.keys(this.state.entrySessions).length+
      Object.keys(this.state.entryAttention).length+Object.keys(this.state.entryResults).length>0;
    const held=!!(this.context.holdOrder&&prior&&value&&(order(prior)!==order(value)||loaded&&prior.revision!==value.revision));
    const stale=held||this.refreshPending||!value||value.status!=='ready';
    const changed=homeSnapshotSignature(value)!==homeSnapshotSignature(prior);
    this.emit({...(changed&&(this.state.paused||held)?{hasPendingUpdate:true}:{...this.entryCache,hasPendingUpdate:false}),
      status:stale?'stale':'ready',error:null,notice,staleSections:this.refreshPending?[...sections]:[]});
  }
  private async readEntries(job:HomeEntryJob|null,signal:AbortSignal,current:()=>boolean):Promise<string|null>{
    if(this.boardFamily()&&(!job||job.boardRevision!==this.entryCache.board?.revision||job.entryRevision!==this.entryCache.board?.entry_revision))return null;
    const previous=job?this.previousEntryPage(job):null;
    const query={...this.entryFilters(),...(this.boardFamily()?{quick:'all' as const}:{}),limit:10,preview:3,...(previous?.next_cursor?{cursor:previous.next_cursor}:{})};
    let value:HomeEntryPage<unknown>;
    if(!job||job.partition==='groups')value=await this.deps.api.entries(query,signal);
    else if(job.partition==='children')value=await this.deps.api.entryChildren(job.groupId!,query,signal);
    else if(job.partition==='sessions')value=await this.deps.api.entrySessions(job.groupId!,job.entryId!,query,signal);
    else if(job.partition==='attention')value=await this.deps.api.entryAttention(job.groupId!,job.entryId!,query,signal);
    else value=await this.deps.api.entryResults(job.groupId!,job.entryId!,query,signal);
    if(!current())return null;
    if(!this.validEntryScope(value,job??{partition:'groups'}))throw Error('HOME_SCOPE_CHANGED');
    if(value.status==='forbidden')throw Object.assign(Error('Home entries forbidden'),{status:403});
    if(job&&previous?.revision!==value.revision)throw Object.assign(Error('Home entries changed'),{status:409});
    if(job&&!['ready','partial'].includes(value.status))throw Error('HOME_ENTRIES_UNAVAILABLE');
    const appendPage=<T>(before:HomeEntryPage<T>,after:HomeEntryPage<T>,key:(item:T)=>string):HomeEntryPage<T>=>{
      const seen=new Set(before.items.map(key));return {...after,items:[...before.items,...after.items.filter(item=>!seen.has(key(item)))]};};
    if(!job){
      const before=this.entryCache.entries,next=value as HomeEntryPage<HomeEntryGroup>;
      this.snapshotStarted=this.lastStarted;
      if(next.status==='unavailable'&&before){this.entryCache={...this.entryCache,entries:{...next,items:before.items,as_of:before.as_of,next_cursor:null,has_more:false}};return null;}
      const same=!this.resetPages&&before&&before.revision===next.revision;
      if(!same)this.entryCache=emptyEntryCache();
      this.entryCache={...this.entryCache,entries:same&&before.items.length>next.items.length
        ?{...next,items:[...next.items,...before.items.slice(next.items.length)],next_cursor:before.next_cursor,has_more:before.has_more}:next};
      this.resetPages=false;
      return before&&!same?'Updated tracking changed pagination. Showing the first page.':null;
    }
    if(!previous)return null;
    if(job.partition==='groups')this.entryCache={...this.entryCache,entries:appendPage(previous as HomeEntryPage<HomeEntryGroup>,value as HomeEntryPage<HomeEntryGroup>,item=>item.id)};
    else if(job.partition==='children')this.entryCache={...this.entryCache,entryChildren:{...this.entryCache.entryChildren,
      [job.groupId!]:appendPage(previous as HomeEntryPage<HomeEntry>,value as HomeEntryPage<HomeEntry>,item=>item.id)}};
    else{
      const key=homeEntryPageKey(job.groupId!,job.entryId!);
      if(job.partition==='sessions')this.entryCache={...this.entryCache,entrySessions:{...this.entryCache.entrySessions,
        [key]:appendPage(previous as HomeEntryPage<HomeSessionRef>,value as HomeEntryPage<HomeSessionRef>,item=>JSON.stringify([item.server_id,item.executor_id,item.session_id]))}};
      if(job.partition==='attention')this.entryCache={...this.entryCache,entryAttention:{...this.entryCache.entryAttention,
        [key]:appendPage(previous as HomeEntryPage<AttentionOccurrence>,value as HomeEntryPage<AttentionOccurrence>,item=>item.attention_id)}};
      if(job.partition==='results')this.entryCache={...this.entryCache,entryResults:{...this.entryCache.entryResults,
        [key]:appendPage(previous as HomeEntryPage<HomeResult>,value as HomeEntryPage<HomeResult>,item=>item.id)}};
    }
    return null;
  }
  private validBoardScope(value:HomeBoardMetadata):boolean{
    const expected=this.entryFilters(),scope=value.scope,root=this.entryCache.board;
    return value.version===1&&scope.workspace_id===(expected.workspace_id??null)&&
      (scope.agent_id??'')===(expected.agent_id??'')&&(scope.state??'')===(expected.state??'')&&
      scope.quick==='all'&&scope.include_recent_results===false&&
      (scope.harness??'')===(expected.harness??'')&&(scope.host??'')===(expected.host??'')&&
      !!value.server_id&&(!root||value.server_id===root.server_id);
  }
  private validBoardSlice(page:HomeBoardSlice,value:HomeBoardMetadata,seen:Set<string>):boolean{
    if(!page||!Array.isArray(page.items)||typeof page.total_is_exact!=='boolean'||typeof page.has_more!=='boolean'||
      !(page.total===null||Number.isInteger(page.total)&&page.total>=page.items.length)||
      page.total_is_exact&&page.total===null||
      (page.has_more?typeof page.next_cursor!=='string'||!page.next_cursor:page.next_cursor!==null))return false;
    for(const entry of page.items){
      if(typeof entry.id!=='string'||!entry.id||seen.has(entry.id)||typeof entry.group_id!=='string'||!entry.group_id||
        !value.entry_revision||entry.entry_revision!==value.entry_revision||
        value.scope.workspace_id!==null&&entry.workspace_id!==value.scope.workspace_id||
        entry.target&&entry.target.server_id!==value.server_id)return false;
      seen.add(entry.id);
    }
    return true;
  }
  private resetBoardPages():void{
    const board=this.entryCache.board;
    this.entryCache={...emptyEntryCache(),board:board?{...board,columns:Object.fromEntries(homeBoardColumns.map(name=>
      [name,{...board.columns[name],has_more:false,next_cursor:null}])) as HomeBoard['columns']}:null};
    this.entryPending=null;this.boardPending=null;this.harnessPending=null;
  }
  private publishBoard(notice:string|null=null,appendOnly=false):void{
    const value=this.entryCache.board,prior=this.state.board;if(!value)return;
    const order=(board:HomeBoard)=>JSON.stringify(homeBoardColumns.map(name=>[name,board.columns[name].items.map(entry=>
      [entry.id,entry.sessions.map(ref=>[ref.server_id,ref.executor_id,ref.session_id]),entry.attention_refs,entry.result_refs])]));
    const loaded=Object.keys(this.state.entrySessions).length+Object.keys(this.state.entryAttention).length+Object.keys(this.state.entryResults).length>0;
    const held=!!(!appendOnly&&this.context.holdOrder&&prior&&(order(prior)!==order(value)||loaded&&prior.revision!==value.revision));
    const changed=homeSnapshotSignature(value)!==homeSnapshotSignature(prior);
    this.emit({...(changed&&(this.state.paused||held)?{hasPendingUpdate:true}:{...this.entryCache,hasPendingUpdate:false}),
      status:held||this.refreshPending||value.status!=='ready'?'stale':'ready',error:null,notice,
      staleSections:this.refreshPending?[...sections]:[]});
  }
  private async readBoard(job:HomeBoardJob|null,signal:AbortSignal,current:()=>boolean):Promise<string|null>{
    const before=this.entryCache.board;
    if(job&&(!before||job.revision!==before.revision||job.entryRevision!==before.entry_revision||
      job.cursor!==before.columns[job.column].next_cursor))return null;
    const {quick:_quick,...filters}=this.entryFilters();
    const query={...filters,limit:10,preview:3,...(job?{cursor:job.cursor}:{})};
    const value=job?await this.deps.api.boardColumn(job.column,query,signal):await this.deps.api.board(query,signal);
    if(!current())return null;
    if(!this.validBoardScope(value))throw Error('HOME_BOARD_SCOPE_CHANGED');
    if(value.status==='forbidden')throw Object.assign(Error('Home board forbidden'),{status:403});
    if(value.status==='disabled')throw Object.assign(Error('Home board disabled'),{code:'HOME_DISABLED'});
    if(job){
      const page=value as HomeBoardPage;
      if(page.partition!=='board_column'||page.column!==job.column)throw Error('HOME_BOARD_COLUMN_CHANGED');
      if(page.revision!==job.revision||page.entry_revision!==job.entryRevision)throw Object.assign(Error('Home board changed'),{status:409});
      if(!['ready','partial'].includes(page.status))throw Error('HOME_BOARD_UNAVAILABLE');
      const previous=before!.columns[job.column],seen=new Set(homeBoardColumns.flatMap(name=>before!.columns[name].items.map(entry=>entry.id)));
      if(!this.validBoardSlice(page,page,seen)||previous.total!==page.total||previous.total_is_exact!==page.total_is_exact)
        throw Object.assign(Error('Home board page changed'),{status:409});
      this.entryCache={...this.entryCache,board:{...before!,columns:{...before!.columns,
        [job.column]:{items:[...previous.items,...page.items],total:page.total,total_is_exact:page.total_is_exact,
          has_more:page.has_more,next_cursor:page.next_cursor}}}};
      return null;
    }
    const next=value as HomeBoard,seen=new Set<string>();
    if(next.partition!=='board'||!next.columns||!homeBoardColumns.every(name=>this.validBoardSlice(next.columns[name],next,seen)))throw Error('HOME_BOARD_INVALID');
    this.snapshotStarted=this.lastStarted;
    if(next.status==='unavailable'&&before){
      this.entryCache={...this.entryCache,board:{...next,columns:Object.fromEntries(homeBoardColumns.map(name=>
        [name,{...next.columns[name],items:before.columns[name].items,has_more:false,next_cursor:null}])) as HomeBoard['columns']}};
      return null;
    }
    const same=!this.resetPages&&before&&before.revision===next.revision&&before.entry_revision===next.entry_revision;
    if(!same){this.entryCache=emptyEntryCache();this.entryPending=null;this.boardPending=null;this.harnessPending=null;}
    this.entryCache={...this.entryCache,board:same?{...next,columns:Object.fromEntries(homeBoardColumns.map(name=>{
      const old=before.columns[name],fresh=next.columns[name];
      return [name,old.items.length>fresh.items.length?{...fresh,items:[...fresh.items,...old.items.slice(fresh.items.length)],
        next_cursor:old.next_cursor,has_more:old.has_more}:fresh];
    })) as HomeBoard['columns']}:next};
    this.resetPages=false;
    return before&&!same?'Updated work changed the board. All columns were revalidated.':null;
  }
  private validHarnessScope(value:HomeBoardMetadata):boolean{
    const f=this.entryFilters(),s=value.scope,root=this.entryCache.harnessBoard;
    const version=this.context.presentationVersion??1;
    return value.version===1&&(value.presentation_version??1)===version&&
      (version!==2||validHomeOperationalSummary(value.operational_summary))&&!!value.server_id&&(!root||root.server_id===value.server_id)&&
      s.workspace_id===(f.workspace_id??null)&&(s.agent_id??'')===(f.agent_id??'')&&(s.state??'')===(f.state??'')&&
      (s.harness??'')===(f.harness??'')&&(s.host??'')===(f.host??'')&&s.quick==='all'&&s.include_recent_results===false;
  }
  private validHarnessItems(items:HomeHarnessChild[],meta:HomeBoardMetadata):boolean{
    const seen=new Set<string>();
    return Array.isArray(items)&&items.every(item=>!!item.id&&!seen.has(item.id)&&!!seen.add(item.id)&&!!item.group_id&&
      typeof item.shared_reference==='boolean'&&!!meta.entry_revision&&item.entry_revision===meta.entry_revision&&
      (meta.scope.workspace_id===null||item.workspace_id===meta.scope.workspace_id)&&(!item.target||item.target.server_id===meta.server_id));
  }
  private validHarnessConnection(c:HomeHarnessConnection,meta:HomeBoardMetadata):boolean{
    return !!c&&c.server_id===meta.server_id&&[c.executor_id,c.binding_id,c.workspace_binding_id,c.agent_id,c.workspace_id,c.harness_id]
      .every(v=>typeof v==='string'&&!!v)&&(meta.scope.workspace_id===null||c.workspace_id===meta.scope.workspace_id)&&
      (c.connect_id===undefined||c.connect_id===null||typeof c.connect_id==='string'&&/^[a-z][a-z0-9_-]{0,63}$/.test(c.connect_id));
  }
  private validHarnessSlice(page:HomeHarnessSlice,meta:HomeBoardMetadata,seen:Set<string>,column:HomeBoardColumn):boolean{
    if(!page||!Array.isArray(page.items)||!this.validHarnessPageShape(page))return false;
    return page.items.every(card=>{
      if(!card.id||seen.has(card.id))return false;
      seen.add(card.id);
      if(card.kind==='request'||card.kind==='delivery'){
        if(meta.presentation_version===2&&(card.kind==='request'?
          ![true,false,null].includes(card.blocks_session!)||!['question','approval','decision','verification','unknown'].includes(card.action_kind!):
          !validHomeDeliverySemantics(card.delivery_semantics)||card.delivery_semantics.evidence!==card.completion_evidence||
          !!card.result&&(!validHomeDeliverySemantics(card.result.delivery_semantics)||
            homeSnapshotSignature(card.result.delivery_semantics)!==homeSnapshotSignature(card.delivery_semantics))))return false;
        return column===(card.kind==='request'?'needs_you':'results')&&this.validHarnessItems([card.entry],meta)&&
          Array.isArray(card.harness_refs)&&card.harness_refs.every(ref=>!!ref.card_id&&this.validHarnessConnection(ref.connection,meta))&&
          (card.kind==='request'?!!card.request?.attention_id&&[true,false,null].includes(card.blocks_harness)&&typeof card.notification_visible==='boolean':
            (!!card.result?.id||!!card.report?.attention_id)&&['canonical','reported'].includes(card.completion_evidence));
      }
      if(card.kind!=='harness'||column==='results')return false;
      if(meta.presentation_version===2){
        const status=card.operational_status,refs=card.resume_confirmation_refs;
        if(!validHomeOperationalStatus(status)||!validHomePlacement(card.placement_reason)||!Array.isArray(refs)||
          refs.some(ref=>!ref||!['request_id','operation_id','session_id','stream_epoch'].every(key=>typeof ref[key as keyof typeof ref]==='string'&&!!ref[key as keyof typeof ref])||
            ref.decision_id!==null&&(typeof ref.decision_id!=='string'||!ref.decision_id)))return false;
        const full=card.placement_reason==='human_block_confirmed'&&status.blocking==='full'&&card.blocks_harness===true;
        const awaiting=card.placement_reason==='awaiting_native_confirmation'&&status.awaiting_native_confirmation&&refs.length>0;
        if(column==='needs_you'?!full&&!awaiting:card.blocks_harness===true||status.blocking==='full'||
          !['normal_monitoring','monitoring_unconfirmed'].includes(card.placement_reason))return false;
      }else if(column==='needs_you'&&card.blocks_harness!==true||column==='active'&&card.blocks_harness===true)return false;
      const c=card.connection;
      if(card.id!==card.group_id||!this.validHarnessConnection(c,meta)||!card.target||
        card.target.kind!=='connection'||card.target.server_id!==c.server_id||card.target.workspace_id!==c.workspace_id||
        card.target.executor_id!==c.executor_id||card.target.binding_id!==c.binding_id||card.target.agent_id!==c.agent_id||
        card.context_state!=='registered'||![true,false,null].includes(card.blocks_harness)||!Array.isArray(card.blocking_request_ids)||
        !['waiting_for_user','awaiting_confirmation','working','registered','unknown'].includes(card.activity_state)||
        !Array.isArray(card.blocking_requests)||typeof card.reminder_snoozed!=='boolean'||card.reconnect_available!==false||typeof card.reconnect_reason!=='string'||
        !Array.isArray(card.events_preview)||card.events_preview.length>3||card.events_preview.some(event=>
          !event.id||!this.validHarnessItems([event.entry],meta)||event.entry_id!==event.entry.id||event.group_id!==event.entry.group_id||event.entry_revision!==meta.entry_revision||
          event.target&&event.target.server_id!==meta.server_id)||
        !this.validHarnessItems(card.children,meta)||
        !this.validHarnessPageShape({items:card.children,total:card.children_total,total_is_exact:card.children_total!==null,
          has_more:card.has_more_children,next_cursor:card.children_cursor}))return false;
      return true;
    });
  }
  private validHarnessPageShape(page:{items:unknown[];total:number|null;total_is_exact:boolean;has_more:boolean;next_cursor:string|null}):boolean{
    return Array.isArray(page.items)&&typeof page.total_is_exact==='boolean'&&typeof page.has_more==='boolean'&&
      (page.total===null||Number.isInteger(page.total)&&page.total>=page.items.length)&&(!page.total_is_exact||page.total!==null)&&
      (page.has_more?typeof page.next_cursor==='string'&&!!page.next_cursor:page.next_cursor===null);
  }
  private resetHarnessPages():void{
    const root=this.entryCache.harnessBoard;
    this.entryCache={...emptyEntryCache(),harnessBoard:root?{...root,
      columns:Object.fromEntries(homeBoardColumns.map(name=>[name,{...root.columns[name],has_more:false,next_cursor:null,
        items:root.columns[name].items.map(card=>card.kind==='harness'?{...card,has_more_children:false,children_cursor:null}:card)}])) as HomeHarnessBoard['columns'],
      unlinked:{...root.unlinked,has_more:false,next_cursor:null}}:null};
    this.entryPending=null;this.boardPending=null;this.harnessPending=null;
  }
  private publishHarness(notice:string|null=null,appendOnly=false):void{
    const value=this.entryCache.harnessBoard,prior=this.state.harnessBoard;if(!value)return;
    const order=(root:HomeHarnessBoard)=>JSON.stringify(homeBoardColumns.map(name=>[name,root.columns[name].items.map(card=>
      card.kind==='harness'?[card.id,card.events_preview.map(event=>event.id)]:[card.id,card.kind==='request'?card.request.source_revision:card.result?.id??card.report?.source_revision])]));
    const held=!!(!appendOnly&&this.context.holdOrder&&prior&&(prior.revision!==value.revision||order(prior)!==order(value)));
    const changed=homeSnapshotSignature(value)!==homeSnapshotSignature(prior);
    this.emit({...(changed&&(this.state.paused||held)?{hasPendingUpdate:true}:{...this.entryCache,hasPendingUpdate:false}),
      status:held||this.refreshPending||value.status!=='ready'?'stale':'ready',error:null,notice,staleSections:this.refreshPending?[...sections]:[]});
  }
  private async readHarness(boardJob:HomeBoardJob|null,childJob:HomeHarnessJob|null,signal:AbortSignal,current:()=>boolean):Promise<string|null>{
    const before=this.entryCache.harnessBoard,job=boardJob??childJob;
    if(boardJob&&(!before||boardJob.revision!==before.revision||boardJob.entryRevision!==before.entry_revision))return null;
    const {quick:_quick,...filters}=this.entryFilters(),query={...filters,limit:10,preview:3,
      ...(this.context.presentationVersion===2?{presentation_version:2 as const}:{}),...(job?.cursor?{cursor:job.cursor}:{})};
    if(childJob){
      const card=childJob.cardId===null?null:homeBoardColumns.flatMap(name=>before!.columns[name].items).filter(item=>item.kind==='harness').find(item=>item.id===childJob.cardId);
      const previous=childJob.cardId===null?this.entryCache.harnessUnlinked??before!.unlinked:this.entryCache.harnessChildren[childJob.cardId]??
        (card?{items:card.children,total:card.children_total,total_is_exact:card.children_total!==null,has_more:card.has_more_children,next_cursor:card.children_cursor}:null);
      if(!childJob.reset&&(!previous||previous.next_cursor!==childJob.cursor))return null;
      const page=childJob.cardId===null?await this.deps.api.harnessUnlinked(query,signal):await this.deps.api.harnessChildren(childJob.cardId,query,signal);
      if(!current())return null;
      if(page.status==='forbidden')throw Object.assign(Error('Harness context forbidden'),{status:403});
      if(!this.validHarnessScope(page)||page.partition!==(childJob.cardId===null?'harness_unlinked':'harness_children')||
        (childJob.cardId!==null&&page.card_id!==childJob.cardId))throw Error('HOME_SCOPE_CHANGED');
      if(!['ready','partial'].includes(page.status)||!this.validHarnessPageShape(page)||!this.validHarnessItems(page.items,page))throw Error('HOME_CONTEXT_UNAVAILABLE');
      if(!childJob.reset&&(page.revision!==childJob.revision||page.entry_revision!==childJob.entryRevision||
        page.total!==previous!.total||page.total_is_exact!==previous!.total_is_exact||
        page.items.some(item=>previous!.items.some(old=>old.id===item.id))))throw Object.assign(Error('Harness activity changed'),{status:409});
      const next={...page,items:childJob.reset?page.items:[...previous!.items,...page.items]};
      if(childJob.cardId===null)this.entryCache={...this.entryCache,harnessUnlinked:next};
      else this.entryCache={...this.entryCache,harnessChildren:{...this.entryCache.harnessChildren,[childJob.cardId]:next}};
      return null;
    }
    if(boardJob&&boardJob.cursor!==before!.columns[boardJob.column].next_cursor)return null;
    const value=boardJob?await this.deps.api.harnessBoardColumn(boardJob.column,query,signal):await this.deps.api.harnessBoard(query,signal);
    if(!current())return null;
    if(value.status==='forbidden')throw Object.assign(Error('Harness board forbidden'),{status:403});
    if(!this.validHarnessScope(value))throw Error('HOME_SCOPE_CHANGED');
    if(boardJob){
      const page=value as HomeHarnessBoardPage,previous=before!.columns[boardJob.column];
      if(page.partition!=='harness_board_column'||page.column!==boardJob.column||page.revision!==boardJob.revision||
        page.entry_revision!==boardJob.entryRevision||!['ready','partial'].includes(page.status)||
        !this.validHarnessSlice(page,page,new Set(homeBoardColumns.flatMap(name=>before!.columns[name].items.map(card=>card.id))),boardJob.column)||
        page.total!==previous.total||page.total_is_exact!==previous.total_is_exact)throw Object.assign(Error('Harness board changed'),{status:409});
      this.entryCache={...this.entryCache,harnessBoard:{...before!,columns:{...before!.columns,[boardJob.column]:{
        items:[...previous.items,...page.items],total:page.total,total_is_exact:page.total_is_exact,has_more:page.has_more,next_cursor:page.next_cursor}}}};
      return null;
    }
    const next=value as HomeHarnessBoard,seen=new Set<string>();
    if(next.partition!=='harness_board'||!next.columns||!homeBoardColumns.every(name=>this.validHarnessSlice(next.columns[name],next,seen,name))||
      !next.unlinked||!this.validHarnessPageShape(next.unlinked)||!this.validHarnessItems(next.unlinked.items,next))throw Error('HOME_HARNESS_BOARD_INVALID');
    this.snapshotStarted=this.lastStarted;
    const same=!this.resetPages&&before&&before.revision===next.revision&&before.entry_revision===next.entry_revision;
    if(!same){this.entryCache=emptyEntryCache();this.entryPending=null;this.boardPending=null;this.harnessPending=null;}
    this.entryCache={...this.entryCache,harnessBoard:same?{...next,columns:Object.fromEntries(homeBoardColumns.map(name=>{
      const old=before.columns[name],fresh=next.columns[name];return [name,old.items.length>fresh.items.length?
        {...fresh,items:[...fresh.items,...old.items.slice(fresh.items.length)],has_more:old.has_more,next_cursor:old.next_cursor}:fresh];
    })) as HomeHarnessBoard['columns']}:next};
    this.resetPages=false;return before&&!same?'Updated harness activity changed the board. All columns were revalidated.':null;
  }
  private publish(notice: string | null = null): void {
    const staleSections: HomeSectionName[] = sections.filter(name => ['partial', 'unavailable', 'forbidden'].includes(this.latest?.[name].status ?? 'unavailable'));
    if (this.activityDirty) staleSections.push('activity');
    const changed=homeSnapshotSignature(this.latest)!==homeSnapshotSignature(this.state.snapshot)||
      homeSnapshotSignature(this.latestActivity)!==homeSnapshotSignature(this.state.activity);
    this.emit({ ...(this.state.paused&&changed ? { hasPendingUpdate: true } : { snapshot: this.latest, activity: this.latestActivity, hasPendingUpdate: false }),
      status: staleSections.length ? 'stale' : 'ready', staleSections, error:null,notice });
  }
  private async pump(): Promise<void> {
    if (!this.allowed() || this.active || (!this.refreshPending && !this.morePending&&!this.entryPending&&!this.boardPending&&!this.harnessPending&&!this.harnessReadPending)) return;
    const entryJob=this.trackingFamily()&&!this.refreshPending?this.entryPending:null;
    const boardJob=(this.boardFamily()||this.harnessFamily())&&!this.refreshPending?this.boardPending:null;
    const contextRead=this.harnessFamily()&&!this.refreshPending?this.harnessReadPending:null;
    const root=this.entryCache.harnessBoard;
    const harnessJob=this.harnessFamily()&&!this.refreshPending?(contextRead&&root?
      {cardId:contextRead.cardId,revision:root.revision!,entryRevision:root.entry_revision,cursor:null,reset:true,retry:contextRead.retry}:this.harnessPending):null;
    if(contextRead)this.harnessReadPending=null;
    const section = this.refreshPending ? null : this.morePending;
    this.refreshPending = false; this.morePending = null;this.entryPending=null;this.boardPending=null;this.harnessPending=null; this.dirtySince = null;
    const job = { generation: this.generation, abort: new AbortController() };
    this.active = job; this.lastStarted = this.deps.now();
    this.emit({ loading: this.trackingFamily()?entryJob===null&&boardJob===null&&harnessJob===null:section===null, loadingMore: section,entryLoading:entryJob,boardLoading:boardJob?.column??null,harnessLoading:harnessJob?(harnessJob.cardId??'unlinked'):null });
    let notice: string | null = null;
    const current = () => this.allowed() && this.active === job && job.generation === this.generation;
    try {
      if(this.harnessFamily()){
        notice=await this.readHarness(boardJob,harnessJob,job.abort.signal,current);
        if(!current())return;
      } else if(this.boardFamily()){
        notice=entryJob?await this.readEntries(entryJob,job.abort.signal,current):await this.readBoard(boardJob,job.abort.signal,current);
        if(!current())return;
      } else if(this.entriesFamily()){
        notice=await this.readEntries(entryJob,job.abort.signal,current);
        if(!current())return;
      } else if (section === null) {
        const value = await this.deps.api.overview(this.filters(), job.abort.signal);
        if (!current()) return;
        if (value.version !== 1 || !this.validScope(value)) throw new Error('HOME_SCOPE_CHANGED');
        this.snapshotStarted = this.lastStarted;
        if (this.resetPages || sections.some(name => this.latest && this.latest[name].items.length > value[name].items.length &&
            value[name].status === 'ready' && value[name].revision !== this.latest[name].revision))
          notice = 'Updated results changed pagination. Showing the first page.';
        const prior = this.resetPages ? null : this.latest;
        this.latest = { ...value, work: retained(value.work, prior?.work),
          attention: retained(value.attention, prior?.attention), server_attention: retained(value.server_attention, prior?.server_attention), results: retained(value.results, prior?.results),
          agents: retained(value.agents, prior?.agents), external_activity: retained(value.external_activity, prior?.external_activity) };
        this.resetPages = false;
        // A loaded feed stays visible, explicitly stale, while its first page
        // is revalidated in this same queue. Never append a prior feed cursor.
        if (this.latestActivity || this.activityDirty) {
          this.activityDirty = true; this.morePending = 'activity';
        }
      } else {
        const previous = section === 'activity' ? (this.activityDirty ? null : this.latestActivity) : this.latest?.[section === 'external' ? 'external_activity' : section];
        const query = { ...this.filters(), limit: section === 'server_attention' ? 20 : 10, ...(previous?.next_cursor ? { cursor: previous.next_cursor } : {}) };
        const value = await this.deps.api[section](query, job.abort.signal);
        if (!current()) return;
        if (value.version !== 1 || !this.validScope(value)) throw new Error('HOME_SCOPE_CHANGED');
        if (previous?.revision && value.revision && previous.revision !== value.revision)
          throw Object.assign(new Error('Home page changed.'), { status: 409 });
        if (!usable(value)) throw Object.assign(new Error('Home section unavailable.'), { code: value.reason_code ?? 'HOME_SECTION_UNAVAILABLE' });
        if ((section === 'attention' || section === 'server_attention') && this.latest) this.latest = { ...this.latest,
          [section]: append(this.latest[section], value as HomePage<AttentionOccurrence>, item => item.attention_id) };
        if (section === 'work' && this.latest) this.latest = { ...this.latest, work: append(this.latest.work, value as HomePage<HomeActivity>, item => item.id) };
        if (section === 'results' && this.latest) this.latest = { ...this.latest, results: append(this.latest.results, value as HomePage<HomeResult>, item => item.id) };
        if (section === 'agents' && this.latest) this.latest = { ...this.latest, agents: append(this.latest.agents, value as HomePage<HomeAgent>, item => item.agent_id) };
        if (section === 'external' && this.latest) this.latest = { ...this.latest, external_activity: append(this.latest.external_activity,
          value as HomePage<ExternalObservation>, item => JSON.stringify([item.source_id, item.observed_instance_id, item.generation])) };
        if (section === 'activity') {
          this.latestActivity = previous
            ? append(previous as HomeSection<HomeFeedEvent>, value as HomePage<HomeFeedEvent>, item => item.id) : value as HomePage<HomeFeedEvent>;
          this.activityDirty = false;
        }
      }
      if(this.harnessFamily()){
        if(harnessJob)this.emit({harnessChildren:this.entryCache.harnessChildren,harnessUnlinked:this.entryCache.harnessUnlinked,error:null,notice});
        else this.publishHarness(notice,!!boardJob||!!harnessJob);
      }else if(this.boardFamily())this.publishBoard(notice,!!boardJob);else if(this.entriesFamily())this.publishEntries(notice);else this.publish(notice);
    } catch (error: unknown) {
      if (!current()) return;
      const failure = info(error);
      if (failure.status === 401 || failure.status === 403) { this.clear(); return; }
      if(failure.code==='HOME_DISABLED'){
        this.entryCache=emptyEntryCache();this.boardPending=null;this.entryPending=null;this.emit({...initialHomeState(),status:'disabled'});return;
      }
      if (failure.status === 409 && (section||entryJob||boardJob||harnessJob)) {
        if(harnessJob&&(harnessJob.retry??0)>=1){
          this.emit({notice:'This activity is still changing. Refresh activity to try again.',error:null});return;
        }
        if(harnessJob)this.harnessReadPending={cardId:harnessJob.cardId,retry:1};
        this.resetPages = true;
        this.refreshPending = true; this.activityDirty = !!this.latestActivity;
        if(this.boardFamily())this.resetBoardPages();
        if(this.harnessFamily())this.resetHarnessPages();
        this.emit({ ...((this.boardFamily()||this.harnessFamily())?this.entryCache:{}),status: 'stale',staleSections:[...sections], error:null,notice: 'Page changed. Refreshing the snapshot.' });
      } else if (failure.name !== 'AbortError') this.emit({ status: this.hasSnapshot() ? 'stale' : 'error',
        error: failure.code ?? 'HOME_READ_FAILED', staleSections: [...sections, 'activity'] });
    } finally {
      if (this.active === job) this.active = null;
      if (job.generation === this.generation) this.emit({ loading: false, loadingMore: null,entryLoading:null,boardLoading:null,harnessLoading:null });
      if (this.allowed()) {
        if ((this.refreshPending || this.morePending||this.entryPending||this.boardPending||this.harnessPending||this.harnessReadPending) && this.context.visible !== false) this.schedule(0);
        else this.schedulePoll();
      }
    }
  }
}
