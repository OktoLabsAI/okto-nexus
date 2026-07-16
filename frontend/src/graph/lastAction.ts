// Pure helpers for the home-graph entity card's body (spec 5e1fa07c, card C2).
//
// The graph payload gives each node a `last_action: {type, at} | null` — the
// raw event type (e.g. "message.created") and its ISO stamp. The card renders
// a human label plus a relative-time reference ("Sent a message · 2 minutes
// ago"). Both functions are PURE (no clock, no DOM) so they can be unit-tested
// and re-run on a tick without side effects.

// Curated map from the canonical event vocabulary to a short, past-tense
// action phrase (dashboard copy is English). The type vocabulary is OPEN — any
// `<noun>.<verb>` a slice emits is valid — so anything not listed here falls
// through to prettifyType() rather than being dropped.
const ACTION_LABELS: Record<string, string> = {
  // messages
  "message.created": "Sent a message",
  "message.delivered": "Received a message",
  "message.read": "Read a message",
  "message.read_receipt": "Read receipt",
  // sessions
  "session.opened": "Opened a session",
  "session.heartbeat": "Heartbeat",
  "session.closed": "Closed session",
  "session.reaped": "Session reaped",
  // handoffs
  "handoff.created": "Created a handoff",
  "handoff.claimed": "Claimed a handoff",
  "handoff.completed": "Completed a handoff",
  "handoff.rejected": "Rejected a handoff",
  "handoff.cancelled": "Cancelled a handoff",
  "handoff.expired": "Handoff expired",
  "handoff.verification_requested": "Requested verification",
  "handoff.verification_failed": "Verification failed",
  "handoff.unblocked": "Handoff unblocked",
  "handoff.dependency_failed": "Dependency failed",
  // governance / approvals
  "governance.denied": "Action denied",
  "approval.requested": "Requested approval",
  "approval.granted": "Granted approval",
  "approval.denied": "Denied approval",
};

// Turn an unmapped raw type into readable copy: split on "." and "_", join
// with spaces, sentence-case. "task.completed" -> "Task completed";
// "agent.custom_verb" -> "Agent custom verb". Empty/garbage -> "Activity".
function prettifyType(type: string): string {
  const words = type.split(/[._]/).filter(Boolean).join(" ").trim();
  if (!words) return "Activity";
  return words.charAt(0).toUpperCase() + words.slice(1);
}

// The card's action label for a raw event type.
export function actionLabel(type: string): string {
  if (!type) return "Activity";
  return ACTION_LABELS[type] ?? prettifyType(type);
}

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

function plural(n: number, unit: string): string {
  return `${n} ${unit}${n === 1 ? "" : "s"} ago`;
}

// Relative-time reference for an ISO stamp, capped at days (the operator asked
// for "x seconds/minutes/hours/days ago"). `nowMs` is injected (Date.now() at
// the call site / tick) so the function stays pure and testable. Unparseable
// stamps -> "unknown time"; future stamps (clock skew) -> "just now".
export function relativeTime(atIso: string, nowMs: number): string {
  const then = Date.parse(atIso);
  if (!Number.isFinite(then)) return "unknown time";
  const seconds = Math.floor((nowMs - then) / 1000);
  if (seconds < 1) return "just now";
  if (seconds < MINUTE) return plural(seconds, "second");
  if (seconds < HOUR) return plural(Math.floor(seconds / MINUTE), "minute");
  if (seconds < DAY) return plural(Math.floor(seconds / HOUR), "hour");
  return plural(Math.floor(seconds / DAY), "day");
}
