import { useEffect, useRef, useState } from "react";
import { api, type RuntimeBindingAgent, type RuntimeOperationRow } from "../api";
import { PageContainer } from "../components/PageContainer";

const button = "rounded-lg border border-surface-300 dark:border-surface-600 px-3 py-2 text-sm disabled:opacity-50";
const card = "rounded-xl border border-surface-200 dark:border-surface-700 p-4 space-y-2";
const uncertain = new Set(["OUTCOME_UNKNOWN", "SENT_UNCONFIRMED", "ACCEPTED"]);

function operationAdvice(row: RuntimeOperationRow): string {
  if (row.reconciliation_id) return "Operator reconciliation recorded. Original transport facts remain unchanged; no native replay was requested.";
  if (row.terminal_event_id) return "A correlated terminal was recorded. This alone does not establish handoff completion or successful publication.";
  if (uncertain.has(row.state)) return "Acceptance or completion is uncertain. Do not resend automatically. Review the attempt and close or reconcile its runtime before operator takeover.";
  if (row.state === "SENDING") return "A transport call may be in flight. A timeout does not prove that no bytes were written.";
  if (["PENDING", "CLAIMED"].includes(row.state)) return "Awaiting transport. Operator cancellation is available only while the server confirms no send-intent.";
  return "Review the recorded state and reason. A transport outcome does not grant authority to execute another task.";
}

export function RuntimesView({ onApprovals }: { onApprovals: () => void }) {
  const [agents, setAgents] = useState<RuntimeBindingAgent[]>([]);
  const [operations, setOperations] = useState<RuntimeOperationRow[]>([]);
  const [bindingCursor, setBindingCursor] = useState<string>();
  const [operationCursor, setOperationCursor] = useState<string>();
  const [nextBinding, setNextBinding] = useState<string | null>(null);
  const [nextOperation, setNextOperation] = useState<string | null>(null);
  const [bindingError, setBindingError] = useState("");
  const [operationError, setOperationError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const request = useRef(0);
  useEffect(() => {
    const generation = ++request.current;
    setBusy(true);
    // Clear the prior snapshot: denied or changed authority must not leave
    // previously visible operation metadata on screen.
    setAgents([]); setOperations([]); setNextBinding(null); setNextOperation(null);
    setBindingError(""); setOperationError("");
    Promise.allSettled([api.runtimeBindings(bindingCursor), api.runtimeOperations(operationCursor)])
      .then(([bindings, outbox]) => {
        if (request.current !== generation) return;
        if (bindings.status === "fulfilled") {
          setAgents(bindings.value.agents);
          setNextBinding(bindings.value.has_more ? bindings.value.next_endpoint_id : null);
        } else setBindingError(String(bindings.reason));
        if (outbox.status === "fulfilled") {
          setOperations(outbox.value.items);
          setNextOperation(outbox.value.has_more ? outbox.value.next_operation_id : null);
        } else setOperationError(String(outbox.reason));
        setBusy(false);
      });
    return () => { ++request.current; };
  }, [bindingCursor, operationCursor, revision]);

  return <PageContainer testId="runtimes-view" className="space-y-6">
    <div className="flex items-start justify-between gap-4">
      <div><h1 className="text-xl font-semibold">Runtimes</h1>
        <p className="text-sm text-surface-500">Authorized runtime records across all workspaces. Connections belong to existing agents.</p></div>
      <div className="flex gap-2">
        <button className={button} onClick={onApprovals}>Review native approvals</button>
        <button className={button} disabled={busy} onClick={() => setRevision(value => value + 1)}>Refresh runtimes</button>
      </div>
    </div>
    {busy && <p role="status">Loading runtime records…</p>}
    <section aria-label="Agent connections" className="space-y-3">
      <h2 className="font-semibold">Agent connections</h2>
      {bindingError && <p role="alert">Connection discovery unavailable: {bindingError}</p>}
      {!busy && !bindingError && !agents.length && <p>No visible connections on this page.</p>}
      {agents.map(agent => <article key={agent.agent_id} className={card} data-testid={`runtime-agent-${agent.agent_id}`}>
        <h3 className="font-semibold">{agent.agent_id}</h3>
        <p className="text-sm">Skills: {agent.skill_names.join(", ") || "None declared"}</p>
        {agent.endpoints.flatMap(endpoint => endpoint.sessions).filter(session => session.current_owner_ready_record).length > 1 &&
          <p className="text-amber-700 dark:text-amber-300">Multiple ready bindings are visible. Check workspace, priority and selection group before choosing an executor; this view does not resolve ambiguous routing.</p>}
        {agent.endpoints.map(endpoint => <div key={endpoint.endpoint_id} className="border-t border-surface-200 dark:border-surface-700 pt-2 text-sm">
          <p><strong>{endpoint.endpoint_id}</strong> · {endpoint.adapter_id} · {endpoint.enabled ? "Enabled" : "Disabled"} · {endpoint.health}</p>
          <p className="break-all">Workspace: {endpoint.workspace_id}</p>
          <p>Capabilities: {endpoint.capability_verification}. Declared support is not a binary compatibility probe.</p>
          {endpoint.sessions.map(session => <div key={session.session_id} className="mt-2" data-testid={`runtime-session-${session.session_id}`}>
            <p className="break-all">{session.session_id} · <strong>{session.lifecycle_state}</strong></p>
            <p>{session.lifecycle_state === "detached" ? "Nexus detached; the external process was not declared terminated." :
              session.current_owner_ready_record ? "Current owner readiness is recorded; process liveness is not probed." : "Historical runtime record; current readiness is not established."}</p>
          </div>)}
          {!endpoint.sessions.length && <p>No runtime session recorded.</p>}
          {endpoint.sessions_has_more && <p>Only the ten latest sessions are shown.</p>}
        </div>)}
      </article>)}
      <div className="flex gap-2">
        {bindingCursor && <button className={button} disabled={busy} onClick={() => setBindingCursor(undefined)}>First connections page</button>}
        {nextBinding && <button className={button} disabled={busy} onClick={() => setBindingCursor(nextBinding)}>Next connections page</button>}
      </div>
    </section>
    <section aria-label="Transport operations" className="space-y-3">
      <h2 className="font-semibold">Transport operations</h2>
      {operationError && <p role="alert">Operator operation inspection unavailable: {operationError}</p>}
      {!busy && !operationError && !operations.length && <p>No operations on this page.</p>}
      {operations.map(row => <article key={row.operation_id} className={card} data-testid={`runtime-operation-${row.operation_id}`}>
        <h3 className="font-semibold break-all">{row.operation_id}</h3>
        <p className="text-sm text-surface-500">{row.source_kind === "delivery_outbox" ? "Conversation delivery" : "Runtime command"}</p>
        <p>{row.agent_id} · {row.endpoint_id} · <strong>{row.state}</strong></p>
        <p>Evidence: {row.ack_level} · Runtime: {row.runtime_lifecycle || "Not linked"}</p>
        <p>Reason: {row.reason || "No reason recorded"}</p>
        <p>{operationAdvice(row)}</p>
        <details><summary className="cursor-pointer">Attempt and recovery details</summary>
          <dl className="text-sm break-all space-y-1 mt-2">
            <dt>Attempt</dt><dd>{row.attempt_id || "Not started"}</dd>
            <dt>Owner epoch</dt><dd>{row.owner_epoch ?? "Not assigned"}</dd>
            <dt>Workspace</dt><dd>{row.workspace_id}</dd>
            <dt>Session</dt><dd>{row.runtime_session_id || "Not linked"}</dd>
            <dt>Reconciliation</dt><dd>{row.reconciliation ? `${row.reconciliation.action}: ${row.reconciliation.reason}` : "None recorded"}</dd>
          </dl>
          <p className="text-sm mt-2">Recovery uses the operator outbox API with this exact snapshot, an idempotency key and a reason. Uncertain takeover requires explicit duplicate-risk acknowledgement. Managed handoff claims cannot be released as conversation.</p>
        </details>
      </article>)}
      <div className="flex gap-2">
        {operationCursor && <button className={button} disabled={busy} onClick={() => setOperationCursor(undefined)}>First operations page</button>}
        {nextOperation && <button className={button} disabled={busy} onClick={() => setOperationCursor(nextOperation)}>Next operations page</button>}
      </div>
    </section>
  </PageContainer>;
}
