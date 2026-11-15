import type { HomeApi } from './homeApi';
import type { HomeActivity, HomeAgent, HomeFeedEvent, HomeFilters, HomeOverview, HomePage, HomePageSection,
  HomeResult, HomeSection, HomeSectionName } from './homeTypes';
import type { ExternalObservation } from './observationTypes';

export interface HomeContext {
  workspace: string | null; identityKey: string; origin?: string; enabled?: boolean; visible?: boolean;
  agent_id?: string; state?: string;
}
export interface HomeInvalidation { type: string; event_id?: number; id?: string | number }
export type HomeStreamStatus = 'live' | 'connecting' | 'reconnecting' | 'off';
export interface HomeState {
  snapshot: HomeOverview | null; activity: HomeSection<HomeFeedEvent> | null;
  status: 'loading' | 'ready' | 'stale' | 'error' | 'forbidden' | 'disabled';
  loading: boolean; loadingMore: HomePageSection | null; paused: boolean; hasPendingUpdate: boolean;
  error: string | null; staleSections: HomeSectionName[]; generation: number;
  scopeKey: string | null;
}
export interface HomeDependencies {
  api: HomeApi; now(): number; setTimeout(callback: () => void, milliseconds: number): unknown;
  clearTimeout(handle: unknown): void; onChange?(state: HomeState): void;
}
export const initialHomeState = (): HomeState => ({ snapshot: null, activity: null, status: 'loading',
  loading: false, loadingMore: null, paused: false, hasPendingUpdate: false, error: null, staleSections: [], generation: 0, scopeKey: null });
const sections = ['work', 'attention', 'results', 'agents', 'external_activity'] as const;
/** Hints only. The fallback/TTL still covers sources without a workspace event. */
export function homeInvalidatedSections(type: string): HomeSectionName[] {
  if (/^observation[.:-]/.test(type)) return ['external_activity', 'agents', 'attention', 'activity'];
  if (/^attention[.:-]/.test(type)) return ['attention', 'results', 'work'];
  if (/^message[.:-]/.test(type)) return ['work', 'agents', 'activity'];
  if (/^handoff[.:-]/.test(type)) return ['work', 'results', 'attention', 'agents', 'activity'];
  if (/^(execution|runtime|native|approval)[.:-]/.test(type)) return ['work', 'results', 'attention', 'agents', 'activity'];
  if (/^(agent|session|authorization|operator|stream)[.:-]/.test(type) || ['reset', 'gap', 'reconnect'].includes(type))
    return [...sections, 'activity'];
  return [];
}
const info = (value: unknown): { status?: number; code?: string; name?: string } =>
  value && typeof value === 'object' ? value : {};
export const homeContextKey = (c: HomeContext): string => JSON.stringify([c.origin ?? '', c.identityKey,
  c.workspace === 'all' ? null : c.workspace || null, c.agent_id ?? '', c.state ?? '']);
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
      this.resetPages = false;
      this.refreshPending = false; this.morePending = null; this.dirtySince = null;
      this.blocked = false;
      this.emit({ ...initialHomeState(), status: this.allowed() ? 'loading' : 'disabled' });
      if (this.allowed()) this.refresh();
    } else if (becameVisible) this.refresh();
    else this.schedulePoll();
  }
  clear(): void {
    this.generation++; this.blocked = true; this.active?.abort.abort();
    this.cancel('timer'); this.cancel('poll'); this.refreshPending = false; this.morePending = null;
    this.latest = null; this.latestActivity = null; this.activityDirty = false;
    this.resetPages = false;
    this.emit({ ...initialHomeState(), status: 'forbidden' });
  }
  dispose(): void { this.clear(); this.disposed = true; }
  refresh(): void {
    if (!this.allowed()) return;
    this.refreshPending = true; this.morePending = null; this.dirtySince = null;
    this.cancel('poll'); this.schedule(0);
  }
  pause(paused = !this.state.paused): void {
    this.emit({ paused });
    if (!paused) this.apply();
  }
  apply(): void {
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
    const affected = event ? homeInvalidatedSections(event.type) : [...sections];
    if (event) {
      const id = event.event_id ?? event.id;
      const key = id === undefined ? null : `${id}:${event.type}`;
      if (key && key === this.eventId) return;
      this.eventId = key;
      if (!affected.length) return;
    }
    this.emit({ status: this.state.snapshot ? 'stale' : 'loading',
      staleSections: [...new Set([...this.state.staleSections, ...affected])] });
    this.refreshPending = true; this.morePending = null;
    if (this.context.visible === false) { this.schedulePoll(); return; }
    this.dirtySince ??= this.deps.now();
    this.schedule(Math.max(0, Math.min(350, this.dirtySince + 500 - this.deps.now())));
  }
  loadMore(section: HomePageSection): void {
    if (!this.allowed() || this.context.visible === false || this.state.paused || this.refreshPending || this.active) return;
    const current = section === 'activity' ? this.latestActivity : this.latest?.[section === 'external' ? 'external_activity' : section];
    if (current && !(section === 'activity' && this.activityDirty) && (!usable(current) || !current.next_cursor)) return;
    if (!current && section !== 'activity') return;
    this.morePending = section; this.schedule(0);
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
  private publish(notice: string | null = null): void {
    const staleSections: HomeSectionName[] = sections.filter(name => ['partial', 'unavailable', 'forbidden'].includes(this.latest?.[name].status ?? 'unavailable'));
    if (this.activityDirty) staleSections.push('activity');
    this.emit({ ...(this.state.paused ? { hasPendingUpdate: true } : { snapshot: this.latest, activity: this.latestActivity, hasPendingUpdate: false }),
      status: staleSections.length ? 'stale' : 'ready', staleSections, error: notice });
  }
  private async pump(): Promise<void> {
    if (!this.allowed() || this.active || (!this.refreshPending && !this.morePending)) return;
    const section = this.refreshPending ? null : this.morePending;
    this.refreshPending = false; this.morePending = null; this.dirtySince = null;
    const job = { generation: this.generation, abort: new AbortController() };
    this.active = job; this.lastStarted = this.deps.now();
    this.emit({ loading: section === null, loadingMore: section });
    let notice: string | null = null;
    const current = () => this.allowed() && this.active === job && job.generation === this.generation;
    try {
      if (section === null) {
        const value = await this.deps.api.overview(this.filters(), job.abort.signal);
        if (!current()) return;
        if (value.version !== 1 || !this.validScope(value)) throw new Error('HOME_SCOPE_CHANGED');
        this.snapshotStarted = this.lastStarted;
        if (this.resetPages || sections.some(name => this.latest && this.latest[name].items.length > value[name].items.length &&
            value[name].status === 'ready' && value[name].revision !== this.latest[name].revision))
          notice = 'Updated results changed pagination. Showing the first page.';
        const prior = this.resetPages ? null : this.latest;
        this.latest = { ...value, work: retained(value.work, prior?.work),
          attention: retained(value.attention, prior?.attention), results: retained(value.results, prior?.results),
          agents: retained(value.agents, prior?.agents), external_activity: retained(value.external_activity, prior?.external_activity) };
        this.resetPages = false;
        // A loaded feed stays visible, explicitly stale, while its first page
        // is revalidated in this same queue. Never append a prior feed cursor.
        if (this.latestActivity || this.activityDirty) {
          this.activityDirty = true; this.morePending = 'activity';
        }
      } else if (section === 'attention') {
        const previous = this.latest?.attention;
        if (!previous?.next_cursor || !this.latest) return;
        const filters = this.filters();
        const query = { ...(filters.workspace_id ? { workspace_id: filters.workspace_id } : {}),
          ...(filters.agent_id ? { agent_id: filters.agent_id } : {}),
          category: 'action_required' as const, state: 'active' as const, seen: 'all' as const,
          cursor: previous.next_cursor, limit: 10 };
        const value = await this.deps.api.attention(query, job.abort.signal);
        if (!current()) return;
        if (value.version !== 1 || (value.filters.workspace_id ?? null) !== (query.workspace_id ?? null) ||
            (value.filters.agent_id ?? '') !== (query.agent_id ?? '') || value.filters.category !== query.category ||
            value.filters.state !== query.state || value.filters.seen !== query.seen)
          throw new Error('HOME_SCOPE_CHANGED');
        if (previous.revision && value.snapshot_revision !== previous.revision)
          throw Object.assign(new Error('Attention page changed.'), { status: 409 });
        this.latest = { ...this.latest, attention: append(previous, { status: 'ready', items: value.items,
          total: value.total, total_is_exact: true, has_more: value.next_cursor !== null, next_cursor: value.next_cursor,
          revision: value.snapshot_revision, as_of: value.observed_at, next_refresh_at: value.next_refresh_at }, item => item.attention_id) };
      } else {
        const previous = section === 'activity' ? (this.activityDirty ? null : this.latestActivity) : this.latest?.[section === 'external' ? 'external_activity' : section];
        const query = { ...this.filters(), limit: 10, ...(previous?.next_cursor ? { cursor: previous.next_cursor } : {}) };
        const value = await this.deps.api[section](query, job.abort.signal);
        if (!current()) return;
        if (value.version !== 1 || !this.validScope(value)) throw new Error('HOME_SCOPE_CHANGED');
        if (previous?.revision && value.revision && previous.revision !== value.revision)
          throw Object.assign(new Error('Home page changed.'), { status: 409 });
        if (!usable(value)) throw Object.assign(new Error('Home section unavailable.'), { code: value.reason_code ?? 'HOME_SECTION_UNAVAILABLE' });
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
      this.publish(notice);
    } catch (error: unknown) {
      if (!current()) return;
      const failure = info(error);
      if (failure.status === 401 || failure.status === 403) { this.clear(); return; }
      if (failure.status === 409 && section) {
        this.resetPages = true;
        this.refreshPending = true; this.activityDirty = !!this.latestActivity;
        this.emit({ status: 'stale', error: 'Page changed. Refreshing the snapshot.' });
      } else if (failure.name !== 'AbortError') this.emit({ status: this.state.snapshot ? 'stale' : 'error',
        error: failure.code ?? 'HOME_READ_FAILED', staleSections: [...sections, 'activity'] });
    } finally {
      if (this.active === job) this.active = null;
      if (job.generation === this.generation) this.emit({ loading: false, loadingMore: null });
      if (this.allowed()) {
        if ((this.refreshPending || this.morePending) && this.context.visible !== false) this.schedule(0);
        else this.schedulePoll();
      }
    }
  }
}
