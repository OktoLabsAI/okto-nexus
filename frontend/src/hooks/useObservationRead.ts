import { useCallback, useEffect, useRef, useState } from 'react';
import { initialObservationRead, ObservationReader } from '../observationReader';

export function useObservationRead<Q, T>(query: Q | null, read: (query: Q, signal: AbortSignal) => Promise<T>, refreshAfter: (value: T) => number) {
  const [state, setState] = useState(initialObservationRead<T>);
  const refs = useRef({ query, read, refreshAfter });
  refs.current = { query, read, refreshAfter };
  const controller = useRef<ObservationReader<Q, T> | null>(null);
  const key = query === null ? null : JSON.stringify(query);
  useEffect(() => {
    const value = new ObservationReader<Q, T>({
      read: (query, signal) => refs.current.read(query, signal), refreshAfter: value => refs.current.refreshAfter(value),
      now: () => performance.now(), setTimeout: (callback, milliseconds) => window.setTimeout(callback, milliseconds),
      clearTimeout: handle => window.clearTimeout(handle as number), onChange: setState,
    });
    controller.current = value;
    value.configure(refs.current.query);
    const wake = () => { if (!document.hidden) value.refresh(); };
    const clear = () => value.clear();
    window.addEventListener('focus', wake);
    document.addEventListener('visibilitychange', wake);
    window.addEventListener('nexus-auth-expired', clear);
    window.addEventListener('nexus-operator-logout', clear);
    return () => {
      value.dispose(); controller.current = null;
      window.removeEventListener('focus', wake);
      document.removeEventListener('visibilitychange', wake);
      window.removeEventListener('nexus-auth-expired', clear);
      window.removeEventListener('nexus-operator-logout', clear);
    };
  }, []);
  useEffect(() => controller.current?.configure(refs.current.query), [key]);
  const refresh = useCallback(() => controller.current?.refresh(), []);
  // Render must not briefly reuse protected data while the scope effect catches up.
  return { state: state.key === key ? state : { ...initialObservationRead<T>(), key }, refresh };
}
