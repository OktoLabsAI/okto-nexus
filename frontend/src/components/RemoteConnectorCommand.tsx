import { useState } from 'react';
import { Copy, Check } from 'lucide-react';

function remoteOrigin(value: string): string | null {
  try {
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.search || url.hash ||
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
  const command = origin ? `okto-nexus-connector connect --server=${quote(origin)} --agent=${quote(agentId)}` : '';
  return <section aria-label="Remote Connector setup" className="space-y-2 rounded-lg border border-surface-300 dark:border-surface-700 p-3">
    <h4 className="font-semibold">Remote Connector</h4>
    <p>Run the command on the remote computer, then enter this agent's API key at the hidden terminal prompt. The key is required; the agent name alone does not authorize a connection.</p>
    <label className="block">Nexus address reachable from the remote computer
      <input aria-label="Remote Nexus address" type="url" value={server} placeholder="http://192.168.1.10:8202"
        className="block w-full rounded border p-2 dark:bg-surface-800" onChange={event => {setServer(event.target.value); setCopied(false);}} />
    </label>
    {!origin && <p>Enter a reachable HTTP or HTTPS server address, including the scheme and port. Localhost refers to the remote computer itself.</p>}
    <label className="block">Terminal <select aria-label="Command terminal" value={shell} className="rounded border p-1 dark:bg-surface-800"
      onChange={event => {setShell(event.target.value); setCopied(false);}}><option value="powershell">PowerShell</option><option value="posix">Bash / zsh</option></select></label>
    {origin && <pre className="whitespace-pre-wrap break-all rounded bg-surface-100 dark:bg-surface-900 p-2" data-testid="connector-command">{command}</pre>}
    <button type="button" className="btn btn-secondary" disabled={!origin} onClick={async () => {
      setError('');
      try {await navigator.clipboard.writeText(command); setCopied(true);}
      catch {setError('Could not access the clipboard. Select and copy the command above.');}
    }}>{copied ? <Check size={14} /> : <Copy size={14} />} {copied ? 'Command copied' : 'Copy Connector command'}</button>
    {error && <p role="alert">{error}</p>}
  </section>;
}
