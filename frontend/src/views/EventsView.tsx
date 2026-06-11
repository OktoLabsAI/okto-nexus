// Live event tail (FR4/FR6): the visual successor of `okto-nexus tail`,
// fed by the shared SSE feed (no polling of its own).

import { useEffect, useRef } from "react";
import type { NexusEvent } from "../api";

export function EventsView({ log }: { log: NexusEvent[] }) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "auto", block: "end" });
  }, [log.length]);

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-5xl mx-auto panel font-mono text-[11px]" data-testid="events-view">
        <div className="px-3 py-2 border-b border-surface-200/60 dark:border-surface-700/50 text-surface-500 dark:text-surface-400">
          event tail (live via SSE) · {log.length} events this session
        </div>
        <div className="p-3 space-y-1">
          {log.length === 0 && (
            <div className="text-surface-400 dark:text-surface-500">
              waiting for events… (any message/handoff/session writes entries)
            </div>
          )}
          {log.map((event) => (
            <div key={event.event_id} className="flex gap-2">
              <span className="text-surface-400 dark:text-surface-600 w-14 shrink-0 text-right">
                #{event.event_id}
              </span>
              <span className="text-accent-600 dark:text-accent-400 w-28 shrink-0">
                {event.stream}
              </span>
              <span className="text-surface-700 dark:text-surface-300 w-56 shrink-0">
                {event.type}
              </span>
              <span className="text-surface-500 dark:text-surface-400 truncate">
                {event.actor_agent_id ?? ""} {JSON.stringify(event.payload ?? "")}
              </span>
            </div>
          ))}
          <div ref={endRef} />
        </div>
      </div>
    </div>
  );
}
