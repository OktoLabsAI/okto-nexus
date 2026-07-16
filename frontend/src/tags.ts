// Client-side mirrors of the domain tag-selector semantics (F1+F3). Used by
// the Tag Registry (usage counts) and the agent Tags/Audience editors (live
// match preview). The SERVER is authoritative — these exist only so the UI
// can preview/annotate without extra round-trips.

import type {
  AgentRow,
  TagExpression,
  TagMap,
  TagSelector,
  TagUse,
} from "./api";

// Persisted maps may carry a bare string where a list is expected (the
// domain grammar accepts both and normalises on write); normalise the same
// way before rendering or matching.
export function normalizeTagMap(raw: unknown): TagMap {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) return {};
  const out: TagMap = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value === "string") out[key] = [value];
    else if (Array.isArray(value)) {
      out[key] = value.filter((v): v is string => typeof v === "string");
    }
  }
  return out;
}

const OPERATORS: readonly TagExpression["operator"][] = [
  "In",
  "NotIn",
  "Exists",
  "DoesNotExist",
];

// Normalise a persisted rich selector: keep well-formed expressions in their
// canonical shape, drop anything malformed (the server validated at write
// time — this is defensive parsing for previews only).
export function normalizeExpressions(raw: unknown): TagExpression[] {
  if (!Array.isArray(raw)) return [];
  const out: TagExpression[] = [];
  for (const entry of raw) {
    if (entry === null || typeof entry !== "object" || Array.isArray(entry)) {
      continue;
    }
    const { key, operator, values } = entry as Record<string, unknown>;
    if (typeof key !== "string" || !key) continue;
    if (
      typeof operator !== "string" ||
      !OPERATORS.includes(operator as TagExpression["operator"])
    ) {
      continue;
    }
    const op = operator as TagExpression["operator"];
    if (op === "Exists" || op === "DoesNotExist") {
      out.push({ key, operator: op });
      continue;
    }
    const list =
      typeof values === "string"
        ? [values]
        : Array.isArray(values)
          ? values.filter((v): v is string => typeof v === "string")
          : [];
    out.push({ key, operator: op, values: list });
  }
  return out;
}

export function scopeSelector(raw: unknown): TagSelector | null {
  if (raw == null) return null;
  if (Array.isArray(raw)) {
    const expressions = normalizeExpressions(raw);
    return expressions.length ? expressions : null;
  }
  const selector = normalizeTagMap(raw);
  return Object.keys(selector).length ? selector : null;
}

export function outboundSelector(agent: AgentRow): TagSelector | null {
  return scopeSelector(agent.comm_scope?.outbound);
}

export function inboundSelector(agent: AgentRow): TagSelector | null {
  return scopeSelector(agent.comm_scope?.inbound);
}

// Hierarchical segment matching (F3): selector value ENG covers agent values
// ENG and ENG/BACKEND but never ENGX — per-"/"-segment equality, not a
// string prefix.
function valueCovers(wanted: string, have: string): boolean {
  const wantedSegments = wanted.split("/");
  const haveSegments = have.split("/");
  return (
    wantedSegments.length <= haveSegments.length &&
    wantedSegments.every((segment, i) => haveSegments[i] === segment)
  );
}

function intersects(wanted: string[], have: string[]): boolean {
  return wanted.some((w) => have.some((h) => valueCovers(w, h)));
}

// One expression against an agent's (normalised) tags — the F3 truth table.
// K8s absence parity: NotIn and DoesNotExist MATCH agents missing the key.
function expressionMatches(expression: TagExpression, tags: TagMap): boolean {
  const present = expression.key in tags;
  const have = tags[expression.key] ?? [];
  switch (expression.operator) {
    case "Exists":
      return present;
    case "DoesNotExist":
      return !present;
    case "In":
      return present && intersects(expression.values ?? [], have);
    case "NotIn":
      return !present || !intersects(expression.values ?? [], have);
  }
}

// Either selector form against an agent's tags. Flat form: AND across keys,
// OR within a key's values (In sugar — hierarchy applies here too); rich
// form: AND across expressions. Empty/absent selector matches everyone.
export function selectorMatches(
  selector: TagSelector | null | undefined,
  tags: TagMap | null | undefined,
): boolean {
  if (selector == null) return true;
  const agentTags = normalizeTagMap(tags);
  if (Array.isArray(selector)) {
    return normalizeExpressions(selector).every((expression) =>
      expressionMatches(expression, agentTags),
    );
  }
  if (Object.keys(selector).length === 0) return true;
  return Object.entries(normalizeTagMap(selector)).every(([key, wanted]) => {
    if (!(key in agentTags) || wanted.length === 0) return false;
    return intersects(wanted, agentTags[key] ?? []);
  });
}

// A rich selector is representable as simple conditions iff every expression
// is an In over a DISTINCT key (the flat map cannot express NotIn/Exists/
// DoesNotExist nor two expressions on one key). Returns the equivalent flat
// map, or null when not representable.
export function toFlatMap(expressions: TagExpression[]): TagMap | null {
  const out: TagMap = {};
  for (const expression of expressions) {
    if (
      expression.operator !== "In" ||
      !expression.values ||
      expression.values.length === 0 ||
      expression.key in out
    ) {
      return null;
    }
    out[expression.key] = expression.values;
  }
  return out;
}

function referencesKey(selector: TagSelector | null, key: string): boolean {
  if (selector == null) return false;
  if (Array.isArray(selector)) {
    return selector.some((expression) => expression.key === key);
  }
  return key in selector;
}

function referencesPair(
  selector: TagSelector | null,
  key: string,
  value: string,
): boolean {
  if (selector == null) return false;
  if (Array.isArray(selector)) {
    // Only the value-carrying operators reference a PAIR; Exists/DoesNotExist
    // reference the key alone (mirrors the server's TAG_IN_USE scan).
    return selector.some(
      (expression) =>
        expression.key === key &&
        (expression.operator === "In" || expression.operator === "NotIn") &&
        (expression.values ?? []).includes(value),
    );
  }
  return (selector[key] ?? []).includes(value);
}

// Every agent reference to `key` (or `key=value`) — the same scan the server
// runs for the TAG_IN_USE guard, recomputed here for usage badges.
export function collectUses(
  agents: AgentRow[],
  key: string,
  value?: string | null,
): TagUse[] {
  const references = (selector: TagSelector | null): boolean =>
    value == null
      ? referencesKey(selector, key)
      : referencesPair(selector, key, value);
  const uses: TagUse[] = [];
  for (const agent of agents) {
    const tags = normalizeTagMap(agent.tags);
    if (references(Object.keys(tags).length ? tags : null)) {
      uses.push({ agent_id: agent.agent_id, kind: "agent_tags" });
    }
    if (
      references(outboundSelector(agent)) ||
      references(inboundSelector(agent))
    ) {
      uses.push({ agent_id: agent.agent_id, kind: "comm_scope" });
    }
  }
  return uses;
}
