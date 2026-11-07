import {useId, useRef, useState} from 'react';
import {buildParticipantGuide, participantOrigin, type CommandShell, type ParticipantClient} from '../participantGuide';

const input = 'block w-full rounded border border-surface-300 dark:border-surface-600 p-2 bg-white dark:bg-surface-800';
const code = 'whitespace-pre-wrap break-all rounded bg-surface-100 dark:bg-surface-900 p-3 text-xs';

export function ParticipantGuide({agentId, workspaceId = '', initialOrigin = typeof window === 'undefined' ? '' : window.location.origin}: {
  agentId?: string; workspaceId?: string; initialOrigin?: string;
}) {
  const prefix = useId();
  const [agent, setAgent] = useState(agentId || '');
  const [workspace, setWorkspace] = useState(workspaceId);
  const [origin, setOrigin] = useState(initialOrigin);
  const [profile, setProfile] = useState('participant');
  const [client, setClient] = useState<ParticipantClient>('claude');
  const [shell, setShell] = useState<CommandShell>(typeof navigator !== 'undefined' && navigator.userAgent.includes('Windows') ? 'powershell' : 'posix');
  const [notice, setNotice] = useState('');
  const generation = useRef(0);
  const changed = () => {generation.current += 1; setNotice('');};
  const address = participantOrigin(origin);
  const guide = buildParticipantGuide({origin,
    agentId: agentId || agent, workspaceId: workspace, profile, client, shell});
  const copy = async (command: string) => {
    const current = ++generation.current;
    setNotice('');
    try {
      await navigator.clipboard.writeText(command);
      if (current === generation.current) setNotice('Public command copied. Enter the key only at the hidden terminal prompt.');
    } catch {
      if (current === generation.current) setNotice('Clipboard unavailable. Select the public command and copy it manually.');
    }
  };
  return <section aria-labelledby={prefix + '-title'} className="space-y-4 text-sm" data-testid="participant-guide">
    <h2 id={prefix + '-title'} className="font-semibold">Use your existing MCP client</h2>
    <p>Add coordination to an existing agent and workspace. Missing identities require a separate explicit operator decision.</p>
    <p>Install Nexus with its <code>serve-lite</code> extra on the computer running the client, without starting a local Server. Run these commands in that computer's project folder.</p>
    <div className="grid gap-3 sm:grid-cols-2">
      <label>Existing agent ID<input className={input} value={agentId || agent} readOnly={agentId !== undefined}
        autoComplete="off" onChange={event => {setAgent(event.target.value); changed();}} /></label>
      <label>Existing workspace ID<input className={input} value={workspace} autoComplete="off"
        onChange={event => {setWorkspace(event.target.value); changed();}} /></label>
      <label>Local participant profile<input className={input} value={profile} maxLength={80} autoComplete="off"
        onChange={event => {setProfile(event.target.value); changed();}} /></label>
      <label>Client<select className={input} value={client} onChange={event => {setClient(event.target.value as ParticipantClient); changed();}}>
        <option value="claude">Claude Code</option><option value="codex">Codex</option><option value="generic">Other client — manual guidance</option>
      </select></label>
      <label>Server origin reachable from the client<input className={input} type="url" value={origin} autoComplete="off" spellCheck={false}
        onChange={event => {setOrigin(event.target.value); changed();}} /></label>
      <label>Terminal<select className={input} value={shell} onChange={event => {setShell(event.target.value as CommandShell); changed();}}>
        <option value="powershell">PowerShell</option><option value="posix">Bash / zsh</option>
      </select></label>
    </div>
    <p>Reuse the same local profile to resume this setup. These public commands guide the CLI review; copying them applies no changes.</p>
    {address?.loopback && <p role="note">Loopback refers to the client computer. If the Server runs elsewhere, enter its reachable HTTPS origin.{address.plaintext ? ' HTTP sends plaintext on this host.' : ''}</p>}
    <p>Init review and apply each request the existing key at a hidden CLI prompt. Transfer it through a protected channel; one-shot key delivery stays separate from these public commands.</p>
    {client === 'generic' && <p role="note">Generic returns reference-only manual guidance. It does not install or qualify an unknown client; use that client's supported configuration and credential delivery. Foreground launch is available only for Claude Code and Codex.</p>}
    {!guide.ok ? <p role="status">{guide.message}</p> : <ol className="space-y-4">
      {guide.steps.map(step => <li key={step.id} className="space-y-2" data-testid={'participant-step-' + step.id}>
        <h3 className="font-medium">{step.title}</h3><pre className={code}>{step.command}</pre>
        <button type="button" className="btn btn-secondary" aria-label={'Copy command: ' + step.title}
          onClick={() => void copy(step.command)}>Copy public command</button><p>{step.explanation}</p>
      </li>)}
    </ol>}
    {notice && <p role="status">{notice}</p>}
    <p>Configuration, credential delivery to a client, MCP negotiation and completed work are separate proofs. Verify trust and reload in the actual client; process exit does not prove participation or completed work.</p>
  </section>;
}
