import { useEffect, useRef, useState } from "react";
import { runtimeApi } from "../runtimeApi";

type RefreshState = "PENDING" | "REQUESTED" | "UPDATED" | "OFFLINE";
const messages: Record<RefreshState, string> = {
  PENDING: "Inventory refresh queued. Waiting for the host.",
  REQUESTED: "The host received the request. Waiting for a new inventory.",
  UPDATED: "The host published a new inventory. Review the current choices.",
  OFFLINE: "The host is offline. The refresh request will remain queued.",
};

export function InventoryRefresh({executorId, onUpdated, compact = false}: {executorId: string; onUpdated: () => void; compact?: boolean}) {
  const [storageKey, setStorageKey] = useState("");
  const [intent, setIntent] = useState("");
  const [state, setState] = useState<RefreshState | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [identityAttempt, setIdentityAttempt] = useState(0);
  const [sending, setSending] = useState(false);
  const updated = useRef(onUpdated);
  updated.current = onUpdated;

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const identity = await runtimeApi.me(controller.signal);
        if (controller.signal.aborted) return;
        const key = `okto-nexus:r4-refresh:${JSON.stringify([identity.server_id, identity.agent_id, executorId])}`;
        const saved = sessionStorage.getItem(key);
        if (saved !== null && (!/^ui_refresh_[0-9a-f]{32}$/.test(saved))) {
          throw new Error("The saved inventory request is invalid.");
        }
        setStorageKey(key);
        if (saved) setIntent(saved);
      } catch (failure) {
        if (!controller.signal.aborted) setError(String(failure));
      }
    })();
    return () => controller.abort();
  }, [executorId, identityAttempt]);

  useEffect(() => {
    if (!intent || !storageKey) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      setSending(true); setError("");
      try {
        const view = await runtimeApi.refreshInventory(executorId, intent, controller.signal);
        if (controller.signal.aborted) return;
        if (view.client_intent_id !== intent || view.executor_id !== executorId || !Object.prototype.hasOwnProperty.call(messages, view.state)) {
          throw new Error("The inventory refresh response does not match this request.");
        }
        setState(view.state);
        if (view.state === "UPDATED") {
          if (sessionStorage.getItem(storageKey) === intent) sessionStorage.removeItem(storageKey);
          setIntent("");
          updated.current();
        } else {
          timer = setTimeout(() => void poll(), 5000);
        }
      } catch (failure) {
        if (!controller.signal.aborted) setError(`${String(failure)} Retry to check the same request.`);
      } finally {
        if (!controller.signal.aborted) setSending(false);
      }
    };
    void poll();
    return () => { controller.abort(); if (timer !== undefined) clearTimeout(timer); };
  }, [executorId, intent, storageKey, attempt]);

  const request = () => {
    if (!storageKey) { setError(""); setIdentityAttempt(value => value + 1); return; }
    if (intent) { setAttempt(value => value + 1); return; }
    try {
      const saved = sessionStorage.getItem(storageKey);
      if (saved) {
        if (!/^ui_refresh_[0-9a-f]{32}$/.test(saved)) throw new Error("The saved inventory request is invalid.");
        setState(null); setIntent(saved); return;
      }
      const bytes = crypto.getRandomValues(new Uint8Array(16));
      const id = `ui_refresh_${Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("")}`;
      // Persist before POST so lost replies, navigation and reload reuse the ID.
      sessionStorage.setItem(storageKey, id);
      setState(null); setIntent(id);
    } catch (failure) { setError(String(failure)); }
  };
  return <div data-testid="inventory-refresh" className="space-y-1">
    <button className="btn btn-secondary" disabled={(!storageKey && !error) || sending || (!!intent && !error)} onClick={request}>
      {error ? "Retry inventory refresh" : compact ? "Refresh" : "Request host inventory refresh"}
    </button>
    {!compact && <p className="text-xs">Ask the host to discover installations again. This does not run a version probe or start a runtime.</p>}
    {sending && <p role="status">Checking the inventory refresh request…</p>}
    {state && <p role="status">{messages[state]}</p>}
    {error && <p role="alert">{error}</p>}
  </div>;
}
