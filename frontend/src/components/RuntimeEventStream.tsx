import { useEffect, useRef, useState } from 'react';
import { runtimeApi, type RuntimeEventPage, type RuntimeScope } from '../runtimeApi';
import { appendTail, prependEvents, previousEventCursor, initialEventWindow, validateEventPage } from '../runtimeEvents';
import { RuntimeTerminal } from './RuntimeTerminal';

interface Props { scope: RuntimeScope; active?: boolean; harness?: string; history?: boolean }
interface Stream {
  events: RuntimeEventPage['events']; epoch: string | null; after: number;
  ready: boolean; gap: boolean; total: number;
}

export function RuntimeEventStream(props: Props) {
  return <EventStream key={JSON.stringify(props.scope)} {...props}/>;
}

function EventStream({scope, active = false, harness, history = false}: Props) {
  const stream = useRef<Stream>({events: [], epoch: null, after: 0, ready: false, gap: false, total: 0});
  const [view, setView] = useState(stream.current);
  const [following, setFollowing] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState('');
  const [previousError, setPreviousError] = useState('');
  const [loadingPrevious, setLoadingPrevious] = useState(false);
  const previousRequest = useRef<AbortController | null>(null);
  const update = (next: Stream) => {stream.current = next; setView(next);};
  useEffect(() => () => previousRequest.current?.abort(), []);

  useEffect(() => {
    if (!following) return;
    const controller = new AbortController();
    let timer: number | undefined;
    const read = async (after: number, epoch: string | null) => {
      const page = await runtimeApi.events(scope, after, epoch, controller.signal);
      validateEventPage(page, scope, after, epoch);
      return page;
    };
    const poll = async () => {
      try {
        const current = stream.current;
        let page = await read(current.after, current.epoch);
        let incoming = page.events;
        if (!current.ready) {
          // Start near the bottom; older events remain available by cursor.
          const target = page.committed_contiguous;
          const start = Math.max(0, target - initialEventWindow);
          if (start > 0) page = await read(start, page.stream_epoch);
          incoming = page.events;
          while (page.has_more && page.next_after_sequence < target && !controller.signal.aborted) {
            page = await read(page.next_after_sequence, page.stream_epoch);
            incoming = appendTail(incoming, page.events);
          }
        }
        if (controller.signal.aborted) return;
        update({...stream.current, events: appendTail(stream.current.events, incoming),
          epoch: page.stream_epoch, after: page.next_after_sequence, ready: true,
          gap: page.gap_pending, total: page.committed_contiguous});
        setError('');
        if (page.has_more || active && following)
          timer = window.setTimeout(() => void poll(), page.has_more ? 200 : 2000);
      } catch (failure) {
        if (!controller.signal.aborted) {setError(String(failure)); setFollowing(false);}
      }
    };
    void poll();
    return () => {controller.abort(); window.clearTimeout(timer);};
  }, [following, active, refresh]);

  const loadPrevious = async () => {
    const current = stream.current, first = current.events[0]?.sequence ?? 1;
    if (!current.ready || first <= 1 || previousRequest.current) return;
    const controller = new AbortController(); previousRequest.current = controller;
    setLoadingPrevious(true); setPreviousError('');
    try {
      const after = previousEventCursor(first);
      const page = await runtimeApi.events(scope, after, current.epoch, controller.signal);
      validateEventPage(page, scope, after, current.epoch);
      if (controller.signal.aborted) return;
      if (page.next_after_sequence < first - 1) throw Error('Earlier events are not available yet. Retry after reconciliation.');
      // Concurrent live reads keep their latest cursor and appended events.
      update({...stream.current, events: prependEvents(stream.current.events, page.events)});
    } catch (failure) {
      if (!controller.signal.aborted) setPreviousError(String(failure));
    } finally {
      if (!controller.signal.aborted) {previousRequest.current = null; setLoadingPrevious(false);}
    }
  };
  const latest = () => {setAutoScroll(true); setFollowing(true); setRefresh(n => n + 1);};
  return <section className="space-y-3 min-w-0" aria-label={history ? 'Runtime session history' : 'Session live tail'}>
    <div className="flex items-center gap-3 flex-wrap text-xs">
      <span role="status">{!view.ready ? 'Loading events…' : history ? 'Recorded session events' : following && active ? 'Following live events' : active ? 'Tail paused' : 'Session ended'}</span>
      {!history && active && <button className="btn btn-secondary" onClick={() => setFollowing(v => !v)}>{following ? 'Pause tail' : 'Resume tail'}</button>}
      <label><input type="checkbox" checked={autoScroll} onChange={e => setAutoScroll(e.target.checked)}/> Auto-scroll</label>
      <button className="btn btn-secondary" onClick={latest}>{history ? 'Refresh history' : 'Latest events'}</button>
    </div>
    {view.ready && <p className="text-xs text-surface-500">Showing {view.events.length ? `${view.events[0].sequence}–${view.after}` : '0'} of {view.total} committed events. Scroll up to load earlier events.</p>}
    {view.gap && <p role="alert" className="text-xs">Some events have not arrived. History is incomplete until the gap is reconciled.</p>}
    {error && <p role="alert" className="text-xs">Events could not be refreshed. Loaded events are preserved. {error}</p>}
    <RuntimeTerminal events={view.events} harness={harness}
      label={history ? 'Recorded runtime events' : 'Live runtime events'}
      empty={view.ready ? 'No activity to display yet.' : 'Waiting for session events…'}
      scrollback={{hasPrevious: (view.events[0]?.sequence ?? 1) > 1, loading: loadingPrevious,
        error: previousError, loadPrevious: () => void loadPrevious(), autoScroll, setAutoScroll}}/>
  </section>;
}
