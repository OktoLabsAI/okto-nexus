// Communication content editor (spec 6f961722): the shared STRUCTURED editor for
// a preset's / an inline binding's style content — the CLOSED set of style
// dimensions with FREE string values. Five short structured labels (datalist-
// suggested but free-typed) plus one free-text note. Reused by both the
// Communication catalog's publish-version composer and the per-agent inline
// binding editor, so the two flows stay pixel-identical. Emits a CommContent
// with only the non-empty dimensions present (empties are pruned here so the
// caller sends a clean {} that the server accepts as a legal, non-directing
// version). Operator-only surface; UI text in English (dashboard convention).

import { type CommContent, type CommDimension } from "../api";

// Per-dimension presentation. `suggestions` seed a <datalist> (typeahead) but
// never constrain — the values are free strings, matching the fail-closed KEYS /
// free VALUES contract. `max` mirrors the server bound (structured 500, note
// 4000) so the field can't stage a payload the PUT would reject.
const DIMENSIONS: {
  key: CommDimension;
  label: string;
  placeholder: string;
  suggestions: string[];
  max: number;
  multiline?: boolean;
}[] = [
  {
    key: "tone",
    label: "Tone",
    placeholder: "e.g. concise, formal, friendly",
    suggestions: ["concise", "formal", "friendly", "explanatory", "neutral"],
    max: 500,
  },
  {
    key: "format",
    label: "Format",
    placeholder: "e.g. markdown, plain text, bullet points",
    suggestions: ["markdown", "plain text", "bullet points", "short paragraphs"],
    max: 500,
  },
  {
    key: "language",
    label: "Language",
    placeholder: "e.g. en, pt-BR, es",
    suggestions: ["en", "pt-BR", "es", "fr", "de"],
    max: 500,
  },
  {
    key: "verbosity",
    label: "Verbosity",
    placeholder: "e.g. low, medium, high",
    suggestions: ["low", "medium", "high"],
    max: 500,
  },
  {
    key: "structure",
    label: "Structure",
    placeholder: "e.g. answer-first, step-by-step, code-first",
    suggestions: [
      "answer-first",
      "step-by-step",
      "code block first, prose after",
    ],
    max: 500,
  },
  {
    key: "additional_instructions",
    label: "Additional instructions",
    placeholder:
      "Free-text guidance, e.g. “Lead with the answer; omit preamble.”",
    suggestions: [],
    max: 4000,
    multiline: true,
  },
];

const inputCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";

export function CommContentEditor({
  value,
  onChange,
  idPrefix = "comm",
  testId = "comm-content-editor",
}: {
  value: CommContent;
  onChange: (next: CommContent) => void;
  // Namespaces the <datalist> ids so two mounted editors never collide.
  idPrefix?: string;
  testId?: string;
}) {
  // Prune empties on every edit so the emitted object only ever carries dimensions
  // the operator actually filled — the caller can send it straight through.
  const patch = (key: CommDimension, raw: string) => {
    const next: CommContent = { ...value };
    if (raw.trim()) next[key] = raw;
    else delete next[key];
    onChange(next);
  };

  const filled = DIMENSIONS.filter((d) => (value[d.key] ?? "").trim()).length;

  return (
    <div className="space-y-2.5" data-testid={testId}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {DIMENSIONS.filter((d) => !d.multiline).map((dim) => {
          const listId = `${idPrefix}-${dim.key}-list`;
          return (
            <label key={dim.key} className="space-y-1">
              <span className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
                {dim.label}
              </span>
              <input
                className={`${inputCls} w-full`}
                value={value[dim.key] ?? ""}
                maxLength={dim.max}
                list={dim.suggestions.length ? listId : undefined}
                placeholder={dim.placeholder}
                onChange={(e) => patch(dim.key, e.target.value)}
                data-testid={`comm-dim-${dim.key}`}
              />
              {dim.suggestions.length > 0 && (
                <datalist id={listId}>
                  {dim.suggestions.map((s) => (
                    <option key={s} value={s} />
                  ))}
                </datalist>
              )}
            </label>
          );
        })}
      </div>

      {DIMENSIONS.filter((d) => d.multiline).map((dim) => (
        <label key={dim.key} className="space-y-1 block">
          <span className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
            {dim.label}
          </span>
          <textarea
            className={`${inputCls} w-full`}
            rows={3}
            value={value[dim.key] ?? ""}
            maxLength={dim.max}
            placeholder={dim.placeholder}
            onChange={(e) => patch(dim.key, e.target.value)}
            data-testid={`comm-dim-${dim.key}`}
          />
        </label>
      ))}

      <p className="text-[10px] text-surface-400 dark:text-surface-500">
        {filled === 0
          ? "Every field is optional — an empty style is valid (it directs nothing)."
          : `${filled} dimension${filled === 1 ? "" : "s"} set. Blank fields are omitted from the agent's whoami.`}
      </p>
    </div>
  );
}

// A compact, read-only rendering of a resolved content dict — the chips the
// catalog's version history and the agent editor's preview both show.
export function CommContentChips({
  content,
  emptyLabel = "no directing content",
}: {
  content: CommContent;
  emptyLabel?: string;
}) {
  const entries = DIMENSIONS.map((d) => [d.key, d.label, content[d.key]] as const).filter(
    ([, , v]) => (v ?? "").trim(),
  );
  if (entries.length === 0) {
    return (
      <span className="text-xs text-surface-400 dark:text-surface-500">
        {emptyLabel}
      </span>
    );
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.map(([key, label, v]) => (
        <span
          key={key}
          className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-md bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300 border border-accent-200 dark:border-accent-800/50"
          title={v ?? ""}
        >
          <span className="uppercase tracking-wide opacity-70">{label}</span>
          <span className="font-mono max-w-[220px] truncate">{v}</span>
        </span>
      ))}
    </div>
  );
}
