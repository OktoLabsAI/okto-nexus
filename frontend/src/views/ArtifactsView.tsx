import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Database,
  Download,
  File,
  FileCode2,
  FileJson2,
  FileText,
  HardDrive,
  Maximize2,
  Search,
  Users,
  X,
} from "lucide-react";
import {
  api,
  type AgentRow,
  type ArtifactDetail,
  type ArtifactItem,
} from "../api";
import { Markdown } from "../components/Markdown";
import { PageContainer } from "../components/PageContainer";
import { ResizablePanel } from "../components/ResizablePanel";
import { useWorkspaceName } from "../components/WorkspaceNames";

const inputCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";

const PAGE_SIZE = 20;

function bytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function dateTime(iso: string): string {
  const value = new Date(iso);
  return Number.isNaN(value.getTime()) ? iso : value.toLocaleString();
}

function localDateBound(value: string, endOfDay: boolean): string {
  const time = endOfDay ? "23:59:59.999" : "00:00:00.000";
  return new Date(`${value}T${time}`).toISOString();
}

function ArtifactIcon({ type }: { type: ArtifactItem["artifact_type"] }) {
  const cls = "text-accent-600 dark:text-accent-400";
  if (type === "json") return <FileJson2 size={17} className={cls} />;
  if (type === "markdown" || type === "html") {
    return <FileCode2 size={17} className={cls} />;
  }
  if (type === "text") return <FileText size={17} className={cls} />;
  return <File size={17} className={cls} />;
}

function ArtifactRow({
  item,
  active,
  onClick,
}: {
  item: ArtifactItem;
  active: boolean;
  onClick: () => void;
}) {
  const workspaceName = useWorkspaceName(item.workspace_id);
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full border-l-2 px-4 py-3 text-left transition-colors ${
        active
          ? "border-accent-500 bg-accent-50 dark:bg-accent-900/20"
          : "border-transparent hover:bg-surface-50 dark:hover:bg-surface-800/50"
      }`}
      data-testid="artifact-row"
    >
      <div className="flex items-center gap-2">
        <ArtifactIcon type={item.artifact_type} />
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-surface-800 dark:text-surface-100">
          {item.name || item.filename}
        </span>
        <span className="chip bg-surface-100 text-surface-600 dark:bg-surface-800 dark:text-surface-300">
          {item.artifact_type}
        </span>
      </div>
      <div className="mt-1 flex min-w-0 items-center gap-1.5 text-[11px] text-surface-500 dark:text-surface-400">
        <span className="truncate">{item.created_by || "anonymous"}</span>
        <span>&middot;</span>
        <span className="truncate">{workspaceName}</span>
        <span>&middot;</span>
        <span className="shrink-0">{bytes(item.size_bytes)}</span>
      </div>
    </button>
  );
}

function ProducerFilter({
  agents,
  value,
  onChange,
}: {
  agents: AgentRow[];
  value: string[];
  onChange: (value: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = useMemo(() => new Set(value), [value]);
  const visibleAgents = useMemo(() => {
    const term = search.trim().toLowerCase();
    return term
      ? agents.filter(
          (agent) =>
            agent.agent_id.toLowerCase().includes(term) ||
            (agent.role ?? "").toLowerCase().includes(term),
        )
      : agents;
  }, [agents, search]);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const toggle = (agentId: string) => {
    onChange(
      selected.has(agentId)
        ? value.filter((candidate) => candidate !== agentId)
        : [...value, agentId],
    );
  };
  const label =
    value.length === 0
      ? "All producers"
      : value.length === 1
        ? value[0]
        : `${value.length} producers`;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className={`${inputCls} flex min-w-[180px] items-center gap-1.5 text-left`}
        aria-haspopup="listbox"
        aria-expanded={open}
        data-testid="artifact-producer-filter"
      >
        <Users size={13} className="shrink-0 text-surface-400" />
        <span className="min-w-0 flex-1 truncate">{label}</span>
        {value.length > 0 && (
          <span className="chip bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300">
            {value.length}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute left-0 top-full z-40 mt-1 flex w-72 flex-col overflow-hidden rounded-xl border border-surface-200 bg-white shadow-xl dark:border-surface-700 dark:bg-surface-800">
          <div className="border-b border-surface-100 p-2 dark:border-surface-700">
            <label className="relative block">
              <Search size={13} className="absolute left-2 top-2 text-surface-400" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Find a producing agent"
                className={`${inputCls} w-full pl-7`}
                aria-label="Find a producing agent"
                autoFocus
              />
            </label>
            <div className="mt-2 flex items-center justify-between px-1 text-[11px] text-surface-500">
              <span>Select one or more agents</span>
              {value.length > 0 && (
                <button type="button" onClick={() => onChange([])} className="font-medium text-accent-600 hover:underline">
                  Clear
                </button>
              )}
            </div>
          </div>
          <div className="max-h-56 overflow-y-auto p-1" role="listbox" aria-multiselectable="true">
            {visibleAgents.map((agent) => (
              <label
                key={agent.agent_id}
                className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-xs hover:bg-surface-50 dark:hover:bg-surface-700/60"
              >
                <input
                  type="checkbox"
                  checked={selected.has(agent.agent_id)}
                  onChange={() => toggle(agent.agent_id)}
                  className="accent-accent-600"
                />
                <span className="min-w-0 flex-1 truncate font-mono text-surface-700 dark:text-surface-200">
                  {agent.agent_id}
                </span>
                {agent.role && <span className="truncate text-surface-400">{agent.role}</span>}
              </label>
            ))}
            {visibleAgents.length === 0 && (
              <p className="px-3 py-5 text-center text-xs text-surface-400">No agents found.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ContentPreview({
  artifact,
  blobUrl,
  expanded = false,
}: {
  artifact: ArtifactDetail;
  blobUrl: string | null;
  expanded?: boolean;
}) {
  if (!artifact.available) {
    return (
      <div className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-300">
        <AlertTriangle size={15} className="mt-0.5 shrink-0" />
        This legacy artifact points to a payload that is no longer available.
      </div>
    );
  }
  if (artifact.media_type.startsWith("image/") && blobUrl) {
    return (
      <img
        src={blobUrl}
        alt={artifact.name || artifact.filename}
        className={`${expanded ? "max-h-full" : "max-h-[55vh]"} max-w-full rounded-lg border border-surface-200 object-contain dark:border-surface-700`}
      />
    );
  }
  if (artifact.media_type === "application/pdf" && blobUrl) {
    return <iframe title={artifact.filename} src={blobUrl} className={`${expanded ? "h-full min-h-[70vh]" : "h-[55vh]"} w-full rounded-lg border border-surface-200 dark:border-surface-700`} />;
  }
  if (artifact.content == null) {
    return (
      <div className="rounded-lg border border-dashed border-surface-300 p-4 text-center text-xs text-surface-500 dark:border-surface-700">
        Preview is not available for this file type. Use Download to inspect the payload.
      </div>
    );
  }
  if (artifact.artifact_type === "markdown") {
    return (
      <div className="rounded-lg border border-surface-200 bg-surface-50 p-4 text-sm dark:border-surface-700 dark:bg-surface-950/40">
        <Markdown text={artifact.content} />
      </div>
    );
  }
  if (artifact.artifact_type === "json") {
    let formatted = artifact.content;
    try {
      formatted = JSON.stringify(JSON.parse(artifact.content), null, 2);
    } catch {
      // Validated on write; retain raw text for a legacy malformed record.
    }
    return (
      <pre className="max-h-[55vh] overflow-auto whitespace-pre-wrap rounded-lg bg-surface-950 p-4 text-xs text-surface-100">
        {formatted}
      </pre>
    );
  }
  return (
    <pre className="max-h-[55vh] overflow-auto whitespace-pre-wrap rounded-lg border border-surface-200 bg-surface-50 p-4 text-xs text-surface-800 dark:border-surface-700 dark:bg-surface-950/40 dark:text-surface-200">
      {artifact.content}
    </pre>
  );
}

function isRichType(artifact: ArtifactDetail): boolean {
  return (
    artifact.artifact_type === "markdown" ||
    artifact.artifact_type === "json" ||
    artifact.artifact_type === "html" ||
    artifact.media_type === "text/html" ||
    artifact.media_type === "application/json"
  );
}

function JsonTree({
  value,
  label,
  depth = 0,
}: {
  value: unknown;
  label?: string;
  depth?: number;
}) {
  if (value !== null && typeof value === "object") {
    const entries = Array.isArray(value)
      ? value.map((item, index) => [String(index), item] as const)
      : Object.entries(value as Record<string, unknown>);
    const kind = Array.isArray(value)
      ? "Array(" + entries.length + ")"
      : "Object(" + entries.length + ")";
    return (
      <details open={depth < 1} className="ml-3 border-l border-surface-200 pl-2 dark:border-surface-700">
        <summary className="cursor-pointer select-none py-0.5 text-xs text-surface-600 hover:text-accent-600 dark:text-surface-300 dark:hover:text-accent-300">
          {label != null && <span className="font-mono font-semibold">{label}: </span>}
          <span className="text-surface-400">{kind}</span>
        </summary>
        <div>
          {entries.map(([key, child]) => (
            <JsonTree key={key} value={child} label={key} depth={depth + 1} />
          ))}
        </div>
      </details>
    );
  }
  const rendered =
    typeof value === "string" ? JSON.stringify(value) : String(value);
  return (
    <div className="ml-3 border-l border-surface-200 py-0.5 pl-2 font-mono text-xs dark:border-surface-700">
      {label != null && <span className="font-semibold text-surface-600 dark:text-surface-300">{label}: </span>}
      <span className={
        typeof value === "string"
          ? "text-emerald-700 dark:text-emerald-300"
          : typeof value === "number"
            ? "text-sky-700 dark:text-sky-300"
            : "text-violet-700 dark:text-violet-300"
      }>
        {rendered}
      </span>
    </div>
  );
}

function flattenMetadata(
  value: Record<string, unknown>,
  prefix = "",
): Array<[string, unknown]> {
  const fields: Array<[string, unknown]> = [];
  for (const [key, child] of Object.entries(value)) {
    const path = prefix ? prefix + "." + key : key;
    if (
      child !== null &&
      typeof child === "object" &&
      !Array.isArray(child) &&
      Object.keys(child as Record<string, unknown>).length > 0
    ) {
      fields.push(
        ...flattenMetadata(child as Record<string, unknown>, path),
      );
    } else {
      fields.push([path, child]);
    }
  }
  return fields;
}

function MetadataFields({
  metadata,
}: {
  metadata: Record<string, unknown>;
}) {
  const fields = flattenMetadata(metadata);
  return (
    <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {fields.map(([label, value]) => (
        <div
          key={label}
          className="min-w-0 rounded-lg border border-surface-200 bg-surface-50 px-3 py-2 dark:border-surface-700 dark:bg-surface-800/60"
        >
          <dt className="text-[10px] font-semibold uppercase tracking-wide text-surface-400">
            {label}
          </dt>
          <dd className="mt-1 break-words text-xs text-surface-700 dark:text-surface-200">
            {Array.isArray(value) ? (
              <span className="flex flex-wrap gap-1">
                {value.map((item, index) => (
                  <span
                    key={index}
                    className="chip bg-surface-200 text-surface-700 dark:bg-surface-700 dark:text-surface-200"
                  >
                    {item !== null && typeof item === "object"
                      ? JSON.stringify(item)
                      : String(item)}
                  </span>
                ))}
                {value.length === 0 && <span className="text-surface-400">Empty list</span>}
              </span>
            ) : value === null ? (
              <span className="text-surface-400">None</span>
            ) : typeof value === "boolean" ? (
              value ? "Yes" : "No"
            ) : typeof value === "object" ? (
              <span className="text-surface-400">Empty object</span>
            ) : (
              String(value)
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function sanitizedHtmlDocument(html: string): string {
  const parsed = new DOMParser().parseFromString(html, "text/html");
  parsed
    .querySelectorAll("script, iframe, object, embed, form, meta, base, link")
    .forEach((element) => element.remove());
  parsed.querySelectorAll("*").forEach((element) => {
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.toLowerCase();
      const value = attribute.value.trim().toLowerCase();
      if (
        name.startsWith("on") ||
        ((name === "src" || name === "href") &&
          !value.startsWith("data:") &&
          !value.startsWith("blob:") &&
          !value.startsWith("#"))
      ) {
        element.removeAttribute(attribute.name);
      }
    }
  });
  return [
    "<!doctype html><html><head><meta charset=\"utf-8\">",
    "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'\">",
    "<style>:root{color-scheme:light;font-family:Inter,ui-sans-serif,system-ui,sans-serif}",
    "body{margin:24px;color:#172033;line-height:1.55;overflow-wrap:anywhere}",
    "img{max-width:100%;height:auto}pre{overflow:auto;padding:12px;border-radius:8px;background:#f1f5f9}",
    "table{border-collapse:collapse}th,td{border:1px solid #cbd5e1;padding:6px 8px}</style>",
    "</head><body>",
    parsed.body.innerHTML,
    "</body></html>",
  ].join("");
}

function RichPreview({ artifact }: { artifact: ArtifactDetail }) {
  const content = artifact.content ?? "";
  if (artifact.artifact_type === "markdown") {
    return (
      <div className="mx-auto max-w-5xl rounded-xl border border-surface-200 bg-white p-6 text-sm shadow-sm dark:border-surface-700 dark:bg-surface-900">
        <Markdown text={content} />
      </div>
    );
  }
  if (
    artifact.artifact_type === "html" ||
    artifact.media_type === "text/html"
  ) {
    return (
      <iframe
        title={"Rich preview of " + artifact.filename}
        srcDoc={sanitizedHtmlDocument(content)}
        sandbox=""
        referrerPolicy="no-referrer"
        className="h-full min-h-[70vh] w-full rounded-xl border border-surface-200 bg-white dark:border-surface-700"
      />
    );
  }
  try {
    return (
      <div className="mx-auto max-w-5xl rounded-xl border border-surface-200 bg-white p-4 shadow-sm dark:border-surface-700 dark:bg-surface-900">
        <JsonTree value={JSON.parse(content)} />
      </div>
    );
  } catch {
    return (
      <div className="rounded-lg bg-amber-50 p-3 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-300">
        This legacy JSON payload is malformed. Switch to Raw to inspect it.
      </div>
    );
  }
}

function ExpandedArtifactModal({
  artifact,
  blobUrl,
  onClose,
  onDownload,
}: {
  artifact: ArtifactDetail;
  blobUrl: string | null;
  onClose: () => void;
  onDownload: () => void;
}) {
  const richCapable = isRichType(artifact) && artifact.content != null;
  const [mode, setMode] = useState<"rich" | "raw">(
    richCapable ? "rich" : "raw",
  );

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-3 backdrop-blur-sm sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="expanded-artifact-title"
      data-testid="expanded-artifact-modal"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="flex h-full max-h-[94vh] w-full max-w-[1500px] flex-col overflow-hidden rounded-2xl border border-surface-200 bg-surface-50 shadow-2xl dark:border-surface-700 dark:bg-surface-950">
        <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-surface-200 bg-white px-4 py-3 dark:border-surface-700 dark:bg-surface-900">
          <ArtifactIcon type={artifact.artifact_type} />
          <div className="min-w-0">
            <h2 id="expanded-artifact-title" className="truncate text-sm font-semibold text-surface-900 dark:text-surface-100">
              {artifact.name || artifact.filename}
            </h2>
            <p className="truncate text-xs text-surface-500">
              {artifact.filename} · {bytes(artifact.size_bytes)}
            </p>
          </div>
          {richCapable && (
            <div className="ml-auto flex rounded-lg bg-surface-100 p-0.5 dark:bg-surface-800" aria-label="Preview mode">
              <button
                type="button"
                onClick={() => setMode("rich")}
                aria-pressed={mode === "rich"}
                className={"rounded-md px-3 py-1.5 text-xs font-medium " + (mode === "rich" ? "bg-white text-surface-900 shadow-sm dark:bg-surface-700 dark:text-white" : "text-surface-500")}
              >
                Rich
              </button>
              <button
                type="button"
                onClick={() => setMode("raw")}
                aria-pressed={mode === "raw"}
                className={"rounded-md px-3 py-1.5 text-xs font-medium " + (mode === "raw" ? "bg-white text-surface-900 shadow-sm dark:bg-surface-700 dark:text-white" : "text-surface-500")}
              >
                Raw
              </button>
            </div>
          )}
          <button type="button" onClick={onDownload} className={(richCapable ? "" : "ml-auto ") + "btn btn-secondary !py-1.5"}>
            <Download size={14} /> Download
          </button>
          <button type="button" onClick={onClose} className="rounded-lg p-2 text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800" aria-label="Close expanded preview">
            <X size={17} />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
          {richCapable && mode === "rich" ? (
            <RichPreview artifact={artifact} />
          ) : artifact.content != null ? (
            <pre className="min-h-full whitespace-pre-wrap rounded-xl bg-surface-950 p-5 font-mono text-xs leading-relaxed text-surface-100">
              {artifact.artifact_type === "json"
                ? (() => {
                    try {
                      return JSON.stringify(JSON.parse(artifact.content ?? ""), null, 2);
                    } catch {
                      return artifact.content;
                    }
                  })()
                : artifact.content}
            </pre>
          ) : (
            <ContentPreview artifact={artifact} blobUrl={blobUrl} expanded />
          )}
        </div>
      </div>
    </div>
  );
}

export function ArtifactsView({
  workspace,
  liveTick,
}: {
  workspace: string;
  liveTick?: number;
}) {
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [producerIds, setProducerIds] = useState<string[]>([]);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [items, setItems] = useState<ArtifactItem[]>([]);
  const [selected, setSelected] = useState<ArtifactDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const listRequestRef = useRef(0);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(queryInput.trim());
      setPage(1);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [queryInput]);

  useEffect(() => {
    api
      .agents()
      .then((data) => setAgents(data.items))
      .catch((exc) => setError((exc as Error).message));
  }, []);

  useEffect(() => setPage(1), [workspace]);

  const fetchList = useCallback(() => {
    const requestId = ++listRequestRef.current;
    setLoading(true);
    const params: Record<string, string> = {
      workspace,
      page: String(page),
      page_size: String(PAGE_SIZE),
    };
    if (query) params.q = query;
    if (type) params.artifact_type = type;
    if (producerIds.length) params.agents = producerIds.join(",");
    if (dateFrom) params.date_from = localDateBound(dateFrom, false);
    if (dateTo) params.date_to = localDateBound(dateTo, true);
    api
      .artifacts(params)
      .then((data) => {
        if (requestId !== listRequestRef.current) return;
        setItems(data.items);
        setTotal(data.total);
        setTotalPages(data.total_pages);
        setError(null);
        setSelected((current) => {
          if (!current) return null;
          return data.items.some((item) => item.artifact_id === current.artifact_id)
            ? current
            : null;
        });
      })
      .catch((exc) => {
        if (requestId === listRequestRef.current) {
          setError((exc as Error).message);
        }
      })
      .finally(() => {
        if (requestId === listRequestRef.current) setLoading(false);
      });
  }, [workspace, query, type, producerIds, dateFrom, dateTo, page]);

  useEffect(() => fetchList(), [fetchList]);
  useEffect(() => {
    if (!liveTick) return;
    const timer = window.setTimeout(fetchList, 400);
    return () => window.clearTimeout(timer);
  }, [liveTick, fetchList]);

  const openDetail = useCallback(
    (artifactId: string) => {
      api
        .artifactDetail(workspace, artifactId)
        .then((detail) => {
          setSelected(detail);
          setExpanded(false);
          setError(null);
        })
        .catch((exc) => setError((exc as Error).message));
    },
    [workspace],
  );

  useEffect(() => {
    setBlobUrl(null);
    if (
      !selected?.available ||
      (!selected.media_type.startsWith("image/") &&
        selected.media_type !== "application/pdf")
    ) {
      return;
    }
    let active = true;
    let nextUrl: string | null = null;
    api
      .artifactBlob(workspace, selected.artifact_id)
      .then((blob) => {
        if (!active) return;
        nextUrl = URL.createObjectURL(blob);
        setBlobUrl(nextUrl);
      })
      .catch((exc) => active && setError((exc as Error).message));
    return () => {
      active = false;
      if (nextUrl) URL.revokeObjectURL(nextUrl);
    };
  }, [selected, workspace]);

  const download = useCallback(() => {
    if (!selected) return;
    api
      .artifactBlob(workspace, selected.artifact_id)
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = selected.filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
      })
      .catch((exc) => setError((exc as Error).message));
  }, [selected, workspace]);

  const metadataEntries = useMemo(
    () => Object.entries(selected?.metadata ?? {}),
    [selected],
  );

  return (
    <PageContainer width="bleed" scroll="none" className="flex" testId="artifacts-view">
      <section className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-surface-200 px-4 py-3 dark:border-surface-700/60">
          <div className="flex flex-wrap items-center gap-2">
            <div>
              <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100">Artifacts</h2>
              <p className="text-xs text-surface-500">Managed payloads produced by agents</p>
            </div>
            <span className="chip bg-surface-100 text-surface-600 dark:bg-surface-800 dark:text-surface-300">
              {total} artifact{total === 1 ? "" : "s"}
            </span>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <ProducerFilter
              agents={agents}
              value={producerIds}
              onChange={(next) => {
                setProducerIds(next);
                setPage(1);
              }}
            />
            <div className="flex items-center gap-1.5 text-xs text-surface-500">
              <CalendarDays size={13} className="shrink-0 text-surface-400" />
              <span>Produced</span>
            </div>
            <label className="relative flex items-center gap-1.5">
              <span className="sr-only">Produced from</span>
              <input
                type="date"
                value={dateFrom}
                max={dateTo || undefined}
                onChange={(event) => {
                  setDateFrom(event.target.value);
                  setPage(1);
                }}
                className={inputCls}
                aria-label="Produced from"
                title="Produced from"
                data-testid="artifact-date-from"
              />
            </label>
            <span className="text-xs text-surface-400">to</span>
            <label>
              <span className="sr-only">Produced through</span>
              <input
                type="date"
                value={dateTo}
                min={dateFrom || undefined}
                onChange={(event) => {
                  setDateTo(event.target.value);
                  setPage(1);
                }}
                className={inputCls}
                aria-label="Produced through"
                title="Produced through"
                data-testid="artifact-date-to"
              />
            </label>
            <div className="ml-auto flex items-center gap-2">
              <label className="relative">
                <Search size={13} className="absolute left-2 top-2 text-surface-400" />
                <input
                  value={queryInput}
                  onChange={(event) => setQueryInput(event.target.value)}
                  placeholder="Search artifacts"
                  className={`${inputCls} w-52 pl-7 pr-7`}
                  aria-label="Search artifacts"
                />
                {queryInput && (
                  <button type="button" onClick={() => setQueryInput("")} className="absolute right-2 top-1.5 text-surface-400" aria-label="Clear search">
                    <X size={14} />
                  </button>
                )}
              </label>
              <select
                value={type}
                onChange={(event) => {
                  setType(event.target.value);
                  setPage(1);
                }}
                className={inputCls}
                aria-label="Artifact type"
              >
                <option value="">All types</option>
                <option value="file">Files</option>
                <option value="text">Text</option>
                <option value="json">JSON</option>
                <option value="markdown">Markdown</option>
                <option value="html">HTML</option>
              </select>
            </div>
          </div>
        </header>
        {error && <div className="m-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-300">{error}</div>}
        <div className="min-h-0 flex-1 overflow-y-auto">
          {loading && items.length === 0 ? (
            <div className="p-8 text-center text-sm text-surface-500">Loading artifacts…</div>
          ) : items.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center text-surface-500">
              <FileText size={30} className="text-surface-300 dark:text-surface-600" />
              <p className="text-sm">No artifacts match this workspace and filter.</p>
              <p className="max-w-sm text-xs">Artifacts appear here after an agent uses <code>artifact_put</code>.</p>
            </div>
          ) : (
            items.map((item) => (
              <ArtifactRow key={item.artifact_id} item={item} active={selected?.artifact_id === item.artifact_id} onClick={() => openDetail(item.artifact_id)} />
            ))
          )}
        </div>
        {total > 0 && (
          <footer className="flex shrink-0 items-center justify-between border-t border-surface-200 px-4 py-2 text-xs text-surface-500 dark:border-surface-700/60">
            <span>
              Page {page} of {Math.max(totalPages, 1)} · {total} result{total === 1 ? "" : "s"}
            </span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                disabled={page <= 1 || loading}
                className="btn btn-secondary !px-2 !py-1 disabled:cursor-not-allowed disabled:opacity-40"
                aria-label="Previous artifacts page"
                data-testid="artifact-page-previous"
              >
                <ChevronLeft size={14} /> Previous
              </button>
              <button
                type="button"
                onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                disabled={page >= totalPages || loading}
                className="btn btn-secondary !px-2 !py-1 disabled:cursor-not-allowed disabled:opacity-40"
                aria-label="Next artifacts page"
                data-testid="artifact-page-next"
              >
                Next <ChevronRight size={14} />
              </button>
            </div>
          </footer>
        )}
      </section>

      {selected && (
        <ResizablePanel storageKey="artifact-detail" defaultWidth={500} testId="artifact-detail">
          <div className="flex items-start gap-3 border-b border-surface-200 pb-3 dark:border-surface-700/60">
            <div className="mt-0.5 rounded-lg bg-accent-100 p-2 dark:bg-accent-900/30"><ArtifactIcon type={selected.artifact_type} /></div>
            <div className="min-w-0 flex-1">
              <h3 className="truncate text-sm font-semibold text-surface-900 dark:text-surface-100">{selected.name || selected.filename}</h3>
              <p className="truncate text-xs text-surface-500">{selected.filename}</p>
            </div>
            <button type="button" onClick={() => setExpanded(true)} className="rounded p-1 text-surface-400 hover:bg-surface-100 hover:text-accent-600 dark:hover:bg-surface-800" aria-label="Open expanded artifact preview" title="Open expanded">
              <Maximize2 size={16} />
            </button>
            <button type="button" onClick={() => setSelected(null)} className="rounded p-1 text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800" aria-label="Close artifact detail"><X size={16} /></button>
          </div>
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pt-4">
            <div className="grid grid-cols-2 gap-3 text-xs">
              <Info label="Type" value={selected.artifact_type} />
              <Info label="Size" value={bytes(selected.size_bytes)} />
              <Info label="Agent" value={selected.created_by || "anonymous"} />
              <Info label="Created" value={dateTime(selected.created_at)} />
            </div>
            <div className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs ${selected.managed ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300" : "bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-300"}`}>
              {selected.managed ? <HardDrive size={15} /> : <Database size={15} />}
              {selected.managed ? "Payload stored in the configured artifact adapter" : "Legacy database record"}
            </div>
            <div>
              <div className="mb-2 flex items-center justify-between">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-surface-500">Preview</h4>
                {selected.available && <button type="button" onClick={download} className="flex items-center gap-1 rounded-lg border border-surface-200 px-2 py-1 text-xs text-surface-700 hover:bg-surface-50 dark:border-surface-700 dark:text-surface-200 dark:hover:bg-surface-800"><Download size={13} /> Download</button>}
              </div>
              <ContentPreview artifact={selected} blobUrl={blobUrl} />
            </div>
            {metadataEntries.length > 0 && (
              <div>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-surface-500">Metadata</h4>
                <MetadataFields metadata={selected.metadata} />
              </div>
            )}
            <Info label="Artifact ID" value={selected.artifact_id} mono />
            {selected.source_path && <Info label="Imported from" value={selected.source_path} mono />}
          </div>
        </ResizablePanel>
      )}
      {selected && expanded && (
        <ExpandedArtifactModal
          key={selected.artifact_id}
          artifact={selected}
          blobUrl={blobUrl}
          onClose={() => setExpanded(false)}
          onDownload={download}
        />
      )}
    </PageContainer>
  );
}

function Info({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-surface-400">{label}</div>
      <div className={`mt-0.5 break-words text-surface-700 dark:text-surface-200 ${mono ? "font-mono text-[11px]" : ""}`}>{value}</div>
    </div>
  );
}
