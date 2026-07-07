import type { ReactNode } from "react";
import type {
  RoutingStrategy,
  RoutingTarget,
  TagExpression,
  TagMap,
  TagSelector,
} from "../api";
import { normalizeExpressions, normalizeTagMap, scopeSelector } from "../tags";

const STRATEGY_LABEL: Record<RoutingStrategy, string> = {
  direct: "Direct",
  capability: "Capability",
  role: "Role",
  tag: "Tag selector",
  broadcast: "Broadcast",
  mixed: "Mixed",
  direct_with_fallback: "Direct with fallback",
};

const CHIP =
  "chip bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300";
const VALUE_CHIP =
  "inline-flex items-center rounded-md bg-surface-100 dark:bg-surface-800 border border-surface-200 dark:border-surface-700 px-1.5 py-0.5 font-mono text-[11px] text-surface-700 dark:text-surface-200";

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function recordOf(target: unknown): Record<string, unknown> | null {
  if (isRecord(target)) return target;
  if (typeof target !== "string" || !target.trim().startsWith("{")) return null;
  try {
    const parsed = JSON.parse(target) as unknown;
    return isRecord(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function strategyOf(target: unknown): RoutingStrategy | string | null {
  const record = recordOf(target);
  const raw = record?.strategy ?? record?.kind;
  if (typeof raw !== "string" || !raw.trim()) return null;
  return raw.trim().toLowerCase().replace(/[-\s]+/g, "_");
}

function stringField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" && value.trim() ? value : "?";
}

function numberField(record: Record<string, unknown>, key: string): number | null {
  const value = record[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function listOfStrings(value: unknown): string[] {
  if (typeof value === "string" && value.trim()) return [value];
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && !!item);
}

function plural(count: number, singular: string, pluralName = `${singular}s`) {
  return count === 1 ? singular : pluralName;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "?";
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (mins < 60) return rest ? `${mins}m ${rest}s` : `${mins}m`;
  const hours = Math.floor(mins / 60);
  const minRest = mins % 60;
  return minRest ? `${hours}h ${minRest}m` : `${hours}h`;
}

export function targetSummary(target: unknown, emptyLabel = "—"): string {
  const record = recordOf(target);
  const strategy = strategyOf(target);
  if (!record || !strategy) return emptyLabel;

  switch (strategy) {
    case "direct":
      return `direct → ${stringField(record, "agent_id")}`;
    case "capability": {
      const names = listOfStrings(record.capability);
      return names.length
        ? `capability: ${names.join(" or ")}`
        : "capability: ?";
    }
    case "role":
      return `role: ${stringField(record, "role")}`;
    case "tag":
      return "tag selector";
    case "broadcast":
      return "broadcast";
    case "mixed": {
      const rules = rulesOf(record);
      return `mixed: ${rules.length} ${plural(rules.length, "rule")}`;
    }
    case "direct_with_fallback":
      return `direct → ${stringField(record, "agent_id")} · fallback after ${formatDuration(
        numberField(record, "fallback_after_seconds"),
      )}`;
    default:
      return String(strategy);
  }
}

function rulesOf(record: Record<string, unknown>): unknown[] {
  const raw = record.rules ?? record.targets;
  return Array.isArray(raw) ? raw : [];
}

function fallbackOf(record: Record<string, unknown>): unknown {
  return record.fallback ?? { strategy: "broadcast" satisfies RoutingStrategy };
}

function valueText(value: unknown): string {
  if (typeof value === "string") return value || "—";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    const values = value
      .map((item) =>
        typeof item === "string" || typeof item === "number" || typeof item === "boolean"
          ? String(item)
          : null,
      )
      .filter((item): item is string => item !== null);
    return values.length ? values.join(", ") : "structured list";
  }
  if (value == null) return "—";
  return "structured value";
}

function Field({
  label,
  children,
  mono = false,
}: {
  label: string;
  children: ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
        {label}
      </div>
      <div
        className={`mt-0.5 break-all text-surface-700 dark:text-surface-200 ${
          mono ? "font-mono" : ""
        }`}
      >
        {children}
      </div>
    </div>
  );
}

function ValuePills({ values }: { values: string[] }) {
  if (!values.length) return <span className="text-surface-400">?</span>;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {values.map((value) => (
        <span key={value} className={VALUE_CHIP}>
          {value}
        </span>
      ))}
    </span>
  );
}

function SelectorView({ selector }: { selector: unknown }) {
  const effective = scopeSelector(selector);
  if (!effective) {
    return <p className="text-xs text-surface-400">empty selector</p>;
  }
  if (Array.isArray(effective)) {
    const expressions = normalizeExpressions(effective);
    return (
      <div className="space-y-1.5">
        {expressions.map((expression, index) => (
          <ExpressionRow key={`${expression.key}-${index}`} expression={expression} />
        ))}
      </div>
    );
  }
  const map = normalizeTagMap(effective);
  return (
    <div className="space-y-1.5">
      {Object.entries(map).map(([key, values]) => (
        <div
          key={key}
          className="flex flex-wrap items-center gap-1.5 text-xs text-surface-600 dark:text-surface-300"
        >
          <span className="font-mono text-surface-500 dark:text-surface-400">
            {key}
          </span>
          <span className="text-surface-400">is any of</span>
          <ValuePills values={values} />
        </div>
      ))}
    </div>
  );
}

function ExpressionRow({ expression }: { expression: TagExpression }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs text-surface-600 dark:text-surface-300">
      <span className="font-mono text-surface-500 dark:text-surface-400">
        {expression.key}
      </span>
      <span className="text-surface-400">{expression.operator}</span>
      {(expression.values ?? []).length > 0 && (
        <ValuePills values={expression.values ?? []} />
      )}
    </div>
  );
}

function TargetShell({
  strategy,
  children,
  depth,
  testId,
}: {
  strategy: string;
  children: ReactNode;
  depth: number;
  testId?: string;
}) {
  return (
    <div
      className={`rounded-lg border border-surface-200 dark:border-surface-700 bg-white/50 dark:bg-surface-900/40 p-3 ${
        depth ? "mt-2" : ""
      }`}
      data-testid={testId}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className={CHIP}>{strategy}</span>
      </div>
      {children}
    </div>
  );
}

function UnknownTarget({
  target,
  depth,
}: {
  target: unknown;
  depth: number;
}) {
  const record = recordOf(target);
  const strategy = strategyOf(target);
  if (!record) {
    return (
      <TargetShell strategy="Unrecognized" depth={depth}>
        <Field label="value" mono>
          {valueText(target)}
        </Field>
      </TargetShell>
    );
  }
  const fields = Object.entries(record).filter(
    ([key]) => key !== "strategy" && key !== "kind",
  );
  return (
    <TargetShell strategy={strategy ? `Unknown: ${strategy}` : "Unknown"} depth={depth}>
      {fields.length ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {fields.map(([key, value]) => (
            <Field key={key} label={key} mono>
              {valueText(value)}
            </Field>
          ))}
        </div>
      ) : (
        <p className="text-xs text-surface-400">no fields</p>
      )}
    </TargetShell>
  );
}

function TargetNode({
  target,
  depth,
}: {
  target: unknown;
  depth: number;
}) {
  const record = recordOf(target);
  const strategy = strategyOf(target);
  if (!record || !strategy) return <UnknownTarget target={target} depth={depth} />;

  switch (strategy) {
    case "direct":
      return (
        <TargetShell strategy={STRATEGY_LABEL.direct} depth={depth}>
          <Field label="agent" mono>
            {stringField(record, "agent_id")}
          </Field>
        </TargetShell>
      );
    case "capability": {
      const names = listOfStrings(record.capability);
      return (
        <TargetShell strategy={STRATEGY_LABEL.capability} depth={depth}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="capability">
              <ValuePills values={names} />
            </Field>
            {typeof record.preferred === "string" && (
              <Field label="preferred" mono>
                {record.preferred}
              </Field>
            )}
          </div>
        </TargetShell>
      );
    }
    case "role":
      return (
        <TargetShell strategy={STRATEGY_LABEL.role} depth={depth}>
          <Field label="role" mono>
            {stringField(record, "role")}
          </Field>
        </TargetShell>
      );
    case "tag":
      return (
        <TargetShell strategy={STRATEGY_LABEL.tag} depth={depth}>
          <Field label="selector">
            <SelectorView selector={record.selector} />
          </Field>
        </TargetShell>
      );
    case "broadcast":
      return (
        <TargetShell strategy={STRATEGY_LABEL.broadcast} depth={depth}>
          <Field label="audience">all eligible workspace agents</Field>
        </TargetShell>
      );
    case "mixed": {
      const rules = rulesOf(record);
      return (
        <TargetShell strategy={STRATEGY_LABEL.mixed} depth={depth}>
          <div className="space-y-2">
            <Field label="match logic">any rule</Field>
            {rules.map((rule, index) => (
              <div key={index}>
                <div className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
                  rule {index + 1}
                </div>
                <TargetNode target={rule} depth={depth + 1} />
              </div>
            ))}
            {rules.length === 0 && (
              <p className="text-xs text-surface-400">no rules</p>
            )}
          </div>
        </TargetShell>
      );
    }
    case "direct_with_fallback":
      return (
        <TargetShell strategy={STRATEGY_LABEL.direct_with_fallback} depth={depth}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="primary agent" mono>
              {stringField(record, "agent_id")}
            </Field>
            <Field label="fallback after" mono>
              {formatDuration(numberField(record, "fallback_after_seconds"))}
            </Field>
          </div>
          <div className="mt-3">
            <div className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
              fallback target
            </div>
            <TargetNode target={fallbackOf(record)} depth={depth + 1} />
          </div>
        </TargetShell>
      );
    default:
      return <UnknownTarget target={target} depth={depth} />;
  }
}

export function TargetDescriptor({
  target,
  testId,
}: {
  target: RoutingTarget | unknown;
  testId?: string;
}) {
  return (
    <div data-testid={testId}>
      <TargetNode target={target} depth={0} />
    </div>
  );
}

export function targetCapabilityNames(target: unknown): string[] {
  const record = recordOf(target);
  return strategyOf(target) === "capability" && record
    ? listOfStrings(record.capability)
    : [];
}

export function targetSelector(target: unknown): TagSelector | null {
  const record = recordOf(target);
  return strategyOf(target) === "tag" && record ? scopeSelector(record.selector) : null;
}

export function targetStrategy(target: unknown): RoutingStrategy | string | null {
  return strategyOf(target);
}
