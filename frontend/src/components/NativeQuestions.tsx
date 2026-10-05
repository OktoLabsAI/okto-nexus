import { useEffect, useState } from "react";
import { type ApprovalDetail } from "../api";
import { runtimeApi } from "../runtimeApi";
import { CanonicalNativeDecision } from "./CanonicalNativeDecision";

export function NativeQuestions({workspace, agent}: {workspace: string; agent: string}) {
  const [items, setItems] = useState<ApprovalDetail[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let pending = false;
    setItems([]);
    const refresh = async () => {
      if (pending) return;
      pending = true;
      try {
        const result = await runtimeApi.nativeInputs(workspace, controller.signal);
        if (!controller.signal.aborted) { setItems(result.items); setError(""); }
      } catch (failure) {
        if (!controller.signal.aborted) setError(String(failure));
      } finally { pending = false; }
    };
    void refresh();
    const timer = window.setInterval(refresh, 2500);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [workspace]);
  const visible = items.filter(item => !agent || item.agent_id === agent);
  if (!visible.length && !error) return null;
  return <section aria-label="Questions addressed to you" className="mb-6 space-y-4">
    {visible.map(detail => <article key={detail.approval_id}
      className="rounded-xl border border-accent-300 bg-white p-4 dark:border-accent-700 dark:bg-surface-900">
      <h3 className="mb-3 font-semibold">{detail.agent_id} has a question for you</h3>
      <CanonicalNativeDecision detail={detail} onChanged={() => {}} />
    </article>)}
    {error && <p role="alert">Could not load runtime questions: {error}</p>}
  </section>;
}
