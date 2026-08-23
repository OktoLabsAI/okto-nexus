// Policies (spec 80624c1a, FR12/TR7): the operator CATALOG of NAMED, versioned
// global policies (migration 022) — one append-only object unifying audience
// (comm_scope) + governance rules. This screen SUPERSEDES the flat governance
// CRUD (spec ffef15bf): the legacy governance_policies were migrated here as
// detached governance-only globals. It is a full-bleed master-detail (a la
// EventsView): the catalog list on the left, the selected policy's header +
// version history + a "publish new version" composer in the right inspector.
// Enforcement is always-on / binding-driven (the feature_governance flag is
// GONE), so there is no "enforcement disabled" banner — a policy simply stages
// until an agent binds it. Denials stay observable via the events log
// (governance.denied), self-gated by the DATA (rendered only when denials
// exist; never consults a flag — the D7 pattern).

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Plus, RefreshCw, ShieldAlert, X } from "lucide-react";
import {
  api,
  ApiError,
  type CommScope,
  type NexusEvent,
  type PolicyInUseDetails,
  type PolicyRecord,
  type PolicyRule,
  type PolicyVersion,
  type TagKeyRow,
  type TagSelector,
} from "../api";
import { PageContainer } from "../components/PageContainer";
import { ResizablePanel } from "../components/ResizablePanel";
import { CommScopeEditor } from "../components/AudienceEditor";
import {
  GovernanceRulesEditor,
  ruleLabel,
} from "../components/GovernanceRulesEditor";
import { useConfirm } from "../components/Confirm";
import {
  CatalogExportButton,
  CatalogImportButton,
  catalogEntityFilename,
  uniqueImportedName,
} from "../components/CatalogTransfer";

const inputCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";

// ------------------------------------------------------------------ //
// Version summaries (compact, for the history table)
// ------------------------------------------------------------------ //
function countConditions(selector: TagSelector | null | undefined): number {
  if (!selector) return 0;
  return Array.isArray(selector)
    ? selector.length
    : Object.keys(selector).length;
}

function audienceSummary(audience: CommScope | null): string {
  if (!audience) return "—";
  const out = countConditions(audience.outbound);
  const inn = countConditions(audience.inbound);
  if (out === 0 && inn === 0) return "public";
  return `outbound: ${out} cond · inbound: ${inn} cond`;
}

// ------------------------------------------------------------------ //
// Denials panel (FR12: denials stay read via the events log)
// ------------------------------------------------------------------ //
const MAX_DENIALS = 20;
const DENIAL_PAGE = 200;
const DENIAL_PAGE_CAP = 5;

async function fetchDenials(workspace: string): Promise<NexusEvent[]> {
  const all: NexusEvent[] = [];
  let after = 0;
  for (let page = 0; page < DENIAL_PAGE_CAP; page += 1) {
    const params: Record<string, string> = {
      type: "governance.denied",
      after: String(after),
      limit: String(DENIAL_PAGE),
    };
    if (workspace !== "all") params.workspace = workspace;
    const data = await api.events(params);
    all.push(...data.items);
    if (data.items.length < DENIAL_PAGE) break;
    after = data.next_cursor;
  }
  return all.slice(-MAX_DENIALS).reverse();
}

type DenialPayload = {
  policy_id?: string;
  action?: string;
  agent_id?: string | null;
  error_code?: string;
  limit_kind?: string;
};

function DenialsPanel({ workspace }: { workspace: string }) {
  const [denials, setDenials] = useState<NexusEvent[]>([]);

  const reload = useCallback(() => {
    fetchDenials(workspace)
      .then(setDenials)
      .catch(() => undefined);
  }, [workspace]);

  useEffect(() => {
    reload();
  }, [reload]);

  // Self-gated by the data: no denials, no panel (never consults the flag).
  if (denials.length === 0) return null;

  return (
    <section className="mt-6 panel p-4" data-testid="denials-panel">
      <div className="flex items-center gap-2 mb-3">
        <ShieldAlert size={15} className="text-red-500 dark:text-red-400" />
        <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100">
          Recent denials
        </h2>
        <span className="chip bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300">
          {denials.length}
        </span>
        <button
          className="btn btn-secondary !px-2 !py-1 ml-auto"
          onClick={reload}
          title="Refresh denials"
          data-testid="refresh-denials"
        >
          <RefreshCw size={12} />
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
              <th className="py-1.5 pr-3 font-medium">When</th>
              <th className="py-1.5 pr-3 font-medium">Agent</th>
              <th className="py-1.5 pr-3 font-medium">Action</th>
              <th className="py-1.5 pr-3 font-medium">Policy</th>
            </tr>
          </thead>
          <tbody>
            {denials.map((event) => {
              const payload = (event.payload ?? {}) as DenialPayload;
              return (
                <tr
                  key={event.event_id}
                  className="border-t border-surface-100 dark:border-surface-800"
                >
                  <td className="py-1.5 pr-3 whitespace-nowrap text-surface-500 dark:text-surface-400">
                    {new Date(event.created_at).toLocaleString()}
                  </td>
                  <td className="py-1.5 pr-3 font-mono">
                    {payload.agent_id ?? event.actor_agent_id ?? "—"}
                  </td>
                  <td className="py-1.5 pr-3">
                    <span className="font-mono">{payload.action ?? "?"}</span>
                    <span className="text-surface-400 dark:text-surface-500">
                      {" "}
                      · {payload.error_code ?? ""}
                    </span>
                  </td>
                  <td className="py-1.5 pr-3 font-mono text-surface-500 dark:text-surface-400">
                    {payload.policy_id ?? "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ //
// The 409 POLICY_IN_USE panel (molded on RegistryView's CapabilityInUsePanel):
// the server's normative binder list (agents that still bind this policy).
// ------------------------------------------------------------------ //
function PolicyInUsePanel({
  details,
  onDismiss,
}: {
  details: PolicyInUseDetails;
  onDismiss: () => void;
}) {
  return (
    <div
      className="mt-3 rounded-lg border border-red-300 dark:border-red-500/30 bg-red-50 dark:bg-red-900/10 p-3.5"
      data-testid="policy-in-use-panel"
    >
      <div className="flex items-center gap-2 mb-2">
        <AlertTriangle size={14} className="text-red-500 dark:text-red-400 shrink-0" />
        <p className="text-xs font-semibold text-red-600 dark:text-red-300">
          Cannot delete — POLICY_IN_USE (409)
        </p>
      </div>
      <p className="text-xs text-red-600/90 dark:text-red-200/90 mb-2">
        Deleting this policy would orphan the bindings of these agents
        (fail-closed policy forbids cascading removal). Detach it from them
        first:
      </p>
      <ul className="text-xs text-surface-700 dark:text-surface-300 space-y-1 mb-3">
        {details.agents.map((agentId) => (
          <li key={agentId} className="flex items-center gap-2">
            <span className="w-1 h-1 rounded-full bg-red-400 shrink-0" />
            <span className="font-mono">{agentId}</span>
            <span className="text-surface-500 dark:text-surface-400">
              — still binds this policy
            </span>
          </li>
        ))}
      </ul>
      <button className="btn btn-secondary !py-1 text-xs" onClick={onDismiss}>
        Dismiss
      </button>
    </div>
  );
}

// ------------------------------------------------------------------ //
// Publish-a-new-version composer: N subject-less governance rules (added to a
// local list) + an audience CommScope. Publishes MAX+1 (append-only). Sends
// `audience` only when a condition exists and `governance` only when a rule
// exists; an empty {} is a legal, non-restricting version.
// ------------------------------------------------------------------ //
function PublishVersionForm({
  policyId,
  catalog,
  onPublished,
}: {
  policyId: string;
  catalog: TagKeyRow[];
  onPublished: () => void | Promise<void>;
}) {
  const [rules, setRules] = useState<PolicyRule[]>([]);
  const [audience, setAudience] = useState<CommScope | null>(null);
  const [audienceIncomplete, setAudienceIncomplete] = useState(false);
  // Bumped after a successful publish to remount the CommScopeEditor and reset
  // its internal leg state (it is initialised from `initial`).
  const [formKey, setFormKey] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const publish = async () => {
    setBusy(true);
    try {
      const body: { audience?: CommScope; governance?: PolicyRule[] } = {};
      if (audience) body.audience = audience;
      if (rules.length) body.governance = rules;
      await api.publishPolicyVersion(policyId, body);
      setRules([]);
      setAudience(null);
      setAudienceIncomplete(false);
      setFormKey((k) => k + 1);
      setError(null);
      await onPublished();
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      className="mt-5 rounded-xl border border-dashed border-surface-300 dark:border-surface-700 p-4"
      data-testid="publish-version-form"
    >
      <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-3">
        Publish a new version
      </h3>

      {/* Governance rules (subject-less) — the SAME editor an agent's inline
          policy uses, since inline and global governance are identical in force. */}
      <div className="mb-4">
        <span className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
          Governance rules
        </span>
        <GovernanceRulesEditor
          rules={rules}
          onChange={setRules}
          testId="draft-rules"
        />
      </div>

      {/* Audience (comm_scope) */}
      <div className="mb-3">
        <span className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
          Audience
        </span>
        <div className="mt-1">
          <CommScopeEditor
            key={formKey}
            initial={null}
            catalog={catalog}
            agents={[]}
            onChange={setAudience}
            onIncompleteChange={setAudienceIncomplete}
          />
        </div>
      </div>

      {error && <p className="mb-2 text-xs text-red-500">{error}</p>}

      <div className="flex items-center gap-2">
        <button
          className="btn btn-primary"
          onClick={publish}
          disabled={busy || audienceIncomplete}
          title={
            audienceIncomplete
              ? "Every In/NotIn audience expression needs at least one value"
              : "Publish the next immutable version (MAX+1)"
          }
          data-testid="publish-version"
        >
          <Plus size={14} /> Publish version
        </button>
        <span className="text-[10px] text-surface-400 dark:text-surface-500">
          Publishing with no rules and no audience is allowed — an empty,
          non-restricting version.
        </span>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ //
// The right inspector for one selected policy: editable header + delete, the
// version history table, and the publish composer.
// ------------------------------------------------------------------ //
function PolicyDetail({
  policyId,
  catalog,
  onClose,
  onChanged,
  onDeleted,
}: {
  policyId: string;
  catalog: TagKeyRow[];
  onClose: () => void;
  onChanged: () => void;
  onDeleted: () => void;
}) {
  const { confirm, dialog } = useConfirm();
  const [record, setRecord] = useState<PolicyRecord | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [inUse, setInUse] = useState<PolicyInUseDetails | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .policy(policyId)
      .then((rec) => {
        setRecord(rec);
        setName(rec.name);
        setDescription(rec.description ?? "");
        setInUse(null);
        setError(null);
      })
      .catch((exc) => setError((exc as Error).message));
  }, [policyId]);

  useEffect(() => {
    load();
  }, [load]);

  const dirty =
    record != null &&
    (name.trim() !== record.name ||
      description.trim() !== (record.description ?? ""));

  const saveHeader = async () => {
    try {
      await api.updatePolicy(policyId, {
        name: name.trim(),
        description,
      });
      setError(null);
      load();
      onChanged();
    } catch (exc) {
      setError((exc as Error).message);
    }
  };

  const remove = async () => {
    try {
      await api.deletePolicy(policyId);
      onDeleted();
    } catch (exc) {
      if (exc instanceof ApiError && exc.code === "POLICY_IN_USE") {
        setInUse(exc.details as PolicyInUseDetails);
      } else {
        setError((exc as Error).message);
      }
    }
  };

  const versions = record?.versions ?? [];

  return (
    <div
      className="flex flex-col h-full min-h-0"
      data-testid="policy-detail-body"
    >
      {dialog}
      <div className="shrink-0 flex items-center gap-2 mb-3">
        <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100 truncate">
          {record ? record.name : "Loading…"}
        </h2>
        {record && (
          <CatalogExportButton
            catalog="policies"
            filename={catalogEntityFilename("okto-nexus-policy", record.name)}
            className="ml-auto btn btn-secondary !py-1"
            title={`Export ${record.name} as JSON`}
            onExport={() => ({
              name: record.name,
              description: record.description,
              versions: (record.versions ?? []).map(({ audience, governance }) => ({
                audience,
                governance,
              })),
            })}
          />
        )}
        <button
          className="text-surface-400 hover:text-surface-700 dark:hover:text-surface-200"
          onClick={onClose}
          title="Close"
          data-testid="close-policy-detail"
        >
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto pr-1">
        {error && <p className="mb-3 text-xs text-red-500">{error}</p>}

        {record && (
          <>
            {/* Editable header */}
            <section className="panel p-4">
              <div className="space-y-3">
                <label className="block">
                  <span className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
                    Name
                  </span>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className={`${inputCls} mt-1 block w-full`}
                    data-testid="policy-name"
                  />
                </label>
                <label className="block">
                  <span className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
                    Description
                  </span>
                  <input
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Optional"
                    className={`${inputCls} mt-1 block w-full`}
                    data-testid="policy-description"
                  />
                </label>
              </div>
              <p className="text-[11px] text-surface-400 dark:text-surface-500 mt-3 font-mono">
                {policyId} · created{" "}
                {new Date(record.created_at).toLocaleString()}
              </p>
              <div className="flex items-center gap-2 mt-3">
                <button
                  className="btn btn-primary"
                  onClick={saveHeader}
                  disabled={!dirty || !name.trim()}
                  data-testid="save-policy-header"
                >
                  Save
                </button>
                <button
                  className="btn btn-danger ml-auto"
                  onClick={() =>
                    confirm({
                      title: "Delete policy?",
                      body: (
                        <span>
                          <b className="font-mono">{record.name}</b> and its{" "}
                          {versions.length} version
                          {versions.length === 1 ? "" : "s"} will be removed. This
                          is refused if any agent still binds it.
                        </span>
                      ),
                      onConfirm: remove,
                    })
                  }
                  data-testid="delete-policy"
                >
                  Delete
                </button>
              </div>
              {inUse && (
                <PolicyInUsePanel
                  details={inUse}
                  onDismiss={() => setInUse(null)}
                />
              )}
            </section>

            {/* Version history */}
            <section className="mt-5" data-testid="version-history">
              <div className="flex items-center gap-2 mb-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-surface-500 dark:text-surface-400">
                  Version history
                </h3>
                <span className="chip bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300">
                  {versions.length}
                </span>
              </div>
              {versions.length === 0 ? (
                <p className="text-xs text-surface-400 dark:text-surface-500">
                  No versions published yet — publish the first one below.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-[11px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
                        <th className="py-1.5 pr-3 font-medium">Ver</th>
                        <th className="py-1.5 pr-3 font-medium">Published</th>
                        <th className="py-1.5 pr-3 font-medium">Audience</th>
                        <th className="py-1.5 pr-3 font-medium">Governance</th>
                      </tr>
                    </thead>
                    <tbody>
                      {versions.map((version: PolicyVersion) => (
                        <tr
                          key={version.version}
                          className="border-t border-surface-100 dark:border-surface-800"
                          data-testid={`version-${version.version}`}
                        >
                          <td className="py-2 pr-3 font-mono">
                            @v{version.version}
                          </td>
                          <td className="py-2 pr-3 whitespace-nowrap text-surface-500 dark:text-surface-400">
                            {new Date(version.published_at).toLocaleString()}
                          </td>
                          <td className="py-2 pr-3 font-mono">
                            {audienceSummary(version.audience)}
                          </td>
                          <td className="py-2 pr-3">
                            {version.governance.length === 0 ? (
                              "—"
                            ) : (
                              <span
                                className="font-mono"
                                title={version.governance
                                  .map(ruleLabel)
                                  .join(", ")}
                              >
                                {version.governance.length} rule
                                {version.governance.length === 1 ? "" : "s"}
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <PublishVersionForm
              policyId={policyId}
              catalog={catalog}
              onPublished={() => {
                load();
                onChanged();
              }}
            />
          </>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ //
// The screen: master list (left) + inspector (right).
// ------------------------------------------------------------------ //
export function PoliciesView({ workspace }: { workspace: string }) {
  const [policies, setPolicies] = useState<PolicyRecord[]>([]);
  const [catalog, setCatalog] = useState<TagKeyRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState({ name: "", description: "" });
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(
    () =>
      api
        .policies()
        .then(({ items }) => {
          setPolicies(items);
          setError(null);
        })
        .catch((exc) => setError((exc as Error).message)),
    [],
  );

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    api
      .tags()
      .then(({ items }) => setCatalog(items))
      .catch(() => undefined);
  }, []);

  const create = async () => {
    const name = draft.name.trim();
    if (!name) return;
    try {
      const created = await api.createPolicy({
        name,
        description: draft.description.trim() || undefined,
      });
      setDraft({ name: "", description: "" });
      setError(null);
      await reload();
      setSelectedId(created.policy_id);
    } catch (exc) {
      setError((exc as Error).message);
    }
  };

  return (
    <PageContainer
      width="bleed"
      scroll="none"
      className="flex"
      testId="policies-view"
    >
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Header + new-policy form */}
        <div className="shrink-0 border-b border-surface-200/60 dark:border-surface-700/60 bg-white/80 dark:bg-surface-900/80 backdrop-blur-md px-4 py-3">
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-lg font-display font-semibold text-surface-900 dark:text-surface-100">
              Policies
            </h1>
            <span className="chip bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
              Operator-only
            </span>
            <span className="chip bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300">
              {policies.length} polic{policies.length === 1 ? "y" : "ies"}
            </span>
            <div className="ml-auto">
              <CatalogImportButton
                catalog="policies"
                onImport={async (value) => {
                  const names = new Set(policies.map((policy) => policy.name.toLocaleLowerCase()));
                  if (!value || typeof value !== "object" || Array.isArray(value)) {
                    throw new Error("The policy export is invalid.");
                  }
                  const row = value as Record<string, unknown>;
                  if (typeof row.name !== "string") {
                    throw new Error("The policy must include a name.");
                  }
                  const rawVersions = Array.isArray(row.versions) ? row.versions : [];
                  const versions = rawVersions.map((versionValue) => {
                    if (
                      !versionValue ||
                      typeof versionValue !== "object" ||
                      Array.isArray(versionValue)
                    ) {
                      throw new Error("The policy contains an invalid version.");
                    }
                    const version = versionValue as Record<string, unknown>;
                    const audience = version.audience;
                    const governance = version.governance;
                    if (
                      audience !== null &&
                      audience !== undefined &&
                      (typeof audience !== "object" || Array.isArray(audience))
                    ) {
                      throw new Error("A policy version contains an invalid audience.");
                    }
                    if (
                      !Array.isArray(governance) ||
                      !governance.every(
                        (rule) =>
                          !!rule && typeof rule === "object" && !Array.isArray(rule),
                      )
                    ) {
                      throw new Error("A policy version contains invalid governance rules.");
                    }
                    return {
                      audience: audience as CommScope | null | undefined,
                      governance: governance as PolicyRule[],
                    };
                  });
                  const created = await api.createPolicy({
                    name: uniqueImportedName(row.name, names),
                    description:
                      typeof row.description === "string" ? row.description : undefined,
                  });
                  for (const version of versions) {
                    await api.publishPolicyVersion(created.policy_id, {
                      ...(version.audience
                        ? { audience: version.audience }
                        : {}),
                      governance: version.governance,
                    });
                  }
                  await reload();
                  setSelectedId(created.policy_id);
                }}
              />
            </div>
          </div>
          <p className="text-xs text-surface-500 dark:text-surface-400 mb-3">
            Named, versioned global policies — one append-only object unifying an{" "}
            <b>audience</b> (who a holder may reach / be reached by) and{" "}
            <b>governance</b> rules (denies + quotas). A policy stages until an
            agent binds it; enforcement is always-on and binding-driven.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <label className="block">
              <span className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
                Name
              </span>
              <input
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                onKeyDown={(e) => e.key === "Enter" && create()}
                placeholder="e.g. tier-gold-only"
                className={`${inputCls} mt-1 block w-48 font-mono`}
                data-testid="new-policy-name"
              />
            </label>
            <label className="block flex-1 min-w-40">
              <span className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
                Description (optional)
              </span>
              <input
                value={draft.description}
                onChange={(e) =>
                  setDraft({ ...draft, description: e.target.value })
                }
                placeholder="What this policy is for"
                className={`${inputCls} mt-1 block w-full`}
                data-testid="new-policy-description"
              />
            </label>
            <button
              className="btn btn-primary"
              onClick={create}
              disabled={!draft.name.trim()}
              data-testid="create-policy"
            >
              <Plus size={14} /> New policy
            </button>
          </div>
          {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
        </div>

        {/* Policy list + denials */}
        <div className="flex-1 overflow-y-auto px-4 py-3" data-testid="policies-list">
          {policies.length === 0 ? (
            <p className="text-xs text-surface-400 dark:text-surface-500">
              No policies yet — create the first one above.
            </p>
          ) : (
            <div className="space-y-1.5">
              {policies.map((policy) => (
                <div
                  key={policy.policy_id}
                  className={`w-full rounded-lg border flex items-start transition-colors ${
                    selectedId === policy.policy_id
                      ? "border-accent-300 dark:border-accent-700 bg-accent-50 dark:bg-accent-900/20"
                      : "border-surface-200 dark:border-surface-700 hover:bg-surface-50 dark:hover:bg-surface-800/50"
                  }`}
                  data-testid={`policy-${policy.policy_id}`}
                >
                  <button
                    onClick={() => setSelectedId(policy.policy_id)}
                    className="min-w-0 flex-1 text-left px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-surface-900 dark:text-surface-100 truncate">
                        {policy.name}
                      </span>
                      {policy.latest_version === 0 ? (
                        <span className="chip bg-surface-200 text-surface-500 dark:bg-surface-700 dark:text-surface-400">
                          no versions
                        </span>
                      ) : (
                        <span className="chip bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300 font-mono">
                          @v{policy.latest_version}
                        </span>
                      )}
                    </div>
                    {policy.description && (
                      <p className="text-xs text-surface-500 dark:text-surface-400 mt-0.5 truncate">
                        {policy.description}
                      </p>
                    )}
                  </button>
                  <CatalogExportButton
                    catalog="policies"
                    filename={catalogEntityFilename("okto-nexus-policy", policy.name)}
                    className="btn btn-secondary !px-2 !py-1 !text-[10px] shrink-0 m-2 ml-0"
                    label="Export JSON"
                    title={`Export ${policy.name} as JSON`}
                    testId={`export-policy-${policy.policy_id}`}
                    onExport={async () => {
                      const record = await api.policy(policy.policy_id);
                      return {
                        name: record.name,
                        description: record.description,
                        versions: (record.versions ?? []).map(
                          ({ audience, governance }) => ({ audience, governance }),
                        ),
                      };
                    }}
                  />
                </div>
              ))}
            </div>
          )}

          <DenialsPanel workspace={workspace} />
        </div>
      </div>

      {selectedId && (
        <ResizablePanel storageKey="policy-detail" testId="policy-detail">
          <PolicyDetail
            key={selectedId}
            policyId={selectedId}
            catalog={catalog}
            onClose={() => setSelectedId(null)}
            onChanged={reload}
            onDeleted={() => {
              setSelectedId(null);
              reload();
            }}
          />
        </ResizablePanel>
      )}
    </PageContainer>
  );
}
