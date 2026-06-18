// AgentSelect — a typeahead combobox for picking an agent from the known set
// (replaces the free-text agent filter). Type to pre-filter the list; pick one;
// "(any)" or the inline ✕ clears it. Reused for the DE/PARA filters.

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Search, X } from "lucide-react";
import type { AgentRow } from "../api";

export function AgentSelect({
  value,
  onChange,
  agents,
  label,
  placeholder = "any agent",
}: {
  value: string;
  onChange: (id: string) => void;
  agents: AgentRow[];
  label?: string;
  placeholder?: string;
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
  const filtered = q
    ? agents.filter(
        (a) =>
          a.agent_id.toLowerCase().includes(q) ||
          (a.role ?? "").toLowerCase().includes(q),
      )
    : agents;

  const pick = (id: string) => {
    onChange(id);
    setQuery("");
    setOpen(false);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        data-testid={`agent-select${label ? `-${label.toLowerCase()}` : ""}`}
        className="flex items-center gap-1.5 rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs min-w-[150px] focus:outline-none focus:ring-2 focus:ring-accent-500/40"
      >
        {label && <span className="text-surface-400 shrink-0">{label}:</span>}
        <span
          className={`font-mono truncate ${
            value ? "text-surface-800 dark:text-surface-200" : "text-surface-400"
          }`}
        >
          {value || placeholder}
        </span>
        {value ? (
          <X
            size={12}
            className="ml-auto shrink-0 text-surface-400 hover:text-surface-700 dark:hover:text-surface-200"
            onClick={(e) => {
              e.stopPropagation();
              pick("");
            }}
          />
        ) : (
          <ChevronDown size={12} className="ml-auto shrink-0 text-surface-400" />
        )}
      </button>

      {open && (
        <div className="absolute z-30 mt-1 w-64 max-h-72 overflow-hidden flex flex-col rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 shadow-xl">
          <div className="relative p-1.5 border-b border-surface-100 dark:border-surface-700">
            <Search
              size={12}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400"
            />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={`search ${agents.length} agents…`}
              className="w-full pl-6 pr-2 py-1 rounded text-xs bg-transparent focus:outline-none"
            />
          </div>
          <div className="overflow-y-auto">
            <button
              onClick={() => pick("")}
              className="w-full text-left px-3 py-1.5 text-xs text-surface-400 hover:bg-surface-50 dark:hover:bg-surface-700"
            >
              (any)
            </button>
            {filtered.map((a) => (
              <button
                key={a.agent_id}
                onClick={() => pick(a.agent_id)}
                className={`w-full text-left px-3 py-1.5 text-xs flex items-center gap-1.5 hover:bg-surface-50 dark:hover:bg-surface-700 ${
                  a.agent_id === value
                    ? "bg-accent-50 dark:bg-accent-900/30"
                    : ""
                }`}
              >
                <span className="font-mono text-surface-700 dark:text-surface-300 truncate">
                  {a.agent_id}
                </span>
                {a.role && (
                  <span className="ml-auto shrink-0 text-surface-400">{a.role}</span>
                )}
              </button>
            ))}
            {filtered.length === 0 && (
              <div className="px-3 py-2 text-xs text-surface-400">no match</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
