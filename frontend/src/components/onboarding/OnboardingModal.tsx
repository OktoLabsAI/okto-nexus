import { useCallback, useEffect, useRef, useState } from 'react';
import { Moon, Sun, X } from 'lucide-react';
import { useTheme } from '../../hooks/useTheme';
import { runtimeApi, type ProjectPresetOverview } from '../../runtimeApi';
import { markCompleted } from './onboardingStorage';
import { ParticipantGuide } from '../ParticipantGuide';

const TITLE = 'onboarding-title';
const button = 'rounded-lg border border-surface-300 dark:border-surface-600 px-4 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500';
const command = 'block whitespace-pre-wrap break-all rounded-lg bg-surface-100 dark:bg-surface-900 p-3 font-mono text-sm';

export function OnboardingModal({onClose, onOpenAgents}: {onClose: () => void; onOpenAgents: () => void}) {
  const [intent, setIntent] = useState<'project' | 'existing'>('project');
  const [preset, setPreset] = useState<ProjectPresetOverview | null>(null);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const {theme, toggle} = useTheme();
  const panel = useRef<HTMLDivElement>(null);
  const first = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => {markCompleted();onClose();}, [onClose]);
  useEffect(() => {
    const previous = document.activeElement;
    first.current?.focus();
    return () => {if (previous instanceof HTMLElement && previous.isConnected) previous.focus();};
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setError('');setPreset(null);
    runtimeApi.projectPreset(controller.signal).then(value => {
      if (!controller.signal.aborted) setPreset(value);
    }).catch(() => {
      if (!controller.signal.aborted) setError('The current project recommendation could not be loaded. Retry or continue in the terminal to review it there.');
    });
    return () => controller.abort();
  }, [reload]);
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {event.preventDefault();close();return;}
      if (event.key !== 'Tab' || !panel.current) return;
      const controls = Array.from(panel.current.querySelectorAll<HTMLElement>(
        'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex="0"]'))
        .filter(element => element.getClientRects().length > 0);
      const beginning = controls[0], end = controls.at(-1);
      if (event.shiftKey && document.activeElement === beginning) {event.preventDefault();end?.focus();}
      else if (!event.shiftKey && document.activeElement === end) {event.preventDefault();beginning?.focus();}
    };
    document.addEventListener('keydown', keydown);
    return () => document.removeEventListener('keydown', keydown);
  }, [close]);
  const openAgents = () => {close();onOpenAgents();};
  return <div role="dialog" aria-modal="true" aria-labelledby={TITLE} data-testid="onboarding-modal"
    className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
    onMouseDown={event => {if (event.target === event.currentTarget) close();}}>
    <div ref={panel} className="flex flex-col w-full max-w-2xl max-h-[calc(100dvh-2rem)] rounded-2xl shadow-2xl border border-surface-200 dark:border-surface-700 bg-white dark:bg-[#0b1929] text-surface-900 dark:text-white">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-surface-200 dark:border-surface-700 p-5">
        <div><p className="text-xs uppercase tracking-widest text-surface-500">Okto Nexus</p><h1 id={TITLE} className="text-2xl font-display font-semibold">Start with your project</h1></div>
        <div className="flex gap-2">
          <button type="button" className={button} onClick={toggle} aria-label={'Switch to ' + (theme === 'dark' ? 'light' : 'dark') + ' theme'}>{theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}</button>
          <button type="button" className={button} onClick={close} aria-label="Close onboarding" data-testid="onboarding-close"><X size={16} /></button>
        </div>
      </header>
      <main className="min-h-0 overflow-y-auto p-5 space-y-5">
        <p className="text-sm text-surface-600 dark:text-surface-300">Connect, work, answer questions and return to your results from the terminal. The dashboard is optional and uses the same agents and connections.</p>
        <div role="group" aria-label="How would you like to connect?" className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <button ref={first} type="button" aria-pressed={intent === 'project'} className={button + (intent === 'project' ? ' border-accent-500 bg-accent-100 dark:bg-accent-900/40' : '')} onClick={() => setIntent('project')}>Work on a project</button>
          <button type="button" aria-pressed={intent === 'existing'} className={button + (intent === 'existing' ? ' border-accent-500 bg-accent-100 dark:bg-accent-900/40' : '')} onClick={() => setIntent('existing')}>Use my existing client</button>
        </div>
        {intent === 'project' ? <section aria-label="Project connection" className="space-y-4">
          <div><h2 className="font-semibold mb-2">Open a terminal in your project</h2><code className={command}>okto-nexus connect</code>
            <p className="text-sm mt-2 text-surface-600 dark:text-surface-300">On the Nexus host, this starts or reuses the service, recommends a supported harness and presents one review. A new agent is created only with operator authority. Complete provider login on the execution host first.</p></div>
          {error ? <div role="alert" className="space-y-2"><p>{error}</p><button className={button} onClick={() => setReload(value => value + 1)}>Retry recommendation</button></div> : !preset ? <p role="status">Loading the Server recommendation…</p> : <div className="rounded-xl border border-surface-200 dark:border-surface-700 p-4 space-y-2" data-testid="project-preset-overview">
            <h2 className="font-semibold">A useful starting configuration</h2>
            <p className="text-sm">{preset.identity.role} · {preset.origin.id}, revision {preset.origin.revision}</p>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <dt>Model and project instructions</dt><dd>Keep the harness configuration</dd>
              <dt>Conversation context</dt><dd>{preset.configuration.session_policy?.replaceAll('_', ' ') || 'Global setting'}</dd>
              <dt>Nexus tool approval</dt><dd>{preset.configuration.tool_access}</dd>
              <dt>Execution authorization</dt><dd>{preset.configuration.authorization.minutes} minutes / {preset.configuration.authorization.actions} actions</dd>
            </dl>
            <p className="text-sm text-surface-600 dark:text-surface-300">Visible collaborators, messages and workspace handoffs stay within the granted scope. Native questions and permissions remain subject to the authorized recipient.</p>
            <details className="text-sm"><summary className="cursor-pointer">Review the effects</summary><ul className="list-disc pl-5 space-y-2 mt-2">{preset.effects.map(effect => <li key={effect}>{effect}</li>)}</ul></details>
          </div>}
          <details className="text-sm"><summary className="cursor-pointer font-medium">The harness runs on another computer</summary>
            <p className="my-2">Run the Connector in that computer's project folder. Select the approved Server and use the agent's protected key input. Operator decisions stay in the operator's authenticated terminal.</p>
            <code className={command}>okto-nexus-connector connect --server SERVER_URL</code>
          </details>
          <div><h2 className="font-semibold mb-2">Start work when you are ready</h2><code className={command}>okto-nexus work</code>
            <p className="text-sm mt-2 text-surface-600 dark:text-surface-300">After local setup, use the same project terminal to request work, follow progress and answer authorized questions. Reopen it to find the same project. Closing this guide does not stop the service or submit work.</p></div>
        </section> : <section aria-label="Existing client connection" className="space-y-3">
          <ParticipantGuide />
        </section>}
        <aside className="border-t border-surface-200 dark:border-surface-700 pt-4 text-sm text-surface-600 dark:text-surface-300">
          <h2 className="font-semibold text-surface-900 dark:text-white mb-1">Already connected from the terminal?</h2>
          <p>Open Agents to inspect the same identity and saved Connections. Changing a display name or role keeps the agent ID and history. A running service, an authenticated client, a ready session and a completed result are different states.</p>
        </aside>
      </main>
      <footer className="flex shrink-0 flex-wrap justify-end gap-2 border-t border-surface-200 dark:border-surface-700 p-4">
        <button type="button" className={button} onClick={close}>Continue in terminal</button>
        <button type="button" className={button + ' bg-accent-600 text-white'} onClick={openAgents} data-testid="onboarding-cta">Open Agents</button>
      </footer>
    </div>
  </div>;
}
