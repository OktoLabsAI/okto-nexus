import { useEffect, useRef, useState } from "react";
import { runtimeApi, type RuntimeEventPage, type RuntimeScope } from "../runtimeApi";

export function RuntimeHistory({scope}: {scope: RuntimeScope}) {
  const [page, setPage] = useState<RuntimeEventPage | null>(null);
  const [cursor, setCursor] = useState(0);
  const [previous, setPrevious] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef<AbortController | null>(null);
  const load = async (after: number, back: number[], epoch: string | null) => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true); setError("");
    try {
      const result = await runtimeApi.events(scope, after, epoch, controller.signal);
      if (controller.signal.aborted) return;
      if (["server_id", "executor_id", "session_id", "agent_id", "binding_id", "workspace_id", "workspace_binding_id"].some(
            key => result.scope[key as keyof RuntimeScope] !== scope[key as keyof RuntimeScope]) ||
          (epoch !== null && result.stream_epoch !== epoch) ||
          result.count !== result.events.length || result.events.length > 100 ||
          result.events.some((event, index) => event.server_id !== scope.server_id ||
            event.executor_id !== scope.executor_id || event.session_id !== scope.session_id ||
            event.stream_epoch !== result.stream_epoch || event.sequence !== after + index + 1) ||
          result.next_after_sequence !== after + result.events.length ||
          (result.has_more && result.events.length === 0)) {
        throw new Error("The event page does not match this session and cursor.");
      }
      setPage(result); setCursor(after); setPrevious(back);
    } catch (failure) { if (!controller.signal.aborted) setError(String(failure)); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  useEffect(() => {
    void load(0, [], null);
    return () => pending.current?.abort();
  }, []);
  return <section aria-label="Runtime session history" className="space-y-2 border-t pt-3">
    <h5 className="font-semibold">Session history</h5>
    <p>Recorded events for this session. Reading history does not send runtime actions.</p>
    {page && <>
      <p role="status">Showing {page.count ? `${cursor + 1}–${page.next_after_sequence}` : "0"} of {page.committed_contiguous} committed events.</p>
      {page.gap_pending && <p role="alert">Some events have not arrived. History is incomplete until the gap is reconciled.</p>}
      {page.events.length === 0 && <p>No recorded events on this page.</p>}
      <ol className="max-h-96 overflow-auto space-y-2" aria-label="Recorded runtime events">
        {page.events.map(event => <li key={event.sequence} className="rounded border p-2">
          <details><summary>{event.sequence}. {event.category}{event.native_type ? ` · ${event.native_type}` : ""}</summary>
            <p>{event.received_at}</p>
            <pre className="whitespace-pre-wrap break-words">{JSON.stringify(event.payload, null, 2)}</pre>
          </details>
        </li>)}
      </ol>
      <button className="btn btn-secondary" disabled={busy || previous.length === 0}
        onClick={() => void load(previous[previous.length - 1], previous.slice(0, -1), page.stream_epoch)}>Previous events</button>
      <button className="btn btn-secondary" disabled={busy || !page.has_more}
        onClick={() => void load(page.next_after_sequence, [...previous, cursor], page.stream_epoch)}>Next events</button>
    </>}
    <button className="btn btn-secondary" disabled={busy}
      onClick={() => void load(cursor, previous, page?.stream_epoch ?? null)}>Refresh history page</button>
    {busy && <p role="status">Loading session history…</p>}
    {error && <p role="alert">History could not be refreshed. Any displayed events are from the last successful read. {error}</p>}
  </section>;
}
