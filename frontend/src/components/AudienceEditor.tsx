// Reusable audience (comm_scope) editing primitives (F1+F2+F3 / sm_188b58c0),
// extracted from AgentTagsEditor so BOTH the agent editor and the policy
// catalog can drive the SAME catalog-only pickers, the same Simple/Expressions
// modes and the same "absence trap" guard. Every key/value is PICKED from the
// central Tag Registry — no free-form input, so the fail-closed existence gate
// on write can only trip on registry races. A persisted selector that is NOT
// representable as simple conditions auto-promotes its leg to Expressions mode.
// Nothing here talks to the API: the owner composes the CommScope and persists.

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, ChevronDown, Eye, X } from "lucide-react";
import {
  type AgentRow,
  type CommScope,
  type TagExpression,
  type TagKeyRow,
  type TagMap,
  type TagOperator,
  type TagSelector,
} from "../api";
import {
  normalizeExpressions,
  normalizeTagMap,
  scopeSelector,
  selectorMatches,
  toFlatMap,
} from "../tags";

const PICK_ITEM =
  "w-full text-left px-2.5 py-1.5 text-xs hover:bg-accent-50 dark:hover:bg-accent-900/20 text-surface-700 dark:text-surface-200";
const PICK_ITEM_DISABLED =
  "w-full text-left px-2.5 py-1.5 text-xs text-surface-300 dark:text-surface-600 cursor-not-allowed";

// The shared audience chip styling (green — distinct from the accent tag chip).
export const AUDIENCE_CHIP =
  "inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/50 font-mono";

// A registry-backed dropdown: a trigger button + a panel listing ONLY
// registered entries (used entries render disabled). The footer reminds the
// operator that growing the vocabulary happens in the Registry. Exported:
// the capability picker (CapabilityPicker) reuses it for the same
// catalog-only guarantee.
export function Picker({
  trigger,
  header,
  items,
  footer,
  filterable = false,
  onPick,
}: {
  trigger: ReactNode;
  header: string;
  items: { id: string; label: ReactNode; disabled?: boolean }[];
  footer: string;
  filterable?: boolean;
  onPick: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const q = query.trim().toLowerCase();
  const visible = q ? items.filter((i) => i.id.toLowerCase().includes(q)) : items;

  return (
    <span className="relative inline-flex" ref={ref}>
      <button
        type="button"
        className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md border border-dashed border-surface-300 dark:border-surface-600 text-surface-500 dark:text-surface-400 hover:text-surface-700 dark:hover:text-surface-200 hover:border-surface-400"
        onClick={() => {
          setOpen((o) => !o);
          setQuery("");
        }}
      >
        {trigger} <ChevronDown size={11} />
      </button>
      {open && (
        <div className="absolute left-0 top-full mt-1 z-30 w-56 rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 shadow-xl overflow-hidden">
          <div className="px-2.5 py-1.5 text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500 border-b border-surface-100 dark:border-surface-700">
            {header}
          </div>
          {filterable && (
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter registered keys…"
              className="w-full bg-transparent border-b border-surface-100 dark:border-surface-700 px-2.5 py-1.5 text-xs focus:outline-none"
            />
          )}
          <div className="max-h-48 overflow-y-auto">
            {visible.map((item) =>
              item.disabled ? (
                <button key={item.id} className={PICK_ITEM_DISABLED} disabled>
                  {item.label}
                </button>
              ) : (
                <button
                  key={item.id}
                  className={PICK_ITEM}
                  onClick={() => {
                    onPick(item.id);
                    setOpen(false);
                  }}
                >
                  {item.label}
                </button>
              ),
            )}
            {visible.length === 0 && (
              <div className="px-2.5 py-2 text-xs text-surface-400">no match</div>
            )}
          </div>
          <div className="px-2.5 py-1.5 text-[11px] text-surface-400 dark:text-surface-500 border-t border-surface-100 dark:border-surface-700">
            {footer}
          </div>
        </div>
      )}
    </span>
  );
}

export function OperatorOnlyBadge() {
  return (
    <span className="chip bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
      Operator-only
    </span>
  );
}

// One key row of a TagMap editor: value chips (removable) + a "+ value"
// picker constrained to that key's registered values.
export function KeyRow({
  keyName,
  values,
  registered,
  chipCls,
  onAdd,
  onRemoveValue,
  onRemoveKey,
}: {
  keyName: string;
  values: string[];
  registered: TagKeyRow | undefined;
  chipCls: string;
  onAdd: (value: string) => void;
  onRemoveValue: (value: string) => void;
  onRemoveKey?: () => void;
}) {
  const available = (registered?.values ?? []).map((v) => ({
    id: v.value,
    label: values.includes(v.value) ? `${v.value} — already added` : v.value,
    disabled: values.includes(v.value),
  }));
  return (
    <div className="flex items-start gap-3">
      <span className="w-28 shrink-0 mt-1 text-xs font-mono text-surface-500 dark:text-surface-400 text-right truncate" title={keyName}>
        {keyName}
      </span>
      <div className="flex flex-wrap gap-1.5 flex-1 items-center">
        {values.map((value) => (
          <span key={value} className={chipCls}>
            {value}
            <button
              className="opacity-70 hover:opacity-100"
              onClick={() => onRemoveValue(value)}
              title={`Remove ${keyName}=${value}`}
            >
              <X size={11} />
            </button>
          </span>
        ))}
        <Picker
          trigger="+ value"
          header={`Registered values — ${keyName}`}
          items={available}
          footer="Missing a value? Add it in the Tag Registry."
          onPick={onAdd}
        />
        {onRemoveKey && (
          <button
            className="ml-auto text-surface-400 hover:text-red-500 text-xs"
            onClick={onRemoveKey}
            title={`Remove the ${keyName} condition`}
          >
            <X size={13} />
          </button>
        )}
      </div>
    </div>
  );
}

const TAG_OPERATORS: TagOperator[] = ["In", "NotIn", "Exists", "DoesNotExist"];
const PRESENCE_OPERATORS: TagOperator[] = ["Exists", "DoesNotExist"];
const ABSENCE_OPERATORS: TagOperator[] = ["NotIn", "DoesNotExist"];

// One match-expression row of the Expressions mode: key (fixed at add time),
// operator dropdown, and — for In/NotIn — registry-constrained value chips.
function ExpressionRow({
  expression,
  registered,
  chipCls,
  onChange,
  onRemove,
}: {
  expression: TagExpression;
  registered: TagKeyRow | undefined;
  chipCls: string;
  onChange: (next: TagExpression) => void;
  onRemove: () => void;
}) {
  const presence = PRESENCE_OPERATORS.includes(expression.operator);
  const values = expression.values ?? [];
  const incomplete = !presence && values.length === 0;
  const available = (registered?.values ?? []).map((v) => ({
    id: v.value,
    label: values.includes(v.value) ? `${v.value} — already added` : v.value,
    disabled: values.includes(v.value),
  }));
  return (
    <div
      className={`flex items-start gap-2 rounded-lg border px-3 py-2 ${
        incomplete
          ? "border-amber-300 dark:border-amber-700/60 bg-amber-50/50 dark:bg-amber-900/10"
          : "border-surface-200 dark:border-surface-700 bg-surface-50/60 dark:bg-surface-900/60"
      }`}
    >
      <span className="w-28 shrink-0 mt-1.5 text-xs font-mono text-surface-500 dark:text-surface-400 text-right truncate" title={expression.key}>
        {expression.key}
      </span>
      <select
        className="shrink-0 text-xs font-mono rounded-md border border-surface-300 dark:border-surface-600 bg-white dark:bg-surface-800 px-1.5 py-1 text-surface-700 dark:text-surface-200"
        value={expression.operator}
        onChange={(e) => {
          const operator = e.target.value as TagOperator;
          onChange(
            PRESENCE_OPERATORS.includes(operator)
              ? { key: expression.key, operator }
              : { key: expression.key, operator, values },
          );
        }}
      >
        {TAG_OPERATORS.map((op) => (
          <option key={op} value={op}>
            {op}
          </option>
        ))}
      </select>
      <div className="flex flex-wrap gap-1.5 flex-1 items-center min-h-[26px]">
        {presence ? (
          <span className="text-xs text-surface-400 dark:text-surface-500 mt-1">
            presence check — no values
          </span>
        ) : (
          <>
            {values.map((value) => (
              <span key={value} className={chipCls}>
                {value}
                <button
                  className="opacity-70 hover:opacity-100"
                  onClick={() =>
                    onChange({
                      ...expression,
                      values: values.filter((x) => x !== value),
                    })
                  }
                  title={`Remove ${expression.key}=${value}`}
                >
                  <X size={11} />
                </button>
              </span>
            ))}
            <Picker
              trigger="+ value"
              header={`Registered values — ${expression.key}`}
              items={available}
              footer="Missing a value? Add it in the Tag Registry."
              onPick={(v) => onChange({ ...expression, values: [...values, v] })}
            />
            {incomplete && (
              <span className="text-[11px] text-amber-600 dark:text-amber-400">
                {expression.operator} needs at least one value
              </span>
            )}
          </>
        )}
        <button
          className="ml-auto text-surface-400 hover:text-red-500 text-xs"
          onClick={onRemove}
          title={`Remove the ${expression.key} expression`}
        >
          <X size={13} />
        </button>
      </div>
    </div>
  );
}

// The per-leg editing state: the F1 flat map (Simple) or the F3 expression
// list (Expressions). A leg whose persisted selector cannot be expressed as
// a flat map opens in the Expressions mode.
export type LegState =
  | { mode: "simple"; map: TagMap }
  | { mode: "advanced"; expressions: TagExpression[] };

export function initLeg(raw: TagSelector | null): LegState {
  if (Array.isArray(raw)) {
    const expressions = normalizeExpressions(raw);
    const flat = toFlatMap(expressions);
    return flat
      ? { mode: "simple", map: flat }
      : { mode: "advanced", expressions };
  }
  return { mode: "simple", map: raw ? normalizeTagMap(raw) : {} };
}

// The selector this leg would persist right now (null = unrestricted).
export function legSelector(leg: LegState): TagSelector | null {
  if (leg.mode === "simple") {
    const complete = Object.fromEntries(
      Object.entries(leg.map).filter(([, values]) => values.length > 0),
    );
    return Object.keys(complete).length ? complete : null;
  }
  return leg.expressions.length ? leg.expressions : null;
}

// In/NotIn rows without values cannot be saved (the server rejects them).
export function legIncomplete(leg: LegState): boolean {
  if (leg.mode === "simple") {
    return Object.values(leg.map).some((values) => values.length === 0);
  }
  return leg.expressions.some(
    (e) =>
      !PRESENCE_OPERATORS.includes(e.operator) && (e.values ?? []).length === 0,
  );
}

// One audience leg (outbound or inbound): mode toggle + condition rows +
// key picker + a live-preview slot. The two legs share IDENTICAL editing
// semantics (registry-only vocabulary on both modes) — only the copy and
// the preview direction differ, so they stay in the caller.
export function AudienceLegEditor({
  title,
  blurb,
  leg,
  setLeg,
  byKey,
  catalog,
  simpleKeyItems,
  chipCls,
  preview,
  children,
}: {
  title: string;
  blurb: ReactNode;
  leg: LegState;
  setLeg: (fn: (cur: LegState) => LegState) => void;
  byKey: Map<string, TagKeyRow>;
  catalog: TagKeyRow[];
  simpleKeyItems: { id: string; label: ReactNode; disabled?: boolean }[];
  chipCls: string;
  preview: ReactNode;
  children?: ReactNode;
}) {
  const patchSimple = (
    key: string,
    mutate: (values: string[]) => string[] | null,
    options: { keepEmpty?: boolean } = {},
  ) =>
    setLeg((cur) => {
      if (cur.mode !== "simple") return cur;
      const next = { ...cur.map };
      const mutated = mutate(next[key] ?? []);
      if (mutated === null || (!options.keepEmpty && mutated.length === 0)) {
        delete next[key];
      } else {
        next[key] = mutated;
      }
      return { mode: "simple", map: next };
    });

  const patchExpression = (index: number, next: TagExpression | null) =>
    setLeg((cur) => {
      if (cur.mode !== "advanced") return cur;
      const expressions =
        next === null
          ? cur.expressions.filter((_, i) => i !== index)
          : cur.expressions.map((e, i) => (i === index ? next : e));
      return { mode: "advanced", expressions };
    });

  const flatEquivalent =
    leg.mode === "advanced" ? toFlatMap(leg.expressions) : null;
  const hasAbsenceOperator =
    leg.mode === "advanced" &&
    leg.expressions.some((e) => ABSENCE_OPERATORS.includes(e.operator));
  // Expression keys are NOT deduplicated: composing two expressions on one
  // key (Exists + NotIn = "has the key AND is not X") is the documented
  // answer to the absence trap.
  const expressionKeyItems = catalog.map((entry) => ({
    id: entry.key,
    label: (
      <span className="flex justify-between gap-2">
        <span className="font-mono">{entry.key}</span>
        <span className="text-surface-400 dark:text-surface-500">
          {`${entry.values.length} value${entry.values.length === 1 ? "" : "s"}`}
        </span>
      </span>
    ),
  }));

  const modeButton = (active: boolean) =>
    `px-2 py-0.5 text-[11px] rounded-md border ${
      active
        ? "border-accent-300 dark:border-accent-700 bg-accent-50 dark:bg-accent-900/30 text-accent-700 dark:text-accent-300"
        : "border-surface-200 dark:border-surface-700 text-surface-500 dark:text-surface-400 hover:text-surface-700 dark:hover:text-surface-200"
    }`;

  return (
    <section className="pt-3 border-t border-surface-200/60 dark:border-surface-700/50">
      <div className="flex items-center gap-2 mb-1">
        <h3 className="text-xs font-semibold tracking-wide text-surface-700 dark:text-surface-200">
          {title}
        </h3>
        <OperatorOnlyBadge />
        <span className="ml-auto inline-flex items-center gap-1">
          <button
            type="button"
            className={modeButton(leg.mode === "simple")}
            disabled={leg.mode === "advanced" && flatEquivalent === null}
            title={
              leg.mode === "advanced" && flatEquivalent === null
                ? "Not representable as simple conditions (NotIn/Exists/DoesNotExist or repeated keys). Remove those expressions first."
                : "Simple conditions: key is any of [values], ANDed"
            }
            onClick={() =>
              setLeg((cur) =>
                cur.mode === "simple"
                  ? cur
                  : { mode: "simple", map: toFlatMap(cur.expressions) ?? {} },
              )
            }
          >
            Simple
          </button>
          <button
            type="button"
            className={modeButton(leg.mode === "advanced")}
            title="Match expressions: In / NotIn / Exists / DoesNotExist"
            onClick={() =>
              setLeg((cur) =>
                cur.mode === "advanced"
                  ? cur
                  : {
                      mode: "advanced",
                      expressions: Object.entries(cur.map).map(
                        ([key, values]) => ({
                          key,
                          operator: "In" as const,
                          values,
                        }),
                      ),
                    },
              )
            }
          >
            Expressions
          </button>
        </span>
      </div>
      <p className="text-xs text-surface-500 dark:text-surface-400 mb-3">
        {blurb}
      </p>
      {leg.mode === "simple" ? (
        <div className="space-y-2">
          {Object.entries(leg.map).map(([key, values]) => (
            <div
              key={key}
              className="flex items-start gap-2 rounded-lg border border-surface-200 dark:border-surface-700 bg-surface-50/60 dark:bg-surface-900/60 px-3 py-2"
            >
              <span className="text-xs text-surface-400 dark:text-surface-500 mt-1 shrink-0">
                is any of
              </span>
              <div className="flex-1 -mt-1">
                <KeyRow
                  keyName={key}
                  values={values}
                  registered={byKey.get(key)}
                  chipCls={chipCls}
                  onAdd={(v) => patchSimple(key, (cur) => [...cur, v])}
                  onRemoveValue={(v) =>
                    patchSimple(key, (cur) => cur.filter((x) => x !== v))
                  }
                  onRemoveKey={() => patchSimple(key, () => null)}
                />
              </div>
            </div>
          ))}
          <Picker
            trigger="+ Add condition (AND) — pick a registered key"
            header="Registered keys"
            items={simpleKeyItems}
            footer="Only registered keys can be used. Manage them in the Tag Registry."
            filterable
            onPick={(key) => patchSimple(key, (cur) => cur, { keepEmpty: true })}
          />
        </div>
      ) : (
        <div className="space-y-2">
          {leg.expressions.map((expression, index) => (
            <ExpressionRow
              key={`${expression.key}-${index}`}
              expression={expression}
              registered={byKey.get(expression.key)}
              chipCls={chipCls}
              onChange={(next) => patchExpression(index, next)}
              onRemove={() => patchExpression(index, null)}
            />
          ))}
          <Picker
            trigger="+ Add expression (AND) — pick a registered key"
            header="Registered keys"
            items={expressionKeyItems}
            footer="Only registered keys can be used. Manage them in the Tag Registry."
            filterable
            onPick={(key) =>
              setLeg((cur) =>
                cur.mode === "advanced"
                  ? {
                      mode: "advanced",
                      expressions: [
                        ...cur.expressions,
                        { key, operator: "In", values: [] },
                      ],
                    }
                  : cur,
              )
            }
          />
          {hasAbsenceOperator && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-200 dark:border-amber-800/50 bg-amber-50/50 dark:bg-amber-900/10 px-3 py-2.5">
              <AlertTriangle size={14} className="text-amber-500 mt-0.5 shrink-0" />
              <p className="text-xs text-amber-700 dark:text-amber-300">
                NotIn and DoesNotExist ALSO match agents that carry no such
                tag at all (Kubernetes semantics). To mean "has the key and is
                not X", add an Exists expression on the same key.
              </p>
            </div>
          )}
        </div>
      )}
      {preview}
      {children}
    </section>
  );
}

// Convenience wrapper: BOTH audience legs (outbound + inbound) as one editor
// that emits a `CommScope | null` (null = unrestricted on both sides) and
// reports whether either leg is incomplete (an In/NotIn without values, which
// the server rejects) so the owner can block its save/publish. `agents` feeds
// the optional live-reach preview; pass `[]` where no agent context exists
// (e.g. the policy catalog, which stages a scope with no bound holders yet).
export function CommScopeEditor({
  initial,
  catalog,
  agents = [],
  onChange,
  onIncompleteChange,
}: {
  initial: CommScope | null;
  catalog: TagKeyRow[];
  agents?: AgentRow[];
  onChange: (scope: CommScope | null) => void;
  onIncompleteChange?: (incomplete: boolean) => void;
}) {
  const [outbound, setOutbound] = useState<LegState>(() =>
    initLeg(scopeSelector(initial?.outbound)),
  );
  const [inbound, setInbound] = useState<LegState>(() =>
    initLeg(scopeSelector(initial?.inbound)),
  );

  const byKey = useMemo(
    () => new Map(catalog.map((entry) => [entry.key, entry])),
    [catalog],
  );
  const keyPickerItems = (used: TagMap) =>
    catalog.map((entry) => ({
      id: entry.key,
      label: (
        <span className="flex justify-between gap-2">
          <span className="font-mono">{entry.key}</span>
          <span className="text-surface-400 dark:text-surface-500">
            {entry.key in used
              ? "in use"
              : `${entry.values.length} value${entry.values.length === 1 ? "" : "s"}`}
          </span>
        </span>
      ),
      disabled: entry.key in used,
    }));

  const outboundEffective = legSelector(outbound);
  const inboundEffective = legSelector(inbound);
  const incomplete = legIncomplete(outbound) || legIncomplete(inbound);

  // Report the composed scope + validity upward whenever a leg changes. The
  // owner passes stable state setters, so re-running on leg changes only is
  // safe (and avoids a feedback loop from changing prop identities).
  useEffect(() => {
    const scope: CommScope = {};
    if (outboundEffective) scope.outbound = outboundEffective;
    if (inboundEffective) scope.inbound = inboundEffective;
    onChange(outboundEffective || inboundEffective ? scope : null);
    onIncompleteChange?.(incomplete);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outbound, inbound]);

  const renderPreview = (
    effective: TagSelector | null,
    verb: string,
  ): ReactNode => {
    if (!agents.length || !effective) return null;
    const matched = agents.filter((a) => selectorMatches(effective, a.tags));
    return (
      <div className="mt-3 flex items-start gap-2 rounded-lg border border-accent-200 dark:border-accent-800/50 bg-accent-50/50 dark:bg-accent-900/10 px-3 py-2.5">
        <Eye size={14} className="text-accent-500 dark:text-accent-400 mt-0.5 shrink-0" />
        <p className="text-xs text-surface-600 dark:text-surface-300">
          {verb}{" "}
          <span className="font-semibold">
            {matched.length} of {agents.length}
          </span>{" "}
          registered agents.
        </p>
      </div>
    );
  };

  return (
    <div className="space-y-2" data-testid="comm-scope-editor">
      <AudienceLegEditor
        title="Audience — outbound"
        blurb={
          <>
            Bounds whom holders of this policy may reach with direct messages,
            broadcasts and handoffs.{" "}
            <span className="text-surface-600 dark:text-surface-300">
              No conditions = no restriction.
            </span>{" "}
            Simple mode: AND across keys, OR across values. Expressions mode
            adds In / NotIn / Exists / DoesNotExist (ANDed). Conditions are
            built from Tag Registry entries only; values match hierarchically by{" "}
            <code className="font-mono">/</code> segment.
          </>
        }
        leg={outbound}
        setLeg={(fn) => setOutbound(fn)}
        byKey={byKey}
        catalog={catalog}
        simpleKeyItems={keyPickerItems(
          outbound.mode === "simple" ? outbound.map : {},
        )}
        chipCls={AUDIENCE_CHIP}
        preview={renderPreview(outboundEffective, "Holders can currently reach")}
      />
      <AudienceLegEditor
        title="Audience — inbound"
        blurb={
          <>
            Bounds who may reach holders of this policy: senders whose tags miss
            the filter are blocked (direct sends) or silently dropped (group
            fan-outs).{" "}
            <span className="text-surface-600 dark:text-surface-300">
              No conditions = anyone may reach them.
            </span>{" "}
            Simple mode: AND across keys, OR across values. Expressions mode
            adds In / NotIn / Exists / DoesNotExist (ANDed). Conditions are
            built from Tag Registry entries only.
          </>
        }
        leg={inbound}
        setLeg={(fn) => setInbound(fn)}
        byKey={byKey}
        catalog={catalog}
        simpleKeyItems={keyPickerItems(
          inbound.mode === "simple" ? inbound.map : {},
        )}
        chipCls={AUDIENCE_CHIP}
        preview={renderPreview(inboundEffective, "Currently reachable by")}
      />
    </div>
  );
}
