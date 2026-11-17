import { useCallback, useEffect, useRef, useState } from 'react';
import { homeApi } from '../homeApi';
import { HomeController, homeContextKey, initialHomeState, type HomeContext, type HomeInvalidation, type HomeStreamStatus } from '../homeController';
import type { HomePageSection,HomeBoardColumn } from '../homeTypes';

export interface HomeOverviewOptions extends HomeContext {
  latestEvent?: HomeInvalidation | null; streamStatus?: HomeStreamStatus;
}
/** Receives invalidations from the shell; never opens a third EventSource. */
export function useHomeOverview(options: HomeOverviewOptions) {
  const [state, setState] = useState(initialHomeState);
  const controller = useRef<HomeController | null>(null);
  const current = useRef(options);
  current.current = options;
  useEffect(() => {
    let live = true;
    const reader = new HomeController({ api: homeApi, now: () => performance.now(),
      setTimeout: (callback, delay) => window.setTimeout(callback, delay),
      clearTimeout: handle => window.clearTimeout(handle as number),
      onChange: value => { if (live) setState(value); } });
    controller.current = reader;
    const configure = () => reader.configure({ ...current.current,
      origin: window.location.origin, visible: current.current.visible !== false && !document.hidden });
    configure();
    const clear = () => reader.clear();
    const wake = () => { configure(); if (!document.hidden) reader.refresh(); };
    document.addEventListener('visibilitychange', configure);
    window.addEventListener('focus', wake);
    window.addEventListener('nexus-auth-expired', clear);
    window.addEventListener('nexus-operator-logout', clear);
    return () => {
      live = false; reader.dispose();
      document.removeEventListener('visibilitychange', configure);
      window.removeEventListener('focus', wake);
      window.removeEventListener('nexus-auth-expired', clear);
      window.removeEventListener('nexus-operator-logout', clear);
      if (controller.current === reader) controller.current = null;
    };
  }, []);
  useEffect(() => {
    controller.current?.configure({ ...options, origin: window.location.origin,
      visible: options.visible !== false && !document.hidden });
  }, [options.workspace, options.identityKey, options.enabled, options.visible, options.agent_id, options.state,options.family,options.quick,options.harness,options.host,options.holdOrder,options.presentationVersion]);
  useEffect(() => { if (options.latestEvent) controller.current?.invalidate(options.latestEvent); }, [options.latestEvent]);
  useEffect(() => { controller.current?.onStreamStatus(options.streamStatus ?? 'off'); }, [options.streamStatus]);
  const refresh = useCallback(() => controller.current?.refresh(), []);
  const loadMore = useCallback((section: HomePageSection) => controller.current?.loadMore(section), []);
  const pause = useCallback((paused?: boolean) => controller.current?.pause(paused), []);
  const apply = useCallback(() => controller.current?.apply(), []);
  const clear = useCallback(() => controller.current?.clear(), []);
  const holdOrder=useCallback((holding:boolean)=>controller.current?.holdOrder(holding),[]);
  const loadEntries=useCallback(()=>controller.current?.loadEntries(),[]);
  const loadGroupChildren=useCallback((groupId:string)=>controller.current?.loadGroupChildren(groupId),[]);
  const loadEntrySessions=useCallback((groupId:string,entryId:string)=>controller.current?.loadEntrySessions(groupId,entryId),[]);
  const loadEntryAttention=useCallback((groupId:string,entryId:string)=>controller.current?.loadEntryAttention(groupId,entryId),[]);
  const loadEntryResults=useCallback((groupId:string,entryId:string)=>controller.current?.loadEntryResults(groupId,entryId),[]);
  const loadBoardColumn=useCallback((column:HomeBoardColumn)=>controller.current?.loadBoardColumn(column),[]);
  const loadHarnessChildren=useCallback((cardId:string|null)=>controller.current?.loadHarnessChildren(cardId),[]);
  const refreshHarnessChildren=useCallback((cardId:string|null)=>controller.current?.refreshHarnessChildren(cardId),[]);
  // Effects run after paint: never render a previous identity/workspace during
  // the intervening render before configure has cleared its controller cache.
  const expected = homeContextKey({ ...options, origin: typeof window === 'undefined' ? '' : window.location.origin });
  const visibleState = state.scopeKey === expected && options.enabled !== false && options.identityKey
    ? state : { ...initialHomeState(), status: options.enabled === false || !options.identityKey ? 'disabled' as const : 'loading' as const };
  return { state: visibleState, refresh, loadMore, pause, apply, clear,holdOrder,loadEntries,loadGroupChildren,loadEntrySessions,loadEntryAttention,loadEntryResults,loadBoardColumn,loadHarnessChildren,refreshHarnessChildren };
}
