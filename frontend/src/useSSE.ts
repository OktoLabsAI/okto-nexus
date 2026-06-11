// Live event feed over /api/v1/stream (FR6): EventSource with automatic
// reconnection resuming from the last seen event_id. EventSource cannot set
// headers, so the credential rides the query string (the middleware's first
// extraction slot). Consumers register a handler; the hook reports liveness.

import { useEffect, useRef, useState } from "react";
import { getApiKey, type NexusEvent } from "./api";

export type SSEStatus = "connecting" | "live" | "reconnecting" | "off";

export function useSSE(onEvent: (event: NexusEvent) => void): SSEStatus {
  const [status, setStatus] = useState<SSEStatus>("off");
  const lastIdRef = useRef<number>(0);
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    // No key is fine on a loopback-bound serve (same-machine trust); the
    // credential rides along only when the operator actually has one.
    const key = getApiKey();
    let source: EventSource | null = null;
    let retryTimer: number | undefined;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      setStatus((s) => (s === "live" ? "reconnecting" : "connecting"));
      const params = new URLSearchParams();
      if (key) params.set("api_key", key);
      if (lastIdRef.current > 0) {
        params.set("last_event_id", String(lastIdRef.current));
      }
      source = new EventSource(`/api/v1/stream?${params}`);
      source.addEventListener("nexus", (raw) => {
        const event = JSON.parse((raw as MessageEvent).data) as NexusEvent;
        lastIdRef.current = Math.max(lastIdRef.current, event.event_id);
        setStatus("live");
        handlerRef.current(event);
      });
      source.onopen = () => setStatus("live");
      source.onerror = () => {
        // Browser EventSource auto-retries, but it does NOT resend our
        // cursor param - rebuild the connection ourselves so resume is
        // exact (no loss, no duplication).
        source?.close();
        setStatus("reconnecting");
        retryTimer = window.setTimeout(connect, 1000);
      };
    };

    connect();
    return () => {
      disposed = true;
      window.clearTimeout(retryTimer);
      source?.close();
    };
  }, []);

  return status;
}
