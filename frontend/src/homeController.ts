import type { HomeApi } from './homeApi';
import type { HomeActivity, HomeAgent, HomeFeedEvent, HomeFilters, HomeOverview, HomePage, HomePageSection,
  HomeResult, HomeSection, HomeSectionName, HomeQuickFilter, HomeEntryQuery, HomeEntryPage, HomeEntryGroup,
  HomeEntry, HomeSessionRef, HomeEntryPartition } from './homeTypes';
import type { ExternalObservation } from './observationTypes';
import type { AttentionOccurrence } from './attentionTypes';

export interface HomeContext {
  workspace: string | null; identityKey: string; origin?: string; enabled?: boolean; visible?: boolean;
  agent_id?: string; state?: string;
  family?: 'legacy'|'entries'; quick?:HomeQuickFilter; harness?:string; host?:string;
  holdOrder?:boolean;
}
export interface HomeEntryJob {partition:HomeEntryPartition;groupId?:string;entryId?:string}
export const homeEntryPageKey=(groupId:string,entryId:string)=>JSON.stringify([groupId,entryId]);
interface HomeEntryCache {
  entries:HomeEntryPage<HomeEntryGroup>|null;
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
  error: string | null; staleSections: HomeSectionName[]; generation: number;
  scopeKey: string | null;
  entryLoading:HomeEntryJob|null;
}
export interface HomeDependencies {
  api: HomeApi; now(): number; setTimeout(callback: () => void, milliseconds: number): unknown;
  clearTimeout(handle: unknown): void; onChange?(state: HomeState): void;
}
const emptyEntryCache=():HomeEntryCache=>({entries:null,entryChildren:{},entrySessions:{},entryAttention:{},entryResults:{}});
export const initialHomeState = (): HomeState => ({ ...emptyEntryCache(),entryLoading:null,snapshot: null, activity: null, status: 'loading',
  loading: false, loadingMore: null, paused: false, hasPendingUpdate: false, error: null, staleSections: [], generation: 0, scopeKey: null });
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
  c.workspace === 'all' ? null : c.workspace || null, c.agent_id ?? '', c.state ?? '',c.family??'legacy',c.quick??'',c.harness??'',c.host??'']);
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
  private hasSnapshot():boolean{return this.entriesFamily()?!!this.state.entries:!!this.state.snapshot;}
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
      this.entryCache=emptyEntryCache();this.entryPending=null;
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
    this.entryCache=emptyEntryCache();this.entryPending=null;
    this.resetPages = false;
    this.emit({ ...initialHomeState(), status: 'forbidden' });
  }
  dispose(): void { this.clear(); this.disposed = true; }
  refresh(): void {
    if (!this.allowed()) return;
    this.refreshPending = true; this.morePending = null;this.entryPending=null; this.dirtySince = null;
    this.cancel('poll'); this.schedule(0);
  }
  pause(paused = !this.state.paused): void {
    this.emit({ paused });
    if (!paused) this.apply();
  }
  holdOrder(holding:boolean):void{this.context={...this.context,holdOrder:holding};}
  apply(): void {
    if(!this.allowed())return;
    if(this.entriesFamily()){this.emit({...this.entryCache,hasPendingUpdate:false,
      status:this.entryCache.entries?.status==='ready'&&!this.refreshPending?'ready':'stale',staleSections:this.refreshPending?[...sections]:[]});return;}
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
    const affected = event ? this.entriesFamily()&&/^(connection|binding|executor|workspace|policy|guardrail|settings)[.:-]/.test(event.type)
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
    this.refreshPending = true; this.morePending = null;this.entryPending=null;
    if (this.context.visible === false) { this.schedulePoll(); return; }
    this.dirtySince ??= this.deps.now();
    this.schedule(Math.max(0, Math.min(350, this.dirtySince + 500 - this.deps.now())));
  }
  loadMore(section: HomePageSection): void {
    if(this.entriesFamily())return;
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
  private loadEntryPage(job:HomeEntryJob):void{
    if(!this.entriesFamily()||!this.allowed()||this.context.visible===false||this.state.paused||this.state.hasPendingUpdate||this.refreshPending||this.active)return;
    const previous=this.previousEntryPage(job);
    if(!previous||!['ready','partial'].includes(previous.status)||!previous.next_cursor)return;
    this.entryPending=job;this.schedule(0);
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
    const entries=this.entryCache.entries;
    if(this.entriesFamily()&&entries&&this.context.visible!==false&&entries.next_refresh_at){
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
    const expected=this.entryFilters(),scope=value.scope,root=this.entryCache.entries;
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
    this.emit({...(this.state.paused||held?{hasPendingUpdate:true}:{...this.entryCache,hasPendingUpdate:false}),
      status:stale?'stale':'ready',error:notice,staleSections:this.refreshPending?[...sections]:[]});
  }
  private async readEntries(job:HomeEntryJob|null,signal:AbortSignal,current:()=>boolean):Promise<string|null>{
    const previous=job?this.previousEntryPage(job):null;
    const query={...this.entryFilters(),limit:10,preview:3,...(previous?.next_cursor?{cursor:previous.next_cursor}:{})};
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
  private publish(notice: string | null = null): void {
    const staleSections: HomeSectionName[] = sections.filter(name => ['partial', 'unavailable', 'forbidden'].includes(this.latest?.[name].status ?? 'unavailable'));
    if (this.activityDirty) staleSections.push('activity');
    this.emit({ ...(this.state.paused ? { hasPendingUpdate: true } : { snapshot: this.latest, activity: this.latestActivity, hasPendingUpdate: false }),
      status: staleSections.length ? 'stale' : 'ready', staleSections, error: notice });
  }
  private async pump(): Promise<void> {
    if (!this.allowed() || this.active || (!this.refreshPending && !this.morePending&&!this.entryPending)) return;
    const entryJob=this.entriesFamily()&&!this.refreshPending?this.entryPending:null;
    const section = this.refreshPending ? null : this.morePending;
    this.refreshPending = false; this.morePending = null;this.entryPending=null; this.dirtySince = null;
    const job = { generation: this.generation, abort: new AbortController() };
    this.active = job; this.lastStarted = this.deps.now();
    this.emit({ loading: this.entriesFamily()?entryJob===null:section===null, loadingMore: section,entryLoading:entryJob });
    let notice: string | null = null;
    const current = () => this.allowed() && this.active === job && job.generation === this.generation;
    try {
      if(this.entriesFamily()){
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
      if(this.entriesFamily())this.publishEntries(notice);else this.publish(notice);
    } catch (error: unknown) {
      if (!current()) return;
      const failure = info(error);
      if (failure.status === 401 || failure.status === 403) { this.clear(); return; }
      if (failure.status === 409 && (section||entryJob)) {
        this.resetPages = true;
        this.refreshPending = true; this.activityDirty = !!this.latestActivity;
        this.emit({ status: 'stale', error: 'Page changed. Refreshing the snapshot.' });
      } else if (failure.name !== 'AbortError') this.emit({ status: this.hasSnapshot() ? 'stale' : 'error',
        error: failure.code ?? 'HOME_READ_FAILED', staleSections: [...sections, 'activity'] });
    } finally {
      if (this.active === job) this.active = null;
      if (job.generation === this.generation) this.emit({ loading: false, loadingMore: null,entryLoading:null });
      if (this.allowed()) {
        if ((this.refreshPending || this.morePending||this.entryPending) && this.context.visible !== false) this.schedule(0);
        else this.schedulePoll();
      }
    }
  }
}
