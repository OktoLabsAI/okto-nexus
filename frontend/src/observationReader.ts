export interface ObservationReadState<T> {
  key: string | null;
  value: T | null;
  status: 'loading' | 'ready' | 'stale' | 'error' | 'forbidden' | 'unavailable';
  loading: boolean;
  error: string | null;
}
export const initialObservationRead = <T>(): ObservationReadState<T> => ({
  key: null, value: null, status: 'loading', loading: false, error: null,
});

/** One passive read at a time; scope changes and authorization loss clear old data. */
export class ObservationReader<Q, T> {
  private state = initialObservationRead<T>();
  private query: Q | null = null;
  private epoch = 0;
  private active: AbortController | null = null;
  private timer: unknown;
  private queued = false;
  private disposed = false;
  private stopped = false;
  constructor(private deps: {
    read(query: Q, signal: AbortSignal): Promise<T>;
    refreshAfter(value: T): number;
    now(): number;
    setTimeout(callback: () => void, milliseconds: number): unknown;
    clearTimeout(handle: unknown): void;
    onChange(state: ObservationReadState<T>): void;
  }) {}
  getState() { return this.state; }
  private emit(patch: Partial<ObservationReadState<T>>) {
    this.state = { ...this.state, ...patch };
    if (!this.disposed) this.deps.onChange(this.state);
  }
  private cancelTimer() { if (this.timer !== undefined) this.deps.clearTimeout(this.timer); this.timer = undefined; }
  configure(query: Q | null) {
    const key = query === null ? null : JSON.stringify(query);
    if (key === this.state.key || this.disposed) return;
    this.epoch++;
    this.active?.abort(); this.active = null; this.cancelTimer(); this.queued = false;
    this.query = query; this.stopped = false;
    this.emit({ ...initialObservationRead<T>(), key });
    if (query !== null) void this.load();
  }
  clear() {
    this.epoch++; this.active?.abort(); this.active = null; this.cancelTimer(); this.queued = false; this.stopped = true;
    this.emit({ value: null, status: 'forbidden', loading: false, error: 'Operator access is required. Protected observations have been cleared.' });
  }
  dispose() { this.disposed = true; this.clear(); }
  refresh() {
    if (this.disposed || this.query === null) return;
    this.stopped = false;
    if (this.active) { this.queued = true; return; }
    void this.load();
  }
  private schedule(milliseconds: number) {
    this.cancelTimer();
    this.timer = this.deps.setTimeout(() => {
      this.timer = undefined;
      if (this.state.value) this.emit({ status: 'stale' });
      void this.load();
    }, milliseconds > 0 ? milliseconds : 1000);
  }
  private request(query: Q, abort: AbortController): Promise<T> {
    return new Promise((resolve, reject) => {
      let settled = false;
      const finish = (result: () => void) => {
        if (settled) return;
        settled = true; this.deps.clearTimeout(timer); abort.signal.removeEventListener('abort', cancelled); result();
      };
      const cancelled = () => finish(() => reject(Object.assign(new Error('Read cancelled.'), {name: 'AbortError'})));
      const timer = this.deps.setTimeout(() => {
        finish(() => reject(new Error('External observation read timed out.'))); abort.abort();
      }, 15000);
      abort.signal.addEventListener('abort', cancelled, {once: true});
      Promise.resolve().then(() => this.deps.read(query, abort.signal)).then(
        value => finish(() => resolve(value)), error => finish(() => reject(error)));
    });
  }
  private async load() {
    if (this.disposed || this.stopped || this.query === null || this.active) return;
    this.cancelTimer();
    const abort = new AbortController(), epoch = this.epoch, started = this.deps.now();
    this.active = abort;
    const current = () => !this.disposed && epoch === this.epoch && this.active === abort;
    this.emit({ loading: true, status: this.state.value ? 'stale' : 'loading' });
    try {
      const value = await this.request(this.query, abort);
      if (!current()) return;
      const seconds = this.deps.refreshAfter(value);
      const remaining = started + Math.max(0, Math.min(15, Number.isFinite(seconds) ? seconds : 0)) * 1000 - this.deps.now();
      this.emit({ value, status: remaining > 0 ? 'ready' : 'stale', error: null });
      this.schedule(remaining);
    } catch (failure) {
      if (!current()) return;
      const error = failure as {status?: number; code?: string; name?: string};
      if ([401, 403].includes(error.status ?? 0)) { this.clear(); return; }
      if (error.status === 404 || error.code === 'OBSERVATION_SELECTION_CHANGED') {
        this.stopped = true;
        this.emit({ value: null, status: 'unavailable', error: error.code === 'OBSERVATION_SELECTION_CHANGED'
          ? 'This instance no longer matches the selected generation and scope. Refresh the source list.'
          : 'This observation is unavailable on the current Server.' });
      } else {
        this.emit({ status: this.state.value ? 'stale' : 'error', error: 'External observations could not be refreshed. Current activity is unknown.' });
        this.schedule(15000);
      }
    } finally {
      if (current()) {
        this.active = null; this.emit({ loading: false });
        if (this.queued && !this.stopped) { this.queued = false; void this.load(); }
      }
    }
  }
}
