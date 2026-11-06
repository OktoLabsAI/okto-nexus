import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { AttentionController, initialAttentionState, type AttentionContext } from '../attentionController';
import type { AttentionFilters, AttentionOccurrence } from '../attentionTypes';

/** Attention owns an invalidation-only channel; it never creates notifications. */
export function useAttention(options: AttentionContext) {
  const [state, setState] = useState(initialAttentionState);
  const [filters, setFilterState] = useState<AttentionFilters>({ state: 'active', seen: 'all' });
  const controller = useRef<AttentionController | null>(null);
  const optionsRef = useRef(options);
  const filtersRef = useRef(filters);
  optionsRef.current = options;
  filtersRef.current = filters;

  useEffect(() => {
    let live = true;
    const current = new AttentionController({
      api, now: () => performance.now(),
      setTimeout: (callback, milliseconds) => window.setTimeout(callback, milliseconds),
      clearTimeout: handle => window.clearTimeout(handle as number),
      onChange: (value, currentFilters) => {
        if (live) { setState(value); setFilterState(currentFilters); }
      },
      openStream: ({ workspace, cursor, onOpen, onError, onControl }) => {
        const params = new URLSearchParams({ view: 'attention' });
        if (workspace) params.set('workspace', workspace);
        if (cursor > 0) params.set('last_event_id', String(cursor));
        const source = new EventSource(`/api/v1/stream?${params}`, { withCredentials: true });
        source.onopen = onOpen;
        source.onerror = onError;
        for (const event of ['attention-reset', 'attention-invalidated']) {
          source.addEventListener(event, raw => {
            try { onControl(event, JSON.parse((raw as MessageEvent).data)); }
            catch { onError(); }
          });
        }
        return { close: () => source.close() };
      },
    });
    controller.current = current;
    current.setFilters(filtersRef.current);
    current.configure(optionsRef.current);
    const wake = () => { if (!document.hidden) current.wake(); };
    const clear = () => current.clear();
    window.addEventListener('focus', wake);
    document.addEventListener('visibilitychange', wake);
    window.addEventListener('nexus-auth-expired', clear);
    window.addEventListener('nexus-operator-logout', clear);
    return () => {
      live = false;
      window.removeEventListener('focus', wake);
      document.removeEventListener('visibilitychange', wake);
      window.removeEventListener('nexus-auth-expired', clear);
      window.removeEventListener('nexus-operator-logout', clear);
      current.dispose();
      if (controller.current === current) controller.current = null;
    };
  }, []);

  useEffect(() => { controller.current?.configure(options); }, [options.workspace, options.visible, options.enabled]);
  const setFilters = useCallback((value: AttentionFilters) => controller.current?.setFilters(value), []);
  const refresh = useCallback(() => controller.current?.refresh(), []);
  const loadMore = useCallback(() => controller.current?.loadMore(), []);
  const markSeen = useCallback((item: AttentionOccurrence, seen: boolean) => controller.current?.markSeen(item, seen) ?? Promise.resolve(), []);
  const snooze = useCallback((item: AttentionOccurrence, until: string | null) => controller.current?.snooze(item, until) ?? Promise.resolve(), []);
  const clear = useCallback(() => controller.current?.clear(), []);
  return { state, filters, setFilters, refresh, loadMore, markSeen, snooze, clear };
}
