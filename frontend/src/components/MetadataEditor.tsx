// Structured agent-metadata editor (spec 09fa9cba): replaces the raw-JSON
// <textarea> in the Agents screen with one typed row per top-level key. Scalars
// (string/number/boolean) are edited inline with their JSON type detected and
// PRESERVED on save; object/array/null values stay behind a per-row "edit as
// JSON" escape hatch so nothing is ever flattened or lost. Frontend-only: it
// emits a clean Record<string, unknown> to the existing PATCH/POST — no schema
// or MCP-surface change. UI text English.
//
// The pure helpers below (detectRowType / rowsFromMetadata / parseNumberValue /
// rowValue / buildMetadata / convertRow) carry the whole correctness burden and
// are exported so they can be reviewed — and later unit-tested — in isolation
// from React. Per the operator's Python-only testing decision there is no JS
// test runner yet, so keep them side-effect-free and self-contained.

import { useEffect, useMemo, useRef, useState } from "react";
import { Braces, Plus, Trash2 } from "lucide-react";

// ---------------------------------------------------------------------------
// Pure model + helpers (no React, no side effects)
// ---------------------------------------------------------------------------

export type MetaRowType = "string" | "number" | "boolean" | "json";

export interface MetaRow {
  // Stable local id for React keys + per-row error addressing. Never emitted.
  id: string;
  key: string;
  type: MetaRowType;
  // Holds the string value, the number's raw text, or the JSON source (json).
  text: string;
  // Holds the boolean value (used only when type === "boolean").
  bool: boolean;
}

// A top-level metadata value maps to exactly one editing affordance. Anything
// that is not a finite scalar (objects, arrays, null, NaN/Infinity) falls back
// to the JSON escape hatch so it round-trips without loss.
export function detectRowType(v: unknown): MetaRowType {
  if (typeof v === "string") return "string";
  if (typeof v === "number" && Number.isFinite(v)) return "number";
  if (typeof v === "boolean") return "boolean";
  return "json";
}

// Build a single row from a stored [key, value] pair. `makeId` is injected so
// this stays deterministic under test.
export function rowFromEntry(key: string, v: unknown, id: string): MetaRow {
  const type = detectRowType(v);
  return {
    id,
    key,
    type,
    text:
      type === "string"
        ? (v as string)
        : type === "number"
          ? String(v)
          : type === "json"
            ? JSON.stringify(v, null, 2)
            : "",
    bool: type === "boolean" ? (v as boolean) : false,
  };
}

// Seed the editor rows from a stored metadata object, preserving key order.
export function rowsFromMetadata(
  meta: Record<string, unknown>,
  makeId: () => string,
): MetaRow[] {
  return Object.entries(meta ?? {}).map(([k, v]) => rowFromEntry(k, v, makeId()));
}

// Number round-trip guard (BR-2): a number-typed row becomes a real JS number
// ONLY when its trimmed text is the canonical stringification of that number
// (String(Number(t)) === t). Otherwise it is kept as a string, so "007", "1.0",
// "1e3", " 5 " and "" are never silently corrupted into a lossy number.
export function parseNumberValue(text: string): number | string {
  const t = text.trim();
  if (t !== "" && Number.isFinite(Number(t)) && String(Number(t)) === t) {
    return Number(t);
  }
  return t;
}

export type RowValue =
  | { ok: true; value: unknown }
  | { ok: false; error: string };

// Resolve one row to its emitted JSON value (or a per-row error for invalid
// JSON in the escape hatch — BR-3).
export function rowValue(row: MetaRow): RowValue {
  switch (row.type) {
    case "string":
      return { ok: true, value: row.text };
    case "boolean":
      return { ok: true, value: row.bool };
    case "number":
      return { ok: true, value: parseNumberValue(row.text) };
    case "json": {
      const src = row.text.trim();
      if (src === "") return { ok: false, error: "Empty — enter JSON or remove the field" };
      try {
        return { ok: true, value: JSON.parse(src) };
      } catch (e) {
        return { ok: false, error: `Invalid JSON: ${(e as Error).message}` };
      }
    }
  }
}

export type BuildResult =
  | { ok: true; value: Record<string, unknown> }
  | { ok: false; value: Record<string, unknown>; rowErrors: Record<string, string> };

// Assemble the emitted metadata object from the rows (BR-4/5/6):
//   • empty-key rows are dropped silently,
//   • duplicate (trimmed) keys block with a per-row error,
//   • each kept value is emitted with its detected JSON type,
//   • no rows -> {} (clears stored metadata).
// On error it still returns the best-effort `value` (valid rows only) so the
// caller can preview, but `ok` is false so Save stays blocked.
export function buildMetadata(rows: MetaRow[]): BuildResult {
  // Drop blank placeholder rows (BR-5): a key that is empty or whitespace-only is
  // an unfilled field, not data. Dedup + emission use the EXACT key (never a
  // trimmed copy) so untouched values round-trip deep-equal (FR-8) and two keys
  // that merely differ by surrounding whitespace are not falsely merged.
  const kept = rows.filter((r) => r.key.trim() !== "");
  const counts = new Map<string, number>();
  for (const r of kept) {
    counts.set(r.key, (counts.get(r.key) ?? 0) + 1);
  }
  const value: Record<string, unknown> = {};
  const rowErrors: Record<string, string> = {};
  for (const r of kept) {
    if ((counts.get(r.key) ?? 0) > 1) {
      rowErrors[r.id] = `Duplicate key "${r.key}"`;
      continue;
    }
    const rv = rowValue(r);
    if (!rv.ok) {
      rowErrors[r.id] = rv.error;
      continue;
    }
    value[r.key] = rv.value;
  }
  if (Object.keys(rowErrors).length > 0) return { ok: false, value, rowErrors };
  return { ok: true, value };
}

// Change a row's type, carrying its current value across as sensibly as
// possible so switching type is not a data-loss action.
export function convertRow(row: MetaRow, nextType: MetaRowType): MetaRow {
  if (row.type === nextType) return row;
  let text = row.text;
  let bool = row.bool;
  if (nextType === "json") {
    if (row.type === "boolean") text = String(row.bool);
    else if (row.type === "number") {
      // Mirror the number row's EMITTED value (FR-4): a canonical number keeps
      // its raw text (valid JSON); a non-canonical one ("007", "+5") is really a
      // string, so quote it — never carry over a bare token that fails JSON.parse.
      const parsed = parseNumberValue(row.text);
      text = typeof parsed === "number" ? row.text.trim() : JSON.stringify(parsed);
    } else text = row.text === "" ? '""' : JSON.stringify(row.text);
  } else if (nextType === "boolean") {
    bool = row.type === "json" ? row.text.trim() === "true" : row.bool;
  } else if (nextType === "string" || nextType === "number") {
    if (row.type === "boolean") text = String(row.bool);
    // number/json keep their raw text; the user refines it inline.
  }
  return { ...row, type: nextType, text, bool };
}

// One-line, length-bounded preview of a json row's value for the collapsed view.
export function jsonPreview(text: string, max = 72): string {
  const src = text.trim();
  if (src === "") return "(empty)";
  let out = src;
  try {
    out = JSON.stringify(JSON.parse(src));
  } catch {
    out = src.replace(/\s+/g, " ");
  }
  return out.length > max ? `${out.slice(0, max - 1)}…` : out;
}

// Module-scoped id source for React keys (unique within a browser session).
// Not part of the pure surface — the helpers above take an injected makeId.
let _idCounter = 0;
const makeId = () => `mrow-${(_idCounter += 1)}`;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const inputCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";
const selectCls =
  "rounded-lg border border-surface-300 dark:border-surface-600 bg-white dark:bg-surface-800 px-1.5 py-1.5 text-xs text-surface-700 dark:text-surface-200 focus:outline-none focus:ring-2 focus:ring-accent-500/40";
const ICON_BTN_DANGER =
  "p-1.5 rounded-lg text-red-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors shrink-0";

const TYPE_OPTIONS: { value: MetaRowType; label: string }[] = [
  { value: "string", label: "text" },
  { value: "number", label: "number" },
  { value: "boolean", label: "boolean" },
  { value: "json", label: "JSON" },
];

export function MetadataEditor({
  initial,
  resetSignal,
  onChange,
  idPrefix = "meta",
  testId = "metadata-editor",
}: {
  // Stored metadata to seed the rows from (byte-preserved for untouched values).
  initial: Record<string, unknown>;
  // Re-seed the rows whenever this changes (e.g. the agent id, or a fresh open).
  // Deliberately NOT `initial` itself, which is a new object every render.
  resetSignal?: string;
  // Reports the current emitted object + whether Save should be allowed. Called
  // on mount, on every edit, and on re-seed. Identity need not be stable.
  onChange: (result: { value: Record<string, unknown>; valid: boolean }) => void;
  idPrefix?: string;
  testId?: string;
}) {
  const [rows, setRows] = useState<MetaRow[]>(() => rowsFromMetadata(initial, makeId));
  // Which json rows have their escape-hatch textarea revealed.
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  // Re-seed when the caller signals a NEW subject (e.g. a persistent instance
  // switching agents). The useState initializer already seeded the first mount,
  // so a mounted-ref skips the redundant mount pass — without it the effect would
  // re-seed with fresh row ids and needlessly remount every row. `initial` is
  // intentionally excluded from deps (it changes identity each render and would
  // clobber in-progress edits); it moves in lockstep with resetSignal anyway.
  const seeded = useRef(false);
  useEffect(() => {
    if (!seeded.current) {
      seeded.current = true;
      return;
    }
    setRows(rowsFromMetadata(initial, makeId));
    setExpanded(new Set());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetSignal]);

  const built = useMemo(() => buildMetadata(rows), [rows]);

  // Report upward without depending on onChange's identity (a ref decouples the
  // effect from an unstable parent callback, so it fires only when `built`
  // actually changes — i.e. on a real edit or re-seed).
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  });
  useEffect(() => {
    onChangeRef.current({ value: built.value, valid: built.ok });
  }, [built]);

  const rowErrors = built.ok ? {} : built.rowErrors;

  const patchRow = (id: string, patch: Partial<MetaRow>) =>
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)));

  const changeType = (id: string, nextType: MetaRowType) =>
    setRows((rs) => rs.map((r) => (r.id === id ? convertRow(r, nextType) : r)));

  const removeRow = (id: string) => {
    setRows((rs) => rs.filter((r) => r.id !== id));
    setExpanded((s) => {
      const next = new Set(s);
      next.delete(id);
      return next;
    });
  };

  const addRow = () =>
    setRows((rs) => [
      ...rs,
      { id: makeId(), key: "", type: "string", text: "", bool: false },
    ]);

  const toggleExpanded = (id: string) =>
    setExpanded((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="space-y-2" data-testid={testId}>
      {rows.length === 0 && (
        <p className="text-xs text-surface-400 dark:text-surface-500">
          No metadata — add a field, or leave empty to store nothing.
        </p>
      )}

      {rows.map((row) => {
        const err = rowErrors[row.id];
        const jsonOpen = row.type === "json" && (expanded.has(row.id) || Boolean(err));
        return (
          <div key={row.id} className="space-y-1" data-testid={`${idPrefix}-row-${row.id}`}>
            <div className="flex items-start gap-2">
              <input
                className={`${inputCls} font-mono w-36 shrink-0`}
                value={row.key}
                onChange={(e) => patchRow(row.id, { key: e.target.value })}
                placeholder="key"
                aria-label="metadata key"
                data-testid={`${idPrefix}-key-${row.id}`}
              />
              <select
                className={selectCls}
                value={row.type}
                onChange={(e) => changeType(row.id, e.target.value as MetaRowType)}
                title="How this value is stored"
                aria-label="metadata value type"
                data-testid={`${idPrefix}-type-${row.id}`}
              >
                {TYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>

              {/* Value control — one per type */}
              <div className="flex-1 min-w-0">
                {row.type === "string" && (
                  <input
                    className={`${inputCls} w-full`}
                    value={row.text}
                    onChange={(e) => patchRow(row.id, { text: e.target.value })}
                    placeholder="value"
                    aria-label="metadata value"
                    data-testid={`${idPrefix}-value-${row.id}`}
                  />
                )}
                {row.type === "number" && (
                  <input
                    className={`${inputCls} w-full font-mono`}
                    value={row.text}
                    onChange={(e) => patchRow(row.id, { text: e.target.value })}
                    inputMode="decimal"
                    placeholder="0"
                    aria-label="metadata number value"
                    data-testid={`${idPrefix}-value-${row.id}`}
                  />
                )}
                {row.type === "boolean" && (
                  <label className="flex items-center gap-2 h-[30px] text-xs text-surface-600 dark:text-surface-300 cursor-pointer">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-surface-300 dark:border-surface-600 text-accent-600 focus:ring-accent-500/40"
                      checked={row.bool}
                      onChange={(e) => patchRow(row.id, { bool: e.target.checked })}
                      aria-label="metadata boolean value"
                      data-testid={`${idPrefix}-value-${row.id}`}
                    />
                    <span className="font-mono">{row.bool ? "true" : "false"}</span>
                  </label>
                )}
                {row.type === "json" && (
                  <div className="space-y-1">
                    {!jsonOpen && (
                      <button
                        type="button"
                        className={`${inputCls} w-full flex items-center gap-1.5 text-left font-mono text-surface-500 dark:text-surface-400 hover:border-accent-300 dark:hover:border-accent-700`}
                        onClick={() => toggleExpanded(row.id)}
                        title="Edit as JSON"
                        data-testid={`${idPrefix}-json-preview-${row.id}`}
                      >
                        <Braces size={12} className="shrink-0 text-surface-400" />
                        <span className="truncate">{jsonPreview(row.text)}</span>
                      </button>
                    )}
                    {jsonOpen && (
                      <textarea
                        className={`${inputCls} w-full font-mono`}
                        rows={4}
                        value={row.text}
                        onChange={(e) => patchRow(row.id, { text: e.target.value })}
                        placeholder='{ "nested": true }'
                        aria-label="metadata JSON value"
                        data-testid={`${idPrefix}-json-${row.id}`}
                      />
                    )}
                  </div>
                )}
              </div>

              <button
                type="button"
                className={ICON_BTN_DANGER}
                onClick={() => removeRow(row.id)}
                title="Remove field"
                aria-label="remove field"
                data-testid={`${idPrefix}-remove-${row.id}`}
              >
                <Trash2 size={14} />
              </button>
            </div>
            {err && (
              <p
                className="text-[11px] text-red-500 pl-[9.5rem]"
                data-testid={`${idPrefix}-error-${row.id}`}
              >
                {err}
              </p>
            )}
          </div>
        );
      })}

      <button
        type="button"
        className="inline-flex items-center gap-1 text-xs text-accent-600 dark:text-accent-400 hover:text-accent-700 dark:hover:text-accent-300"
        onClick={addRow}
        data-testid={`${idPrefix}-add`}
      >
        <Plus size={13} /> Add field
      </button>
    </div>
  );
}
