import { useEffect, useRef, useState } from "react";
import { runtimeApi, type BindingView, type RuntimeSession } from "../runtimeApi";
import { RuntimeHistory } from "./RuntimeHistory";

export function RuntimeSessions({agentId, binding}: {agentId: string; binding: BindingView}) {
  const [rows, setRows] = useState<RuntimeSession[] | null>(null);
  const [selected, setSelected] = useState<RuntimeSession | null>(null);
  const [after, setAfter] = useState("");
  const [previous, setPrevious] = useState<string[]>([]);
  const [next, setNext] = useState("");
  const [more, setMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);
  const load = async (cursor: string, back: string[]) => {
    pending.current?.abort();
    const controller = new AbortController(); pending.current = controller;
    setBusy(true); setError("");
    try {
      const me = await runtimeApi.me(controller.signal);
      const page = await runtimeApi.sessions(agentId, binding, cursor, controller.signal);
      if (controller.signal.aborted) return;
      if (page.sessions.length > 25 || page.sessions.some((row, index) =>
          row.scope.server_id !== me.server_id || row.scope.agent_id !== agentId ||
          row.scope.executor_id !== binding.executor_id || row.scope.binding_id !== binding.binding_id ||
          row.scope.session_id <= (index ? page.sessions[index - 1].scope.session_id : cursor)) ||
          page.next_after_session_id !== (page.sessions[page.sessions.length - 1]?.scope.session_id ?? cursor) ||
          (page.has_more && page.sessions.length === 0)) throw new Error("The session list does not match this connection.");
      setRows(page.sessions); setAfter(cursor); setPrevious(back);
      setNext(page.next_after_session_id); setMore(page.has_more);
      setSelected(null);
    } catch (failure) { if (!controller.signal.aborted) setError(String(failure)); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  return <section aria-label="Previous runtime sessions" className="space-y-3 border-t pt-3">
    <h4 className="font-semibold">Previous sessions</h4>
    <p>Browse recorded sessions for this agent and connection, including closed sessions. This does not start, reuse or repair a runtime.</p>
    <button className="btn btn-secondary" disabled={busy} onClick={() => void load("", [])}>Refresh session list</button>
    {rows && <>
      {rows.length === 0 ? <p>No sessions found in this scope.</p> : <div className="overflow-auto"><table className="w-full text-left">
        <thead><tr><th>Session</th><th>Lifecycle</th><th>Lease</th><th>History</th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.scope.session_id}>
          <td className="break-all">{row.scope.session_id}</td><td>{row.lifecycle_state}</td><td>{row.lease_state}</td>
          <td><button className="btn btn-secondary" disabled={busy} aria-label={`View history ${row.scope.session_id}`}
            onClick={() => setSelected(row)}>View history</button></td>
        </tr>)}</tbody>
      </table></div>}
      <button className="btn btn-secondary" disabled={busy || previous.length === 0}
        onClick={() => void load(previous[previous.length - 1], previous.slice(0, -1))}>Previous sessions page</button>
      <button className="btn btn-secondary" disabled={busy || !more}
        onClick={() => void load(next, [...previous, after])}>Next sessions page</button>
    </>}
    {selected && <div><p>Selected session: {selected.scope.session_id}. Process: {selected.process_state}.</p>
      {selected.durable_release_pending && <p>Release confirmation is pending.</p>}
      <RuntimeHistory key={selected.scope.session_id} scope={selected.scope} />
    </div>}
    {busy && <p role="status">Loading sessions…</p>}
    {error && <p role="alert">The session list could not be refreshed. Any displayed rows are from the last successful read. {error}</p>}
  </section>;
}
