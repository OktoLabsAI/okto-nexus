// EventDetailModal — the structured view of a single event (FR4): every column
// (event_id, stream, type, actor, workspace, visibility, target, created_at)
// plus the complete payload JSON, pretty-printed. Opened by clicking a row in
// EventsView. Mirrors MessageDetailModal's grammar.

import { X } from "lucide-react";
import type { NexusEvent } from "../api";

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

export function EventDetailModal({
  event,
  onClose,
}: {
  event: NexusEvent;
  onClose: () => void;
}) {
  const payloadText = pretty(event.payload);
  const targetText = pretty(event.target);
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="relative w-[680px] max-w-[94vw] max-h-[86vh] flex flex-col bg-white dark:bg-[#0b1929] rounded-2xl shadow-2xl border border-surface-200/50 dark:border-[#142840] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        data-testid="event-detail-modal"
      >
        <button
          onClick={onClose}
          className="absolute top-3 right-3 p-1.5 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300 hover:bg-surface-100 dark:hover:bg-white/10 rounded-lg transition-colors z-10"
        >
          <X size={16} />
        </button>

        <header className="px-6 pt-6 pb-4 border-b border-surface-200/50 dark:border-[#142840]">
          <h2 className="font-display font-semibold text-base text-surface-900 dark:text-white pr-8">
            Event #{event.event_id}
          </h2>
          <div className="mt-1 text-xs flex items-center gap-1.5 flex-wrap">
            <span className="chip bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300 font-mono">
              {event.type}
            </span>
            <span className="text-surface-400">·</span>
            <span className="text-surface-500 dark:text-surface-400">{event.stream}</span>
          </div>
        </header>

        <div className="overflow-y-auto px-6 py-4 space-y-5 text-xs">
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
    </div>
  );
}
