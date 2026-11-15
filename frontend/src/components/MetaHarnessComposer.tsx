import {useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent, type ReactNode} from 'react';
import {ArrowDown, CircleAlert, FileText, LoaderCircle, MessageSquare, Paperclip, Radio, Send, UserRound, Waypoints, X} from 'lucide-react';
import {api, ApiError, type AgentRow, type ArtifactItem, type MetaHarnessAudience, type MetaHarnessKind, type MetaHarnessSendResult, type WorkspaceListItem} from '../api';
import {AgentSelect} from './AgentSelect';
import {workspaceDisplayName} from './WorkspaceNames';
import {useAgentModalGuard, useAgentModalChanges} from './AgentActionModal';
const OPERATOR = 'operator';
const MAX_ATTACHMENTS = 10;
const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024;
function shortWorkspace(id: string, workspaces: WorkspaceListItem[]): string {
  const index = workspaces.findIndex((workspace) => workspace.workspace_id === id);
  return index >= 0 ? workspaceDisplayName(workspaces[index], index) : id.slice(0, 8);
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


/** The same composer serves Meta-harness and Home; sends remain canonical operator actions. */
export function MetaHarnessComposer({workspace, workspaces, agents, onSent, onArtifact, onDirtyChange}: {
  workspace: string; workspaces: WorkspaceListItem[]; agents: AgentRow[];
  onSent: () => void | Promise<void>; onArtifact?: (artifact: ArtifactItem) => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [targetAgentId, setTargetAgentId] = useState("");
  const [sendWorkspace, setSendWorkspace] = useState("");
  const [recipientNamespaces, setRecipientNamespaces] = useState<{agent: string; ids: string[]} | null>(null);
  const [namespaceError, setNamespaceError] = useState<string | null>(null);
  const [kind, setKind] = useState<MetaHarnessKind>("message");
  const [audience, setAudience] = useState<MetaHarnessAudience>("private");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [sending, setSending] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [receipt, setReceipt] = useState<MetaHarnessSendResult | null>(null);
  const lifetime = useRef({active:true});
  useEffect(() => {
    const selected = {active:true};lifetime.current = selected;
    const invalidate = () => {selected.active = false;};
    window.addEventListener('nexus-auth-expired', invalidate);
    window.addEventListener('nexus-operator-logout', invalidate);
    return () => {invalidate();window.removeEventListener('nexus-auth-expired', invalidate);window.removeEventListener('nexus-operator-logout', invalidate);};
  }, []);
  const sendingLock = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const availableAgents = useMemo(
    () => agents.filter((agent) => agent.agent_id !== OPERATOR && agent.is_active),
    [agents],
  );

  const changes = useAgentModalChanges();
  const dirty = !!subject.trim() || !!body.trim() || attachments.length > 0;
  useAgentModalGuard(dirty, sending);
  useEffect(() => {onDirtyChange?.(dirty); return () => onDirtyChange?.(false);}, [dirty, onDirtyChange]);
  useEffect(() => {
    if (audience === "private") return;
    if (workspace !== "all") {
      setSendWorkspace(workspace);
      return;
    }
    setSendWorkspace((current) =>
      current && workspaces.some((item) => item.workspace_id === current)
        ? current
        : workspaces[0]?.workspace_id || "",
    );
  }, [workspace, workspaces, audience]);

  useEffect(() => {
    if (audience !== "private" || !targetAgentId) return;
    let active = true;
    let refresh: ReturnType<typeof setTimeout>;
    let controller: AbortController;
    setRecipientNamespaces(null);
    setNamespaceError(null);
    const loadNamespaces = async () => {
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        const { items } = await api.metaHarnessWorkspaces(targetAgentId, controller.signal);
        if (!active) return;
        const ids = items.map((item) => item.workspace_id);
        setRecipientNamespaces({agent: targetAgentId, ids});
        setNamespaceError(null);
        setSendWorkspace((current) => ids.includes(current) ? current : ids.includes(workspace) ? workspace : ids[0] || "");
      } catch (exc) {
        if (active) setNamespaceError(controller.signal.aborted
          ? "Namespace request timed out. Retrying automatically…" : (exc as Error).message);
      } finally {
        clearTimeout(timeout);
        if (active) refresh = setTimeout(loadNamespaces, 10000);
      }
    };
    void loadNamespaces();
    return () => { active = false; clearTimeout(refresh); controller?.abort(); };
  }, [targetAgentId, audience, workspace]);

  const namespacesReady = audience !== "private" || recipientNamespaces?.agent === targetAgentId;
  const sendWorkspaces = audience === "private"
    ? workspaces.filter((item) => namespacesReady && recipientNamespaces?.ids.includes(item.workspace_id))
    : workspaces;
  const validSendWorkspace = namespacesReady && sendWorkspaces.some((item) => item.workspace_id === sendWorkspace);
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
  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const content = body.trim();
    if ((!content && !attachments.length) || !validSendWorkspace || sendingLock.current || uncertain || !lifetime.current.active) return;
    if (audience === "private" && !targetAgentId) {
      setError("Choose an agent for a private turn.");
      return;
    }
    sendingLock.current = true;
    setSending(true);
    setError(null);
    const selected = lifetime.current, current = () => selected.active && lifetime.current === selected;
    let attempted = false, confirmed = false;
    try {
      let staged = [...attachments];
      for (const attachment of staged) {
        if (!current()) return;
        if (attachment.artifact?.workspace_id === sendWorkspace) continue;
        const artifact = await api.uploadMetaHarnessArtifact(
          sendWorkspace,
          attachment.file,
        );
        if (!current()) return;
        staged = staged.map((item) =>
          item.id === attachment.id ? { ...item, artifact } : item,
        );
        setAttachments(staged);
        onArtifact?.(artifact);
      }
      const artifactIds = staged
        .map((attachment) => attachment.artifact?.artifact_id)
        .filter((artifactId): artifactId is string => Boolean(artifactId));
      const deliveredBody =
        content ||
        `Attached ${artifactIds.length === 1 ? "1 document" : `${artifactIds.length} documents`}: ${staged
          .map((attachment) => attachment.file.name)
          .join(", ")}.`;
      if (!current()) return;
      attempted = true;
      const result = await api.metaHarnessSend({
        workspace: sendWorkspace,
        kind,
        audience,
        to_agent_id: audience === "private" ? targetAgentId : undefined,
        subject: subject.trim() || undefined,
        body: deliveredBody,
        artifact_ids: artifactIds,
      });
      if (!current()) return;
      confirmed = true;setReceipt(result);
      setSubject("");
      setBody("");
      setAttachments([]);
      if (result.runtime_rejections?.length) {
        setError(result.runtime_rejections.map((item) => `${item.recipient_agent_id}: ${item.message}`).join("\n"));
      }
      changes?.reset();
      await onSent();
    } catch (exc) {
      if (!current()) return;
      if (attempted && !confirmed && !(exc instanceof ApiError && exc.status >= 400 && exc.status < 500)) setUncertain(true);
      setError((exc as Error).message);
    } finally {
      sendingLock.current = false;
      if (current()) setSending(false);
    }
  };

  const cannotSend =
    sending || uncertain ||
    (!body.trim() && !attachments.length) ||
    !validSendWorkspace ||
    (audience === "private" && !targetAgentId);

return (
          <form onSubmit={submit} className="mx-auto max-w-5xl" data-testid="meta-harness-composer" aria-busy={sending}>
            {receipt && <div role="status" className="text-sm mb-3 space-y-1"><p>Canonical {receipt.kind} recorded{receipt.status ? ` · ${receipt.status}` : ''}.</p>
              <p className="text-xs break-all">{receipt.handoff_id || receipt.message_id || receipt.approval_id || 'Review the canonical receipt.'}</p>
              <p className="text-xs text-surface-500">Recording or delivery does not confirm execution or completion.</p></div>}
            {uncertain && <p role="alert" className="text-sm mb-3">Delivery is unconfirmed. Inspect the canonical message or handoff before making another request. This composer will not resend it.</p>}
            <fieldset disabled={sending || uncertain}>
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
                {(workspace === "all" || audience === "private") && (
                  <select
                    value={sendWorkspace}
                    onChange={(event) => setSendWorkspace(event.target.value)}
                    aria-label="Send namespace"
                    disabled={!namespacesReady || sendWorkspaces.length === 0}
                    title="Namespaces available for the selected agent"
                    className="rounded-lg border border-surface-200 bg-white px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-accent-500/40 dark:border-surface-700 dark:bg-surface-800"
                  >
                    {sendWorkspaces.length === 0 && <option value="">{namespaceError ? "Could not load namespaces" : !namespacesReady ? "Loading namespaces…" : "No namespace available"}</option>}
                    {sendWorkspaces.map((item) => (
                      <option key={item.workspace_id} value={item.workspace_id}>
                        {shortWorkspace(item.workspace_id, workspaces)} · {item.workspace_id.slice(-8)}
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
            </fieldset>
          </form>

);
}
