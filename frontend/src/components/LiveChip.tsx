// The "● Live" connection chip — the canvas/header live indicator. Shared so
// every live surface (the header AND the graph's right-hand monitor panel)
// reads the SAME bus-connection state from one definition: green when live,
// amber while (re)connecting, grey when off. Mirrors the Pulse status grammar.

import type { SSEStatus } from "../useSSE";

const LIVE_CHIP: Record<SSEStatus, readonly [string, string]> = {
  live: [
    "● Live",
    "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  ],
  connecting: [
    "● Connecting",
    "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  ],
  reconnecting: [
    "● Reconnecting",
    "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  ],
  off: [
    "● Off",
    "bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300",
  ],
};

export function LiveChip({
  status,
  className = "",
}: {
  status: SSEStatus;
  className?: string;
}) {
  const [label, color] = LIVE_CHIP[status];
  return <span className={`chip ${color} ${className}`.trim()}>{label}</span>;
}
