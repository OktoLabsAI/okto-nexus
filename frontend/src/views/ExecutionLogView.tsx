import { useEffect, useRef, useState } from "react";
import { api, type ExecutionLogEntry } from "../api";
import { PageContainer } from "../components/PageContainer";

const control = "rounded-lg border border-surface-300 dark:border-surface-600 bg-transparent px-3 py-2 text-sm disabled:opacity-50";
const initial = { severity: "", agent_id: "", adapter_id: "", since: "", until: "" };

export function ExecutionLogView({ workspace }: { workspace: string }) {
  const [filters, setFilters] = useState(initial);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [items, setItems] = useState<ExecutionLogEntry[]>([]);
  const [more, setMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);
  useEffect(() => { setOffset(0); }, [workspace]);
  useEffect(() => {
    const current = ++generation.current;
    const params = new URLSearchParams({ offset: String(offset), limit: "100" });
    if (workspace && workspace !== "all") params.set("workspace_id", workspace);
    Object.entries(filters).forEach(([key, value]) => {
      if (value.trim()) params.set(key, ["since", "until"].includes(key) ? new Date(value).toISOString() : value.trim());
    });
    setBusy(true); setError(""); setItems([]); setMore(false);
    api.executionLog(params).then(result => {
      if (generation.current === current) { setItems(result.items); setMore(result.has_more); }
    }).catch(reason => { if (generation.current === current) setError(String(reason)); })
      .finally(() => { if (generation.current === current) setBusy(false); });
    return () => { ++generation.current; };
  }, [workspace, filters, offset, revision]);
  function change(key: keyof typeof initial, value: string) {
    setOffset(0); setFilters(previous => ({ ...previous, [key]: value }));
  }
  return <PageContainer testId="execution-log-view" className="space-y-5">
    <div className="flex justify-between items-start gap-4">
      <div><h1 className="text-xl font-semibold">Execution log</h1>
        <p className="text-sm text-surface-500">Runtime connection errors, execution receipts, session events and authorization decisions.</p>
        <p className="text-sm text-surface-500">{workspace && workspace !== "all" ? "Selected workspace" : "All workspaces"} · Newest first · Refresh to load new records.</p>
      </div>
      <button className={control} disabled={busy} onClick={() => { setOffset(0); setRevision(value => value + 1); }}>Refresh log</button>
    </div>
    <div className="flex flex-wrap items-end gap-3">
      <label className="text-sm">Severity<select aria-label="Severity" className={`${control} block`} value={filters.severity} onChange={event => change("severity", event.target.value)}>
        <option value="">All</option><option value="error">Errors</option><option value="warning">Warnings</option><option value="info">Info</option>
      </select></label>
      <label className="text-sm">Agent<input aria-label="Log agent" className={`${control} block`} placeholder="Agent ID" value={filters.agent_id} onChange={event => change("agent_id", event.target.value)} /></label>
      <label className="text-sm">Runtime<input aria-label="Log runtime" className={`${control} block`} placeholder="Adapter ID" value={filters.adapter_id} onChange={event => change("adapter_id", event.target.value)} /></label>
      <label className="text-sm">From<input aria-label="Log from" type="datetime-local" className={`${control} block`} value={filters.since} onChange={event => change("since", event.target.value)} /></label>
      <label className="text-sm">Through<input aria-label="Log through" type="datetime-local" className={`${control} block`} value={filters.until} onChange={event => change("until", event.target.value)} /></label>
      <button className={control} onClick={() => { setFilters(initial); setOffset(0); }}>Clear filters</button>
    </div>
    {busy && <p role="status">Loading execution log…</p>}
    {error && <p role="alert">Execution log unavailable: {error}</p>}
    {!busy && !error && !items.length && <p>No execution records match these filters.</p>}
    <div className="space-y-3">
      {items.map(item => <article key={item.id} data-testid="execution-log-entry" className="rounded-xl border border-surface-200 dark:border-surface-700 p-4 space-y-2">
        <div className="flex flex-wrap gap-3 items-center">
          <span className={`rounded px-2 py-1 text-xs font-semibold uppercase ${item.severity === "error" ? "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200" : item.severity === "warning" ? "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200" : "bg-surface-100 dark:bg-surface-800"}`}>{item.severity}</span>
          <strong className="break-all">{item.code}</strong>
          <time dateTime={item.timestamp} className="text-sm text-surface-500">{new Date(item.timestamp).toLocaleString("en-US")}</time>
        </div>
        <p className="text-sm break-all">{item.agent_id || "System"} · {item.adapter_id || "Nexus"} · {item.action} · {item.source}</p>
        {item.details.message && <p className="text-sm whitespace-pre-wrap break-words">{item.details.message}</p>}
        <details><summary className="cursor-pointer text-sm">Diagnostic details</summary>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm break-all mt-2">
            {Object.entries({ Workspace: item.workspace_id, Endpoint: item.endpoint_id, Executor: item.executor_id, Session: item.session_id, Operation: item.operation_id, ...item.details }).filter(([, value]) => value != null).map(([key, value]) => <div key={key} className="contents"><dt className="text-surface-500">{key}</dt><dd>{value}</dd></div>)}
          </dl>
          {item.source === "dispatch snapshot" && <p className="text-sm mt-2">Current dispatch failure; the timestamp is the operation creation time.</p>}
        </details>
      </article>)}
    </div>
    <div className="flex gap-3 items-center">
      <button className={control} disabled={busy || offset === 0} onClick={() => setOffset(value => Math.max(0, value - 100))}>Previous page</button>
      <span className="text-sm">Page {Math.floor(offset / 100) + 1}</span>
      <button className={control} disabled={busy || !more} onClick={() => setOffset(value => value + 100)}>Next page</button>
    </div>
  </PageContainer>;
}
