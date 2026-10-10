import { useEffect, useRef, useState } from 'react';
import { runtimeApi, type RuntimeSession } from '../runtimeApi';
import { connectionSessions, SessionClosures } from '../connectionSessions';
import { AgentActionModal, AgentModalFooter } from './AgentActionModal';

export function ConnectionSessionConflict({agentId, bindingIds, closures, onCancel, onReady}: {
  agentId: string; bindingIds: string[]; closures: SessionClosures; onCancel: () => void; onReady: () => Promise<void>;
}) {
  const [sessions, setSessions] = useState<RuntimeSession[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const live = useRef(true);
  const ready = useRef(onReady); ready.current = onReady;
  const started = useRef(0);
  useEffect(() => {
    live.current = true;
    return () => {live.current = false;};
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    let reading = false;
    const refresh = async () => {
      if (reading) return;
      reading = true;
      try {
        const current = await connectionSessions(runtimeApi, agentId, bindingIds, controller.signal);
        if (controller.signal.aborted) return;
        setSessions(current); setLoaded(true);
        if (waiting && current.length === 0) {
          setWaiting(false); setBusy(true);
          try {await ready.current();} finally {if (live.current) setBusy(false);}
        } else if (waiting && Date.now() - started.current > 120000) {
          setWaiting(false);
          setError('Sessions are still open. You can keep waiting, request closure, or return to editing. Your changes have not been saved.');
        }
      } catch (failure) {
        if (!controller.signal.aborted) {setError(String(failure)); setWaiting(false);}
      } finally {reading = false;}
    };
    void refresh();
    const timer = waiting ? window.setInterval(() => void refresh(), 2000) : undefined;
    return () => {controller.abort(); if (timer) window.clearInterval(timer);};
  }, [agentId, bindingIds, waiting, reload]);
  const wait = () => {setError(''); started.current = Date.now(); setWaiting(true);};
  const close = async () => {
    setBusy(true); setError('');
    const results = await Promise.allSettled(sessions.map(session => closures.close(runtimeApi, session)));
    if (!live.current) return;
    setBusy(false);
    const failures = results.filter((r): r is PromiseRejectedResult => r.status === 'rejected');
    if (failures.length) {
      setError(failures.map(r => String(r.reason)).join(' ')); setReload(n => n + 1);
    } else wait();
  };
  return <AgentActionModal title="Open sessions" compact="tall" guardChanges={false} busy={busy} onClose={onCancel}>
    <div className="space-y-3 text-sm">
      <p>This change requires the existing sessions to close. Your edits are kept until the connection is saved.</p>
      <p>Waiting does not interrupt work. Shared sessions can remain open after a response; use Close sessions to end them.</p>
      {loaded && <p role="status">{sessions.length} open session(s) for <strong>{agentId}</strong>.</p>}
      {sessions.length > 0 && <ul className="max-h-40 overflow-y-auto space-y-1 text-xs">
        {sessions.map(s => <li key={s.scope.session_id} className="break-all">{s.scope.session_id} · {s.lifecycle_state}</li>)}
      </ul>}
      <p>Closing requests a graceful stop and may interrupt unfinished work. It only targets the sessions listed above.</p>
      <p className="text-xs text-surface-500">Returning to editing stops waiting. Any closure already requested continues.</p>
      {waiting && <p role="status">Waiting for confirmed closure before saving…</p>}
      {error && <p role="alert">{error}</p>}
      {error && <button className="btn btn-secondary" disabled={busy || waiting} onClick={() => {setError('');setReload(n => n + 1);}}>Refresh sessions</button>}
    </div>
    <AgentModalFooter>
      <button className="btn btn-secondary" disabled={busy} onClick={onCancel}>Keep editing</button>
      <button className="btn btn-secondary" disabled={busy || waiting || !loaded} onClick={wait}>{waiting ? 'Waiting…' : 'Wait and save'}</button>
      <button className="btn btn-primary" disabled={busy || waiting || !loaded || !sessions.length} onClick={() => void close()}>{busy ? 'Processing…' : 'Close sessions and save'}</button>
    </AgentModalFooter>
  </AgentActionModal>;
}
