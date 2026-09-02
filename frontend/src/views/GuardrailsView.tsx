import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Info,
  Link2,
  Plus,
  RotateCw,
  Save,
  ShieldAlert,
  Trash2,
  Users,
} from "lucide-react";
import {
  api,
  ApiError,
  type AgentGroupRecord,
  type AgentRow,
  type CapabilityRow,
  type GuardrailAssignment,
  type GuardrailDenial,
  type GuardrailEvaluatorKind,
  type GuardrailInUseDetails,
  type GuardrailMode,
  type GuardrailRecord,
  type GuardrailScopeKind,
  type GuardrailSurface,
  type GuardrailVersionStatus,
  type GuardrailVersionMode,
} from "../api";
import { AgentSelect } from "../components/AgentSelect";
import { useConfirm } from "../components/Confirm";
import { PageContainer } from "../components/PageContainer";
import { useWorkspaceName } from "../components/WorkspaceNames";
import {
  CatalogExportButton,
  CatalogImportButton,
  catalogEntityFilename,
  uniqueImportedName,
} from "../components/CatalogTransfer";

const inputCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";
const sectionCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900";

const SURFACES: GuardrailSurface[] = ["message", "artifact", "handoff"];
const SURFACE_LABELS: Record<GuardrailSurface, string> = {
  message: "Messages",
  artifact: "Artifacts",
  handoff: "Handoffs",
};
const FIELD_OPTIONS: Array<{
  value: string;
  surface: GuardrailSurface;
  label: string;
  description: string;
}> = [
  { value: "subject", surface: "message", label: "Message subject", description: "The subject line." },
  { value: "body", surface: "message", label: "Message body", description: "The text written by the agent." },
  { value: "artifact_type", surface: "artifact", label: "Artifact type", description: "The artifact format or category." },
  { value: "name", surface: "artifact", label: "Artifact name", description: "The artifact display name." },
  { value: "content", surface: "artifact", label: "Artifact content", description: "Inline artifact contents." },
  { value: "metadata", surface: "artifact", label: "Artifact metadata", description: "The artifact metadata object." },
  { value: "path", surface: "artifact", label: "Artifact path", description: "The referenced local path." },
  { value: "payload", surface: "handoff", label: "Handoff instructions", description: "The work passed to another agent." },
  { value: "acceptance_criteria", surface: "handoff", label: "Acceptance criteria", description: "The criteria used to accept the handoff." },
];
const STATUSES: GuardrailVersionStatus[] = [
  "draft",
  "active",
  "deprecated",
  "archived",
];
const MODES: GuardrailMode[] = ["audit", "warn", "enforce"];
const VERSION_MODES: GuardrailVersionMode[] = ["latest", "pinned"];

function splitList(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function errorText(exc: unknown): string {
  if (exc instanceof ApiError) {
    return `${exc.code}: ${exc.message}${detailsText(exc.details) ? ` ${detailsText(exc.details)}` : ""}`;
  }
  return (exc as Error).message;
}

function detailsText(details: unknown): string {
  if (!details || typeof details !== "object") return "";
  const typed = details as GuardrailInUseDetails;
  if (!Array.isArray(typed.assignments)) return "";
  return `Assignments: ${typed.assignments.join(", ")}`;
}

function JsonCell({ value }: { value: unknown }) {
  return (
    <pre className="max-h-28 overflow-auto rounded-md bg-surface-100 dark:bg-surface-800 px-2 py-1 text-[11px] leading-5 text-surface-700 dark:text-surface-300">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function HeaderForm({
  label,
  helpText,
  onCreate,
}: {
  label: string;
  helpText: string;
  onCreate: (body: { name: string; description?: string }) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await onCreate({
        name: name.trim(),
        description: description.trim() || undefined,
      });
      setName("");
      setDescription("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <p className="mb-3 text-xs text-surface-500 dark:text-surface-400">
        {helpText}
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] gap-2">
        <label className="space-y-1 text-[11px] font-medium text-surface-600 dark:text-surface-300">
          {label} name
          <input
            className={`${inputCls} block w-full`}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={`e.g. ${label === "Group" ? "Finance agents" : "Protect customer data"}`}
          />
        </label>
        <label className="space-y-1 text-[11px] font-medium text-surface-600 dark:text-surface-300">
          Description <span className="font-normal text-surface-400">(optional)</span>
          <input
            className={`${inputCls} block w-full`}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Explain its purpose"
          />
        </label>
        <button
          className="btn btn-primary self-end justify-center"
          onClick={submit}
          disabled={busy || !name.trim()}
        >
          <Plus size={14} /> Create {label.toLowerCase()}
        </button>
      </div>
    </div>
  );
}

function GroupsPanel({
  groups,
  agents,
  selected,
  onSelect,
  onRefresh,
  onError,
}: {
  groups: AgentGroupRecord[];
  agents: AgentRow[];
  selected: string | null;
  onSelect: (id: string | null) => void;
  onRefresh: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const { confirm, dialog } = useConfirm();
  const [memberAgent, setMemberAgent] = useState("");

  const current = groups.find((group) => group.group_id === selected) ?? null;
  const currentMemberIds = new Set(
    (current?.members ?? []).map((member) => member.agent_id),
  );
  const availableAgents = agents.filter(
    (agent) => !currentMemberIds.has(agent.agent_id),
  );

  useEffect(() => {
    if (!current) {
      setMemberAgent("");
      return;
    }
    if (!availableAgents.some((agent) => agent.agent_id === memberAgent)) {
      setMemberAgent(availableAgents[0]?.agent_id ?? "");
    }
  }, [current?.group_id, memberAgent, availableAgents]);

  const create = async (body: { name: string; description?: string }) => {
    try {
      const created = await api.createGuardrailGroup(body);
      onSelect(created.group_id);
      await onRefresh();
    } catch (exc) {
      onError(errorText(exc));
    }
  };

  const remove = (group: AgentGroupRecord) => {
    confirm({
      title: `Delete ${group.name}?`,
      body: "The group can only be deleted when no guardrail assignment uses it.",
      onConfirm: async () => {
        try {
          await api.deleteGuardrailGroup(group.group_id);
          onSelect(null);
          await onRefresh();
        } catch (exc) {
          onError(errorText(exc));
        }
      },
    });
  };

  const removeMember = (agentId: string) => {
    if (!current) return;
    confirm({
      title: `Remove ${agentId} from ${current.name}?`,
      body: "Guardrails assigned to this group will stop applying to this agent.",
      onConfirm: async () => {
        await api.removeGuardrailGroupMember(current.group_id, agentId);
        await onRefresh();
      },
    });
  };

  const addMember = async () => {
    if (!current || !memberAgent) return;
    try {
      await api.addGuardrailGroupMember(current.group_id, {
        agent_id: memberAgent,
      });
      await onRefresh();
    } catch (exc) {
      onError(errorText(exc));
    }
  };

  return (
    <section className={`${sectionCls} p-4 min-h-[420px]`}>
      {dialog}
      <div className="flex items-center gap-2 mb-3">
        <Users size={16} className="text-accent-600 dark:text-accent-400" />
        <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100">
          1. Agent groups
        </h2>
      </div>
      <HeaderForm
        label="Group"
        helpText="Create a reusable roster, then add agents from the list. Assignments made to the group apply to every member."
        onCreate={create}
      />
      <div className="mt-4 grid grid-cols-1 lg:grid-cols-[minmax(180px,0.7fr)_minmax(320px,1.3fr)] gap-3">
        <div className="space-y-2">
          {groups.map((group) => (
            <button
              key={group.group_id}
              className={`w-full text-left rounded-lg border px-3 py-2 text-xs transition-colors ${
                selected === group.group_id
                  ? "border-accent-400 bg-accent-50 dark:bg-accent-900/20"
                  : "border-surface-200 dark:border-surface-700 hover:bg-surface-50 dark:hover:bg-surface-800"
              }`}
              onClick={() => onSelect(group.group_id)}
            >
              <span className="block font-semibold text-surface-800 dark:text-surface-100 truncate">
                {group.name}
              </span>
              <span className="block text-surface-500 dark:text-surface-400 truncate">
                {(group.members ?? []).length} agent{(group.members ?? []).length === 1 ? "" : "s"}
              </span>
            </button>
          ))}
          {groups.length === 0 && (
            <p className="rounded-lg bg-surface-50 dark:bg-surface-800 p-3 text-xs text-surface-500">
              No groups yet. Create one above to build an agent roster.
            </p>
          )}
        </div>
        <div className="rounded-lg border border-surface-200 dark:border-surface-700 p-4">
          {current ? (
            <>
              <div className="flex items-center gap-2">
                <p className="text-xs font-semibold text-surface-800 dark:text-surface-100 truncate">
                  {current.name}
                </p>
                <button
                  className="ml-auto btn btn-secondary !py-1"
                  onClick={() => remove(current)}
                  title="Delete group"
                >
                  <Trash2 size={13} />
                  <span>Delete group</span>
                </button>
              </div>
              <p className="mt-1 text-xs text-surface-500 dark:text-surface-400">
                {current.description || "Choose which registered agents belong to this group."}
              </p>
              <div className="mt-4 rounded-lg bg-surface-50 dark:bg-surface-800/70 p-3">
                <label className="block text-xs font-semibold text-surface-700 dark:text-surface-200">
                  Add an agent to this group
                </label>
                <p className="mt-1 mb-2 text-[11px] text-surface-500 dark:text-surface-400">
                  The picker is populated from registered Nexus agents.
                </p>
                <div className="flex flex-wrap gap-2">
                  <div className="min-w-[230px] flex-1">
                    <AgentSelect
                      value={memberAgent}
                      onChange={setMemberAgent}
                      agents={availableAgents}
                      label="Agent"
                      allowEmpty={false}
                      placeholder={availableAgents.length ? "Select an agent" : "All agents are members"}
                    />
                  </div>
                  <button
                    className="btn btn-primary !py-1"
                    onClick={addMember}
                    disabled={!memberAgent}
                  >
                    <Plus size={13} /> Add agent
                  </button>
                </div>
              </div>
              <div className="mt-4">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-surface-400">
                  Agents in this group ({(current.members ?? []).length})
                </p>
                <div className="space-y-1 max-h-44 overflow-auto">
                  {(current.members ?? []).map((member) => {
                    const agent = agents.find((item) => item.agent_id === member.agent_id);
                    return (
                      <div
                        key={member.agent_id}
                        className="flex items-center gap-2 rounded-md bg-surface-50 dark:bg-surface-800 px-2 py-2 text-xs"
                      >
                        <span className="font-mono truncate">{member.agent_id}</span>
                        {agent?.role && <span className="text-surface-400">{agent.role}</span>}
                        <button
                          className="ml-auto btn btn-secondary !px-2 !py-1"
                          title={`Remove ${member.agent_id}`}
                          onClick={() => removeMember(member.agent_id)}
                        >
                          <Trash2 size={12} /> Remove
                        </button>
                      </div>
                    );
                  })}
                  {(current.members ?? []).length === 0 && (
                    <p className="text-xs text-surface-500 dark:text-surface-400">
                      This group has no agents yet.
                    </p>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="flex min-h-[220px] items-center justify-center text-center">
              <p className="max-w-xs text-xs text-surface-500 dark:text-surface-400">
                Select a group to see its roster and add registered agents.
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function LegacyGuardrailsPanel({
  guardrails,
  selected,
  onSelect,
  onRefresh,
  onError,
}: {
  guardrails: GuardrailRecord[];
  selected: GuardrailRecord | null;
  onSelect: (id: string | null) => void;
  onRefresh: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [status, setStatus] = useState<GuardrailVersionStatus>("active");
  const [kind, setKind] = useState("keyword_blocklist");
  const [keywords, setKeywords] = useState("");
  const [fields, setFields] = useState("body");
  const [surfaces, setSurfaces] = useState<GuardrailSurface[]>(["message"]);

  const create = async (body: { name: string; description?: string }) => {
    const created = await api.createGuardrail(body);
    onSelect(created.guardrail_id);
    await onRefresh();
  };

  const remove = async (guardrail: GuardrailRecord) => {
    try {
      await api.deleteGuardrail(guardrail.guardrail_id);
      onSelect(null);
      await onRefresh();
    } catch (exc) {
      if (exc instanceof ApiError) {
        onError(`${exc.code}: ${exc.message} ${detailsText(exc.details)}`);
      } else {
        onError((exc as Error).message);
      }
    }
  };

  const addVersion = async () => {
    if (!selected) return;
    const words = splitList(keywords);
    const evaluator_config =
      kind === "keyword_blocklist"
        ? { kind, keywords: words }
        : { kind, patterns: words };
    try {
      await api.addGuardrailVersion(selected.guardrail_id, {
        status,
        evaluator_kind: "deterministic",
        evaluator_config,
        surfaces,
        field_targets: splitList(fields),
      });
      setKeywords("");
      await onRefresh();
    } catch (exc) {
      onError((exc as Error).message);
    }
  };

  const toggleSurface = (surface: GuardrailSurface) => {
    setSurfaces((current) =>
      current.includes(surface)
        ? current.filter((item) => item !== surface)
        : [...current, surface],
    );
  };

  return (
    <section className={`${sectionCls} p-4 min-h-[440px]`}>
      <div className="flex items-center gap-2 mb-3">
        <ShieldAlert size={16} className="text-rose-500" />
        <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100">
          Guardrails
        </h2>
      </div>
      <HeaderForm
        label="Guardrail"
        helpText="Create a named guardrail, then configure how its rule detects content."
        onCreate={create}
      />
      <div className="mt-4 grid grid-cols-1 xl:grid-cols-[minmax(0,0.9fr)_minmax(340px,1fr)] gap-3">
        <div className="space-y-2">
          {guardrails.map((guardrail) => (
            <div
              key={guardrail.guardrail_id}
              className={`w-full rounded-lg border flex items-start text-xs transition-colors ${
                selected?.guardrail_id === guardrail.guardrail_id
                  ? "border-accent-400 bg-accent-50 dark:bg-accent-900/20"
                  : "border-surface-200 dark:border-surface-700 hover:bg-surface-50 dark:hover:bg-surface-800"
              }`}
              data-testid={`guardrail-${guardrail.guardrail_id}`}
            >
              <button
                className="min-w-0 flex-1 text-left px-3 py-2"
                onClick={() => onSelect(guardrail.guardrail_id)}
              >
                <span className="block font-semibold text-surface-800 dark:text-surface-100 truncate">
                  {guardrail.name}
                </span>
                <span className="text-surface-500 dark:text-surface-400">
                  v{guardrail.latest_version} active{" "}
                  {guardrail.latest_active_version ?? "-"}
                </span>
              </button>
              <CatalogExportButton
                catalog="guardrails"
                filename={catalogEntityFilename(
                  "okto-nexus-guardrail",
                  guardrail.name,
                )}
                className="btn btn-secondary !px-2 !py-1 !text-[10px] shrink-0 m-2 ml-0"
                label="Export JSON"
                title={`Export ${guardrail.name} as JSON`}
                testId={`export-guardrail-${guardrail.guardrail_id}`}
                onExport={() => ({
                  name: guardrail.name,
                  description: guardrail.description,
                  versions: (guardrail.versions ?? []).map(
                    ({
                      status: versionStatus,
                      evaluator_kind,
                      evaluator_config,
                      surfaces: versionSurfaces,
                      field_targets,
                    }) => ({
                      status: versionStatus,
                      evaluator_kind,
                      evaluator_config,
                      surfaces: versionSurfaces,
                      field_targets,
                    }),
                  ),
                })}
              />
            </div>
          ))}
        </div>
        <div className="rounded-lg border border-surface-200 dark:border-surface-700 p-3 min-w-0">
          {selected ? (
            <>
              <div className="flex items-center gap-2">
                <p className="text-xs font-semibold text-surface-800 dark:text-surface-100 truncate">
                  {selected.name}
                </p>
                <CatalogExportButton
                  catalog="guardrails"
                  filename={catalogEntityFilename(
                    "okto-nexus-guardrail",
                    selected.name,
                  )}
                  className="ml-auto btn btn-secondary !py-1"
                  title={`Export ${selected.name} as JSON`}
                  onExport={() => ({
                    name: selected.name,
                    description: selected.description,
                    versions: (selected.versions ?? []).map(
                      ({
                        status: versionStatus,
                        evaluator_kind,
                        evaluator_config,
                        surfaces: versionSurfaces,
                        field_targets,
                      }) => ({
                        status: versionStatus,
                        evaluator_kind,
                        evaluator_config,
                        surfaces: versionSurfaces,
                        field_targets,
                      }),
                    ),
                  })}
                />
                <button
                  className="btn btn-secondary !py-1"
                  onClick={() => remove(selected)}
                  title="Delete guardrail"
                >
                  <Trash2 size={13} />
                </button>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <select
                  className={inputCls}
                  value={status}
                  onChange={(e) =>
                    setStatus(e.target.value as GuardrailVersionStatus)
                  }
                >
                  {STATUSES.map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>
                <select
                  className={inputCls}
                  value={kind}
                  onChange={(e) => setKind(e.target.value)}
                >
                  <option value="keyword_blocklist">keyword_blocklist</option>
                  <option value="regex">regex</option>
                </select>
                <input
                  className={`${inputCls} col-span-2`}
                  value={keywords}
                  onChange={(e) => setKeywords(e.target.value)}
                  placeholder="keyword or pattern list"
                />
                <input
                  className={`${inputCls} col-span-2`}
                  value={fields}
                  onChange={(e) => setFields(e.target.value)}
                  placeholder="field targets"
                />
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {SURFACES.map((surface) => (
                  <label
                    key={surface}
                    className="inline-flex items-center gap-1 text-xs text-surface-600 dark:text-surface-300"
                  >
                    <input
                      type="checkbox"
                      checked={surfaces.includes(surface)}
                      onChange={() => toggleSurface(surface)}
                    />
                    {surface}
                  </label>
                ))}
              </div>
              <button
                className="mt-3 btn btn-primary"
                onClick={addVersion}
                disabled={!keywords.trim() || !fields.trim() || surfaces.length === 0}
              >
                <Save size={14} /> Add version
              </button>
              <div className="mt-4 overflow-auto max-h-48">
                <table className="min-w-full text-xs">
                  <thead>
                    <tr className="text-left text-[11px] uppercase text-surface-400">
                      <th className="py-1 pr-3">Version</th>
                      <th className="py-1 pr-3">Status</th>
                      <th className="py-1 pr-3">Surfaces</th>
                      <th className="py-1">Fields</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(selected.versions ?? []).map((version) => (
                      <tr
                        key={version.version}
                        className="border-t border-surface-100 dark:border-surface-800"
                      >
                        <td className="py-1 pr-3 font-mono">v{version.version}</td>
                        <td className="py-1 pr-3">{version.status}</td>
                        <td className="py-1 pr-3">{version.surfaces.join(", ")}</td>
                        <td className="py-1">{version.field_targets.join(", ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="text-xs text-surface-500 dark:text-surface-400">
              Select a guardrail
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

const REGEX_TEMPLATES = [
  {
    label: "Email address",
    pattern: String.raw`\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b`,
  },
  {
    label: "Credit card-like number",
    pattern: String.raw`\b(?:\d[ -]*?){13,19}\b`,
  },
  {
    label: "API key or token",
    pattern: String.raw`\b(?:api[_-]?key|token)\s*[:=]\s*['"]?[A-Za-z0-9_-]{16,}\b`,
  },
];

function ruleSummary(version: NonNullable<GuardrailRecord["versions"]>[number]) {
  const kind = String(version.evaluator_config.kind ?? "custom");
  if (kind === "keyword_blocklist") {
    return `${(version.evaluator_config.keywords as unknown[] | undefined)?.length ?? 0} blocked keyword(s)`;
  }
  if (kind === "regex") {
    return `${(version.evaluator_config.patterns as unknown[] | undefined)?.length ?? 0} regular expression(s)`;
  }
  if (kind === "token_limit") {
    return `Maximum ${String(version.evaluator_config.max_tokens ?? "?")} tokens`;
  }
  if (kind === "pii_detection") return "Built-in personal data detection";
  return kind;
}

function GuardrailsPanel({
  guardrails,
  selected,
  onSelect,
  onRefresh,
  onError,
}: {
  guardrails: GuardrailRecord[];
  selected: GuardrailRecord | null;
  onSelect: (id: string | null) => void;
  onRefresh: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const { confirm, dialog } = useConfirm();
  const [status, setStatus] = useState<GuardrailVersionStatus>("draft");
  const [kind, setKind] = useState<
    "keyword_blocklist" | "regex" | "pii_detection" | "token_limit"
  >("keyword_blocklist");
  const [ruleInput, setRuleInput] = useState("");
  const [sample, setSample] = useState("");
  const [ignoreCase, setIgnoreCase] = useState(true);
  const [maxTokens, setMaxTokens] = useState("1000");
  const [fields, setFields] = useState<string[]>(["body"]);
  const [surfaces, setSurfaces] = useState<GuardrailSurface[]>(["message"]);

  const patterns = useMemo(
    () =>
      ruleInput
        .split(/\r?\n/)
        .map((item) => item.trim())
        .filter(Boolean),
    [ruleInput],
  );
  const regexCheck = useMemo(() => {
    if (kind !== "regex" || patterns.length === 0) return null;
    try {
      const compiled = patterns.map(
        (pattern) => new RegExp(pattern, ignoreCase ? "i" : undefined),
      );
      return {
        valid: true as const,
        matches: sample ? compiled.some((expression) => expression.test(sample)) : false,
      };
    } catch (exc) {
      return { valid: false as const, message: (exc as Error).message };
    }
  }, [ignoreCase, kind, patterns, sample]);

  const create = async (body: { name: string; description?: string }) => {
    try {
      const created = await api.createGuardrail(body);
      onSelect(created.guardrail_id);
      await onRefresh();
    } catch (exc) {
      onError(errorText(exc));
    }
  };

  const remove = (guardrail: GuardrailRecord) => {
    confirm({
      title: `Delete ${guardrail.name}?`,
      body: "A guardrail can only be deleted when no assignment uses it.",
      onConfirm: async () => {
        try {
          await api.deleteGuardrail(guardrail.guardrail_id);
          onSelect(null);
          await onRefresh();
        } catch (exc) {
          onError(errorText(exc));
        }
      },
    });
  };

  const toggleSurface = (surface: GuardrailSurface) => {
    setSurfaces((current) => {
      const next = current.includes(surface)
        ? current.filter((item) => item !== surface)
        : [...current, surface];
      const allowedFields = new Set(
        FIELD_OPTIONS.filter((option) => next.includes(option.surface)).map(
          (option) => option.value,
        ),
      );
      setFields((currentFields) => {
        const retained = currentFields.filter((field) => allowedFields.has(field));
        if (!current.includes(surface) && !retained.some((field) =>
          FIELD_OPTIONS.some(
            (option) => option.surface === surface && option.value === field,
          ),
        )) {
          const defaultField = FIELD_OPTIONS.find(
            (option) => option.surface === surface,
          )?.value;
          if (defaultField) retained.push(defaultField);
        }
        return retained;
      });
      return next;
    });
  };

  const toggleField = (value: string) => {
    setFields((current) =>
      current.includes(value)
        ? current.filter((field) => field !== value)
        : [...current, value],
    );
  };

  const requiresEntries = kind === "keyword_blocklist" || kind === "regex";
  const canSave =
    Boolean(selected) &&
    surfaces.length > 0 &&
    fields.length > 0 &&
    (!requiresEntries || patterns.length > 0) &&
    (kind !== "regex" || regexCheck?.valid === true) &&
    (kind !== "token_limit" || Number.isInteger(Number(maxTokens)) && Number(maxTokens) >= 0);

  const addVersion = async () => {
    if (!selected || !canSave) return;
    const evaluator_config: Record<string, unknown> = { kind };
    if (kind === "keyword_blocklist") evaluator_config.keywords = splitList(ruleInput);
    if (kind === "regex") {
      evaluator_config.patterns = patterns;
      evaluator_config.ignore_case = ignoreCase;
    }
    if (kind === "token_limit") evaluator_config.max_tokens = Number(maxTokens);
    try {
      await api.addGuardrailVersion(selected.guardrail_id, {
        status,
        evaluator_kind: "deterministic",
        evaluator_config,
        surfaces,
        field_targets: fields,
      });
      setRuleInput("");
      setSample("");
      await onRefresh();
    } catch (exc) {
      onError(errorText(exc));
    }
  };

  const changeVersionStatus = async (version: number, value: GuardrailVersionStatus) => {
    if (!selected) return;
    try {
      await api.updateGuardrailVersionStatus(selected.guardrail_id, version, {
        status: value,
      });
      await onRefresh();
    } catch (exc) {
      onError(errorText(exc));
    }
  };

  return (
    <section className={`${sectionCls} p-4 min-h-[520px]`}>
      {dialog}
      <div className="flex items-center gap-2 mb-3">
        <ShieldAlert size={16} className="text-rose-500" />
        <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100">
          2. Guardrail rules
        </h2>
      </div>
      <HeaderForm
        label="Guardrail"
        helpText="A guardrail defines what content to inspect and what should count as a match. It does not target agents until you create an assignment below."
        onCreate={create}
      />

      <div className="mt-4 grid grid-cols-1 xl:grid-cols-[minmax(190px,0.65fr)_minmax(420px,1.35fr)] gap-3">
        <div className="space-y-2">
          {guardrails.map((guardrail) => (
            <button
              key={guardrail.guardrail_id}
              className={`w-full rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
                selected?.guardrail_id === guardrail.guardrail_id
                  ? "border-accent-400 bg-accent-50 dark:bg-accent-900/20"
                  : "border-surface-200 dark:border-surface-700 hover:bg-surface-50 dark:hover:bg-surface-800"
              }`}
              data-testid={`guardrail-${guardrail.guardrail_id}`}
              onClick={() => onSelect(guardrail.guardrail_id)}
            >
              <span className="block font-semibold text-surface-800 dark:text-surface-100 truncate">
                {guardrail.name}
              </span>
              <span className="block text-surface-500 dark:text-surface-400">
                {guardrail.latest_version} version{guardrail.latest_version === 1 ? "" : "s"} · active v{guardrail.latest_active_version ?? "none"}
              </span>
            </button>
          ))}
          {guardrails.length === 0 && (
            <p className="rounded-lg bg-surface-50 dark:bg-surface-800 p-3 text-xs text-surface-500">
              No guardrails yet. Create one above, then configure its first rule.
            </p>
          )}
        </div>

        <div className="rounded-lg border border-surface-200 dark:border-surface-700 p-4 min-w-0">
          {selected ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-surface-800 dark:text-surface-100 truncate">
                    Configure rule: {selected.name}
                  </p>
                  <p className="text-[11px] text-surface-500 dark:text-surface-400">
                    {selected.description || "Choose the detector, content surfaces and fields."}
                  </p>
                </div>
                <CatalogExportButton
                  catalog="guardrails"
                  filename={catalogEntityFilename("okto-nexus-guardrail", selected.name)}
                  className="ml-auto btn btn-secondary !py-1"
                  title={`Export ${selected.name} as JSON`}
                  onExport={() => ({
                    name: selected.name,
                    description: selected.description,
                    versions: (selected.versions ?? []).map((version) => ({
                      status: version.status,
                      evaluator_kind: version.evaluator_kind,
                      evaluator_config: version.evaluator_config,
                      surfaces: version.surfaces,
                      field_targets: version.field_targets,
                    })),
                  })}
                />
                <button className="btn btn-secondary !py-1" onClick={() => remove(selected)}>
                  <Trash2 size={13} /> Delete
                </button>
              </div>

              <div className="mt-4 space-y-4 rounded-lg bg-surface-50 dark:bg-surface-800/60 p-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <label className="text-xs font-semibold text-surface-700 dark:text-surface-200">
                    Detection method
                    <select
                      className={`${inputCls} mt-1 block w-full`}
                      value={kind}
                      onChange={(event) => setKind(event.target.value as typeof kind)}
                    >
                      <option value="keyword_blocklist">Blocked words or phrases</option>
                      <option value="regex">Regular expression (advanced)</option>
                      <option value="pii_detection">Personal data (built in)</option>
                      <option value="token_limit">Maximum token count</option>
                    </select>
                  </label>
                  <label className="text-xs font-semibold text-surface-700 dark:text-surface-200">
                    Initial version status
                    <select
                      className={`${inputCls} mt-1 block w-full`}
                      value={status}
                      onChange={(event) => setStatus(event.target.value as GuardrailVersionStatus)}
                    >
                      <option value="draft">Draft — save without applying</option>
                      <option value="active">Active — available to assignments</option>
                    </select>
                  </label>
                </div>

                {kind === "keyword_blocklist" && (
                  <label className="block text-xs font-semibold text-surface-700 dark:text-surface-200">
                    Words or phrases to detect
                    <textarea
                      className={`${inputCls} mt-1 min-h-20 w-full font-mono`}
                      value={ruleInput}
                      onChange={(event) => setRuleInput(event.target.value)}
                      placeholder={"One per line or comma-separated\ne.g. confidential, internal only"}
                    />
                  </label>
                )}

                {kind === "regex" && (
                  <div className="rounded-lg border border-accent-200 dark:border-accent-700 bg-white dark:bg-surface-900 p-3">
                    <div className="flex items-start gap-2">
                      <Info size={15} className="mt-0.5 shrink-0 text-accent-600" />
                      <div>
                        <p className="text-xs font-semibold text-surface-800 dark:text-surface-100">
                          Regular expression assistant
                        </p>
                        <p className="text-[11px] text-surface-500 dark:text-surface-400">
                          Start with a template or enter one expression per line. Nexus validates every expression before saving.
                        </p>
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {REGEX_TEMPLATES.map((template) => (
                        <button
                          key={template.label}
                          type="button"
                          className="btn btn-secondary !py-1"
                          onClick={() => setRuleInput(template.pattern)}
                        >
                          Use {template.label}
                        </button>
                      ))}
                    </div>
                    <label className="mt-3 block text-xs font-semibold text-surface-700 dark:text-surface-200">
                      Expression
                      <textarea
                        className={`${inputCls} mt-1 min-h-20 w-full font-mono`}
                        value={ruleInput}
                        onChange={(event) => setRuleInput(event.target.value)}
                        placeholder={String.raw`Example: \bsecret-\d+\b`}
                        aria-describedby="regex-feedback"
                      />
                    </label>
                    <label className="mt-2 flex items-center gap-2 text-xs text-surface-600 dark:text-surface-300">
                      <input type="checkbox" checked={ignoreCase} onChange={(event) => setIgnoreCase(event.target.checked)} />
                      Ignore uppercase/lowercase differences
                    </label>
                    <label className="mt-3 block text-xs font-semibold text-surface-700 dark:text-surface-200">
                      Try it with sample text <span className="font-normal text-surface-400">(not saved)</span>
                      <input
                        className={`${inputCls} mt-1 block w-full`}
                        value={sample}
                        onChange={(event) => setSample(event.target.value)}
                        placeholder="Paste an example to see whether it matches"
                      />
                    </label>
                    <div id="regex-feedback" className={`mt-2 flex items-center gap-1.5 text-[11px] ${
                      regexCheck?.valid === false
                        ? "text-red-600 dark:text-red-300"
                        : "text-emerald-600 dark:text-emerald-300"
                    }`}>
                      {regexCheck?.valid === false ? <AlertTriangle size={13} /> : <CheckCircle2 size={13} />}
                      {regexCheck?.valid === false
                        ? `Invalid expression: ${regexCheck.message}`
                        : regexCheck?.valid
                          ? sample
                            ? regexCheck.matches ? "Valid expression — sample matches." : "Valid expression — sample does not match."
                            : "Valid expression. Add sample text to test it."
                          : "Enter an expression or choose a template."}
                    </div>
                  </div>
                )}

                {kind === "pii_detection" && (
                  <div className="rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900 p-3 text-xs text-surface-600 dark:text-surface-300">
                    The built-in detector checks for common personal data, such as email addresses and identifiers. No expression is required.
                  </div>
                )}

                {kind === "token_limit" && (
                  <label className="block text-xs font-semibold text-surface-700 dark:text-surface-200">
                    Maximum number of tokens
                    <input
                      type="number"
                      min="0"
                      step="1"
                      className={`${inputCls} mt-1 block w-full`}
                      value={maxTokens}
                      onChange={(event) => setMaxTokens(event.target.value)}
                    />
                  </label>
                )}

                <fieldset>
                  <legend className="text-xs font-semibold text-surface-700 dark:text-surface-200">
                    Where should Nexus inspect content?
                  </legend>
                  <p className="mt-1 text-[11px] text-surface-500 dark:text-surface-400">
                    Select one or more communication surfaces.
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {SURFACES.map((surface) => (
                      <label key={surface} className={`rounded-lg border px-3 py-2 text-xs ${
                        surfaces.includes(surface)
                          ? "border-accent-400 bg-accent-50 dark:bg-accent-900/20"
                          : "border-surface-200 dark:border-surface-700"
                      }`}>
                        <input
                          className="mr-2"
                          type="checkbox"
                          checked={surfaces.includes(surface)}
                          onChange={() => toggleSurface(surface)}
                        />
                        {SURFACE_LABELS[surface]}
                      </label>
                    ))}
                  </div>
                </fieldset>

                <fieldset>
                  <legend className="text-xs font-semibold text-surface-700 dark:text-surface-200">
                    What content should Nexus inspect?
                  </legend>
                  <p className="mt-1 text-[11px] text-surface-500 dark:text-surface-400">
                    These labels replace internal field names such as <code>body</code>. The API key remains visible for advanced users.
                  </p>
                  <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {FIELD_OPTIONS.filter((option) => surfaces.includes(option.surface)).map((option) => (
                      <label key={`${option.surface}-${option.value}`} className={`rounded-lg border px-3 py-2 ${
                        fields.includes(option.value)
                          ? "border-accent-300 bg-white dark:bg-surface-900"
                          : "border-surface-200 dark:border-surface-700"
                      }`}>
                        <span className="flex items-start gap-2">
                          <input
                            className="mt-0.5"
                            type="checkbox"
                            checked={fields.includes(option.value)}
                            onChange={() => toggleField(option.value)}
                          />
                          <span>
                            <span className="block text-xs font-medium text-surface-700 dark:text-surface-200">{option.label}</span>
                            <span className="block text-[11px] text-surface-500">{option.description} <code>{option.value}</code></span>
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                </fieldset>

                <div className="flex flex-wrap items-center gap-2 border-t border-surface-200 dark:border-surface-700 pt-3">
                  <p className="text-[11px] text-surface-500">
                    New versions are immutable. Start as Draft when you want to review before assigning.
                  </p>
                  <button className="btn btn-primary ml-auto" onClick={addVersion} disabled={!canSave}>
                    <Save size={14} /> Save rule version
                  </button>
                </div>
              </div>

              <div className="mt-4 overflow-auto max-h-60">
                <table className="min-w-full text-xs">
                  <thead>
                    <tr className="text-left text-[11px] uppercase text-surface-400">
                      <th className="py-1 pr-3">Version</th>
                      <th className="py-1 pr-3">Rule</th>
                      <th className="py-1 pr-3">Inspects</th>
                      <th className="py-1">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(selected.versions ?? []).map((version) => (
                      <tr key={version.version} className="border-t border-surface-100 dark:border-surface-800 align-top">
                        <td className="py-2 pr-3 font-mono">v{version.version}</td>
                        <td className="py-2 pr-3">{ruleSummary(version)}</td>
                        <td className="py-2 pr-3">
                          {version.field_targets.map((field) => FIELD_OPTIONS.find((option) => option.value === field)?.label ?? field).join(", ")}
                        </td>
                        <td className="py-2">
                          <select
                            className={inputCls}
                            aria-label={`Status for version ${version.version}`}
                            value={version.status}
                            onChange={(event) => changeVersionStatus(version.version, event.target.value as GuardrailVersionStatus)}
                          >
                            {STATUSES.map((item) => <option key={item} value={item}>{item}</option>)}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="flex min-h-[300px] items-center justify-center text-center">
              <p className="max-w-xs text-xs text-surface-500 dark:text-surface-400">
                Select a guardrail to configure its detection rule, content surfaces and fields.
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function LegacyAssignmentsPanel({
  assignments,
  groups,
  guardrails,
  onRefresh,
  onError,
}: {
  assignments: GuardrailAssignment[];
  groups: AgentGroupRecord[];
  guardrails: GuardrailRecord[];
  onRefresh: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [scope, setScope] = useState<"global" | "agent_group">("global");
  const [groupId, setGroupId] = useState("");
  const [guardrailId, setGuardrailId] = useState("");
  const [versionMode, setVersionMode] =
    useState<GuardrailVersionMode>("latest");
  const [pinned, setPinned] = useState("1");
  const [mode, setMode] = useState<GuardrailMode>("enforce");

  useEffect(() => {
    if (!groupId && groups[0]) setGroupId(groups[0].group_id);
    if (!guardrailId && guardrails[0]) setGuardrailId(guardrails[0].guardrail_id);
  }, [groupId, groups, guardrailId, guardrails]);

  const create = async () => {
    if (!guardrailId) return;
    try {
      await api.createGuardrailAssignment({
        scope_kind: scope,
        group_id: scope === "agent_group" ? groupId : null,
        guardrail_id: guardrailId,
        version_mode: versionMode,
        pinned_version: versionMode === "pinned" ? Number(pinned) : null,
        mode,
        priority: 100,
        enabled: true,
      });
      await onRefresh();
    } catch (exc) {
      onError((exc as Error).message);
    }
  };

  return (
    <section className={`${sectionCls} p-4`}>
      <div className="flex items-center gap-2 mb-3">
        <Link2 size={16} className="text-emerald-600 dark:text-emerald-400" />
        <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100">
          Assignments
        </h2>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-2">
        <select
          className={inputCls}
          value={scope}
          onChange={(e) => setScope(e.target.value as "global" | "agent_group")}
        >
          <option value="global">global</option>
          <option value="agent_group">agent_group</option>
        </select>
        <select
          className={inputCls}
          value={groupId}
          onChange={(e) => setGroupId(e.target.value)}
          disabled={scope === "global"}
        >
          {groups.map((group) => (
            <option key={group.group_id} value={group.group_id}>
              {group.name}
            </option>
          ))}
        </select>
        <select
          className={inputCls}
          value={guardrailId}
          onChange={(e) => setGuardrailId(e.target.value)}
        >
          {guardrails.map((guardrail) => (
            <option key={guardrail.guardrail_id} value={guardrail.guardrail_id}>
              {guardrail.name}
            </option>
          ))}
        </select>
        <select
          className={inputCls}
          value={versionMode}
          onChange={(e) => setVersionMode(e.target.value as GuardrailVersionMode)}
        >
          {VERSION_MODES.map((item) => (
            <option key={item}>{item}</option>
          ))}
        </select>
        <input
          className={inputCls}
          value={pinned}
          onChange={(e) => setPinned(e.target.value)}
          disabled={versionMode === "latest"}
        />
        <div className="flex gap-2">
          <select
            className={`${inputCls} min-w-0 flex-1`}
            value={mode}
            onChange={(e) => setMode(e.target.value as GuardrailMode)}
          >
            {MODES.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
          <button
            className="btn btn-primary shrink-0"
            onClick={create}
            disabled={!guardrailId || (scope === "agent_group" && !groupId)}
          >
            <Plus size={14} />
          </button>
        </div>
      </div>
      <div className="mt-4 overflow-auto">
        <table className="min-w-full text-xs">
          <thead>
            <tr className="text-left text-[11px] uppercase text-surface-400">
              <th className="py-1 pr-3">Scope</th>
              <th className="py-1 pr-3">Guardrail</th>
              <th className="py-1 pr-3">Version</th>
              <th className="py-1 pr-3">Mode</th>
              <th className="py-1 pr-3">State</th>
              <th className="py-1" />
            </tr>
          </thead>
          <tbody>
            {assignments.map((assignment) => (
              <tr
                key={assignment.assignment_id}
                className="border-t border-surface-100 dark:border-surface-800"
              >
                <td className="py-1 pr-3">
                  {assignment.scope_kind}
                  {assignment.group_id ? `:${assignment.group_id}` : ""}
                </td>
                <td className="py-1 pr-3 font-mono">{assignment.guardrail_id}</td>
                <td className="py-1 pr-3">
                  {assignment.version_mode}
                  {assignment.pinned_version ? `@${assignment.pinned_version}` : ""}
                </td>
                <td className="py-1 pr-3">{assignment.mode}</td>
                <td className="py-1 pr-3">
                  {assignment.enabled ? "enabled" : "disabled"}
                </td>
                <td className="py-1 text-right">
                  <button
                    className="text-surface-400 hover:text-red-500"
                    title="Delete assignment"
                    onClick={async () => {
                      await api.deleteGuardrailAssignment(
                        assignment.assignment_id,
                      );
                      await onRefresh();
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const MODE_LABELS: Record<GuardrailMode, string> = {
  audit: "Audit only",
  warn: "Warn without blocking",
  enforce: "Enforce and block",
};

function AssignmentsPanel({
  assignments,
  groups,
  capabilities,
  guardrails,
  onRefresh,
  onError,
}: {
  assignments: GuardrailAssignment[];
  groups: AgentGroupRecord[];
  capabilities: CapabilityRow[];
  guardrails: GuardrailRecord[];
  onRefresh: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const { confirm, dialog } = useConfirm();
  const [scope, setScope] = useState<GuardrailScopeKind>("global");
  const [groupId, setGroupId] = useState("");
  const [capability, setCapability] = useState("");
  const [guardrailId, setGuardrailId] = useState("");
  const [versionMode, setVersionMode] = useState<GuardrailVersionMode>("latest");
  const [pinned, setPinned] = useState("");
  const [mode, setMode] = useState<GuardrailMode>("audit");

  const selectedGuardrail = guardrails.find(
    (guardrail) => guardrail.guardrail_id === guardrailId,
  );
  const activeVersions = (selectedGuardrail?.versions ?? []).filter(
    (version) => version.status === "active",
  );

  useEffect(() => {
    if (!groupId && groups[0]) setGroupId(groups[0].group_id);
    if (!capability && capabilities[0]) setCapability(capabilities[0].name);
    if (!guardrailId && guardrails[0]) setGuardrailId(guardrails[0].guardrail_id);
  }, [capabilities, capability, groupId, groups, guardrailId, guardrails]);

  useEffect(() => {
    if (!activeVersions.some((version) => String(version.version) === pinned)) {
      setPinned(activeVersions.at(-1)?.version.toString() ?? "");
    }
  }, [activeVersions, pinned]);

  const targetReady =
    scope === "global" ||
    (scope === "agent_group" && Boolean(groupId)) ||
    (scope === "capability" && Boolean(capability));
  const canCreate =
    Boolean(guardrailId) &&
    Boolean(selectedGuardrail?.latest_active_version) &&
    targetReady &&
    (versionMode === "latest" || Boolean(pinned));

  const createNow = async () => {
    try {
      await api.createGuardrailAssignment({
        scope_kind: scope,
        group_id: scope === "agent_group" ? groupId : null,
        capability: scope === "capability" ? capability : null,
        guardrail_id: guardrailId,
        version_mode: versionMode,
        pinned_version: versionMode === "pinned" ? Number(pinned) : null,
        mode,
        priority: 100,
        enabled: true,
      });
      await onRefresh();
    } catch (exc) {
      onError(errorText(exc));
    }
  };

  const create = () => {
    if (!canCreate) return;
    if (mode === "enforce") {
      confirm({
        title: "Enable blocking for this assignment?",
        body: "Matching writes from the selected agents will be rejected. Consider starting in Audit only mode.",
        onConfirm: createNow,
      });
      return;
    }
    void createNow();
  };

  const updateAssignment = async (
    assignment: GuardrailAssignment,
    patch: { mode?: GuardrailMode; enabled?: boolean },
  ) => {
    const run = async () => {
      try {
        await api.updateGuardrailAssignment(assignment.assignment_id, patch);
        await onRefresh();
      } catch (exc) {
        onError(errorText(exc));
      }
    };
    if (patch.mode === "enforce" && assignment.mode !== "enforce") {
      confirm({
        title: "Switch this assignment to Enforce?",
        body: "Matching writes from the targeted agents will be blocked.",
        onConfirm: run,
      });
    } else {
      await run();
    }
  };

  const targetLabel = (assignment: GuardrailAssignment) => {
    if (assignment.scope_kind === "global") return "All registered agents";
    if (assignment.scope_kind === "capability") {
      return `Agents with capability: ${assignment.capability}`;
    }
    const group = groups.find((item) => item.group_id === assignment.group_id);
    return `Group: ${group?.name ?? assignment.group_id}`;
  };

  return (
    <section className={`${sectionCls} p-4`}>
      {dialog}
      <div className="flex items-center gap-2">
        <Link2 size={16} className="text-emerald-600 dark:text-emerald-400" />
        <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100">
          3. Apply a guardrail to agents
        </h2>
      </div>
      <p className="mt-1 text-xs text-surface-500 dark:text-surface-400">
        Choose who receives an active rule: everyone, the members of an explicit group, or any agent that announces a capability.
      </p>

      <div className="mt-4 rounded-lg bg-surface-50 dark:bg-surface-800/60 p-4">
        <fieldset>
          <legend className="text-xs font-semibold text-surface-700 dark:text-surface-200">
            Who should this guardrail apply to?
          </legend>
          <div className="mt-2 grid grid-cols-1 sm:grid-cols-3 gap-2">
            {([
              ["global", "All agents", "Every registered agent"],
              ["agent_group", "An agent group", "Only members you selected above"],
              ["capability", "A capability", "Agents that announce this capability"],
            ] as const).map(([value, label, description]) => (
              <label key={value} className={`rounded-lg border p-3 text-xs ${
                scope === value
                  ? "border-accent-400 bg-white dark:bg-surface-900"
                  : "border-surface-200 dark:border-surface-700"
              }`}>
                <span className="flex items-start gap-2">
                  <input type="radio" name="assignment-scope" value={value} checked={scope === value} onChange={() => setScope(value)} />
                  <span>
                    <span className="block font-semibold text-surface-700 dark:text-surface-200">{label}</span>
                    <span className="block mt-0.5 text-[11px] text-surface-500">{description}</span>
                  </span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
          {scope === "agent_group" && (
            <label className="text-xs font-semibold text-surface-700 dark:text-surface-200">
              Agent group
              <select className={`${inputCls} mt-1 block w-full`} value={groupId} onChange={(event) => setGroupId(event.target.value)}>
                {groups.map((group) => <option key={group.group_id} value={group.group_id}>{group.name} ({(group.members ?? []).length})</option>)}
              </select>
              {groups.length === 0 && <span className="mt-1 block text-[11px] text-amber-600">Create a group and add agents first.</span>}
            </label>
          )}
          {scope === "capability" && (
            <label className="text-xs font-semibold text-surface-700 dark:text-surface-200">
              Agent capability
              <select className={`${inputCls} mt-1 block w-full`} value={capability} onChange={(event) => setCapability(event.target.value)}>
                {capabilities.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
              </select>
              {capabilities.length === 0 && <span className="mt-1 block text-[11px] text-amber-600">Register a capability in Registry first.</span>}
            </label>
          )}
          <label className="text-xs font-semibold text-surface-700 dark:text-surface-200">
            Guardrail rule
            <select className={`${inputCls} mt-1 block w-full`} value={guardrailId} onChange={(event) => setGuardrailId(event.target.value)}>
              {guardrails.map((guardrail) => (
                <option key={guardrail.guardrail_id} value={guardrail.guardrail_id}>
                  {guardrail.name}{guardrail.latest_active_version ? ` (active v${guardrail.latest_active_version})` : " (no active version)"}
                </option>
              ))}
            </select>
            {selectedGuardrail && !selectedGuardrail.latest_active_version && (
              <span className="mt-1 block text-[11px] text-amber-600">Activate a valid version before assigning this guardrail.</span>
            )}
          </label>
          <label className="text-xs font-semibold text-surface-700 dark:text-surface-200">
            Version selection
            <select className={`${inputCls} mt-1 block w-full`} value={versionMode} onChange={(event) => setVersionMode(event.target.value as GuardrailVersionMode)}>
              <option value="latest">Always use latest active version</option>
              <option value="pinned">Keep one active version</option>
            </select>
          </label>
          {versionMode === "pinned" && (
            <label className="text-xs font-semibold text-surface-700 dark:text-surface-200">
              Active version
              <select className={`${inputCls} mt-1 block w-full`} value={pinned} onChange={(event) => setPinned(event.target.value)}>
                {activeVersions.map((version) => <option key={version.version} value={version.version}>Version {version.version}</option>)}
              </select>
            </label>
          )}
          <label className="text-xs font-semibold text-surface-700 dark:text-surface-200">
            Behavior when content matches
            <select className={`${inputCls} mt-1 block w-full`} value={mode} onChange={(event) => setMode(event.target.value as GuardrailMode)}>
              {MODES.map((item) => <option key={item} value={item}>{MODE_LABELS[item]}</option>)}
            </select>
          </label>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900 p-3">
          <div className="min-w-0 text-xs text-surface-600 dark:text-surface-300">
            <span className="font-semibold">Review:</span>{" "}
            {scope === "global"
              ? "All registered agents"
              : scope === "agent_group"
                ? `Members of ${groups.find((group) => group.group_id === groupId)?.name ?? "the selected group"}`
                : `Agents with ${capability || "the selected capability"}`}{" "}
            will use {selectedGuardrail?.name ?? "the selected guardrail"} in {MODE_LABELS[mode].toLowerCase()} mode.
          </div>
          <button className="btn btn-primary ml-auto" onClick={create} disabled={!canCreate}>
            <Plus size={14} /> Create assignment
          </button>
        </div>
      </div>

      <div className="mt-4 overflow-auto">
        <table className="min-w-full text-xs">
          <thead>
            <tr className="text-left text-[11px] uppercase text-surface-400">
              <th className="py-1 pr-3">Applies to</th>
              <th className="py-1 pr-3">Guardrail</th>
              <th className="py-1 pr-3">Version</th>
              <th className="py-1 pr-3">Behavior</th>
              <th className="py-1 pr-3">Enabled</th>
              <th className="py-1"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {assignments.map((assignment) => {
              const guardrail = guardrails.find((item) => item.guardrail_id === assignment.guardrail_id);
              return (
                <tr key={assignment.assignment_id} className="border-t border-surface-100 dark:border-surface-800">
                  <td className="py-2 pr-3 font-medium">{targetLabel(assignment)}</td>
                  <td className="py-2 pr-3">{guardrail?.name ?? assignment.guardrail_id}</td>
                  <td className="py-2 pr-3">{assignment.version_mode === "latest" ? "Latest active" : `Version ${assignment.pinned_version}`}</td>
                  <td className="py-2 pr-3">
                    <select
                      className={inputCls}
                      aria-label={`Behavior for ${guardrail?.name ?? assignment.guardrail_id}`}
                      value={assignment.mode}
                      onChange={(event) => void updateAssignment(assignment, { mode: event.target.value as GuardrailMode })}
                    >
                      {MODES.map((item) => <option key={item} value={item}>{MODE_LABELS[item]}</option>)}
                    </select>
                  </td>
                  <td className="py-2 pr-3">
                    <label className="inline-flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={assignment.enabled}
                        onChange={(event) => void updateAssignment(assignment, { enabled: event.target.checked })}
                      />
                      {assignment.enabled ? "On" : "Off"}
                    </label>
                  </td>
                  <td className="py-2 text-right">
                    <button
                      className="btn btn-secondary !px-2 !py-1"
                      onClick={() => confirm({
                        title: "Delete this assignment?",
                        body: "The guardrail rule itself will remain available.",
                        onConfirm: async () => {
                          await api.deleteGuardrailAssignment(assignment.assignment_id);
                          await onRefresh();
                        },
                      })}
                    >
                      <Trash2 size={13} /> Delete
                    </button>
                  </td>
                </tr>
              );
            })}
            {assignments.length === 0 && (
              <tr><td colSpan={6} className="py-5 text-center text-surface-500">No guardrails are assigned to agents yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function DenialsPanel({
  workspace,
  denials,
  behavior,
  onRefresh,
}: {
  workspace: string;
  denials: GuardrailDenial[];
  behavior: string;
  onRefresh: () => Promise<void>;
}) {
  const workspaceName = useWorkspaceName(workspace);
  return (
    <section className={`${sectionCls} p-4`}>
      <div className="flex items-center gap-2 mb-3">
        <Activity size={16} className="text-amber-600 dark:text-amber-400" />
        <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100">
          Denials
        </h2>
        <button className="ml-auto btn btn-secondary !py-1" onClick={onRefresh}>
          <RotateCw size={13} /> Refresh
        </button>
      </div>
      <p className="mb-3 text-xs text-surface-500 dark:text-surface-400 truncate">
          {workspaceName} - {behavior}
      </p>
      <div className="overflow-auto">
        <table className="min-w-full text-xs">
          <thead>
            <tr className="text-left text-[11px] uppercase text-surface-400">
              <th className="py-1 pr-3">Event</th>
              <th className="py-1 pr-3">Actor</th>
              <th className="py-1 pr-3">Created</th>
              <th className="py-1">Payload</th>
            </tr>
          </thead>
          <tbody>
            {denials.map((denial) => (
              <tr
                key={denial.event_id}
                className="border-t border-surface-100 dark:border-surface-800 align-top"
              >
                <td className="py-2 pr-3 font-mono">{denial.event_id}</td>
                <td className="py-2 pr-3 font-mono">
                  {denial.actor_agent_id ?? "-"}
                </td>
                <td className="py-2 pr-3">{denial.created_at}</td>
                <td className="py-2 min-w-[320px]">
                  <JsonCell value={denial.payload} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function GuardrailsView({ workspace }: { workspace: string }) {
  const [groups, setGroups] = useState<AgentGroupRecord[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [capabilities, setCapabilities] = useState<CapabilityRow[]>([]);
  const [guardrails, setGuardrails] = useState<GuardrailRecord[]>([]);
  const [assignments, setAssignments] = useState<GuardrailAssignment[]>([]);
  const [denials, setDenials] = useState<GuardrailDenial[]>([]);
  const [behavior, setBehavior] = useState("");
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);
  const [selectedGuardrail, setSelectedGuardrail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedGuardrailRecord = useMemo(
    () =>
      guardrails.find((guardrail) => guardrail.guardrail_id === selectedGuardrail) ??
      null,
    [guardrails, selectedGuardrail],
  );

  const loadCatalog = useCallback(async () => {
    const [groupPage, guardrailPage, assignmentPage, agentPage, capabilityPage] = await Promise.all([
      api.guardrailGroups(),
      api.guardrails(),
      api.guardrailAssignments(),
      api.agents(),
      api.capabilities(),
    ]);
    setGroups(groupPage.items);
    setAgents(agentPage.items);
    setCapabilities(capabilityPage.items);
    const detailed = await Promise.all(
      guardrailPage.items.map((guardrail) =>
        api.guardrail(guardrail.guardrail_id),
      ),
    );
    setGuardrails(detailed);
    setAssignments(assignmentPage.items);
    setError(null);
  }, []);

  const loadDenials = useCallback(async () => {
    const page = await api.guardrailDenials({
      workspace,
      limit: "50",
    });
    setDenials(page.items);
    setBehavior(page.s6_behavior);
  }, [workspace]);

  const loadAll = useCallback(async () => {
    try {
      await Promise.all([loadCatalog(), loadDenials()]);
    } catch (exc) {
      setError((exc as Error).message);
    }
  }, [loadCatalog, loadDenials]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  return (
    <PageContainer width="wide" scroll="y" testId="guardrails-view">
      <div className="flex items-center gap-3 mb-4">
        <div>
          <h1 className="text-xl font-semibold text-surface-900 dark:text-surface-100">
            Guardrails
          </h1>
          <p className="mt-1 text-xs text-surface-500 dark:text-surface-400">
            Define a content rule, then apply it to all agents, an explicit group, or agents with a capability.
          </p>
        </div>
        <div className="ml-auto">
          <CatalogImportButton
            catalog="guardrails"
            onImport={async (value) => {
              const names = new Set(
                guardrails.map((guardrail) => guardrail.name.toLocaleLowerCase()),
              );
              if (!value || typeof value !== "object" || Array.isArray(value)) {
                throw new Error("The guardrail export is invalid.");
              }
              const row = value as Record<string, unknown>;
              if (typeof row.name !== "string") {
                throw new Error("The guardrail must include a name.");
              }
              const rawVersions = Array.isArray(row.versions) ? row.versions : [];
              const versions = rawVersions.map((versionValue) => {
                if (
                  !versionValue ||
                  typeof versionValue !== "object" ||
                  Array.isArray(versionValue)
                ) {
                  throw new Error("The guardrail contains an invalid version.");
                }
                const version = versionValue as Record<string, unknown>;
                const versionStatus = version.status;
                const evaluatorKind = version.evaluator_kind;
                const evaluatorConfig = version.evaluator_config;
                const versionSurfaces = version.surfaces;
                const fieldTargets = version.field_targets;
                if (
                  typeof versionStatus !== "string" ||
                  !STATUSES.includes(versionStatus as GuardrailVersionStatus) ||
                  (evaluatorKind !== "deterministic" && evaluatorKind !== "llm") ||
                  !evaluatorConfig ||
                  typeof evaluatorConfig !== "object" ||
                  Array.isArray(evaluatorConfig) ||
                  !Array.isArray(versionSurfaces) ||
                  !versionSurfaces.every(
                    (surface) =>
                      typeof surface === "string" &&
                      SURFACES.includes(surface as GuardrailSurface),
                  ) ||
                  !Array.isArray(fieldTargets) ||
                  !fieldTargets.every((field) => typeof field === "string")
                ) {
                  throw new Error("The guardrail contains an invalid version contract.");
                }
                return {
                  status: versionStatus as GuardrailVersionStatus,
                  evaluator_kind: evaluatorKind as GuardrailEvaluatorKind,
                  evaluator_config: evaluatorConfig as Record<string, unknown>,
                  surfaces: versionSurfaces as GuardrailSurface[],
                  field_targets: fieldTargets as string[],
                };
              });
              const created = await api.createGuardrail({
                name: uniqueImportedName(row.name, names),
                description:
                  typeof row.description === "string" ? row.description : undefined,
              });
              for (const version of versions) {
                await api.addGuardrailVersion(created.guardrail_id, version);
              }
              await loadCatalog();
              setSelectedGuardrail(created.guardrail_id);
            }}
          />
        </div>
        <button className="btn btn-secondary" onClick={loadAll}>
          <RotateCw size={14} /> Refresh
        </button>
      </div>
      {error && (
        <div className="mb-4 rounded-lg border border-red-300 dark:border-red-500/40 bg-red-50 dark:bg-red-900/10 px-3 py-2 text-xs text-red-700 dark:text-red-200">
          {error}
        </div>
      )}
      <div className="grid grid-cols-1 2xl:grid-cols-[minmax(360px,0.8fr)_minmax(520px,1.2fr)] gap-4">
        <GroupsPanel
          groups={groups}
          agents={agents}
          selected={selectedGroup}
          onSelect={setSelectedGroup}
          onRefresh={loadCatalog}
          onError={setError}
        />
        <GuardrailsPanel
          guardrails={guardrails}
          selected={selectedGuardrailRecord}
          onSelect={setSelectedGuardrail}
          onRefresh={loadCatalog}
          onError={setError}
        />
      </div>
      <div className="mt-4 space-y-4">
        <AssignmentsPanel
          assignments={assignments}
          groups={groups}
          capabilities={capabilities}
          guardrails={guardrails}
          onRefresh={loadCatalog}
          onError={setError}
        />
        <DenialsPanel
          workspace={workspace}
          denials={denials}
          behavior={behavior}
          onRefresh={loadDenials}
        />
      </div>
    </PageContainer>
  );
}
