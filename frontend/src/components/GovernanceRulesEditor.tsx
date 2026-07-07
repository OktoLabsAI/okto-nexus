// Reusable governance-rules composer (spec 80624c1a). The SAME editor drives
// BOTH a global policy's published version AND an agent's INLINE policy —
// inline and global governance have IDENTICAL force and vocabulary (they differ
// only in placement/registration and reuse), so they share one control. The
// rules are SUBJECT-LESS: the attachment (the binding) IS the subject, so a
// rule is only {action, limit_kind, limit_value?, window?}. Controlled: the
// owner holds the `rules` array; this component owns only the in-progress draft.

import { useState } from "react";
import { Plus, X } from "lucide-react";
import type {
  PolicyAction,
  PolicyLimitKind,
  PolicyRule,
  PolicyWindow,
} from "../api";

const inputCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";

// Closed governance vocabularies (subject-less: the binding IS the subject).
export const ACTIONS: PolicyAction[] = [
  "message_create",
  "broadcast",
  "handoff_create",
  "artifact_put",
];
const APPROVAL_ACTIONS: PolicyAction[] = ["message_create", "handoff_create"];
export const LIMIT_KINDS: PolicyLimitKind[] = [
  "deny",
  "max_count",
  "max_bytes",
  "max_open_handoffs",
  "require_approval",
];
export const WINDOWS: PolicyWindow[] = ["1h", "24h"];

export const LIMIT_HELP: Record<PolicyLimitKind, string> = {
  deny: "Categorically block the action",
  max_count: "At most N actions per rolling window",
  max_bytes: "Payload may not exceed N bytes",
  max_open_handoffs: "At most N non-terminal created handoffs",
  require_approval: "Intercept the action until an operator approves or rejects it",
};

// A compact one-line label for a rule (history tables, chips).
export function ruleLabel(rule: PolicyRule): string {
  if (rule.limit_kind === "deny") return `${rule.action}:deny`;
  const bound = rule.limit_value != null ? ` ≤ ${rule.limit_value}` : "";
  return `${rule.action}:${rule.limit_kind}${bound}`;
}

export function GovernanceRulesEditor({
  rules,
  onChange,
  testId = "governance-rules",
}: {
  rules: PolicyRule[];
  onChange: (next: PolicyRule[]) => void;
  testId?: string;
}) {
  const [ruleDraft, setRuleDraft] = useState({
    action: "message_create" as PolicyAction,
    limit_kind: "deny" as PolicyLimitKind,
    limit_value: "",
    window: "1h" as PolicyWindow,
  });

  const needsLimit =
    ruleDraft.limit_kind !== "deny" &&
    ruleDraft.limit_kind !== "require_approval";
  const needsWindow = ruleDraft.limit_kind === "max_count";
  const canAddRule = !needsLimit || Number(ruleDraft.limit_value) > 0;
  const actionOptions =
    ruleDraft.limit_kind === "require_approval" ? APPROVAL_ACTIONS : ACTIONS;

  const addRule = () => {
    const rule: PolicyRule = {
      action: ruleDraft.action,
      limit_kind: ruleDraft.limit_kind,
    };
    if (needsLimit) rule.limit_value = Number(ruleDraft.limit_value);
    if (needsWindow) rule.window = ruleDraft.window;
    onChange([...rules, rule]);
    setRuleDraft((cur) => ({ ...cur, limit_value: "" }));
  };

  const removeRule = (index: number) =>
    onChange(rules.filter((_, i) => i !== index));

  return (
    <div data-testid={testId}>
      {rules.length > 0 && (
        <ul className="mt-2 space-y-1.5" data-testid={`${testId}-list`}>
          {rules.map((rule, index) => (
            <li
              key={index}
              className="flex items-center gap-2 text-xs rounded-lg border border-surface-200 dark:border-surface-700 bg-surface-50/60 dark:bg-surface-900/60 px-3 py-1.5"
            >
              <span className="font-mono text-surface-700 dark:text-surface-200">
                {ruleLabel(rule)}
              </span>
              {rule.window && (
                <span className="text-surface-400 dark:text-surface-500 font-mono">
                  / {rule.window}
                </span>
              )}
              <button
                className="ml-auto text-surface-400 hover:text-red-500"
                onClick={() => removeRule(index)}
                title="Remove this rule"
                data-testid={`${testId}-remove-${index}`}
              >
                <X size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
            Action
          </span>
          <select
            value={ruleDraft.action}
            onChange={(e) =>
              setRuleDraft({ ...ruleDraft, action: e.target.value as PolicyAction })
            }
            className={`${inputCls} mt-1 block font-mono`}
            data-testid={`${testId}-action`}
          >
            {actionOptions.map((action) => (
              <option key={action} value={action}>
                {action}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
            Limit
          </span>
          <select
            value={ruleDraft.limit_kind}
            onChange={(e) => {
              const limit_kind = e.target.value as PolicyLimitKind;
              setRuleDraft({
                ...ruleDraft,
                action:
                  limit_kind === "require_approval" &&
                  !APPROVAL_ACTIONS.includes(ruleDraft.action)
                    ? "message_create"
                    : ruleDraft.action,
                limit_kind,
              });
            }}
            className={`${inputCls} mt-1 block font-mono`}
            title={LIMIT_HELP[ruleDraft.limit_kind]}
            data-testid={`${testId}-limit-kind`}
          >
            {LIMIT_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {kind}
              </option>
            ))}
          </select>
        </label>
        {needsLimit && (
          <label className="block">
            <span className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
              Value
            </span>
            <input
              type="number"
              min={1}
              value={ruleDraft.limit_value}
              onChange={(e) =>
                setRuleDraft({ ...ruleDraft, limit_value: e.target.value })
              }
              placeholder="N"
              className={`${inputCls} mt-1 block w-24`}
              data-testid={`${testId}-limit-value`}
            />
          </label>
        )}
        {needsWindow && (
          <label className="block">
            <span className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
              Window
            </span>
            <select
              value={ruleDraft.window}
              onChange={(e) =>
                setRuleDraft({
                  ...ruleDraft,
                  window: e.target.value as PolicyWindow,
                })
              }
              className={`${inputCls} mt-1 block font-mono`}
              data-testid={`${testId}-window`}
            >
              {WINDOWS.map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
          </label>
        )}
        <button
          className="btn btn-secondary"
          onClick={addRule}
          disabled={!canAddRule}
          data-testid={`${testId}-add`}
        >
          <Plus size={13} /> Add rule
        </button>
      </div>
    </div>
  );
}
