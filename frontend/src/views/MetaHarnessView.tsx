import {
  ArrowDown,
  Bot,
  CheckCheck,
  CheckCircle2,
  ChevronUp,
  CircleAlert,
  Clock3,
  Download,
  FileText,
  LoaderCircle,
  MessageSquare,
  Paperclip,
  Radio,
  Send,
  X,
  UserRound,
  Waypoints,
} from "lucide-react";
import {
  type ChangeEvent,
  type FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  api,
  type AgentRow,
  type ArtifactItem,
  type GraphHandoff,
  type MessageRow,
  type MetaHarnessAudience,
  type MetaHarnessKind,
  type WorkspaceListItem,
} from "../api";
import { AgentSelect } from "../components/AgentSelect";
import { Markdown } from "../components/Markdown";
import { PageContainer } from "../components/PageContainer";
import { workspaceDisplayName } from "../components/WorkspaceNames";
import { agentColor } from "../graph/agentColor";

const OPERATOR = "operator";
const TIMELINE_PAGE_SIZE = 20;
const MAX_ATTACHMENTS = 10;
const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024;
type ReceiptDisplay = "inline" | "timeline";

type TimelineEntry = {
  id: string;
  timestamp: string;
  workspaceId: string;
  direction: "incoming" | "outgoing";
  kind: MetaHarnessKind;
  audience: MetaHarnessAudience;
  agentId: string;
  recipients: string[];
  subject: string | null;
  content: string;
  artifacts: string[];
  deliveries?: MessageRow["deliveries"];
  status?: string;
  outcome?: "completed" | "rejected";
};

type TimelineOrder = {
  scope: string;
  next: number;
  positions: Map<string, number>;
};

function targetAgent(row: MessageRow | GraphHandoff): string | undefined {
  return row.target?.strategy === "direct" ? row.target.agent_id : undefined;
}

function audienceOf(row: MessageRow | GraphHandoff): MetaHarnessAudience {
  return row.target?.strategy === "broadcast" ? "broadcast" : "private";
}

function artifactIds(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is string =>
          typeof item === "string" && Boolean(item.trim()),
      )
    : [];
}

function bodyFromPayload(payload: unknown): {
  subject: string | null;
  body: string;
  artifacts: string[];
} {
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    const value = payload as Record<string, unknown>;
    if (typeof value.body === "string") {
      return {
        subject: typeof value.subject === "string" ? value.subject : null,
        body: value.body,
        artifacts: artifactIds(value.artifacts),
      };
    }
    const legacyBody = value.request ?? value.prompt;
    if (typeof legacyBody === "string") {
      return {
        subject: typeof value.subject === "string" ? value.subject : null,
        body: legacyBody,
        artifacts: artifactIds(value.artifacts),
      };
    }
    return {
      subject: null,
      body: JSON.stringify(value, null, 2),
      artifacts: artifactIds(value.artifacts),
    };
  }
  if (typeof payload === "string") {
    return { subject: null, body: payload, artifacts: [] };
  }
  return {
    subject: null,
    body: payload == null ? "(empty handoff request)" : JSON.stringify(payload, null, 2),
    artifacts: [],
  };
}

function outcomeText(value: string): string {
  if (!value) return "(empty response)";
  try {
    const parsed = JSON.parse(value) as unknown;
    return typeof parsed === "string" ? parsed : JSON.stringify(parsed);
  } catch {
    return value;
  }
}

function humanize(key: string): string {
  return key
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function scalarText(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function structuredMarkdown(value: unknown, depth = 0): string {
  const indent = "  ".repeat(depth);
  if (Array.isArray(value)) {
    if (value.length === 0) return `${indent}- None`;
    return value
      .map((item) => {
        if (item !== null && typeof item === "object") {
          return `${indent}-\n${structuredMarkdown(item, depth + 1)}`;
        }
        return `${indent}- ${scalarText(item)}`;
      })
      .join("\n");
  }
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return `${indent}None`;
    return entries
      .map(([key, item]) => {
        const label = humanize(key);
        if (item !== null && typeof item === "object") {
          return `${indent}**${label}:**\n${structuredMarkdown(item, depth + 1)}`;
        }
        return `${indent}**${label}:** ${scalarText(item)}`;
      })
      .join("\n\n");
  }
  return `${indent}${scalarText(value)}`;
}

function formatChatContent(text: string): string {
  const trimmed = text.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return text;
  try {
    return structuredMarkdown(JSON.parse(trimmed) as unknown);
  } catch {
    return text;
  }
}

function involvedAgent(entry: TimelineEntry, agentId: string): boolean {
  if (!agentId) return true;
  if (entry.agentId === agentId || entry.recipients.includes(agentId)) return true;
  return entry.audience === "broadcast";
}

function isReadReceiptMessage(message: MessageRow): boolean {
  const body = message.body ?? message.preview;
  try {
    const payload = JSON.parse(body) as unknown;
    return (
      payload !== null &&
      typeof payload === "object" &&
      !Array.isArray(payload) &&
      (payload as Record<string, unknown>).kind === "message.read_receipt"
    );
  } catch {
    return false;
  }
}

function buildTimeline(
  messages: MessageRow[],
  handoffs: GraphHandoff[],
  receiptDisplay: ReceiptDisplay,
): TimelineEntry[] {
  const rows: TimelineEntry[] = [];

  for (const message of messages) {
    if (receiptDisplay === "inline" && isReadReceiptMessage(message)) continue;
    const outgoing = message.from_agent_id === OPERATOR;
    const recipients = message.deliveries.map((delivery) => delivery.recipient_agent_id);
    const directTarget = targetAgent(message);
    rows.push({
      id: `message:${message.message_id}`,
      timestamp: message.created_at,
      workspaceId: message.workspace_id,
      direction: outgoing ? "outgoing" : "incoming",
      kind: "message",
      audience: audienceOf(message),
      agentId: outgoing ? OPERATOR : message.from_agent_id,
      recipients: recipients.length ? recipients : directTarget ? [directTarget] : [],
      subject: message.subject,
      content: message.body ?? message.preview,
      artifacts: artifactIds(message.artifacts),
      deliveries: outgoing ? message.deliveries : undefined,
      status: outgoing
        ? recipients.length
          ? `${recipients.length} recipient${recipients.length === 1 ? "" : "s"}`
          : "no recipient"
        : undefined,
    });
  }

  for (const handoff of handoffs) {
    const request = bodyFromPayload(handoff.payload);
    const directTarget = targetAgent(handoff);
    const recipients = directTarget ? [directTarget] : handoff.claimed_by ? [handoff.claimed_by] : [];
    rows.push({
      id: `handoff:${handoff.handoff_id}:0-request`,
      timestamp: handoff.created_at,
      workspaceId: handoff.workspace_id,
      direction: "outgoing",
      kind: "handoff",
      audience: audienceOf(handoff),
      agentId: OPERATOR,
      recipients,
      subject: request.subject,
      content: request.body,
      artifacts: request.artifacts,
      status: handoff.status,
    });

    if (handoff.result != null || handoff.rejected_reason != null) {
      const rejected = handoff.rejected_reason != null;
      rows.push({
        id: `handoff:${handoff.handoff_id}:1-outcome`,
        timestamp:
          handoff.updated_at &&
          new Date(handoff.updated_at).getTime() >= new Date(handoff.created_at).getTime()
            ? handoff.updated_at
            : handoff.created_at,
        workspaceId: handoff.workspace_id,
        direction: "incoming",
        kind: "handoff",
        audience: audienceOf(handoff),
        agentId: handoff.claimed_by || directTarget || "agent",
        recipients: [OPERATOR],
        subject: rejected ? "Handoff rejected" : "Handoff completed",
        content: rejected
          ? handoff.rejected_reason || "(no reason provided)"
          : outcomeText(handoff.result || ""),
        status: handoff.status,
        artifacts: [],
        outcome: rejected ? "rejected" : "completed",
      });
    }
  }

  return rows.sort(
    (a, b) =>
      new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime() ||
      a.id.localeCompare(b.id),
  );
}

function isAcknowledged(delivery: MessageRow["deliveries"][number]): boolean {
  return delivery.status === "read" || Boolean(delivery.read_at);
}

function fullStamp(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function receiptState(delivery: MessageRow["deliveries"][number]): string {
  if (isAcknowledged(delivery)) return "Acknowledged";
  if (delivery.status === "delivered") return "Received · awaiting acknowledgement";
  if (delivery.status === "parked") return "Parked · awaiting acknowledgement";
  return "Waiting for receipt";
}

function ReceiptStatusFlag({
  deliveries,
  onOpen,
}: {
  deliveries: MessageRow["deliveries"];
  onOpen: () => void;
}) {
  const acknowledged = deliveries.filter(isAcknowledged).length;
  const complete = deliveries.length > 0 && acknowledged === deliveries.length;
  const label = complete
    ? `All ${deliveries.length} recipients acknowledged this message`
    : `${acknowledged} of ${deliveries.length} recipients acknowledged this message`;
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`inline-flex items-center gap-1 border-0 bg-transparent p-0 text-[10px] font-semibold normal-case tracking-normal transition-opacity hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white/70 ${
        complete
          ? "text-emerald-100 drop-shadow-[0_0_4px_rgba(52,211,153,0.85)]"
          : "text-surface-300"
      }`}
      aria-label={`${label}. Open details.`}
      title={`${label}. Click for details.`}
      data-testid="meta-harness-receipt-status"
    >
      <CheckCheck size={13} aria-hidden="true" />
      <span>{acknowledged}/{deliveries.length} ack</span>
    </button>
  );
}

function ReceiptDetailsModal({
  entry,
  agents,
  onClose,
}: {
  entry: TimelineEntry;
  agents: AgentRow[];
  onClose: () => void;
}) {
  const deliveries = entry.deliveries ?? [];
  const acknowledged = deliveries.filter(isAcknowledged);
  const pending = deliveries.filter((delivery) => !isAcknowledged(delivery));
  const complete = deliveries.length > 0 && pending.length === 0;

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/45 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="receipt-details-title"
      data-testid="meta-harness-receipt-modal"
    >
      <div className="flex max-h-[min(720px,90vh)] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-surface-200 bg-white shadow-2xl dark:border-surface-700 dark:bg-surface-900">
        <header className="flex items-start gap-3 border-b border-surface-200 px-5 py-4 dark:border-surface-700">
          <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${complete ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300" : "bg-surface-100 text-surface-500 dark:bg-surface-800 dark:text-surface-300"}`}>
            <CheckCheck size={20} />
          </span>
          <div className="min-w-0 flex-1">
            <h3 id="receipt-details-title" className="font-display text-sm font-semibold text-surface-900 dark:text-surface-100">
              Delivery and read receipts
            </h3>
            <p className="mt-0.5 text-xs text-surface-500 dark:text-surface-400">
              {acknowledged.length} of {deliveries.length} target{deliveries.length === 1 ? "" : "s"} acknowledged this message.
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-surface-400 hover:bg-surface-100 hover:text-surface-700 dark:hover:bg-surface-800 dark:hover:text-surface-200" aria-label="Close receipt details">
            <X size={17} />
          </button>
        </header>

        {!complete && pending.length > 0 && (
          <div className="border-b border-surface-200 bg-surface-50 px-5 py-3 text-xs text-surface-600 dark:border-surface-700 dark:bg-surface-950/50 dark:text-surface-300">
            <span className="font-semibold">Waiting for acknowledgement from:</span>{" "}
            <span className="font-mono">{pending.map((delivery) => delivery.recipient_agent_id).join(", ")}</span>
          </div>
        )}

        <div className="min-h-0 overflow-y-auto p-4">
          <div className="space-y-2">
            {deliveries.map((delivery) => {
              const read = isAcknowledged(delivery);
              const profile = agents.find((agent) => agent.agent_id === delivery.recipient_agent_id);
              return (
                <div key={delivery.delivery_id} className="rounded-xl border border-surface-200 px-4 py-3 dark:border-surface-700">
                  <div className="flex items-center gap-3">
                    <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full ${read ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300" : "bg-surface-100 text-surface-500 dark:bg-surface-800 dark:text-surface-300"}`}>
                      {read ? <CheckCircle2 size={16} /> : <Clock3 size={16} />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-mono text-xs font-semibold text-surface-800 dark:text-surface-100">
                        {delivery.recipient_agent_id}
                      </div>
                      {profile?.role && <div className="truncate text-[11px] text-surface-400">{profile.role}</div>}
                    </div>
                    <span className={`chip ${read ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300" : "bg-surface-100 text-surface-600 dark:bg-surface-800 dark:text-surface-300"}`}>
                      {receiptState(delivery)}
                    </span>
                  </div>
                  <dl className="mt-3 grid grid-cols-1 gap-2 border-t border-surface-100 pt-3 text-[11px] sm:grid-cols-3 dark:border-surface-800">
                    <div><dt className="text-surface-400">Queued</dt><dd className="mt-0.5 text-surface-700 dark:text-surface-200">{fullStamp(delivery.created_at)}</dd></div>
                    <div><dt className="text-surface-400">Received</dt><dd className="mt-0.5 text-surface-700 dark:text-surface-200">{fullStamp(delivery.delivered_at)}</dd></div>
                    <div><dt className="text-surface-400">Acknowledged</dt><dd className="mt-0.5 text-surface-700 dark:text-surface-200">{fullStamp(delivery.read_at)}</dd></div>
                  </dl>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

function preserveArrivalOrder(
  entries: TimelineEntry[],
  order: TimelineOrder,
  scope: string,
): TimelineEntry[] {
  if (order.scope !== scope) {
    order.scope = scope;
    order.next = 0;
    order.positions.clear();
  }

  // The first hydration is already chronological. Entries discovered by later
  // refreshes receive the next position so a live chat turn never jumps above
  // content that was already visible because of clock skew between producers.
  for (const entry of entries) {
    if (!order.positions.has(entry.id)) {
      order.positions.set(entry.id, order.next);
      order.next += 1;
    }
  }

  return [...entries].sort(
    (a, b) => (order.positions.get(a.id) ?? 0) - (order.positions.get(b.id) ?? 0),
  );
}

function mergeMessages(current: MessageRow[], incoming: MessageRow[]): MessageRow[] {
  const merged = new Map(current.map((message) => [message.message_id, message]));
  for (const message of incoming) merged.set(message.message_id, message);
  return [...merged.values()];
}

function shortWorkspace(id: string, workspaces: WorkspaceListItem[]): string {
  const index = workspaces.findIndex((workspace) => workspace.workspace_id === id);
  return index >= 0 ? workspaceDisplayName(workspaces[index], index) : id.slice(0, 8);
}

function stamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

type PendingAttachment = {
  id: string;
  file: File;
  artifact?: ArtifactItem;
};

function ChoiceButton({
  active,
  onClick,
  icon,
  children,
  testId,
}: {
  active: boolean;
  onClick: () => void;
  icon: ReactNode;
  children: ReactNode;
  testId: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      aria-pressed={active}
      className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
        active
          ? "bg-surface-900 text-white dark:bg-white dark:text-surface-900"
          : "text-surface-500 hover:bg-surface-100 dark:text-surface-400 dark:hover:bg-surface-800"
      }`}
    >
      {icon}
      {children}
    </button>
  );
}

function ChatTurn({
  entry,
  agents,
  workspaces,
  showWorkspace,
  artifactDetails,
  onDownloadArtifact,
  showReceiptFlags,
  onOpenReceipt,
}: {
  entry: TimelineEntry;
  agents: AgentRow[];
  workspaces: WorkspaceListItem[];
  showWorkspace: boolean;
  artifactDetails: Record<string, ArtifactItem>;
  onDownloadArtifact: (workspaceId: string, artifactId: string) => void;
  showReceiptFlags: boolean;
  onOpenReceipt: (entry: TimelineEntry) => void;
}) {
  const outgoing = entry.direction === "outgoing";
  const identity = outgoing ? OPERATOR : entry.agentId;
  const profile = agents.find((agent) => agent.agent_id === identity);
  const color = outgoing ? "#0284c7" : agentColor(identity, profile?.color);
  const audienceLabel = !outgoing
    ? "to You"
    : entry.audience === "broadcast"
      ? "Broadcast"
      : entry.recipients.length
        ? `to ${entry.recipients.join(", ")}`
        : "Private";

  return (
    <article
      className={`flex gap-3 ${outgoing ? "justify-end" : "justify-start"}`}
      data-testid={`meta-harness-turn-${entry.id.replaceAll(":", "-")}`}
    >
      {!outgoing && (
        <div
          className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-full text-xs font-semibold text-white shadow-sm"
          style={{ backgroundColor: color }}
          title={identity}
        >
          {identity.slice(0, 2).toUpperCase()}
        </div>
      )}
      <div className={`min-w-0 max-w-[min(78%,760px)] ${outgoing ? "items-end" : "items-start"} flex flex-col`}>
        <div className="mb-1 flex flex-wrap items-center gap-1.5 px-1 text-[11px] text-surface-400 dark:text-surface-500">
          <span className="font-mono font-medium text-surface-600 dark:text-surface-300">
            {outgoing ? "You" : identity}
          </span>
          <span>·</span>
          <span className={`chip ${entry.kind === "handoff" ? "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300" : "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"}`}>
            {entry.kind}
          </span>
          <span>{audienceLabel}</span>
          {showWorkspace && <span>· {shortWorkspace(entry.workspaceId, workspaces)}</span>}
          <span>· {stamp(entry.timestamp)}</span>
        </div>
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
            outgoing
              ? "rounded-br-md bg-accent-600 text-white"
              : entry.outcome === "rejected"
                ? "rounded-bl-md border border-red-200 bg-red-50 text-red-950 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-100"
                : entry.outcome === "completed"
                  ? "rounded-bl-md border border-emerald-200 bg-emerald-50 text-emerald-950 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-100"
                  : "rounded-bl-md border border-surface-200 bg-white text-surface-800 dark:border-surface-700 dark:bg-surface-800 dark:text-surface-100"
          }`}
        >
          {entry.subject && (
            <div className={`mb-1.5 text-xs font-semibold ${outgoing ? "text-white/80" : "text-surface-500 dark:text-surface-400"}`}>
              {entry.subject}
            </div>
          )}
          <Markdown text={formatChatContent(entry.content)} />
          {entry.artifacts.length > 0 && (
            <div
              className="mt-3 flex flex-wrap gap-2"
              data-testid="meta-harness-turn-artifacts"
            >
              {entry.artifacts.map((artifactId) => {
                const detail = artifactDetails[artifactId];
                const label = detail?.name || detail?.filename || artifactId;
                return (
                  <button
                    key={artifactId}
                    type="button"
                    onClick={() => onDownloadArtifact(entry.workspaceId, artifactId)}
                    title={`Download ${label}`}
                    className={`inline-flex max-w-full items-center gap-2 rounded-lg border px-2.5 py-2 text-left text-xs transition-colors ${
                      outgoing
                        ? "border-white/25 bg-white/10 text-white hover:bg-white/20"
                        : "border-surface-200 bg-surface-50 text-surface-700 hover:border-accent-300 dark:border-surface-600 dark:bg-surface-900/60 dark:text-surface-200"
                    }`}
                  >
                    <FileText size={15} className="shrink-0" />
                    <span className="min-w-0">
                      <span className="block truncate font-medium">
                        {label}
                      </span>
                      <span className={outgoing ? "text-white/65" : "text-surface-400"}>
                        {detail
                          ? `${humanize(detail.artifact_type)} · ${formatBytes(detail.size_bytes)}`
                          : "Artifact"}
                      </span>
                    </span>
                    <Download size={13} className="shrink-0 opacity-70" />
                  </button>
                );
              })}
            </div>
          )}
          {entry.status && (
            <div className={`mt-2 flex items-center justify-between gap-2 text-[10px] font-medium uppercase tracking-wider ${outgoing ? "text-white/70" : "text-surface-400 dark:text-surface-500"}`}>
              <span className="inline-flex items-center gap-1">
                {entry.outcome === "completed" ? <CheckCircle2 size={11} /> : entry.outcome === "rejected" ? <CircleAlert size={11} /> : null}
                {entry.status}
              </span>
              {showReceiptFlags && outgoing && entry.kind === "message" && Boolean(entry.deliveries?.length) && (
                <ReceiptStatusFlag deliveries={entry.deliveries ?? []} onOpen={() => onOpenReceipt(entry)} />
              )}
            </div>
          )}
        </div>
      </div>
      {outgoing && (
        <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent-600 text-white shadow-sm" title="operator">
          <UserRound size={15} />
        </div>
      )}
    </article>
  );
}

export function MetaHarnessView({
  workspace,
  workspaces,
  liveTick,
}: {
  workspace: string;
  workspaces: WorkspaceListItem[];
  liveTick?: number;
}) {
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [messages, setMessages] = useState<MessageRow[]>([]);
  const [handoffs, setHandoffs] = useState<GraphHandoff[]>([]);
  const [filterAgent, setFilterAgent] = useState("");
  const [targetAgentId, setTargetAgentId] = useState("");
  const [sendWorkspace, setSendWorkspace] = useState("");
  const [kind, setKind] = useState<MetaHarnessKind>("message");
  const [audience, setAudience] = useState<MetaHarnessAudience>("private");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [artifactDetails, setArtifactDetails] = useState<
    Record<string, ArtifactItem>
  >({});
  const [receiptDisplay, setReceiptDisplay] = useState<ReceiptDisplay>("inline");
  const [receiptEntry, setReceiptEntry] = useState<TimelineEntry | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [sending, setSending] = useState(false);
  const [messagePage, setMessagePage] = useState(1);
  const [messageTotal, setMessageTotal] = useState(0);
  const [visibleCount, setVisibleCount] = useState(TIMELINE_PAGE_SIZE);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const timelineRef = useRef<HTMLDivElement>(null);
  const feedScopeRef = useRef(workspace);
  const preserveScrollRef = useRef(false);
  const timelineOrderRef = useRef<TimelineOrder>({
    scope: workspace,
    next: 0,
    positions: new Map(),
  });

  const availableAgents = useMemo(
    () => agents.filter((agent) => agent.agent_id !== OPERATOR && agent.is_active),
    [agents],
  );
  const filterAgents = useMemo(
    () => agents.filter((agent) => agent.agent_id !== OPERATOR),
    [agents],
  );

  useEffect(() => {
    api
      .agents()
      .then(({ items }) => {
        setAgents(items);
        setTargetAgentId((current) => current || items.find((item) => item.agent_id !== OPERATOR && item.is_active)?.agent_id || "");
      })
      .catch((exc) => setError((exc as Error).message));
  }, []);

  useEffect(() => {
    api
      .settings()
      .then(({ items }) => {
        const value = items.find(
          (item) => item.key === "meta_harness_receipt_display",
        )?.value;
        const next: ReceiptDisplay = value === "timeline" ? "timeline" : "inline";
        timelineOrderRef.current.positions.clear();
        timelineOrderRef.current.next = 0;
        setReceiptDisplay(next);
      })
      .catch(() => {
        // A settings read failure must not blank the conversation; the new
        // inline presentation is the safe documented default.
        setReceiptDisplay("inline");
      });
  }, []);

  useEffect(() => {
    if (workspace !== "all") {
      setSendWorkspace(workspace);
      return;
    }
    setSendWorkspace((current) =>
      current && workspaces.some((item) => item.workspace_id === current)
        ? current
        : workspaces[0]?.workspace_id || "",
    );
  }, [workspace, workspaces]);

  const loadFeed = useCallback(async () => {
    const scopeChanged = feedScopeRef.current !== workspace;
    const params: Record<string, string> = {
      agent: OPERATOR,
      page: "1",
      page_size: String(TIMELINE_PAGE_SIZE),
      include_body: "true",
    };
    const scopedWorkspace = workspace === "all" ? undefined : workspace;
    if (scopedWorkspace) params.workspace = scopedWorkspace;
    try {
      const [messagePage, handoffPage] = await Promise.all([
        api.messages(params),
        api.handoffs(scopedWorkspace, { from_agent: OPERATOR }),
      ]);
      if (scopeChanged) {
        feedScopeRef.current = workspace;
        setMessages(messagePage.items);
        setMessagePage(1);
        setVisibleCount(TIMELINE_PAGE_SIZE);
      } else {
        setMessages((current) => mergeMessages(current, messagePage.items));
      }
      setMessageTotal(messagePage.total);
      setHandoffs(handoffPage.items);
      setError(null);
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setLoading(false);
    }
  }, [workspace]);

  useEffect(() => {
    setLoading(true);
    loadFeed();
  }, [loadFeed]);

  useEffect(() => {
    if (!liveTick) return;
    const timer = window.setTimeout(loadFeed, 450);
    return () => window.clearTimeout(timer);
  }, [liveTick, loadFeed]);

  const timeline = useMemo(
    () =>
      preserveArrivalOrder(
        buildTimeline(messages, handoffs, receiptDisplay),
        timelineOrderRef.current,
        workspace,
      ).filter((entry) => involvedAgent(entry, filterAgent)),
    [messages, handoffs, receiptDisplay, filterAgent, workspace],
  );
  const visibleTimeline = useMemo(
    () => timeline.slice(-visibleCount),
    [timeline, visibleCount],
  );
  const visibleArtifactRefs = useMemo(() => {
    const refs = new Map<string, string>();
    for (const entry of visibleTimeline) {
      for (const artifactId of entry.artifacts) {
        if (!refs.has(artifactId)) refs.set(artifactId, entry.workspaceId);
      }
    }
    return refs;
  }, [visibleTimeline]);
  const hasOlderMessages =
    visibleCount < timeline.length || messages.length < messageTotal;

  useEffect(() => {
    setVisibleCount(TIMELINE_PAGE_SIZE);
  }, [filterAgent, workspace]);

  useEffect(() => {
    if (preserveScrollRef.current) {
      preserveScrollRef.current = false;
      return;
    }
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [visibleTimeline.length, workspace, filterAgent]);

  useEffect(() => {
    const missing = [...visibleArtifactRefs].filter(
      ([artifactId]) => !artifactDetails[artifactId],
    );
    if (!missing.length) return;
    let active = true;
    void Promise.allSettled(
      missing.map(async ([artifactId, workspaceId]) => {
        const detail = await api.artifactDetail(workspaceId, artifactId, false);
        return [artifactId, detail] as const;
      }),
    ).then((results) => {
      if (!active) return;
      if (!results.some((result) => result.status === "fulfilled")) return;
      setArtifactDetails((current) => {
        const next = { ...current };
        for (const result of results) {
          if (result.status === "fulfilled") next[result.value[0]] = result.value[1];
        }
        return next;
      });
    });
    return () => {
      active = false;
    };
  }, [artifactDetails, visibleArtifactRefs]);

  const loadMoreMessages = async () => {
    if (loadingMore || !hasOlderMessages) return;
    const scroller = timelineRef.current;
    const previousHeight = scroller?.scrollHeight ?? 0;
    const previousTop = scroller?.scrollTop ?? 0;
    preserveScrollRef.current = true;
    setLoadingMore(true);

    try {
      const hiddenLoaded = Math.max(0, timeline.length - visibleCount);
      if (hiddenLoaded < TIMELINE_PAGE_SIZE && messages.length < messageTotal) {
        const nextPage = messagePage + 1;
        const params: Record<string, string> = {
          agent: OPERATOR,
          page: String(nextPage),
          page_size: String(TIMELINE_PAGE_SIZE),
          include_body: "true",
        };
        if (workspace !== "all") params.workspace = workspace;
        const page = await api.messages(params);

        // History backfill belongs at its real chronological position. Clear
        // first-seen ordering before merging; subsequent live entries will
        // again append without jumping around.
        timelineOrderRef.current.positions.clear();
        timelineOrderRef.current.next = 0;
        setMessages((current) => mergeMessages(current, page.items));
        setMessagePage(nextPage);
        setMessageTotal(page.total);
      }
      setVisibleCount((current) => current + TIMELINE_PAGE_SIZE);
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => {
          const currentScroller = timelineRef.current;
          if (currentScroller) {
            currentScroller.scrollTop =
              previousTop + (currentScroller.scrollHeight - previousHeight);
          }
        });
      });
    } catch (exc) {
      preserveScrollRef.current = false;
      setError((exc as Error).message);
    } finally {
      setLoadingMore(false);
    }
  };

  // OpenAI-style composer: one line at rest, growing with content up to eight
  // lines before its own scrollbar appears.
  useEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    input.style.height = "auto";
    const computed = window.getComputedStyle(input);
    const lineHeight = Number.parseFloat(computed.lineHeight) || 20;
    const verticalPadding =
      (Number.parseFloat(computed.paddingTop) || 0) +
      (Number.parseFloat(computed.paddingBottom) || 0);
    const maxHeight = lineHeight * 8 + verticalPadding;
    input.style.height = `${Math.min(input.scrollHeight, maxHeight)}px`;
    input.style.overflowY = input.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [body]);

  const selectAttachments = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!selected.length) return;
    const oversized = selected.filter((file) => file.size > MAX_ATTACHMENT_BYTES);
    const valid = selected.filter((file) => file.size <= MAX_ATTACHMENT_BYTES);
    const available = Math.max(0, MAX_ATTACHMENTS - attachments.length);
    const errors: string[] = [];
    if (oversized.length) {
      errors.push(
        `${oversized.map((file) => file.name).join(", ")} exceeded the 25 MB limit`,
      );
    }
    if (valid.length > available) {
      errors.push(`a turn can include up to ${MAX_ATTACHMENTS} attachments`);
    }
    setError(errors.length ? `${errors.join("; ")}.` : null);
    setAttachments((current) => [
      ...current,
      ...valid.slice(0, available).map((file) => ({
        id: `${file.name}:${file.size}:${file.lastModified}:${crypto.randomUUID()}`,
        file,
      })),
    ]);
  };

  const downloadArtifact = async (workspaceId: string, artifactId: string) => {
    try {
      const blob = await api.artifactBlob(workspaceId, artifactId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = artifactDetails[artifactId]?.filename || artifactId;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (exc) {
      setError((exc as Error).message);
    }
  };

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const content = body.trim();
    if ((!content && !attachments.length) || !sendWorkspace || sending) return;
    if (audience === "private" && !targetAgentId) {
      setError("Choose an agent for a private turn.");
      return;
    }
    setSending(true);
    setError(null);
    try {
      let staged = [...attachments];
      for (const attachment of staged) {
        if (attachment.artifact?.workspace_id === sendWorkspace) continue;
        const artifact = await api.uploadMetaHarnessArtifact(
          sendWorkspace,
          attachment.file,
        );
        staged = staged.map((item) =>
          item.id === attachment.id ? { ...item, artifact } : item,
        );
        setAttachments(staged);
        setArtifactDetails((current) => ({
          ...current,
          [artifact.artifact_id]: artifact,
        }));
      }
      const artifactIds = staged
        .map((attachment) => attachment.artifact?.artifact_id)
        .filter((artifactId): artifactId is string => Boolean(artifactId));
      const deliveredBody =
        content ||
        `Attached ${artifactIds.length === 1 ? "1 document" : `${artifactIds.length} documents`}: ${staged
          .map((attachment) => attachment.file.name)
          .join(", ")}.`;
      await api.metaHarnessSend({
        workspace: sendWorkspace,
        kind,
        audience,
        to_agent_id: audience === "private" ? targetAgentId : undefined,
        subject: subject.trim() || undefined,
        body: deliveredBody,
        artifact_ids: artifactIds,
      });
      setSubject("");
      setBody("");
      setAttachments([]);
      await loadFeed();
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setSending(false);
    }
  };

  const cannotSend =
    sending ||
    (!body.trim() && !attachments.length) ||
    !sendWorkspace ||
    (audience === "private" && !targetAgentId);

  return (
    <PageContainer width="bleed" scroll="none" testId="meta-harness-view">
      <div className="flex h-full min-h-0 flex-col bg-white dark:bg-surface-950">
        <header className="shrink-0 border-b border-surface-200/70 bg-white/90 px-5 py-3 backdrop-blur dark:border-surface-800 dark:bg-surface-950/90">
          <div className="mx-auto flex max-w-5xl items-center gap-4">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-nexus-blue to-nexus-violet text-white shadow-glow-violet">
              <Bot size={20} />
            </div>
            <div className="min-w-0">
              <h2 className="font-display text-base font-semibold text-surface-900 dark:text-white">Meta-harness</h2>
              <p className="truncate text-xs text-surface-500 dark:text-surface-400">Talk to agents and follow message or handoff outcomes in one timeline.</p>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <span className="hidden text-[11px] text-surface-400 sm:inline">Show conversation with</span>
              <AgentSelect
                value={filterAgent}
                onChange={setFilterAgent}
                agents={filterAgents}
                placeholder="all agents"
                label="Agent"
              />
            </div>
          </div>
        </header>

        <div
          ref={timelineRef}
          className="min-h-0 flex-1 overflow-y-auto"
          data-testid="meta-harness-timeline"
        >
          <div className="mx-auto flex min-h-full max-w-5xl flex-col px-4 py-6 sm:px-6">
            {loading ? (
              <div className="grid flex-1 place-items-center text-sm text-surface-400">
                <LoaderCircle className="animate-spin" size={22} />
              </div>
            ) : timeline.length === 0 ? (
              <div className="grid flex-1 place-items-center py-16 text-center">
                <div>
                  <div className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-2xl bg-surface-100 text-surface-400 dark:bg-surface-900 dark:text-surface-500">
                    <MessageSquare size={22} />
                  </div>
                  <h3 className="font-display text-sm font-semibold text-surface-700 dark:text-surface-200">Start a conversation</h3>
                  <p className="mt-1 max-w-sm text-xs text-surface-400 dark:text-surface-500">Choose a delivery type and audience below. Agent replies and handoff results will appear here automatically.</p>
                </div>
              </div>
            ) : (
              <div className="mt-auto space-y-6">
                {hasOlderMessages && (
                  <div className="flex justify-center pb-1">
                    <button
                      type="button"
                      onClick={() => void loadMoreMessages()}
                      disabled={loadingMore}
                      className="inline-flex items-center gap-2 rounded-full border border-surface-200 bg-white px-3 py-1.5 text-xs font-medium text-surface-600 shadow-sm transition-colors hover:border-accent-300 hover:text-accent-600 disabled:cursor-wait disabled:opacity-60 dark:border-surface-700 dark:bg-surface-900 dark:text-surface-300 dark:hover:border-accent-700 dark:hover:text-accent-300"
                      aria-label="Load more messages"
                      data-testid="meta-harness-load-more"
                    >
                      {loadingMore ? (
                        <LoaderCircle className="animate-spin" size={14} />
                      ) : (
                        <ChevronUp size={14} />
                      )}
                      {loadingMore ? "Loading messages…" : "Load more messages"}
                    </button>
                  </div>
                )}
                {visibleTimeline.map((entry) => (
                  <ChatTurn
                    key={entry.id}
                    entry={entry}
                    agents={agents}
                    workspaces={workspaces}
                    showWorkspace={workspace === "all"}
                    artifactDetails={artifactDetails}
                    onDownloadArtifact={(workspaceId, artifactId) => {
                      void downloadArtifact(workspaceId, artifactId);
                    }}
                    showReceiptFlags={receiptDisplay === "inline"}
                    onOpenReceipt={setReceiptEntry}
                  />
                ))}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>
        {receiptEntry && (
          <ReceiptDetailsModal
            entry={receiptEntry}
            agents={agents}
            onClose={() => setReceiptEntry(null)}
          />
        )}

        <div className="shrink-0 border-t border-white bg-white px-4 py-3 dark:border-surface-950 dark:bg-surface-950">
          <form onSubmit={submit} className="mx-auto max-w-5xl" data-testid="meta-harness-composer">
            {error && (
              <div className="mb-2 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300" role="alert">
                <CircleAlert size={14} />
                {error}
              </div>
            )}
            <div className="rounded-2xl border border-surface-200 bg-white p-2 shadow-card transition-shadow focus-within:shadow-card-hover dark:border-surface-700 dark:bg-surface-800 dark:shadow-card-dark">
              <div className="flex items-center gap-2 border-b border-surface-100 px-2 dark:border-surface-700">
                <label htmlFor="meta-harness-subject" className="shrink-0 text-xs font-medium text-surface-500 dark:text-surface-400">
                  Subject
                </label>
                <input
                  id="meta-harness-subject"
                  value={subject}
                  onChange={(event) => setSubject(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      inputRef.current?.focus();
                    }
                  }}
                  placeholder="Add a subject (optional)"
                  className="min-w-0 flex-1 bg-transparent py-2 text-sm text-surface-800 outline-none placeholder:text-surface-400 dark:text-surface-100"
                />
              </div>
              {attachments.length > 0 && (
                <div
                  className="flex flex-wrap gap-2 px-2 pt-2"
                  data-testid="meta-harness-attachments"
                >
                  {attachments.map((attachment) => (
                    <div
                      key={attachment.id}
                      className="flex min-w-0 max-w-full items-center gap-2 rounded-lg bg-surface-100 px-2.5 py-2 text-xs text-surface-700 dark:bg-surface-900 dark:text-surface-200"
                    >
                      {sending && !attachment.artifact ? (
                        <LoaderCircle
                          size={14}
                          className="shrink-0 animate-spin text-accent-500"
                        />
                      ) : (
                        <FileText size={14} className="shrink-0 text-accent-500" />
                      )}
                      <span className="min-w-0">
                        <span className="block max-w-56 truncate font-medium">
                          {attachment.file.name}
                        </span>
                        <span className="text-[10px] text-surface-400">
                          {attachment.artifact
                            ? "Ready as artifact"
                            : formatBytes(attachment.file.size)}
                        </span>
                      </span>
                      <button
                        type="button"
                        onClick={() =>
                          setAttachments((current) =>
                            current.filter((item) => item.id !== attachment.id),
                          )
                        }
                        disabled={sending}
                        aria-label={`Remove ${attachment.file.name}`}
                        className="rounded p-0.5 text-surface-400 hover:bg-surface-200 hover:text-surface-700 disabled:opacity-40 dark:hover:bg-surface-700 dark:hover:text-surface-100"
                      >
                        <X size={13} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <textarea
                ref={inputRef}
                value={body}
                onChange={(event) => setBody(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void submit();
                  }
                }}
                placeholder={kind === "handoff" ? "Describe the work to delegate…" : "Message an agent…"}
                aria-label="Message"
                rows={1}
                className="max-h-[176px] min-h-[36px] w-full resize-none bg-transparent px-2 py-2 text-sm leading-5 text-surface-800 outline-none placeholder:text-surface-400 dark:text-surface-100"
              />
              <div className="flex flex-wrap items-center gap-2 border-t border-surface-100 pt-2 dark:border-surface-700">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  onChange={selectAttachments}
                  className="hidden"
                  data-testid="meta-harness-file-input"
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={sending || attachments.length >= MAX_ATTACHMENTS}
                  aria-label="Attach documents"
                  title={`Attach up to ${MAX_ATTACHMENTS} documents (25 MB each)`}
                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-surface-500 transition-colors hover:bg-surface-100 hover:text-accent-600 disabled:cursor-not-allowed disabled:opacity-40 dark:text-surface-400 dark:hover:bg-surface-700 dark:hover:text-accent-300"
                  data-testid="meta-harness-attach"
                >
                  <Paperclip size={15} />
                </button>
                <div className="flex rounded-xl bg-surface-50 p-0.5 dark:bg-surface-900" aria-label="Delivery type">
                  <ChoiceButton active={kind === "message"} onClick={() => setKind("message")} icon={<MessageSquare size={13} />} testId="meta-kind-message">Message</ChoiceButton>
                  <ChoiceButton active={kind === "handoff"} onClick={() => setKind("handoff")} icon={<Waypoints size={13} />} testId="meta-kind-handoff">Handoff</ChoiceButton>
                </div>
                <div className="flex rounded-xl bg-surface-50 p-0.5 dark:bg-surface-900" aria-label="Audience">
                  <ChoiceButton active={audience === "private"} onClick={() => setAudience("private")} icon={<UserRound size={13} />} testId="meta-audience-private">Private</ChoiceButton>
                  <ChoiceButton active={audience === "broadcast"} onClick={() => setAudience("broadcast")} icon={<Radio size={13} />} testId="meta-audience-broadcast">Broadcast</ChoiceButton>
                </div>
                {audience === "private" && (
                  <AgentSelect
                    value={targetAgentId}
                    onChange={setTargetAgentId}
                    agents={availableAgents}
                    placeholder="choose agent"
                    label="To"
                    allowEmpty={false}
                    menuPlacement="top"
                  />
                )}
                {workspace === "all" && (
                  <select
                    value={sendWorkspace}
                    onChange={(event) => setSendWorkspace(event.target.value)}
                    aria-label="Send workspace"
                    className="rounded-lg border border-surface-200 bg-white px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-accent-500/40 dark:border-surface-700 dark:bg-surface-800"
                  >
                    {workspaces.length === 0 && <option value="">No workspace available</option>}
                    {workspaces.map((item) => (
                      <option key={item.workspace_id} value={item.workspace_id}>
                        {shortWorkspace(item.workspace_id, workspaces)}
                      </option>
                    ))}
                  </select>
                )}
                <span className="hidden min-w-0 flex-1 truncate text-[11px] text-surface-400 lg:block">
                  {kind === "handoff" && audience === "broadcast"
                    ? "All eligible agents can see it; the first claim wins."
                    : audience === "broadcast"
                      ? "Delivered to agents currently present in this workspace."
                      : kind === "handoff"
                        ? "The selected agent receives claimable work."
                        : "A direct private message to the selected agent."}
                </span>
                <button
                  type="submit"
                  disabled={cannotSend}
                  className="btn btn-primary ml-auto !rounded-xl !px-3 disabled:cursor-not-allowed disabled:opacity-40"
                  aria-label="Send turn"
                  data-testid="meta-harness-send"
                >
                  {sending ? <LoaderCircle className="animate-spin" size={15} /> : <Send size={15} />}
                  <span className="hidden sm:inline">Send</span>
                </button>
              </div>
            </div>
            <div className="mt-1.5 flex items-center justify-center gap-1 text-[10px] text-surface-400 dark:text-surface-500">
              <ArrowDown size={10} /> Enter to send · Shift+Enter for a new line
            </div>
          </form>
        </div>
      </div>
    </PageContainer>
  );
}
