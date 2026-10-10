import { useEffect, useRef, useState } from 'react';
import { runtimeApi, type RuntimeEventPage, type RuntimeScope } from '../runtimeApi';
import { appendTail, validateEventPage } from '../runtimeEvents';

export function RuntimeSessionTail({scope, active}: {scope: RuntimeScope; active: boolean}) {
  const [events, setEvents] = useState<RuntimeEventPage['events']>([]);
  const [following, setFollowing] = useState(true);
  const [scroll, setScroll] = useState(true);
  const [error, setError] = useState('');
  const [gap, setGap] = useState(false);
  const [reload, setReload] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const box = useRef<HTMLOListElement>(null);
  useEffect(() => {
    if (!following) return;
    const controller = new AbortController();
    let timer: number | undefined, after = 0, epoch: string | null = null, initial = true;
    const poll = async () => {
      try {
        let result = await runtimeApi.events(scope, after, epoch, controller.signal);
        validateEventPage(result, scope, after, epoch);
        if (initial && result.committed_contiguous > 100) {
          after = result.committed_contiguous - 100; epoch = result.stream_epoch;
          result = await runtimeApi.events(scope, after, epoch, controller.signal);
          validateEventPage(result, scope, after, epoch);
        }
        if (controller.signal.aborted) return;
        const reset = initial;
        setEvents(old => appendTail(reset ? [] : old, result.events));
        initial = false; after = result.next_after_sequence; epoch = result.stream_epoch;
        setGap(result.gap_pending);setError('');setLoaded(true);
        if (active || result.has_more) timer = window.setTimeout(() => void poll(), result.has_more ? 200 : 2000);
      } catch (failure) {if (!controller.signal.aborted) {setError(String(failure));setFollowing(false);}}
    };
    void poll();
    return () => {controller.abort();window.clearTimeout(timer);};
  }, [scope.server_id, scope.executor_id, scope.session_id, following, active, reload]);
  useEffect(() => {if (scroll && box.current) box.current.scrollTop = box.current.scrollHeight;}, [events, scroll]);
  return <section className="space-y-3 min-w-0" aria-label="Session live tail">
    <div className="flex items-center gap-3 flex-wrap text-xs">
      <span role="status">{!loaded ? 'Loading events…' : following && active ? 'Following live events' : active ? 'Tail paused' : 'Session ended'}</span>
      {active && <button className="btn btn-secondary" onClick={() => setFollowing(v => !v)}>{following ? 'Pause tail' : 'Resume tail'}</button>}
      <label><input type="checkbox" checked={scroll} onChange={e => setScroll(e.target.checked)} /> Auto-scroll</label>
      <button className="btn btn-secondary" onClick={() => {setFollowing(true);setReload(n => n + 1);}}>Latest events</button>
    </div>
    <p className="text-xs text-surface-500">Showing up to 200 recent events. Full history remains available in History.</p>
    {gap && <p role="alert" className="text-xs">Some events have not arrived. Waiting for reconciliation.</p>}
    {error && <p role="alert" className="text-xs">Tail paused: {error}</p>}
    <ol ref={box} className="runtime-admin-tail space-y-2" aria-label="Live runtime events">
      {events.map(event => <li key={`${event.stream_epoch}:${event.sequence}`} className="rounded-lg bg-surface-50 dark:bg-surface-800 p-3 text-xs min-w-0">
        <div className="flex justify-between gap-2 flex-wrap text-surface-500"><span>{event.sequence} · {event.native_type || event.category}</span><time>{event.received_at}</time></div>
        <pre className="whitespace-pre-wrap break-all mt-2">{JSON.stringify(event.payload, null, 2)}</pre>
      </li>)}
      {loaded && !events.length && <li className="text-sm text-surface-500">No recorded events yet.</li>}
    </ol>
  </section>;
}
