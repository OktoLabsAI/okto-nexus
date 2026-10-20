import { createContext, useContext, useLayoutEffect, useRef } from 'react';

export type SettingsDraft = { dirty: boolean; valid: boolean; save: () => Promise<boolean> };
export const SettingsDrafts = createContext<((id: string, draft: SettingsDraft | null) => void) | null>(null);

// Components remain usable independently; Settings supplies the shared save owner.
export function useSettingsDraft(id: string, draft: SettingsDraft) {
  const register = useContext(SettingsDrafts);
  const latest = useRef(draft);
  latest.current = draft;
  useLayoutEffect(() => {
    register?.(id, {dirty: draft.dirty, valid: draft.valid, save: () => latest.current.save()});
    return () => register?.(id, null);
  }, [register, id, draft.dirty, draft.valid]);
  return !!register;
}
