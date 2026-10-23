// Operator notifications (issue #78). "Unread" is the server-side delivery
// state that the Messages screen shows: a delivery to the operator that is
// still in the unread state. The browser keeps one marker, the created_at of
// the newest unread delivery that the operator has already seen. Messages at
// or before the marker do not count for the badge, the toast or the divider.

export const OPERATOR = "operator";
export const OPERATOR_SEEN_KEY = "okto-nexus-operator-seen";
export const BROWSER_NOTIFY_KEY = "okto-nexus-operator-notify";

// The views that show operator messages. Opening one of them marks the
// unread messages as seen.
export const OPERATOR_VIEWS: readonly string[] = ["Messages", "Meta-harness"];

export interface OperatorUnreadItem {
  message_id: string;
  workspace_id: string;
  from_agent_id: string;
  subject: string | null;
  preview: string;
  created_at: string;
}

export interface OperatorUnread {
  count: number;
  latest_created_at: string | null;
  items: OperatorUnreadItem[];
}

// Items that the toast logic has not reported yet.
export function newItems(
  items: OperatorUnreadItem[],
  reported: ReadonlySet<string>,
): OperatorUnreadItem[] {
  return items.filter((item) => !reported.has(item.message_id));
}

// True when a message row has an unread delivery to the operator that is
// newer than the marker (any unread delivery when there is no marker).
export function isNewForOperator(
  deliveries: { recipient_agent_id: string; status: string; created_at: string }[],
  marker: string | null | undefined,
): boolean {
  return deliveries.some(
    (delivery) =>
      delivery.recipient_agent_id === OPERATOR &&
      delivery.status === "unread" &&
      (!marker || delivery.created_at > marker),
  );
}

export function readSeenMarker(): string | null {
  try {
    return localStorage.getItem(OPERATOR_SEEN_KEY);
  } catch {
    return null;
  }
}

export function writeSeenMarker(value: string): void {
  try {
    localStorage.setItem(OPERATOR_SEEN_KEY, value);
  } catch {
    /* storage is optional */
  }
}

export function browserNotifyEnabled(): boolean {
  try {
    return (
      localStorage.getItem(BROWSER_NOTIFY_KEY) === "on" &&
      typeof Notification !== "undefined" &&
      Notification.permission === "granted"
    );
  } catch {
    return false;
  }
}

// Turn the browser notification on or off. Turning it on asks for the
// permission. Returns the state that applies after the call.
export async function setBrowserNotify(on: boolean): Promise<boolean> {
  if (!on) {
    localStorage.setItem(BROWSER_NOTIFY_KEY, "off");
    return false;
  }
  if (typeof Notification === "undefined") return false;
  const permission =
    Notification.permission === "default"
      ? await Notification.requestPermission()
      : Notification.permission;
  const granted = permission === "granted";
  localStorage.setItem(BROWSER_NOTIFY_KEY, granted ? "on" : "off");
  return granted;
}

export function toastTitle(item: OperatorUnreadItem): string {
  return `New message from ${item.from_agent_id}`;
}

export function toastText(item: OperatorUnreadItem): string {
  return item.subject || item.preview || "(no subject)";
}

// Show a browser notification for an item while the tab is in the background.
export function notifyInBackground(
  item: OperatorUnreadItem,
  onClick: () => void,
): void {
  if (!document.hidden || !browserNotifyEnabled()) return;
  const note = new Notification(toastTitle(item), {
    body: toastText(item),
    tag: item.message_id,
  });
  note.onclick = () => {
    window.focus();
    onClick();
    note.close();
  };
}
