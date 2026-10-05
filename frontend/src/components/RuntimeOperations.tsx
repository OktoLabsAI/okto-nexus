import { useEffect, useRef, useState } from "react";
import { RuntimeHistory } from "./RuntimeHistory";
import { ApiError } from "../api";
import { runtimeApi, type BindingView, type RuntimeIntent, type RuntimeOperation,
  type RuntimeRequest, type RuntimeResolution, type RuntimeScope, type RuntimeSession } from "../runtimeApi";

type Saved = {request: RuntimeRequest; resolution: RuntimeResolution | null; submissionAttempted: boolean; reviewError?: string; connectionVerified?: boolean; startedAt?: number};
const labels: Record<RuntimeIntent, string> = {"runtime.start": "Start or reuse a runtime",
  "turn.submit": "Send a turn", "turn.steer": "Steer a turn", "turn.interrupt": "Interrupt a turn", "runtime.close": "Close the runtime"};
const fieldClass = "block w-full rounded border p-2 dark:bg-surface-800";

export function RuntimeOperations({agentId, binding, canStart, connectionTest = false, testConfigurationKey = '', onTestStateChange}: {
  agentId: string; binding: BindingView; canStart: boolean; connectionTest?: boolean; testConfigurationKey?: string; onTestStateChange?: (state: string) => void;
}) {
  const mounted = useRef(true);
  const lock = useRef(false);
  const currentRecord = useRef<Saved | null>(null);
  const [storageKey, setStorageKey] = useState("");
  const [saved, setSaved] = useState<Saved | null>(null);
  const [operation, setOperation] = useState<RuntimeOperation | null>(null);
  const [followUps, setFollowUps] = useState<RuntimeOperation[]>([]);
  const [session, setSession] = useState<RuntimeSession | null>(null);
  const [intent, setIntent] = useState<RuntimeIntent>("runtime.start");
  const [sessionId, setSessionId] = useState("");
  const [selection, setSelection] = useState(connectionTest ? "new" : "automatic");
  const testPrompt = "Reply with exactly NEXUS_CONNECTION_OK to confirm this connection.";
  const [text, setText] = useState(connectionTest ? testPrompt : "");
  const [targetKind, setTargetKind] = useState<"native_turn_id" | "current_run">("native_turn_id");
  const [turnId, setTurnId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());

  const matches = (scope: RuntimeScope) => scope.agent_id === agentId && scope.binding_id === binding.binding_id &&
    scope.executor_id === binding.executor_id && scope.workspace_id === binding.workspace_id &&
    scope.workspace_binding_id === binding.workspace_binding_id;
  const persist = (value: Saved) => {
    sessionStorage.setItem(storageKey, JSON.stringify(value));
    currentRecord.current = value;
    if (mounted.current) setSaved(value);
  };
  const run = async (task: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError("");
    try { await task(); }
    catch (failure) { if (mounted.current) setError(String(failure)); }
    finally { lock.current = false; if (mounted.current) setBusy(false); }
  };
  const check = async (record: Saved, signal?: AbortSignal) => {
    const view = await runtimeApi.intent(record.request.client_intent_id, signal);
    if (!matches(view.resolution.scope) || view.resolution.client_intent_id !== record.request.client_intent_id ||
        (view.operation && (!matches(view.operation.scope) || view.operation.operation_id !== view.resolution.operation_id))) {
      throw new Error("The returned operation does not match this selection.");
    }
    if (signal?.aborted || !mounted.current || currentRecord.current?.request.client_intent_id !== record.request.client_intent_id) return;
    persist({...currentRecord.current, resolution: view.resolution});
    // A reuse resolution points at the original opening receipt. Reading that
    // receipt does not replace admission of this newly reviewed reuse request.
    if (view.resolution.reuse && !currentRecord.current.submissionAttempted) return;
    setOperation(view.operation);
    if (view.operation) {
      setSessionId(view.resolution.session_id);
      const current = await runtimeApi.session(view.resolution.session_id, signal);
      if (!matches(current.scope)) throw new Error("The returned session does not match this selection.");
      const children = await Promise.all(view.operation.follow_up_operation_ids.map(id => runtimeApi.operation(id, signal)));
      if (children.some(child => !matches(child.scope) || child.scope.session_id !== view.resolution.session_id)) {
        throw new Error("The initial turn does not match this session.");
      }
      if (!signal?.aborted && mounted.current && currentRecord.current?.request.client_intent_id === record.request.client_intent_id) {
        setSession(current); setFollowUps(children);
      }
    }
  };

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    void (async () => {
      try {
        const me = await runtimeApi.me(controller.signal);
        if (controller.signal.aborted) return;
        const identity = [me.server_id, me.agent_id, agentId, binding.binding_id, ...(connectionTest ? ["connection-test", binding.binding_revision, testConfigurationKey] : [])];
        const key = `okto-nexus:r4-runtime:${JSON.stringify([...identity, binding.workspace_binding_id])}`;
        let raw = sessionStorage.getItem(key);
        if (!raw) {
          const previous = sessionStorage.getItem(`okto-nexus:r4-runtime:${JSON.stringify(identity)}`);
          if (previous && JSON.parse(previous)?.request?.workspace_binding_id === binding.workspace_binding_id) raw = previous;
        }
        if (raw) {
          const record = JSON.parse(raw) as Saved;
          if (!record.request || record.request.agent_id !== agentId || record.request.binding_id !== binding.binding_id ||
              record.request.workspace_binding_id !== binding.workspace_binding_id || !record.request.client_intent_id ||
              typeof record.submissionAttempted !== "boolean") throw new Error("The saved runtime request is invalid. Keep it for recovery; no request was sent.");
          currentRecord.current = record; setSaved(record);
          if (record.reviewError) setError(record.reviewError);
          setIntent(record.request.intent);
          setSessionId(record.resolution?.session_id || record.request.session_id || "");
        }
        setStorageKey(key);
      } catch (failure) { if (!controller.signal.aborted) setError(String(failure)); }
    })();
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => { mounted.current = false; controller.abort(); window.clearInterval(timer); };
  }, [agentId, binding.binding_id, binding.workspace_binding_id]);

  // Recovery only reads. Neither reload nor polling repeats a mutation.
  useEffect(() => {
    if (!storageKey || !saved || saved.reviewError) return;
    const controller = new AbortController();
    let active = false;
    const refresh = async () => {
      if (active || lock.current) return;
      active = true;
      try { if (currentRecord.current) await check(currentRecord.current, controller.signal); }
      catch (failure) { if (!controller.signal.aborted && mounted.current) setError(String(failure)); }
      finally { active = false; }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2500);
    return () => { controller.abort(); window.clearInterval(timer); };
    // The request identity is immutable; polling must not restart on each read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey, saved?.request.client_intent_id, saved?.reviewError]);

  const review = async () => {
    let record = saved;
    if (!record) {
      const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, "0")).join("");
      const request: RuntimeRequest = {client_intent_id: `ui_${id}`, agent_id: agentId, intent,
        binding_id: binding.binding_id, workspace_binding_id: binding.workspace_binding_id};
      if (intent === "runtime.start") {
        if (selection === "new") request.new_session = true;
        if (selection === "existing") request.session_id = sessionId.trim();
      } else request.session_id = sessionId.trim();
      if ((intent === "runtime.start" || intent === "turn.submit" || intent === "turn.steer") && text) request.text = text;
      if (intent === "turn.steer" || intent === "turn.interrupt") request.target = {
        kind: targetKind, expected_turn_id: targetKind === "native_turn_id" ? turnId.trim() : null};
      record = {request, resolution: null, submissionAttempted: false, startedAt: Date.now()};
      persist(record); // Storage failure must prevent the first POST.
    }
    record = {...record, reviewError: undefined};
    persist(record);
    let resolution: RuntimeResolution;
    try {
      resolution = await runtimeApi.resolve(record.request);
    } catch (failure) {
      // A known refusal is not a lost response. Preserve its explanation across
      // refreshes instead of polling an intent that was never admitted.
      if (failure instanceof ApiError && failure.status >= 400 && failure.status < 500) {
        persist({...record, reviewError: String(failure)});
      }
      throw failure;
    }
    if (!matches(resolution.scope) || resolution.client_intent_id !== record.request.client_intent_id) {
      throw new Error("The resolved request does not match this selection.");
    }
    if (mounted.current) persist({...record, resolution});
  };
  const resolution = saved?.resolution;
  const expired = !!resolution && Date.parse(resolution.expires_at) <= now;
  const needsText = intent === "turn.submit" || intent === "turn.steer";
  const targeted = intent === "turn.steer" || intent === "turn.interrupt";
  const needsSession = intent !== "runtime.start" || selection === "existing";
  const canReview = storageKey && (intent !== "runtime.start" || canStart) &&
    (!needsSession || sessionId.trim()) && (!needsText || text.trim()) &&
    (!targeted || targetKind !== "native_turn_id" || turnId.trim());
  const uncertain = !!saved?.submissionAttempted && !operation;
  const isObserved = (value: RuntimeOperation) => !!value.executor_stage &&
    !["RECEIVED_DURABLE", "PREPARED", "SUBMISSION_STARTED", "OUTCOME_UNKNOWN"].includes(value.executor_stage) &&
    value.admission_state !== "RECONCILING";
  const observed = !!operation && isObserved(operation) && followUps.length === operation.follow_up_operation_ids.length && followUps.every(isObserved);
  const canClear = !!saved && (!saved.submissionAttempted || observed);

  const testPassed = connectionTest && saved?.request.intent === 'runtime.start' && !!operation &&
    !operation.error && followUps.length > 0 && followUps.length === operation.follow_up_operation_ids.length &&
    followUps.every(child => !child.error && child.executor_stage === 'SUCCEEDED' && !!child.result?.output_text.includes('NEXUS_CONNECTION_OK'));
  useEffect(() => {
    if (!connectionTest) return;
    const verified = testPassed || saved?.connectionVerified;
    onTestStateChange?.(verified ? session?.lifecycle_state === 'CLOSED' ? 'Verified · test session closed' : 'Verified · close test session' :
      saved ? 'Test in progress / review result' : 'Not tested');
  }, [connectionTest, testPassed, saved?.connectionVerified, saved?.request.client_intent_id, session?.lifecycle_state, onTestStateChange]);
  const submitReviewed = async () => {
    const record = currentRecord.current;
    if (!record?.resolution) throw new Error('Review this test before submitting it.');
    const resolved = record.resolution;
    if (!resolved.can_submit) throw new Error('Connection is not ready: ' + resolved.blockers.join(', '));
    persist({...record, submissionAttempted: true});
    const result = await runtimeApi.submit(resolved);
    if (!matches(result.scope) || result.operation_id !== resolved.operation_id) throw new Error('The test result does not match this connection.');
    if (mounted.current) {setOperation(result); setSessionId(resolved.session_id);}
  };
  const closeTest = async () => {
    if (!session || !matches(session.scope)) throw new Error('The test session is unavailable.');
    const request: RuntimeRequest = {client_intent_id: 'ui_' + crypto.randomUUID().replaceAll('-', ''),
      agent_id: agentId, binding_id: binding.binding_id, workspace_binding_id: binding.workspace_binding_id,
      intent: 'runtime.close', session_id: session.scope.session_id};
    const record: Saved = {request, resolution: null, submissionAttempted: false, connectionVerified: testPassed || saved?.connectionVerified};
    persist(record); setOperation(null); setFollowUps([]); setIntent('runtime.close');
    const resolved = await runtimeApi.resolve(request);
    if (!matches(resolved.scope) || resolved.session_id !== request.session_id) throw new Error('The close request does not match the test session.');
    persist({...record, resolution: resolved});
    await submitReviewed();
  };
  return <section aria-label="Runtime operations" className="space-y-3 border-t pt-3">
    <h4 className="font-semibold">{connectionTest ? 'Test connection' : 'Runtime operations'}</h4>
    {connectionTest && <p>A short message opens a separate test session using the saved settings and account. Provider usage may apply.</p>}
    {(testPassed || saved?.connectionVerified) && <div role="status" className="rounded-lg border border-green-500 p-3 text-green-700 dark:text-green-300"><strong>Connection verified</strong><p>The harness started and returned the expected response.</p></div>}
    {connectionTest && saved?.submissionAttempted && !observed && !saved.connectionVerified && <p role="status">Testing connection…</p>}
    {connectionTest && saved?.submissionAttempted && saved.startedAt && now - saved.startedAt > 90000 && !observed && <p role="status">The test is still pending. Check Execution log and Approvals for this agent. This page keeps tracking the same request; it does not start another session.</p>}
    {connectionTest && observed && session && session.lifecycle_state !== 'CLOSED' && saved?.request.intent !== 'runtime.close' && <button className="btn btn-secondary" disabled={busy} onClick={() => void run(closeTest)}>Close test session</button>}
    {connectionTest && saved?.request.intent === 'runtime.close' && session?.lifecycle_state === 'CLOSED' && <p role="status">Test session closed.</p>}
    {connectionTest && !saved && <button className="btn btn-primary" disabled={busy || !storageKey || (intent === "runtime.start" && !canStart)} onClick={() => void run(async () => {await review(); await submitReviewed();})}>{busy ? 'Submitting…' : intent === "runtime.close" ? "Close test session" : "Test connection"}</button>}
    {connectionTest && !canStart && !saved && <p role="alert">Execution is not authorized or the installation is unavailable. Return to Authorization and refresh readiness.</p>}
    {!connectionTest && <p>Review an action, then submit it for this agent and connection. Execution requires the agent's current grant.</p>}
    {!connectionTest && !saved && <fieldset disabled={busy || !storageKey} className="space-y-2">
      <label className="block">Action <select aria-label="Runtime action" className={fieldClass} value={intent}
        onChange={event => setIntent(event.target.value as RuntimeIntent)}>
        {Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      {intent === "runtime.start" && <label className="block">Session selection <select aria-label="Session selection" className={fieldClass}
        value={selection} onChange={event => setSelection(event.target.value)}>
        <option value="automatic">Reuse if unambiguous; otherwise start</option><option value="new">Create a new session</option>
        <option value="existing">Reuse a specific session</option>
      </select></label>}
      {needsSession && <label className="block">Session ID <input aria-label="Runtime session ID" className={fieldClass} value={sessionId}
        maxLength={160} onChange={event => setSessionId(event.target.value)} /></label>}
      {(intent === "runtime.start" || needsText) && <label className="block">{intent === "runtime.start" ? "Initial message (optional)" : "Message"}
        <textarea aria-label="Runtime message" className={fieldClass} rows={3} value={text} maxLength={65536}
          onChange={event => setText(event.target.value)} /></label>}
      {targeted && <>
        <label className="block">Turn target <select aria-label="Turn target" className={fieldClass} value={targetKind}
          onChange={event => setTargetKind(event.target.value as typeof targetKind)}>
          <option value="native_turn_id">Specific native turn</option><option value="current_run">Current run at execution time</option>
        </select></label>
        {targetKind === "native_turn_id" && <label className="block">Native turn ID <input aria-label="Native turn ID" className={fieldClass}
          maxLength={160} value={turnId} onChange={event => setTurnId(event.target.value)} /></label>}
      </>}
      {!canStart && intent === "runtime.start" && <p>Starting is unavailable. Review installation readiness and execution authority above.</p>}
      <button className="btn btn-secondary" disabled={!canReview} onClick={() => void run(review)}>Review runtime action</button>
    </fieldset>}
    {saved && <details open={!connectionTest || undefined} className="space-y-2">
      <summary hidden={!connectionTest} className="cursor-pointer text-sm">Test details and recovery</summary>
      <p>{labels[saved.request.intent]}{saved.request.target && ` · ${saved.request.target.kind === "current_run" ? "Current run at execution time" : `Native turn ${saved.request.target.expected_turn_id}`}`}</p>
      {saved.request.text && <details><summary>Reviewed message</summary><pre className="whitespace-pre-wrap break-words">{saved.request.text}</pre></details>}
      {!resolution && <button className="btn btn-secondary" disabled={busy} onClick={() => void run(review)}>Retry the same review</button>}
      {resolution && <>
        <p>{resolution.reuse ? "Reuse existing session" : "Session"}: <span data-testid="runtime-operation-session">{resolution.session_id}</span></p>
        {!resolution.can_submit && <p role="alert">Cannot submit: {resolution.blockers.join(", ")}</p>}
        {expired && !saved.submissionAttempted && <p role="status">This review expired. Review a new request before submitting.</p>}
        {!operation && <button className="btn btn-primary" disabled={busy || !resolution.can_submit || (expired && !saved.submissionAttempted)}
          onClick={() => void run(async () => {
            const record = {...saved, submissionAttempted: true};
            persist(record);
            const result = await runtimeApi.submit(resolution);
            if (!matches(result.scope) || result.operation_id !== resolution.operation_id) throw new Error("The admitted operation does not match this selection.");
            if (mounted.current) { setOperation(result); setSessionId(resolution.session_id); }
          })}>{uncertain ? "Retry the same submission" : "Submit reviewed action"}</button>}
      </>}
      {uncertain && <p role="status">Submission is not confirmed. Check its result or retry the same request. Do not create a replacement action.</p>}
      <button className="btn btn-secondary" disabled={busy} onClick={() => void run(() => check(saved))}>Check action result</button>
      {operation && <div role="status" data-testid="runtime-operation-status">
        <p>Admission: {operation.admission_state}. Execution: {operation.executor_stage || "Awaiting executor"}.</p>
        {operation.possible_effect && <p>The action may have taken effect.</p>}
        {operation.executor_stage === "OUTCOME_UNKNOWN" && <p>The outcome is unknown. Reconcile the session before further work.</p>}
        {operation.error && <p>{operation.error.code}: {operation.error.message}</p>}
        {operation.follow_up_operation_ids.length > 0 && <p>Initial turn operations: {operation.follow_up_operation_ids.join(", ")}</p>}
        {followUps.map(child => <div key={child.operation_id}><p>Initial turn: {child.executor_stage || child.admission_state}.</p>
          {child.error && <p>{child.error.code}: {child.error.message}</p>}
          {child.result && <pre className="whitespace-pre-wrap break-words">{child.result.output_text}{child.result.output_truncated ? "\n[Output truncated]" : ""}</pre>}
        </div>)}
        {operation.result && <pre className="whitespace-pre-wrap break-words">{operation.result.output_text}{operation.result.output_truncated ? "\n[Output truncated]" : ""}</pre>}
      </div>}
      {session && <p>Session: {session.lifecycle_state}. Lease: {session.lease_state}.{session.durable_release_pending ? " Release confirmation pending." : ""}</p>}
      {!connectionTest && session && <RuntimeHistory key={JSON.stringify([session.scope.server_id, session.scope.executor_id, session.scope.session_id])} scope={session.scope} />}
      {canClear && (!connectionTest || !session || session.lifecycle_state === "CLOSED") && <button className="btn btn-secondary" disabled={busy} onClick={() => {
        sessionStorage.removeItem(storageKey); currentRecord.current = null; setSaved(null); setOperation(null); setFollowUps([]); setSession(null); setText(""); setError("");
        if (connectionTest) {setIntent(session && session.lifecycle_state !== "CLOSED" ? "runtime.close" : "runtime.start"); setText(testPrompt);} else if (sessionId) setIntent("turn.submit");
      }}>{connectionTest ? (session && session.lifecycle_state !== "CLOSED" ? "Prepare to close test session" : "Reset test") : saved.submissionAttempted ? "Prepare another action" : "Discard review"}</button>}
      <p className="text-xs">This tab retains the request and message for recovery. Refreshing only checks the recorded result.</p>
    </details>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
