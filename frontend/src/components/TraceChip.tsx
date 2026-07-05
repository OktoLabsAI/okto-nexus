// Trajectory chip (R-I1): a violet font-mono pill for a trace_id carried by a
// message / handoff / event. Self-gated by the DATA (decision D7): callers
// render it unconditionally and it returns null when the row has no trace -
// the UI never consults the feature_trace flag. The clickable form is how
// every screen jumps to the Events view with the trace filter applied.

import { Route } from "lucide-react";

export function TraceChip({
  traceId,
  onClick,
  className = "",
}: {
  traceId: string | null | undefined;
  onClick?: (traceId: string) => void;
  className?: string;
}) {
  if (!traceId) return null;
  const base =
    "chip inline-flex items-center gap-1 max-w-[180px] font-mono " +
    "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300 " +
    className;
  const body = (
    <>
      <Route size={11} className="shrink-0" />
      <span className="truncate">{traceId}</span>
    </>
  );
  if (!onClick) {
    return (
      <span className={base} title={traceId} data-testid="trace-chip">
        {body}
      </span>
    );
  }
  return (
    <button
      onClick={() => onClick(traceId)}
      className={`${base} hover:bg-violet-200 dark:hover:bg-violet-900/70 transition-colors`}
      title={`Show this trajectory in Events (${traceId})`}
      data-testid="trace-chip"
    >
      {body}
    </button>
  );
}
