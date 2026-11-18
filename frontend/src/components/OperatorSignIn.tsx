import {useEffect, useState} from 'react';
import {api} from '../api';

export function OperatorSignIn({configured, onUnlock, autoFocus = false}: {
  configured?: boolean;
  onUnlock?: () => void;
  autoFocus?: boolean;
}) {
  const [available, setAvailable] = useState(configured);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (configured !== undefined) {setAvailable(configured);return;}
    let mounted = true;
    void api.operatorStatus().then(status => {if (mounted) setAvailable(status.configured);})
      .catch(() => {if (mounted) setError('Operator access could not be checked.');});
    return () => {mounted = false;};
  }, [configured]);

  if (available !== true) return <p className="text-sm text-surface-500" role="status">
    {error || (available === undefined ? 'Checking operator access…' :
      'Configure operator access in System settings on the Nexus server to send session messages.')}
  </p>;
  return <form aria-label="Operator sign-in" className="space-y-2" onSubmit={async event => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      await api.operatorLogin(username.trim(), password);
      setPassword('');
      if (onUnlock) onUnlock();
      else window.dispatchEvent(new Event('nexus-operator-login'));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Sign-in could not be completed.');
    } finally {
      setBusy(false);
    }
  }}>
    <label className="block text-sm">Username<input autoFocus={autoFocus} autoComplete="username" required
      value={username} onChange={event => setUsername(event.target.value)}
      className="block w-full rounded-md border bg-transparent p-2"/></label>
    <label className="block text-sm">Password<input type="password" autoComplete="current-password" required
      value={password} onChange={event => setPassword(event.target.value)}
      className="block w-full rounded-md border bg-transparent p-2"/></label>
    {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
  </form>;
}
