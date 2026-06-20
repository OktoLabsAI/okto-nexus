// Message detail: full metadata + per-recipient delivery lanes + the complete
// body of a single message. `MessageDetail` is presentational and fills its
// container (used INLINE inside the Messages master-detail ResizablePanel);
// `MessageDetailModal` keeps the old overlay form as a thin wrapper.

import { X } from "lucide-react";
import type { MessageRow } from "../api";
import { Markdown } from "./Markdown";

const LANE_CHIP: Record<string, string> = {
  unread: "bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300",
  delivered: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  parked: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  read: "bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300",
};

function Meta({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div className="flex gap-2">
      <span className="text-surface-400 dark:text-surface-500 w-24 shrink-0">{label}</span>
      <span className="font-mono text-surface-700 dark:text-surface-300 break-all">{value}</span>
    </div>
  );
}

// Presentational detail body — fills a flex column (h-full). Header scrolls
// nothing; the sections scroll inside the flex-1 region.
export function MessageDetail({
  message,
  onClose,
}: {
  message: MessageRow;
  onClose?: () => void;
}) {
  const body = message.body ?? message.preview ?? "";
  return (
    <div className="flex flex-col h-full min-h-0" data-testid="message-detail">
      <header className="shrink-0 flex items-start gap-2 pb-3 border-b border-surface-200/50 dark:border-surface-700/50">
        <div className="min-w-0 flex-1">
          <h2 className="font-display font-semibold text-base text-surface-900 dark:text-white break-words">
            {message.subject || "(no subject)"}
          </h2>
          <div className="mt-1 text-xs flex items-center gap-1.5 flex-wrap">
            <span className="font-mono text-accent-600 dark:text-accent-400">
              {message.from_agent_id}
            </span>
            <span className="text-surface-400">→</span>
            {message.deliveries.length === 0 ? (
              <span className="chip bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300">
                no recipient
              </span>
            ) : (
              message.deliveries.map((d) => (
                <span key={d.delivery_id} className="font-mono text-surface-600 dark:text-surface-400">
                  {d.recipient_agent_id}
                </span>
              ))
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
        {/* Metadata */}
        <section className="space-y-1">
          <h3 className="text-surface-500 dark:text-surface-400 font-medium uppercase tracking-wider mb-1.5">
            Metadata
          </h3>
          <Meta label="message_id" value={message.message_id} />
          <Meta label="created_at" value={message.created_at} />
          <Meta label="workspace" value={message.workspace_id} />
          <Meta label="channel" value={message.channel_id} />
        </section>

        {/* Delivery lanes */}
        {message.deliveries.length > 0 && (
          <section className="space-y-1.5">
            <h3 className="text-surface-500 dark:text-surface-400 font-medium uppercase tracking-wider mb-1.5">
              Delivery
            </h3>
            <div className="space-y-1.5">
              {message.deliveries.map((d) => (
                <div
                  key={d.delivery_id}
                  className="flex items-center gap-2 flex-wrap bg-surface-50 dark:bg-surface-900 rounded-lg px-2.5 py-1.5"
                >
                  <span className="font-mono text-surface-700 dark:text-surface-300">
                    {d.recipient_agent_id}
                  </span>
                  <span className={`chip ${LANE_CHIP[d.status] ?? LANE_CHIP.read}`}>
                    {d.status}
                  </span>
                  <span className="ml-auto text-surface-400 dark:text-surface-500 text-[11px]">
                    {d.read_at
                      ? `read ${d.read_at}`
                      : d.delivered_at
                        ? `delivered ${d.delivered_at}`
                        : `queued ${d.created_at}`}
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Body */}
        <section>
          <h3 className="text-surface-500 dark:text-surface-400 font-medium uppercase tracking-wider mb-1.5">
            Content
          </h3>
          <div className="bg-surface-50 dark:bg-surface-900 border border-surface-200/60 dark:border-surface-700/50 rounded-lg p-3 text-surface-700 dark:text-surface-300 leading-relaxed">
            {body ? <Markdown text={body} /> : <span className="text-surface-400">(no body)</span>}
          </div>
        </section>
      </div>
    </div>
  );
}

// Legacy overlay wrapper (kept for any modal caller); the Messages screen now
// renders MessageDetail inline in a ResizablePanel.
export function MessageDetailModal({
  message,
  onClose,
}: {
  message: MessageRow;
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
        data-testid="message-detail-modal"
      >
        <MessageDetail message={message} onClose={onClose} />
      </div>
    </div>
  );
}
