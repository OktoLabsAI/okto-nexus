import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  Braces,
  CheckCheck,
  CheckCircle2,
  Clock,
  GitBranch,
  User,
  XCircle,
} from "lucide-react";

export type StructuredMessagePayload = Record<string, unknown> & { kind: string };

type Tone = "receipt" | "info" | "success" | "warning" | "danger" | "neutral";

interface Presentation {
  label: string;
  tone: Tone;
  icon: LucideIcon;
}

const PRESENTATIONS: Record<string, Presentation> = {
  "message.read_receipt": {
    label: "Read receipt",
    tone: "receipt",
    icon: CheckCheck,
  },
  "handoff.directed": {
    label: "Directed handoff",
    tone: "info",
    icon: ArrowRight,
  },
  "handoff.completed": {
    label: "Handoff completed",
    tone: "success",
    icon: CheckCircle2,
  },
  "handoff.rejected": {
    label: "Handoff rejected",
    tone: "danger",
    icon: XCircle,
  },
  "handoff.verification_requested": {
    label: "Verification requested",
    tone: "warning",
    icon: Bell,
  },
  "handoff.verification_failed": {
    label: "Verification failed",
    tone: "danger",
    icon: AlertTriangle,
  },
  "handoff.unblocked": {
    label: "Handoff unblocked",
    tone: "success",
    icon: GitBranch,
  },
  "handoff.dependency_failed": {
    label: "Dependency failed",
    tone: "danger",
    icon: GitBranch,
  },
};

const TONES: Record<
  Tone,
  { card: string; header: string; icon: string; badge: string; detail: string }
> = {
  receipt: {
    card: "border-sky-200/90 bg-sky-50/80 dark:border-sky-700/50 dark:bg-sky-950/35",
    header: "border-sky-200/70 dark:border-sky-700/40",
    icon: "bg-sky-100 text-sky-700 dark:bg-sky-900/60 dark:text-sky-300",
    badge: "text-sky-700 dark:text-sky-300",
    detail: "bg-white/65 dark:bg-sky-950/50",
  },
  info: {
    card: "border-violet-200/90 bg-violet-50/80 dark:border-violet-700/50 dark:bg-violet-950/30",
    header: "border-violet-200/70 dark:border-violet-700/40",
    icon: "bg-violet-100 text-violet-700 dark:bg-violet-900/60 dark:text-violet-300",
    badge: "text-violet-700 dark:text-violet-300",
    detail: "bg-white/65 dark:bg-violet-950/45",
  },
  success: {
    card: "border-emerald-200/90 bg-emerald-50/80 dark:border-emerald-700/50 dark:bg-emerald-950/30",
    header: "border-emerald-200/70 dark:border-emerald-700/40",
    icon: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-300",
    badge: "text-emerald-700 dark:text-emerald-300",
    detail: "bg-white/65 dark:bg-emerald-950/45",
  },
  warning: {
    card: "border-amber-200/90 bg-amber-50/80 dark:border-amber-700/50 dark:bg-amber-950/30",
    header: "border-amber-200/70 dark:border-amber-700/40",
    icon: "bg-amber-100 text-amber-700 dark:bg-amber-900/60 dark:text-amber-300",
    badge: "text-amber-700 dark:text-amber-300",
    detail: "bg-white/65 dark:bg-amber-950/45",
  },
  danger: {
    card: "border-rose-200/90 bg-rose-50/85 dark:border-rose-700/50 dark:bg-rose-950/30",
    header: "border-rose-200/70 dark:border-rose-700/40",
    icon: "bg-rose-100 text-rose-700 dark:bg-rose-900/60 dark:text-rose-300",
    badge: "text-rose-700 dark:text-rose-300",
    detail: "bg-white/65 dark:bg-rose-950/45",
  },
  neutral: {
    card: "border-surface-200 bg-surface-50 dark:border-surface-700 dark:bg-surface-900/70",
    header: "border-surface-200 dark:border-surface-700",
    icon: "bg-surface-200 text-surface-700 dark:bg-surface-700 dark:text-surface-200",
    badge: "text-surface-600 dark:text-surface-300",
    detail: "bg-white/70 dark:bg-surface-800/70",
  },
};

export function parseStructuredMessage(text: string): StructuredMessagePayload | null {
  if (!text.trim().startsWith("{")) return null;
  try {
    const value: unknown = JSON.parse(text);
    if (
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      typeof (value as Record<string, unknown>).kind === "string" &&
      String((value as Record<string, unknown>).kind).trim()
    ) {
      return value as StructuredMessagePayload;
    }
  } catch {
    // Malformed or ordinary prose that starts with "{" keeps the normal
    // markdown rendering path in the chat bubble.
  }
  return null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function optionalStringArray(value: unknown): Array<string | null> {
  return Array.isArray(value)
    ? value.map((item) => (typeof item === "string" ? item : null))
    : [];
}

function humanize(value: string): string {
  return value
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function shortId(value: string): string {
  if (value.length <= 22) return value;
  return `${value.slice(0, 14)}…${value.slice(-6)}`;
}

function formatTimestamp(value: string): string {
  const millis = Date.parse(value);
  if (!Number.isFinite(millis)) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(millis));
}

function Detail({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="min-w-0">
      <div className="text-[9px] font-semibold uppercase tracking-wider text-surface-400 dark:text-surface-500">
        {label}
      </div>
      <div className="mt-0.5 min-w-0 text-[11px] text-surface-700 dark:text-surface-300">
        {children}
      </div>
    </div>
  );
}

function IdValue({ value }: { value: string }) {
  return (
    <code className="font-mono text-[10px] break-all" title={value}>
      {shortId(value)}
    </code>
  );
}

function ActorValue({ value }: { value: string }) {
  return (
    <span className="inline-flex items-center gap-1 font-mono font-medium">
      <User size={11} aria-hidden="true" />
      {value}
    </span>
  );
}

function LongText({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-black/5 bg-white/60 px-2.5 py-2 dark:border-white/5 dark:bg-black/15">
      <div className="text-[9px] font-semibold uppercase tracking-wider text-surface-500 dark:text-surface-400">
        {label}
      </div>
      <div className="mt-1 whitespace-pre-wrap break-words text-[11px] leading-relaxed text-surface-700 dark:text-surface-200">
        {value}
      </div>
    </div>
  );
}

function NextStep({ value }: { value: string }) {
  return (
    <div className="flex items-start gap-1.5 rounded-lg border border-black/5 bg-white/55 px-2 py-1.5 text-[10px] leading-relaxed text-surface-600 dark:border-white/5 dark:bg-black/10 dark:text-surface-300">
      <ArrowRight size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
      <span>
        <b>Next step:</b> {value}
      </span>
    </div>
  );
}

function ReadReceiptDetails({ payload }: { payload: StructuredMessagePayload }) {
  const reader = stringValue(payload.read_by);
  const readAt = stringValue(payload.read_at);
  const messageIds = optionalStringArray(payload.message_ids);
  // Preserve array positions: the backend intentionally emits null for a
  // message without a subject, and filtering it would pair later subjects
  // with the wrong message_id.
  const subjects = optionalStringArray(payload.subjects);
  const count = Math.max(messageIds.length, subjects.length);

  return (
    <>
      <div className="grid grid-cols-2 gap-2">
        {reader && (
          <Detail label="Read by">
            <ActorValue value={reader} />
          </Detail>
        )}
        {readAt && (
          <Detail label="Read at">
            <span title={readAt}>{formatTimestamp(readAt)}</span>
          </Detail>
        )}
      </div>
      {count > 0 && (
        <div className="space-y-1">
          <div className="text-[9px] font-semibold uppercase tracking-wider text-surface-400 dark:text-surface-500">
            {count === 1 ? "Message read" : `${count} messages read`}
          </div>
          {Array.from({ length: count }, (_, index) => (
            <div
              key={messageIds[index] ?? `${subjects[index]}-${index}`}
              className="flex items-start gap-1.5 rounded-lg border border-black/5 bg-white/60 px-2 py-1.5 dark:border-white/5 dark:bg-black/10"
            >
              <CheckCheck size={12} className="mt-0.5 shrink-0 text-sky-600 dark:text-sky-300" />
              <div className="min-w-0 flex-1">
                <div className="break-words text-[10px] font-medium text-surface-700 dark:text-surface-200">
                  {subjects[index] || "(no subject)"}
                </div>
                {messageIds[index] && (
                  <div className="mt-0.5 text-surface-400 dark:text-surface-500">
                    <IdValue value={messageIds[index]} />
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function HandoffDetails({ payload }: { payload: StructuredMessagePayload }) {
  const handoffId = stringValue(payload.handoff_id);
  const fromAgent = stringValue(payload.from_agent_id);
  const actor = stringValue(payload.by_agent_id);
  const claimant = stringValue(payload.claimed_by);
  const lease = stringValue(payload.lease_expires_at);
  const unblockedBy = stringValue(payload.unblocked_by);
  const failedDependency = stringValue(payload.failed_dependency);
  const dependencyStatus = stringValue(payload.dependency_status);
  const feedback = stringValue(payload.feedback);
  const result = stringValue(payload.result);
  const reason = stringValue(payload.reason);
  const nextStep = stringValue(payload.next_step);

  return (
    <>
      <div className="grid grid-cols-2 gap-2">
        {handoffId && (
          <Detail label="Handoff">
            <IdValue value={handoffId} />
          </Detail>
        )}
        {fromAgent && (
          <Detail label="From">
            <ActorValue value={fromAgent} />
          </Detail>
        )}
        {actor && (
          <Detail label="By">
            <ActorValue value={actor} />
          </Detail>
        )}
        {claimant && (
          <Detail label="Claimed by">
            <ActorValue value={claimant} />
          </Detail>
        )}
        {unblockedBy && (
          <Detail label="Unblocked by">
            <IdValue value={unblockedBy} />
          </Detail>
        )}
        {failedDependency && (
          <Detail label="Failed dependency">
            <IdValue value={failedDependency} />
          </Detail>
        )}
        {dependencyStatus && <Detail label="Dependency status">{dependencyStatus}</Detail>}
        {lease && (
          <Detail label="Lease expires">
            <span className="inline-flex items-center gap-1" title={lease}>
              <Clock size={11} aria-hidden="true" />
              {formatTimestamp(lease)}
            </span>
          </Detail>
        )}
      </div>
      {feedback && <LongText label="Feedback" value={feedback} />}
      {result && <LongText label="Result" value={result} />}
      {reason && <LongText label="Reason" value={reason} />}
      {nextStep && <NextStep value={nextStep} />}
    </>
  );
}

function StructuredValue({
  value,
  depth = 0,
}: {
  value: unknown;
  depth?: number;
}): ReactNode {
  if (value === null || value === undefined) return <span className="text-surface-400">—</span>;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return value.toLocaleString();
  if (typeof value === "string") return <span className="whitespace-pre-wrap break-words">{value}</span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-surface-400">None</span>;
    return (
      <div className="space-y-1">
        {value.map((item, index) => (
          <div key={index} className="rounded bg-black/5 px-1.5 py-1 dark:bg-white/5">
            <StructuredValue value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }
  if (typeof value === "object") {
    if (depth >= 3) return <span className="text-surface-400">Nested details</span>;
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <span className="text-surface-400">None</span>;
    return (
      <div className="space-y-1 border-l border-surface-300 pl-2 dark:border-surface-600">
        {entries.map(([key, nested]) => (
          <div key={key}>
            <span className="mr-1 text-[9px] font-semibold uppercase tracking-wider text-surface-400">
              {humanize(key)}
            </span>
            <StructuredValue value={nested} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }
  return String(value);
}

function GenericDetails({ payload }: { payload: StructuredMessagePayload }) {
  const entries = Object.entries(payload).filter(([key]) => key !== "kind");
  if (entries.length === 0) {
    return <div className="text-[10px] text-surface-400">No additional details.</div>;
  }
  return (
    <div className="space-y-2">
      {entries.map(([key, value]) => (
        <Detail key={key} label={humanize(key)}>
          <StructuredValue value={value} />
        </Detail>
      ))}
    </div>
  );
}

export function StructuredMessage({
  payload,
  subject,
}: {
  payload: StructuredMessagePayload;
  subject?: string | null;
}) {
  const known = PRESENTATIONS[payload.kind];
  const presentation: Presentation =
    known ?? {
      label: humanize(payload.kind),
      tone: "neutral",
      icon: Braces,
    };
  const tone = TONES[presentation.tone];
  const Icon = presentation.icon;
  const status = stringValue(payload.status);
  // Only native handoff notifications use the specialised lifecycle layout.
  // A future/third-party handoff.* kind keeps every field through the generic
  // structured renderer instead of silently dropping an unfamiliar shape.
  const handoffKind = known !== undefined && payload.kind.startsWith("handoff.");

  return (
    <article
      className={`overflow-hidden rounded-xl border shadow-sm ${tone.card}`}
      data-testid="structured-message"
      data-kind={payload.kind}
    >
      <header className={`flex items-start gap-2 border-b px-2.5 py-2 ${tone.header}`}>
        <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg ${tone.icon}`}>
          <Icon size={15} aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <div className={`text-[9px] font-bold uppercase tracking-[0.14em] ${tone.badge}`}>
            {presentation.label}
          </div>
          {subject && (
            <div className="mt-0.5 break-words text-[11px] font-semibold leading-snug text-surface-800 dark:text-surface-100">
              {subject}
            </div>
          )}
        </div>
        {status && (
          <span className={`chip shrink-0 bg-white/70 dark:bg-black/20 ${tone.badge}`}>
            {status}
          </span>
        )}
      </header>
      <div className={`space-y-2.5 px-2.5 py-2 ${tone.detail}`}>
        {payload.kind === "message.read_receipt" ? (
          <ReadReceiptDetails payload={payload} />
        ) : handoffKind ? (
          <HandoffDetails payload={payload} />
        ) : (
          <GenericDetails payload={payload} />
        )}
      </div>
    </article>
  );
}
