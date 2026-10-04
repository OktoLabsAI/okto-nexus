import { useEffect, useRef, useState } from "react";
import { api, type ApprovalDetail } from "../api";
import { runtimeApi, type NativeDecisionRequest, type NativeDecisionView } from "../runtimeApi";
import { NativeApprovalInput } from "./NativeApprovalInput";

type Proposal = Omit<NativeDecisionRequest, "client_intent_id" | "decision" | "response"> & {
  expires_at: string; display: unknown; recipient_agent_id?: string | null;
};

export function CanonicalNativeDecision({detail, onChanged}: {detail: ApprovalDetail; onChanged: () => void}) {
  const proposal = detail.request_payload?.kwargs as Proposal | undefined;
  const alive = useRef(true);
  const locked = useRef(false);
  const attemptedAnswer = useRef<string | null>(null);
  const [key, setKey] = useState("");
  const [canAnswer, setCanAnswer] = useState(false);
  const [saved, setSaved] = useState<NativeDecisionRequest | null>(null);
  const [view, setView] = useState<NativeDecisionView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());
  const valid = !!proposal?.approval_key && proposal.approval_key.canonical_request_id === detail.approval_id &&
    typeof proposal.expected_revision === "number" && typeof proposal.cas_token === "string" && typeof proposal.request_hash === "string";
  const expired = !proposal || Date.parse(proposal.expires_at) <= now || !Number.isFinite(Date.parse(proposal.expires_at));
  const checkIdentity = (result: NativeDecisionView) => {
    if (!proposal || Object.entries(proposal.approval_key).some(([name, value]) => result.approval_key[name] !== value)) {
      throw new Error("The decision does not match the reviewed runtime request.");
    }
  };
  const recover = async (signal?: AbortSignal) => {
    const latest = await api.approvalDetail(detail.approval_id);
    const decision = latest.executed_result as NativeDecisionView | undefined;
    if (decision?.decision_id) {
      const result = await runtimeApi.nativeDecision(decision.decision_id, signal);
      checkIdentity(result);
      if (alive.current && !signal?.aborted) setView(result);
    }
  };
  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    void (async () => {
      try {
        const me = await runtimeApi.me(controller.signal);
        if (controller.signal.aborted || !proposal) return;
        if (me.server_id !== proposal.approval_key.server_id) throw new Error("The native request belongs to another Server.");
        setCanAnswer(me.agent_id === (proposal.recipient_agent_id ?? "operator"));
        const storageKey = `okto-nexus:r4-native:${JSON.stringify([me.server_id, me.agent_id, detail.approval_id])}`;
        const raw = sessionStorage.getItem(storageKey);
        if (raw) {
          const record = JSON.parse(raw) as NativeDecisionRequest;
          if (!record.client_intent_id || record.approval_key?.canonical_request_id !== detail.approval_id ||
              !["approve", "deny"].includes(record.decision) || "response" in record) {
            throw new Error("The saved decision metadata is invalid. No decision was sent.");
          }
          setSaved(record);
        }
        setKey(storageKey);
        await recover(controller.signal);
      } catch (failure) { if (!controller.signal.aborted) setError(String(failure)); }
    })();
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => { alive.current = false; controller.abort(); window.clearInterval(timer); };
  }, [detail.approval_id]);
  useEffect(() => {
    if (!key) return;
    const controller = new AbortController();
    let pending = false;
    const timer = window.setInterval(() => {
      if (pending || locked.current) return;
      pending = true;
      void recover(controller.signal).catch(failure => {
        if (!controller.signal.aborted && alive.current) setError(String(failure));
      }).finally(() => { pending = false; });
    }, 2500);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [key]);

  const decide = async (decision: "approve" | "deny", response?: Record<string, unknown>) => {
    if (locked.current || !key || !valid || !proposal || expired || view || !canAnswer) return;
    locked.current = true; setBusy(true); setError("");
    try {
      if (saved && saved.decision !== decision) throw new Error("Recover the original decision before choosing another response.");
      const encodedAnswer = JSON.stringify(response ?? null);
      if (attemptedAnswer.current !== null && attemptedAnswer.current !== encodedAnswer) {
        throw new Error("Retry the same answer or check the original decision. The pending answer cannot be changed.");
      }
      const metadata: NativeDecisionRequest = saved || {
        client_intent_id: `ui_${Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, "0")).join("")}`,
        approval_key: proposal.approval_key, expected_revision: proposal.expected_revision,
        request_hash: proposal.request_hash, cas_token: proposal.cas_token, decision,
      };
      // Only immutable CAS metadata survives reload. Answers remain in memory
      // and must be explicitly re-entered if an uncertain input is retried.
      sessionStorage.setItem(key, JSON.stringify(metadata));
      setSaved(metadata);
      attemptedAnswer.current = encodedAnswer;
      const result = await runtimeApi.decideNative({...metadata, ...(response ? {response} : {})});
      checkIdentity(result);
      if (alive.current) { setView(result); onChanged(); }
    } catch (failure) { if (alive.current) setError(String(failure)); }
    finally { locked.current = false; if (alive.current) setBusy(false); }
  };
  const formDetail: ApprovalDetail = {...detail,
    status: view || expired || !valid || !key || !canAnswer || saved?.decision === "deny" ? "approved" : detail.status,
    request_payload: {kwargs: {payload: proposal?.display}},
    decision_detail: {operation_id: view?.native_operation_id || "", state: view ? view.native_stage : "PENDING",
      decision: null, reason: null, expires_at: proposal?.expires_at || "", response: null},
  };
  return <section aria-label="Native runtime decision" className="space-y-3">
    {!valid && <p role="alert">The canonical runtime request is incomplete. Refresh its details.</p>}
    {key && !canAnswer && <p role="status">This request is addressed to {proposal?.recipient_agent_id ?? "operator"}.</p>}
    {proposal && <p>Agent {String(proposal.approval_key.agent_id)} · Host {String(proposal.approval_key.executor_id)} · Session {String(proposal.approval_key.session_id)}</p>}
    {view ? <div role="status" data-testid="canonical-native-status">
      <p>Decision: {view.canonical_state}. Native delivery: {view.native_stage}.</p>
      <p>A recorded decision does not prove application by the provider.</p>
      {view.possible_effect && <p>The response may have reached the provider.</p>}
      {view.native_stage === "OUTCOME_UNKNOWN" && <p>Delivery is uncertain. Reconcile the session before attempting further work.</p>}
    </div> : <>
      <NativeApprovalInput detail={formDetail} busy={busy} canonicalPermission={proposal?.approval_key.kind === "native_approval"}
        onApprove={response => void decide("approve", response)} />
      {saved && <p role="status">A decision request was sent. Check its result before retrying the same choice. Answers are not saved in browser storage; re-enter the same answer if needed.</p>}
      <button className="btn btn-secondary" disabled={busy || !key || !valid || !canAnswer || expired || (!!saved && saved.decision !== "deny") || detail.status !== "pending"}
        onClick={() => void decide("deny")}>{saved?.decision === "deny" ? "Retry the same denial" : "Deny runtime request"}</button>
    </>}
    <button className="btn btn-secondary" disabled={busy} onClick={() => {
      setError(""); void recover().catch(failure => { if (alive.current) setError(String(failure)); });
    }}>Check native decision</button>
    {expired && !view && <p role="status">This native request expired. No new answer can be submitted.</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
