import { useEffect, useState } from 'react';
import { type RuntimeSession } from '../runtimeApi';
import { api } from '../api';

type Row = RuntimeSession & {host: string; harness: string};

export function RuntimeSessionSummary({agentId, workspace, refreshKey}: {
  agentId: string; workspace: string; refreshKey: number;
}) {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [more, setMore] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setRows([]);
    void (async () => {
      const page = await api.agentRuntimeSessions(agentId, workspace);
      if (controller.signal.aborted) return;
      setRows(page.items);
      setMore(page.has_more);
    })().catch(failure => { if (!controller.signal.aborted) setError(String(failure)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [agentId, workspace, refreshKey]);
  return <div data-testid="graph-runtime-sessions" className="space-y-1">
    {loading ? <p role="status">Loading runtime sessions…</p> : error ?
      <p role="alert">Runtime sessions unavailable. {error}</p> : <>
      {!rows.length && <p className="text-surface-400">No runtime sessions.</p>}
      {rows.map(row => <div key={`${row.scope.executor_id}:${row.scope.session_id}`}
        className="rounded border border-surface-200 p-2 dark:border-surface-700">
        <div className="flex justify-between gap-2"><span title={row.scope.session_id} className="font-mono">{row.scope.session_id.slice(0,14)}…</span>
          <span>{row.lifecycle_state}</span></div>
        <div className="text-surface-500">{row.harness} · {row.host}</div>
        <div className="text-surface-500">Lease: {row.lease_state} · {row.control_available ? 'Connected' : 'Not available'}</div>
      </div>)}
      {more && <p>Showing 100 sessions, active sessions first. Open Connections for the full history.</p>}
    </>}
  </div>;
}
