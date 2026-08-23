// Event detail: every column + the full payload JSON. `EventDetail` is
// presentational and fills its container (used INLINE in the Events
// master-detail ResizablePanel); `EventDetailModal` keeps the overlay form.

import { X } from "lucide-react";
import type { NexusEvent } from "../api";
import { TraceChip } from "./TraceChip";
import { useWorkspaceName } from "./WorkspaceNames";
import { TargetDescriptor } from "./TargetDescriptor";

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

function fieldLabel(value: string): string {
  return value.replace(/_/g, " ");
}

function StructuredData({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null || value === undefined || value === "") {
    return <span className="text-surface-400 dark:text-surface-500">—</span>;
  }
  if (typeof value === "string") {
    return (
      <span className="whitespace-pre-wrap break-words text-surface-700 dark:text-surface-200">
        {value}
      </span>
    );
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return (
      <span className="font-mono text-surface-700 dark:text-surface-200">
        {String(value)}
      </span>
    );
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-surface-400">empty list</span>;
    const primitives = value.every(
      (item) => item === null || ["string", "number", "boolean"].includes(typeof item),
    );
    if (primitives) {
      return (
        <div className="flex flex-wrap gap-1">
          {value.map((item, index) => (
            <span key={index} className="chip bg-surface-100 text-surface-600 dark:bg-surface-800 dark:text-surface-300 font-mono">
              {String(item ?? "—")}
            </span>
          ))}
        </div>
      );
    }
    return (
      <div className="space-y-2">
        {value.map((item, index) => (
          <div key={index} className="rounded-lg border border-surface-200 dark:border-surface-700 p-2.5">
            <div className="text-[10px] uppercase tracking-wide text-surface-400 mb-1">item {index + 1}</div>
            <StructuredData value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (!entries.length) return <span className="text-surface-400">empty object</span>;
    return (
      <div className={depth === 0 ? "rounded-lg border border-surface-200 dark:border-surface-700 divide-y divide-surface-100 dark:divide-surface-800" : "space-y-2"}>
        {entries.map(([key, item]) => (
          <div key={key} className={depth === 0 ? "grid grid-cols-[110px_minmax(0,1fr)] gap-3 px-3 py-2" : "grid grid-cols-[96px_minmax(0,1fr)] gap-2"}>
            <span className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500 break-words">
              {fieldLabel(key)}
            </span>
            <div className="min-w-0"><StructuredData value={item} depth={depth + 1} /></div>
          </div>
        ))}
      </div>
    );
  }
  return <span className="text-surface-600 dark:text-surface-300">{String(value)}</span>;
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
  const workspaceName = useWorkspaceName(event.workspace_id);
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
          <Meta label="workspace" value={workspaceName} />
          <Meta label="visibility" value={event.visibility ?? "public"} />
          <Meta label="created_at" value={event.created_at} />
        </section>

        {/* Target (routing descriptor), when present */}
        {event.target !== null && event.target !== undefined && (
          <section>
            <h3 className="text-surface-500 dark:text-surface-400 font-medium uppercase tracking-wider mb-1.5">
              Target
            </h3>
            <TargetDescriptor target={event.target} testId="event-target" />
          </section>
        )}

        {/* Payload — complete, pretty-printed */}
        <section>
          <h3 className="text-surface-500 dark:text-surface-400 font-medium uppercase tracking-wider mb-1.5">
            Payload
          </h3>
          <div data-testid="event-payload">
            <StructuredData value={event.payload} />
          </div>
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
