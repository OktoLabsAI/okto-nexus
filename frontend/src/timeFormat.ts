// Shared time helpers for the dashboard. Timestamps arrive as ISO strings
// (UTC). Show them in the browser local time zone. Keep the raw ISO string
// for the title attribute.

const SHORT = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

/** Short local time, for example "Oct 23, 02:15 PM". Returns the input when it is not a date. */
export function formatTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : SHORT.format(date);
}

/** Full raw ISO string for a title attribute. Undefined when the value is empty. */
export function isoTitle(value: string | null | undefined): string | undefined {
  return value || undefined;
}

/** Milliseconds left until an ISO time. Null when the value is empty or invalid. */
export function msUntil(value: string | null | undefined, now: number): number | null {
  if (!value) return null;
  const at = new Date(value).getTime();
  return Number.isNaN(at) ? null : at - now;
}

/** Text for a remaining duration, for example "1h 05m left" or "expired". */
export function formatRemaining(ms: number): string {
  if (ms <= 0) return "expired";
  const totalMinutes = Math.floor(ms / 60000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, "0")}m left`;
  if (totalMinutes > 0) return `${totalMinutes}m left`;
  return `${Math.max(1, Math.ceil(ms / 1000))}s left`;
}
