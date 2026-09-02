import {
  ArrowDown,
  Bot,
  CheckCircle2,
  ChevronUp,
  CircleAlert,
  LoaderCircle,
  MessageSquare,
  Radio,
  Send,
  UserRound,
  Waypoints,
} from "lucide-react";
import {
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

function bodyFromPayload(payload: unknown): { subject: string | null; body: string } {
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    const value = payload as Record<string, unknown>;
    if (typeof value.body === "string") {
      return {
        subject: typeof value.subject === "string" ? value.subject : null,
        body: value.body,
      };
    }
    const legacyBody = value.request ?? value.prompt;
    if (typeof legacyBody === "string") {
      return {
        subject: typeof value.subject === "string" ? value.subject : null,
        body: legacyBody,
      };
    }
    return { subject: null, body: JSON.stringify(value, null, 2) };
  }
  if (typeof payload === "string") return { subject: null, body: payload };
  return {
    subject: null,
    body: payload == null ? "(empty handoff request)" : JSON.stringify(payload, null, 2),
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

function buildTimeline(messages: MessageRow[], handoffs: GraphHandoff[]): TimelineEntry[] {
  const rows: TimelineEntry[] = [];

  for (const message of messages) {
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
}: {
  entry: TimelineEntry;
  agents: AgentRow[];
  workspaces: WorkspaceListItem[];
  showWorkspace: boolean;
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
          {entry.status && (
            <div className={`mt-2 flex items-center gap-1 text-[10px] font-medium uppercase tracking-wider ${outgoing ? "text-white/70" : "text-surface-400 dark:text-surface-500"}`}>
              {entry.outcome === "completed" ? <CheckCircle2 size={11} /> : entry.outcome === "rejected" ? <CircleAlert size={11} /> : null}
              {entry.status}
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
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [sending, setSending] = useState(false);
  const [messagePage, setMessagePage] = useState(1);
  const [messageTotal, setMessageTotal] = useState(0);
  const [visibleCount, setVisibleCount] = useState(TIMELINE_PAGE_SIZE);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
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
        buildTimeline(messages, handoffs),
        timelineOrderRef.current,
        workspace,
      ).filter((entry) => involvedAgent(entry, filterAgent)),
    [messages, handoffs, filterAgent, workspace],
  );
  const visibleTimeline = useMemo(
    () => timeline.slice(-visibleCount),
    [timeline, visibleCount],
  );
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

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const content = body.trim();
    if (!content || !sendWorkspace || sending) return;
    if (audience === "private" && !targetAgentId) {
      setError("Choose an agent for a private turn.");
      return;
    }
    setSending(true);
    setError(null);
    try {
      await api.metaHarnessSend({
        workspace: sendWorkspace,
        kind,
        audience,
        to_agent_id: audience === "private" ? targetAgentId : undefined,
        subject: subject.trim() || undefined,
        body: content,
      });
      setSubject("");
      setBody("");
      await loadFeed();
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setSending(false);
    }
  };

  const cannotSend =
    sending ||
    !body.trim() ||
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
                  />
                ))}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

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
