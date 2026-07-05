// Event detail: every column + the full payload JSON. `EventDetail` is
// presentational and fills its container (used INLINE in the Events
// master-detail ResizablePanel); `EventDetailModal` keeps the overlay form.

import { X } from "lucide-react";
import type { NexusEvent } from "../api";
import { TraceChip } from "./TraceChip";

function Meta({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex gap-2">
      <span className="text-surface-400 dark:text-surface-500 w-24 shrink-0">{label}</span>
      <span className="font-mono text-surface-700 dark:text-surface-300 break-all">
        {value ?? <span className="text-surface-400">—</span>}
      </span>
    </div>
  );
}

// Pretty-print arbitrary JSON-ish values; never throws on circular/oddities.
function pretty(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

// Surface the correlation/identity keys buried in the payload/target so the
// inspector reads at a glance (task_id, handoff_id, message_id, status, ...).
const SUMMARY_KEYS = [
  "task_id",
  "handoff_id",
  "message_id",
  "session_id",
  "channel_id",
  "status",
  "reason",
];

export function payloadSummary(event: NexusEvent): [string, string][] {
  const src: Record<string, unknown> = {};
  for (const blob of [event.payload, event.target]) {
    if (blob && typeof blob === "object" && !Array.isArray(blob)) {
      Object.assign(src, blob as Record<string, unknown>);
    }
  }
  const out: [string, string][] = [];
  for (const k of SUMMARY_KEYS) {
    const v = src[k];
    if (v !== undefined && v !== null && v !== "") out.push([k, String(v)]);
  }
  return out;
}

export function EventDetail({
  event,
  onClose,
  onOpenTrace,
}: {
  event: NexusEvent;
  onClose?: () => void;
  onOpenTrace?: (traceId: string) => void;
}) {
  const payloadText = pretty(event.payload);
  const targetText = pretty(event.target);
  const summary = payloadSummary(event);
  return (
    <div className="flex flex-col h-full min-h-0" data-testid="event-detail">
      <header className="shrink-0 flex items-start gap-2 pb-3 border-b border-surface-200/50 dark:border-surface-700/50">
        <div className="min-w-0 flex-1">
          <h2 className="font-display font-semibold text-base text-surface-900 dark:text-white">
            Event #{event.event_id}
          </h2>
          <div className="mt-1 text-xs flex items-center gap-1.5 flex-wrap">
            <span className="chip bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300 font-mono">
              {event.type}
            </span>
            <span className="text-surface-400">·</span>
            <span className="text-surface-500 dark:text-surface-400">{event.stream}</span>
            {event.trace_id && (
              <>
                <span className="text-surface-400">·</span>
                <TraceChip traceId={event.trace_id} onClick={onOpenTrace} />
              </>
            )}
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="shrink-0 p-1.5 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300 hover:bg-surface-100 dark:hover:bg-white/10 rounded-lg transition-colors"
            title="Close"
          >
            <X size={16} />
          </button>
        )}
      </header>

      <div className="flex-1 min-h-0 overflow-y-auto pt-4 space-y-5 text-xs">
        {summary.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {summary.map(([k, v]) => (
              <span
                key={k}
                className="chip bg-surface-100 text-surface-600 dark:bg-surface-800 dark:text-surface-300 font-mono"
                title={k}
              >
                {k}: {v}
              </span>
            ))}
          </div>
        )}

        {/* Metadata — every column */}
        <section className="space-y-1">
          <h3 className="text-surface-500 dark:text-surface-400 font-medium uppercase tracking-wider mb-1.5">
            Metadata
          </h3>
          <Meta label="event_id" value={String(event.event_id)} />
          <Meta label="stream" value={event.stream} />
          <Meta label="type" value={event.type} />
          <Meta label="actor" value={event.actor_agent_id} />
          <Meta label="workspace" value={event.workspace_id} />
          <Meta label="visibility" value={event.visibility ?? "public"} />
          <Meta label="created_at" value={event.created_at} />
        </section>

        {/* Target (routing descriptor), when present */}
        {targetText && (
          <section>
            <h3 className="text-surface-500 dark:text-surface-400 font-medium uppercase tracking-wider mb-1.5">
              Target
            </h3>
            <pre className="bg-surface-50 dark:bg-surface-900 border border-surface-200/60 dark:border-surface-700/50 rounded-lg p-3 text-surface-700 dark:text-surface-300 overflow-x-auto whitespace-pre-wrap break-all">
              {targetText}
            </pre>
          </section>
        )}

        {/* Payload — complete, pretty-printed */}
        <section>
          <h3 className="text-surface-500 dark:text-surface-400 font-medium uppercase tracking-wider mb-1.5">
            Payload
          </h3>
          <pre
            className="bg-surface-50 dark:bg-surface-900 border border-surface-200/60 dark:border-surface-700/50 rounded-lg p-3 text-surface-700 dark:text-surface-300 overflow-x-auto whitespace-pre-wrap break-all"
            data-testid="event-payload"
          >
            {payloadText || <span className="text-surface-400">(empty)</span>}
          </pre>
        </section>
      </div>
    </div>
  );
}

// Legacy overlay wrapper; the Events screen now renders EventDetail inline.
export function EventDetailModal({
  event,
  onClose,
}: {
  event: NexusEvent;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="relative w-[680px] max-w-[94vw] max-h-[86vh] p-6 bg-white dark:bg-[#0b1929] rounded-2xl shadow-2xl border border-surface-200/50 dark:border-[#142840] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        data-testid="event-detail-modal"
      >
        <EventDetail event={event} onClose={onClose} />
      </div>
    </div>
  );
}
