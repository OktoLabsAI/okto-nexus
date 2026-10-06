import { ConfigurationHelp } from './ConfigurationHelp';
import { useEffect, useRef, useState } from "react";
import { ApiError } from "../api";
import { runtimeApi, type LocalPreparationRequest, type RuntimeChoice } from "../runtimeApi";

const inputClass = "block w-full rounded border p-2 dark:bg-surface-800";

export function EmbeddedPreparation({agentId, executorId, hostLabel, workspaceId, workspaceLabel,
  inventoryRevision, choice, onPrepared, beforePrepare}: {
  agentId: string; executorId: string; hostLabel: string; workspaceId: string; workspaceLabel: string;
  inventoryRevision: string; choice: RuntimeChoice; onPrepared: (workspaceId: string) => void;
  beforePrepare?: () => Promise<void>;
}) {
  const storageKey = "okto-nexus:r4-local-preparation:" + JSON.stringify([
    agentId, executorId, workspaceId, choice.adapter_id, choice.candidate_ref, inventoryRevision,
    ...(choice.binding ? [choice.binding.binding_id, choice.binding.binding_revision] : []),
  ]);
  const [saved] = useState(() => {
    try {
      const raw = sessionStorage.getItem(storageKey);
      if (!raw) return {request: null, error: ""};
      const request = JSON.parse(raw) as LocalPreparationRequest;
      if (request.agent_id !== agentId || request.adapter_id !== choice.adapter_id ||
          request.candidate_ref !== choice.candidate_ref || request.inventory_revision !== inventoryRevision ||
          request.workspace_id !== (workspaceId || null) || request.approved !== true ||
          typeof request.client_intent_id !== "string" || typeof request.local_consent_id !== "string" ||
          typeof request.workspace_root !== "string" || typeof request.workspace_label !== "string" ||
          (request.provider_home !== null && typeof request.provider_home !== "string") ||
          !request.secret_bindings || typeof request.secret_bindings !== "object") {
        throw new Error("The saved preparation does not match this selection. Review it before continuing.");
      }
      return {request, error: ""};
    } catch (failure) { return {request: null, error: String(failure)}; }
  });
  const [pending, setPending] = useState<LocalPreparationRequest | null>(saved.request);
  const [root, setRoot] = useState(saved.request?.workspace_root || "");
  const [workspacePaths, setWorkspacePaths] = useState<{path: string}[]>([]);
  const [home, setHome] = useState(saved.request ? saved.request.provider_home || "" : choice.provider_home_suggestion || "");
  const [label, setLabel] = useState(saved.request?.workspace_label || workspaceLabel);
  const [references, setReferences] = useState(saved.request
    ? Object.entries(saved.request.secret_bindings).map(([name, ref]) => `${name}=${ref}`).join("\n") : "");
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(saved.error);
  const runtimeSettings: Record<string, {name: string; home: string; credential: string}> = {
    codex_app_server: {name: 'Codex', home: 'Use the Codex configuration directory (.codex or CODEX_HOME) containing the login.', credential: 'OPENAI_API_KEY=vault:provider-key'},
    claude_stream: {name: 'Claude Code', home: 'Use the Claude configuration directory (.claude or CLAUDE_CONFIG_DIR) containing the login.', credential: 'ANTHROPIC_API_KEY=vault:provider-key'},
    pi_rpc: {name: 'Pi', home: 'Use the Pi agent directory (.pi/agent or PI_CODING_AGENT_DIR) containing settings.json and auth.json.', credential: 'OPENAI_API_KEY=vault:provider-key'},
  };
  const settings = runtimeSettings[choice.adapter_id];
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (!workspaceId) return;
    const controller = new AbortController();
    runtimeApi.workspacePaths(workspaceId, executorId, controller.signal)
      .then(({items}) => {
        if (controller.signal.aborted) return;
        setWorkspacePaths(items);
        if (items.length === 1 && !saved.request) setRoot(current => current || items[0].path);
      })
      .catch(() => { /* Manual entry remains available. */ });
    return () => controller.abort();
  }, [workspaceId, executorId, saved.request]);

  const submit = async () => {
    setBusy(true); setError("");
    try {
      let request = pending;
      if (!request) {
        if (!approved || !root.trim() || !choice.candidate_ref) throw new Error("Review and approve the local folders first.");
        const secretBindings: Record<string, string> = Object.create(null);
        for (const line of references.split("\n").filter(line => line.trim())) {
          const match = /^([A-Za-z_][A-Za-z0-9_]{0,127})=((?:vault|provider):[^\r\n\0]+)$/.exec(line.trim());
          if (!match || !match[2].split(":").slice(1).join(":").trim() ||
              /nxs_|nxsept_|nxc4_|nxt4_/.test(match[2]) || match[2].length > 256 || match[1] in secretBindings) {
            throw new Error("Use one unique NAME=vault:reference or NAME=provider:reference per line. Do not enter secret values.");
          }
          secretBindings[match[1]] = match[2];
        }
        if (Object.keys(secretBindings).length > 64) throw new Error("At most 64 protected references are allowed.");
        const id = "ui_" + Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, "0")).join("");
        request = {client_intent_id: id, local_consent_id: id, approved: true,
          agent_id: agentId, adapter_id: choice.adapter_id, candidate_ref: choice.candidate_ref,
          inventory_revision: inventoryRevision, workspace_id: workspaceId || null,
          workspace_label: workspaceId ? "" : label.trim(), workspace_root: root.trim(), provider_home: home.trim() || null,
          secret_bindings: secretBindings};
        // Persist before any request. Lost responses and tab reload retain the
        // same consent, scope and body; no credentials are stored here.
        sessionStorage.setItem(storageKey, JSON.stringify(request));
        setPending(request);
      }
      await beforePrepare?.();
      const result = await runtimeApi.prepareLocal(executorId, request);
      if (result.executor_id !== executorId || result.agent_id !== agentId ||
          result.inventory_revision !== inventoryRevision || !result.realization_ref || !result.workspace_id ||
          (workspaceId && result.workspace_id !== workspaceId)) {
        throw new Error("The returned preparation does not match this selection.");
      }
      window.dispatchEvent(new Event("nexus-workspaces-changed"));
      if (mounted.current) onPrepared(result.workspace_id);
    } catch (failure) {
      // Only a first, explicitly rejected request can be edited. A retry may
      // follow a lost successful reply, so keep its original identity/body.
      if (!pending && failure instanceof ApiError && failure.status >= 400 && failure.status < 500) {
        try {
          sessionStorage.removeItem(storageKey);
          if (mounted.current) { setPending(null); setApproved(false); }
        } catch { /* Retain the recorded request if storage cannot be updated. */ }
      }
      if (mounted.current) setError(String(failure));
    }
    finally { if (mounted.current) setBusy(false); }
  };

  return <section aria-label="Local workspace preparation" className="space-y-3">
    <h5 className="font-semibold">Folders and login <ConfigurationHelp label="Folders and login">These paths are on the Nexus server, not the browser computer. Use existing absolute directories. Folder consent, connection approval, and execution authorization are separate.</ConfigurationHelp></h5>
    <p className="text-xs text-surface-500">Host: {hostLabel}</p>

    <fieldset disabled={busy || pending !== null || !!saved.error} className="space-y-2">
      {workspaceId && workspacePaths.length > 0 && <label className="block">Previously used folders on this execution host
        <select aria-label="Saved workspace directory" className={inputClass}
          value={workspacePaths.some(item => item.path === root) ? root : ''}
          onChange={event => setRoot(event.target.value)}>
          <option value="">Enter a new folder</option>
          {workspacePaths.map(item => <option key={item.path} value={item.path}>{item.path}</option>)}
        </select>
      </label>}
      <label className="block">Workspace directory <span className="text-xs text-surface-500">Required</span><ConfigurationHelp label="Workspace directory">Existing absolute directory this harness may use for the selected workspace.</ConfigurationHelp><input required aria-label="Workspace directory" className={inputClass} value={root} maxLength={4096} onChange={event => setRoot(event.target.value)} /></label>
      {!workspaceId && <label className="block">New workspace name <span className="text-xs text-surface-500">Required</span><input required aria-label="New workspace name" className={inputClass} value={label} maxLength={160} onChange={event => setLabel(event.target.value)} /></label>}
      {workspaceId && <p>Workspace: {workspaceLabel || workspaceId}</p>}
      <label className="block">Login directory <span className="text-xs text-surface-500">Optional</span><ConfigurationHelp label="Login directory">{(settings?.home || "Use an existing provider login directory.") + " Leave blank when using protected credential references instead. Discovery does not grant access."}</ConfigurationHelp><input aria-label="Provider home directory" className={inputClass} value={home} maxLength={4096} onChange={event => setHome(event.target.value)} /></label>
      {choice.provider_home_suggestion && <p className="text-xs text-surface-500">Detected login directory available.</p>}


      <details><summary className="cursor-pointer text-surface-500">Advanced credentials · Optional</summary><label className="block mt-2">Protected credential references<ConfigurationHelp label="Protected credential references">Use NAME=vault:reference or NAME=provider:reference, one per line. Enter references only, never API keys or tokens.</ConfigurationHelp><textarea aria-label="Protected credential references" className={inputClass} value={references} maxLength={25000} rows={2} placeholder={settings?.credential} onChange={event => setReferences(event.target.value)} /></label>
      </details>
      <label className="block"><input type="checkbox" checked={approved} onChange={event => setApproved(event.target.checked)} /> I approve these folders and credential references. <span className="text-xs text-surface-500">Required</span></label>
    </fieldset>

    {busy && <p role="status">Saving folders and login…</p>}
    {pending && !busy && <p role="status">This preparation request was recorded. Retry the same request to confirm its result; its folders and consent remain unchanged.</p>}
    <button className="btn btn-primary" disabled={busy || !!saved.error || (!pending && (!approved || !root.trim() || (!workspaceId && (!label.trim() || /[\\/:]/.test(label)))))}
      onClick={() => void submit()}>{busy ? "Saving…" : pending ? "Retry the same preparation" : "Approve local preparation"}</button>
    {error && <p role="alert">{error}</p>}
  </section>;
}
