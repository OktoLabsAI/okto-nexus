import type {
  AttentionFilters, AttentionOccurrence, AttentionPage, AttentionPageQuery,
  AttentionPreferenceResponse, AttentionSeenRequest, AttentionSnoozeRequest,
  AttentionState, AttentionSummary,
} from './attentionTypes';

export interface AttentionApi {
  attention(query: AttentionPageQuery, signal?: AbortSignal): Promise<AttentionPage>;
  attentionSummary(filters: AttentionFilters, signal?: AbortSignal): Promise<AttentionSummary>;
  attentionSeen(id: string, body: AttentionSeenRequest, signal?: AbortSignal): Promise<AttentionPreferenceResponse>;
  attentionSnooze(id: string, body: AttentionSnoozeRequest, signal?: AbortSignal): Promise<AttentionPreferenceResponse>;
}
export interface AttentionStreamOptions {
  workspace?: string;
  cursor: number;
  onOpen(): void;
  onError(): void;
  onControl(event: string, value: unknown): void;
}
export interface AttentionControllerDependencies {
  api: AttentionApi;
  now(): number; // Monotonic milliseconds, independent of the Server clock.
  setTimeout(callback: () => void, milliseconds: number): unknown;
  clearTimeout(handle: unknown): void;
  openStream(options: AttentionStreamOptions): { close(): void };
  onChange?(state: AttentionState, filters: AttentionFilters): void;
}
export interface AttentionContext { workspace: string; visible: boolean; enabled: boolean }
type Mutation = {
  id: string; item: AttentionOccurrence; body: AttentionSeenRequest | AttentionSnoozeRequest;
  kind: 'seen' | 'snooze'; promise: Promise<void>; resolve(): void;
};
type Job = { kind: 'refresh' | 'more' | 'mutation'; epoch: number; abort?: AbortController };

export const initialAttentionState = (): AttentionState => ({
  page: null, summary: null, status: 'loading', loading: false, loadingMore: false,
  pendingIds: [], error: null, notice: null, streamStatus: 'off',
});
const errorInfo = (error: unknown) => error as { status?: number; code?: string; message?: string; name?: string };
const abortError = () => Object.assign(new Error('Attention request cancelled.'), { name: 'AbortError' });
const canonicalFilters = (filters: AttentionFilters): string => JSON.stringify(Object.entries(filters).sort());

/** One request queue, one scoped stream, and no inferred empty snapshots. */
export class AttentionController {
  private state = initialAttentionState();
  private context: AttentionContext = { workspace: '', visible: false, enabled: false };
  private filters: AttentionFilters = { state: 'active', seen: 'all' };
  private epoch = 0;
  private disposed = false;
  private stopped = true;
  private active: Job | null = null;
  private refreshQueued = false;
  private moreQueued = false;
  private mutations: Mutation[] = [];
  private pending = new Map<string, Mutation>();
  private stream: { close(): void } | null = null;
  private streamGeneration = 0;
  private eventCursor = 0;
  private deadline: unknown;
  private batch: unknown;
  private reconnect: unknown;
  private dirtySince: number | null = null;
  private summaryDue = Infinity;
  private pageDue = Infinity;

  constructor(private deps: AttentionControllerDependencies) {}
  getState(): AttentionState { return this.state; }
  getFilters(): AttentionFilters { return { ...this.filters, ...this.baseFilters() }; }
  private baseFilters(): AttentionFilters {
    return this.context.workspace && this.context.workspace !== 'all' ? { workspace_id: this.context.workspace } : {};
  }
  private emit(patch: Partial<AttentionState> = {}): void {
    this.state = { ...this.state, ...patch };
    if (!this.disposed) this.deps.onChange?.(this.state, this.getFilters());
  }
  private cancelTimer(name: 'deadline' | 'batch' | 'reconnect'): void {
    if (this[name] !== undefined) this.deps.clearTimeout(this[name]);
    this[name] = undefined;
  }
  private canRun(): boolean { return !this.disposed && this.context.enabled && !this.stopped; }
  private current(job: Job): boolean { return this.canRun() && this.active === job && job.epoch === this.epoch; }
  private closeStream(): void {
    this.streamGeneration++;
    this.stream?.close();
    this.stream = null;
    this.cancelTimer('reconnect');
  }
  private cancelRead(): void {
    if (this.active && this.active.kind !== 'mutation') {
      const job = this.active;
      this.active = null;
      job.abort?.abort();
    }
    this.moreQueued = false;
    this.cancelTimer('batch');
    this.dirtySince = null;
  }
  private stop(status: 'forbidden' | 'disabled', message: string | null): void {
    this.epoch++;
    this.stopped = true;
    const job = this.active;
    this.active = null;
    job?.abort?.abort();
    this.refreshQueued = this.moreQueued = false;
    this.cancelTimer('deadline');
    this.cancelTimer('batch');
    this.dirtySince = null;
    this.closeStream();
    for (const mutation of this.pending.values()) mutation.resolve();
    this.pending.clear();
    this.mutations = [];
    this.eventCursor = 0;
    this.summaryDue = this.pageDue = Infinity;
    this.emit({ ...initialAttentionState(), status, error: message });
  }
  configure(next: AttentionContext): void {
    if (this.disposed) return;
    const scopeChanged = next.workspace !== this.context.workspace;
    const enabledChanged = next.enabled !== this.context.enabled;
    const visibilityChanged = next.visible !== this.context.visible;
    this.context = { ...next };
    if (!next.enabled) {
      this.stop('disabled', null);
      return;
    }
    if (scopeChanged || enabledChanged) {
      this.stop('disabled', null);
      this.stopped = false;
      this.emit({ status: 'loading', loading: true });
      this.connect();
      this.queueRefresh();
    } else if (visibilityChanged && this.canRun()) {
      this.cancelRead();
      this.pageDue = Infinity;
      this.emit({ page: null, loadingMore: false, status: this.state.summary ? 'ready' : 'loading' });
      this.queueRefresh();
    }
  }
  setFilters(next: AttentionFilters): void {
    const { workspace_id: _workspace, ...rest } = next;
    const normalized = Object.fromEntries(Object.entries({ state: 'active', seen: 'all', ...rest })
      .filter(([, value]) => value !== undefined)) as AttentionFilters;
    if (canonicalFilters(normalized) === canonicalFilters(this.filters)) return;
    this.filters = normalized;
    this.cancelRead();
    this.pageDue = Infinity;
    this.emit({ page: null, loadingMore: false, notice: null, error: null,
      status: this.canRun() ? (this.context.visible ? 'loading' : this.state.summary ? 'ready' : 'loading') : this.state.status });
    if (this.canRun()) this.queueRefresh();
  }
  clear(): void { this.stop('forbidden', null); }
  dispose(): void { this.stop('forbidden', null); this.disposed = true; }
  refresh(): void {
    if (this.disposed || !this.context.enabled) return;
    if (this.stopped) { this.stopped = false; this.connect(); }
    this.queueRefresh();
  }
  wake(): void {
    if (!this.canRun()) return;
    if (!this.stream) this.connect();
    this.queueRefresh();
  }
  private queueRefresh(): void {
    if (!this.canRun()) return;
    this.cancelTimer('deadline');
    this.cancelTimer('batch');
    this.dirtySince = null;
    this.refreshQueued = true;
    this.moreQueued = false;
    this.pump();
  }
  private invalidate(): void {
    if (!this.canRun()) return;
    this.moreQueued = false;
    this.emit({ status: this.state.page || this.state.summary ? 'stale' : 'loading' });
    const now = this.deps.now();
    this.dirtySince ??= now;
    this.cancelTimer('batch');
    this.batch = this.deps.setTimeout(() => this.queueRefresh(), Math.max(0, Math.min(250, this.dirtySince + 1000 - now)));
  }
  private schedule(): void {
    this.cancelTimer('deadline');
    if (!this.canRun()) return;
    const due = Math.min(this.summaryDue, this.context.visible ? this.pageDue : Infinity,
      this.deps.now() + 15000);
    this.deadline = this.deps.setTimeout(() => this.queueRefresh(), Math.max(1, due - this.deps.now()));
  }
  private due(value: AttentionSummary, started: number): number {
    const seconds = Number.isFinite(value.refresh_after_seconds) ? value.refresh_after_seconds : 15;
    return started + Math.max(1, Math.min(15000, seconds * 1000));
  }
  loadMore(): void {
    if (!this.canRun() || !this.context.visible || this.state.status !== 'ready' ||
        !this.state.page?.next_cursor || this.state.loading || this.state.loadingMore || this.refreshQueued) return;
    this.moreQueued = true;
    this.pump();
  }
  markSeen(item: AttentionOccurrence, seen: boolean): Promise<void> {
    return this.mutate(item, 'seen', { source_revision: item.source_revision, preference_revision: item.seen_state.revision, seen });
  }
  snooze(item: AttentionOccurrence, until: string | null): Promise<void> {
    return this.mutate(item, 'snooze', { source_revision: item.source_revision, preference_revision: item.seen_state.revision, until });
  }
  private mutate(item: AttentionOccurrence, kind: Mutation['kind'], body: Mutation['body']): Promise<void> {
    const pending = this.pending.get(item.attention_id);
    if (pending) return pending.promise;
    if (!this.canRun()) return Promise.resolve();
    const current = this.state.page?.items.find(row => row.attention_id === item.attention_id);
    if (!current || current.source_revision !== item.source_revision || current.seen_state.revision !== item.seen_state.revision) {
      this.emit({ notice: 'Attention changed. Review the refreshed item.' });
      this.queueRefresh();
      return Promise.resolve();
    }
    let resolve!: () => void;
    const promise = new Promise<void>(done => { resolve = done; });
    const mutation: Mutation = { id: item.attention_id, item, kind, body, promise, resolve };
    this.pending.set(mutation.id, mutation);
    this.mutations.push(mutation);
    this.emit({ pendingIds: [...this.pending.keys()], error: null, notice: null });
    this.pump();
    return promise;
  }
  private pump(): void {
    if (!this.canRun() || this.active) return;
    const mutation = this.mutations.shift();
    const kind = mutation ? 'mutation' : this.refreshQueued ? 'refresh' : this.moreQueued ? 'more' : null;
    if (!kind) { this.schedule(); return; }
    if (kind === 'refresh') this.refreshQueued = false;
    if (kind === 'more') this.moreQueued = false;
    const job: Job = { kind, epoch: this.epoch };
    this.active = job;
    void this.run(job, mutation).finally(() => {
      if (this.active !== job) return;
      this.active = null;
      this.emit({ loading: false, loadingMore: false });
      this.pump();
    });
  }
  private request<T>(job: Job, fn: (signal: AbortSignal) => Promise<T>): Promise<T> {
    if (!this.current(job)) return Promise.reject(abortError());
    const abort = new AbortController();
    job.abort = abort;
    return new Promise<T>((resolve, reject) => {
      let settled = false;
      const finish = (callback: () => void) => {
        if (settled) return;
        settled = true;
        this.deps.clearTimeout(timer);
        abort.signal.removeEventListener('abort', cancelled);
        callback();
      };
      const cancelled = () => finish(() => reject(abortError()));
      const timer = this.deps.setTimeout(() => finish(() => {
        abort.abort();
        reject(new Error('Attention request timed out. Refresh to check the current state.'));
      }), 15000);
      abort.signal.addEventListener('abort', cancelled, { once: true });
      Promise.resolve().then(() => {
        if (abort.signal.aborted) throw abortError();
        return fn(abort.signal);
      }).then(value => finish(() => resolve(value)), error => finish(() => reject(error)));
    });
  }
  private failed(job: Job, error: unknown): boolean {
    if (!this.current(job) || errorInfo(error)?.name === 'AbortError') return true;
    const info = errorInfo(error);
    if (info?.status === 401 || info?.status === 403) {
      this.stop('forbidden', 'An authorized operator session is required.');
      return true;
    }
    if (info?.code === 'FEATURE_DISABLED') {
      this.stop('disabled', 'Attention is disabled.');
      return true;
    }
    if (info?.status === 409 || info?.status === 404 && job.kind === 'mutation') {
      this.emit({ page: null, status: 'loading', notice: 'Attention changed. Review the refreshed view.', error: null });
      this.moreQueued = false;
      this.refreshQueued = job.kind !== 'refresh';
      if (job.kind === 'refresh') this.emit({ status: this.state.summary ? 'stale' : 'error',
        error: 'Attention changed again. Refresh to obtain the current view.' });
    } else {
      this.emit({ status: this.state.page || this.state.summary ? 'stale' : 'error',
        error: info?.message || 'Attention is temporarily unavailable. Refresh to try again.' });
    }
    this.summaryDue = this.pageDue = this.deps.now() + 5000;
    return false;
  }
  private async run(job: Job, mutation?: Mutation): Promise<void> {
    if (job.kind === 'mutation' && mutation) {
      try {
        await this.request(job, signal => mutation.kind === 'seen'
          ? this.deps.api.attentionSeen(mutation.id, mutation.body as AttentionSeenRequest, signal)
          : this.deps.api.attentionSnooze(mutation.id, mutation.body as AttentionSnoozeRequest, signal));
        if (this.current(job)) this.emit({ notice: 'Viewing preference saved.', status: 'stale' });
      } catch (error) { this.failed(job, error); }
      finally {
        if (this.current(job)) {
          this.pending.delete(mutation.id);
          this.emit({ pendingIds: [...this.pending.keys()] });
          this.refreshQueued = true; // Reconcile a lost response; never replay the mutation.
        }
        mutation.resolve();
      }
      return;
    }
    if (job.kind === 'more') {
      const previous = this.state.page;
      if (!previous?.next_cursor || !this.context.visible) return;
      this.emit({ loadingMore: true, error: null });
      try {
        const started = this.deps.now();
        const page = await this.request(job, signal => this.deps.api.attention(
          { ...this.getFilters(), cursor: previous.next_cursor!, limit: 50 }, signal));
        if (!this.current(job)) return;
        const ids = new Set(previous.items.map(item => item.attention_id));
        if (page.snapshot_revision !== previous.snapshot_revision || page.items.some(item => ids.has(item.attention_id)) ||
            page.next_cursor !== null && page.next_cursor === previous.next_cursor) {
          throw Object.assign(new Error('Attention changed while paging.'), { status: 409 });
        }
        this.pageDue = this.due(page, started);
        this.emit({ page: { ...page, items: [...previous.items, ...page.items] }, status: 'ready' });
      } catch (error) { this.failed(job, error); }
      return;
    }
    this.emit({ loading: true, loadingMore: false, status: this.state.page || this.state.summary ? 'stale' : 'loading' });
    let errors = false;
    try {
      const started = this.deps.now();
      const summary = await this.request(job, signal => this.deps.api.attentionSummary(this.baseFilters(), signal));
      if (!this.current(job)) return;
      this.summaryDue = this.due(summary, started);
      this.eventCursor = Math.max(this.eventCursor, summary.event_cursor);
      this.emit({ summary });
    } catch (error) { errors = true; if (this.failed(job, error)) return; }
    if (this.context.visible && this.current(job)) {
      try {
        const started = this.deps.now();
        const page = await this.request(job, signal => this.deps.api.attention({ ...this.getFilters(), limit: 50 }, signal));
        if (!this.current(job)) return;
        this.pageDue = this.due(page, started);
        this.eventCursor = Math.max(this.eventCursor, page.event_cursor);
        this.emit({ page });
      } catch (error) { errors = true; if (this.failed(job, error)) return; }
    }
    if (this.current(job)) {
      if (!errors) this.emit({ status: this.refreshQueued || this.dirtySince !== null ? 'stale' : 'ready', error: null });
      else if (this.state.page || this.state.summary) this.emit({ status: 'stale' });
    }
  }
  private connect(): void {
    if (!this.canRun()) return;
    this.closeStream();
    const generation = this.streamGeneration;
    const current = () => this.canRun() && generation === this.streamGeneration;
    this.emit({ streamStatus: this.state.streamStatus === 'off' ? 'connecting' : 'reconnecting' });
    const lost = () => {
      if (!current()) return;
      this.closeStream();
      this.emit({ streamStatus: 'reconnecting', status: this.state.page || this.state.summary ? 'stale' : 'loading' });
      this.queueRefresh(); // EventSource hides HTTP status: reauthorize through the API.
      if (this.canRun()) this.reconnect = this.deps.setTimeout(() => this.connect(), 1000);
    };
    try {
      const opened = this.deps.openStream({ workspace: this.baseFilters().workspace_id, cursor: this.eventCursor,
        onOpen: () => { if (current()) this.emit({ streamStatus: 'live' }); }, onError: lost,
        onControl: (event, raw) => {
          if (!current()) return;
          const data = raw as { version?: number; event_cursor?: number; reason?: string; clear?: boolean } | null;
          const reset = event === 'attention-reset';
          const mustClear = data?.reason === 'authorization_lost' || data?.reason === 'feature_disabled';
          const validReason = reset
            ? ['snapshot_required', 'retention_gap', 'source_unavailable', 'authorization_lost', 'feature_disabled'].includes(data?.reason ?? '')
            : event === 'attention-invalidated' && data?.reason === 'canonical_change';
          if (!data || data.version !== 1 || !Number.isSafeInteger(data.event_cursor) || data.event_cursor! < 0 ||
              !validReason || data.clear !== mustClear) { lost(); return; }
          if (data.clear === true) {
            this.stop(data.reason === 'feature_disabled' ? 'disabled' : 'forbidden',
              data.reason === 'feature_disabled' ? 'Attention is disabled.' : 'An authorized operator session is required.');
            return;
          }
          this.eventCursor = reset ? data.event_cursor! : Math.max(this.eventCursor, data.event_cursor!);
          if (data.reason === 'source_unavailable') { lost(); return; }
          this.emit({ streamStatus: 'live' });
          this.invalidate();
        },
      });
      if (current()) this.stream = opened;
      else opened.close();
    } catch { lost(); }
  }
}
