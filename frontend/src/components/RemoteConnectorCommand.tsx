import { useState } from 'react';
import { Copy, Check } from 'lucide-react';

function remoteOrigin(value: string): string | null {
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash ||
        (url.pathname !== '/' && url.pathname !== '') ||
        ['localhost', '[::1]', '0.0.0.0'].includes(url.hostname) || /^127\./.test(url.hostname)) return null;
    return url.origin;
  } catch { return null; }
}

export function RemoteConnectorCommand({agentId}: {agentId: string}) {
  const [server, setServer] = useState(remoteOrigin(window.location.origin) || '');
  const [shell, setShell] = useState(navigator.userAgent.includes('Windows') ? 'powershell' : 'posix');
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');
  const origin = remoteOrigin(server.trim());
  const quote = (value: string) => shell === 'powershell'
    ? "'" + value.replace(/['\u2018\u2019\u201a\u201b]/g, character => character + character) + "'"
    : "'" + value.replace(/'/g, "'\"'\"'") + "'";
  const command = `okto-nexus-connector connect --server=${quote(origin || 'https://NEXUS_SERVER:8202')} --agent=${quote(agentId)}`;
  return <section aria-label="Remote Connector setup" className="space-y-2 rounded-lg border border-surface-300 dark:border-surface-700 p-3">
    <h4 className="font-semibold">Remote Connector</h4>
    <p>Run this command on the remote computer. The Connector asks for this agent's API key and guides runtime selection.</p>
    <label className="block">Nexus address reachable from the remote computer
      <input aria-label="Remote Nexus address" type="url" value={server} placeholder="https://nexus.example:8202"
        className="block w-full rounded border p-2 dark:bg-surface-800" onChange={event => {setServer(event.target.value); setCopied(false);}} />
    </label>
    {!origin && <p>Enter the Server's reachable HTTPS address. Localhost refers to the remote computer itself.</p>}
    <label className="block">Terminal <select aria-label="Command terminal" value={shell} className="rounded border p-1 dark:bg-surface-800"
      onChange={event => {setShell(event.target.value); setCopied(false);}}><option value="powershell">PowerShell</option><option value="posix">Bash / zsh</option></select></label>
    <pre className="whitespace-pre-wrap break-all rounded bg-surface-100 dark:bg-surface-900 p-2" data-testid="connector-command">{command}</pre>
    <button type="button" className="btn btn-secondary" disabled={!origin} onClick={async () => {
      setError('');
      try {await navigator.clipboard.writeText(command); setCopied(true);}
      catch {setError('Could not access the clipboard. Select and copy the command above.');}
    }}>{copied ? <Check size={14} /> : <Copy size={14} />} {copied ? 'Command copied' : 'Copy Connector command'}</button>
    {error && <p role="alert">{error}</p>}
  </section>;
}
