import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
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
  type GuardrailAssignment,
  type GuardrailDenial,
  type GuardrailInUseDetails,
  type GuardrailMode,
  type GuardrailRecord,
  type GuardrailSurface,
  type GuardrailVersionStatus,
  type GuardrailVersionMode,
} from "../api";
import { PageContainer } from "../components/PageContainer";

const inputCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";
const sectionCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900";

const SURFACES: GuardrailSurface[] = ["message", "artifact", "handoff"];
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
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
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
  onCreate,
}: {
  label: string;
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
    <div className="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] gap-2">
      <input
        className={inputCls}
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder={`${label} name`}
      />
      <input
        className={inputCls}
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Description"
      />
      <button
        className="btn btn-primary justify-center"
        onClick={submit}
        disabled={busy || !name.trim()}
      >
        <Plus size={14} /> Create
      </button>
    </div>
  );
}

function GroupsPanel({
  groups,
  selected,
  onSelect,
  onRefresh,
  onError,
}: {
  groups: AgentGroupRecord[];
  selected: string | null;
  onSelect: (id: string | null) => void;
  onRefresh: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [memberAgent, setMemberAgent] = useState("");

  const current = groups.find((group) => group.group_id === selected) ?? null;

  const create = async (body: { name: string; description?: string }) => {
    await api.createGuardrailGroup(body);
    await onRefresh();
  };

  const remove = async (group: AgentGroupRecord) => {
    try {
      await api.deleteGuardrailGroup(group.group_id);
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

  const addMember = async () => {
    if (!current || !memberAgent.trim()) return;
    try {
      await api.addGuardrailGroupMember(current.group_id, {
        agent_id: memberAgent.trim(),
      });
      setMemberAgent("");
      await onRefresh();
    } catch (exc) {
      onError((exc as Error).message);
    }
  };

  return (
    <section className={`${sectionCls} p-4 min-h-[340px]`}>
      <div className="flex items-center gap-2 mb-3">
        <Users size={16} className="text-accent-600 dark:text-accent-400" />
        <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100">
          Groups
        </h2>
      </div>
      <HeaderForm label="Group" onCreate={create} />
      <div className="mt-4 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(220px,0.65fr)] gap-3">
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
                {group.group_id}
              </span>
            </button>
          ))}
        </div>
        <div className="rounded-lg border border-surface-200 dark:border-surface-700 p-3">
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
                </button>
              </div>
              <div className="mt-3 flex gap-2">
                <input
                  className={`${inputCls} min-w-0 flex-1`}
                  value={memberAgent}
                  onChange={(e) => setMemberAgent(e.target.value)}
                  placeholder="agent_id"
                />
                <button className="btn btn-primary !py-1" onClick={addMember}>
                  <Plus size={13} />
                </button>
              </div>
              <div className="mt-3 space-y-1 max-h-36 overflow-auto">
                {(current.members ?? []).map((member) => (
                  <div
                    key={member.agent_id}
                    className="flex items-center gap-2 rounded-md bg-surface-50 dark:bg-surface-800 px-2 py-1 text-xs"
                  >
                    <span className="font-mono truncate">{member.agent_id}</span>
                    <button
                      className="ml-auto text-surface-400 hover:text-red-500"
                      title="Remove member"
                      onClick={async () => {
                        await api.removeGuardrailGroupMember(
                          current.group_id,
                          member.agent_id,
                        );
                        await onRefresh();
                      }}
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-xs text-surface-500 dark:text-surface-400">
              Select a group
            </p>
          )}
        </div>
      </div>
    </section>
  );
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
      <HeaderForm label="Guardrail" onCreate={create} />
      <div className="mt-4 grid grid-cols-1 xl:grid-cols-[minmax(0,0.9fr)_minmax(340px,1fr)] gap-3">
        <div className="space-y-2">
          {guardrails.map((guardrail) => (
            <button
              key={guardrail.guardrail_id}
              className={`w-full text-left rounded-lg border px-3 py-2 text-xs transition-colors ${
                selected?.guardrail_id === guardrail.guardrail_id
                  ? "border-accent-400 bg-accent-50 dark:bg-accent-900/20"
                  : "border-surface-200 dark:border-surface-700 hover:bg-surface-50 dark:hover:bg-surface-800"
              }`}
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
          ))}
        </div>
        <div className="rounded-lg border border-surface-200 dark:border-surface-700 p-3 min-w-0">
          {selected ? (
            <>
              <div className="flex items-center gap-2">
                <p className="text-xs font-semibold text-surface-800 dark:text-surface-100 truncate">
                  {selected.name}
                </p>
                <button
                  className="ml-auto btn btn-secondary !py-1"
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

function AssignmentsPanel({
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
        {workspace} - {behavior}
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
    const [groupPage, guardrailPage, assignmentPage] = await Promise.all([
      api.guardrailGroups(),
      api.guardrails(),
      api.guardrailAssignments(),
    ]);
    setGroups(groupPage.items);
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
        <h1 className="text-xl font-semibold text-surface-900 dark:text-surface-100">
          Guardrails
        </h1>
        <button className="ml-auto btn btn-secondary" onClick={loadAll}>
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
