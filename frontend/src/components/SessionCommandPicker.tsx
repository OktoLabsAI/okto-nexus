import {useEffect, useRef, useState} from 'react';
import {runtimeApi, type InteractionScope, type SessionCommandCatalog, type SessionCommandStatus} from '../runtimeApi';
import {assertInteractionScope} from '../sessionConversation';

function sessionStatus(value: SessionCommandStatus) {
  switch (value.lifecycle_state) {
    case 'READY':
      return value.control_available ? 'The session is available.' : 'The session is open. Controls are unavailable.';
    case 'OPEN_PENDING':
      return 'The session is opening.';
    case 'CLOSED':
      return 'The session has closed.';
    case 'FAILED':
      return 'The session encountered an error.';
    default:
      return 'The current session status is unavailable.';
  }
}

export function SessionCommandPicker({scope, draft, locked, canSend, canSteer, canInterrupt,
  onSelect, onSend, onSteer, onInterrupt, onAccessLost}: {
  scope: InteractionScope;
  draft: string;
  locked: boolean;
  canSend: boolean;
  canSteer: boolean;
  canInterrupt: boolean;
  onSelect: (id: string, needsMessage: boolean) => void;
  onSend: (message: string, revision: string) => void;
  onSteer: (message: string, revision: string, trigger: HTMLButtonElement) => void;
  onInterrupt: (revision: string) => void;
  onAccessLost: () => void;
}) {
  const [catalog, setCatalog] = useState<SessionCommandCatalog | null>(null);
  const [refresh, refreshCatalog] = useState(0);
  const [showAll, setShowAll] = useState(false);
  const [notice, setNotice] = useState('');
  const text = draft.trimStart();
  const match = /^\/([^\s]*)(?:\s+([\s\S]*))?$/.exec(text);
  const query = match?.[1].toLowerCase() ?? '';
  const message = match?.[2] ?? '';
  const selected = catalog?.items.find(item => item.command_id === query);
  const showList = showAll || query === '' || !selected;
  const statusRequest = useRef<AbortController | null>(null);
  const [checkingStatus, setCheckingStatus] = useState(false);
  useEffect(() => () => statusRequest.current?.abort(), []);

  useEffect(() => {
    const controller = new AbortController();
    setCatalog(null);
    setNotice('');
    void runtimeApi.sessionCommands(scope, controller.signal).then(value => {
      if (controller.signal.aborted) return;
      assertInteractionScope({...value.scope, session_owner_generation: value.session_owner_generation}, scope);
      if (value.version !== 1 || !value.capability_revision || !Array.isArray(value.items)) {
        throw new Error('Unknown session command catalogue.');
      }
      setCatalog(value);
    }).catch(error => {
      if (controller.signal.aborted) return;
      if (error.status === 401) onAccessLost();
      else setNotice('Session commands are temporarily unavailable.');
    });
    return () => controller.abort();
  }, [refresh]);

  async function showStatus(revision: string) {
    if (statusRequest.current) return;
    const controller = new AbortController();
    statusRequest.current = controller;
    setCheckingStatus(true);
    setNotice('');
    try {
      const value = await runtimeApi.sessionCommandStatus(scope, revision, controller.signal);
      if (controller.signal.aborted) return;
      assertInteractionScope({...value.scope, session_owner_generation: value.session_owner_generation}, scope);
      setNotice(sessionStatus(value));
    } catch (error) {
      if (controller.signal.aborted) return;
      const status = (error as {status?: number})?.status;
      if (status === 401) onAccessLost();
      else setNotice(status === 409 ? 'Session commands changed. Refresh the list and review again.'
        : 'The session status could not be loaded.');
    } finally {
      if (!controller.signal.aborted) {
        statusRequest.current = null;
        setCheckingStatus(false);
      }
    }
  }

  const needsMessage = selected?.arguments.includes('message') ?? false;
  const invalidArgument = needsMessage
    ? !message.trim() || /^[\s]*[!/]/.test(message) || new TextEncoder().encode(message).length > 64 * 1024
    : !!message.trim();
  const label = selected?.handler === 'enqueue' ? 'Confirm send for next turn'
    : selected?.handler === 'review_steer' ? 'Review reorientation'
    : selected?.handler === 'review_interrupt' ? 'Review interruption'
    : selected?.handler === 'session_status' ? 'Show session status' : 'Show commands';
  const controlsAvailable = selected?.handler === 'enqueue' ? canSend
    : selected?.handler === 'review_steer' ? canSteer
    : selected?.handler === 'review_interrupt' ? canInterrupt : true;

  function run(trigger: HTMLButtonElement) {
    if (!catalog || selected?.state !== 'supported' || invalidArgument || locked || checkingStatus || !controlsAvailable) return;
    const revision = catalog.capability_revision;
    switch (selected.handler) {
      case 'catalog': setShowAll(true); break;
      case 'session_status': void showStatus(revision); break;
      case 'enqueue': onSend(message, revision); break;
      case 'review_steer': onSteer(message, revision, trigger); break;
      case 'review_interrupt': onInterrupt(revision); break;
    }
  }

  return <section aria-label="Session commands" className="space-y-2 rounded-md border p-2">
    {!catalog && !notice && <p role="status" className="text-sm">Loading session commands…</p>}
    {catalog && selected && <div className="space-y-1 text-sm">
      <p className="font-medium">{selected.label} · {selected.source === 'nexus' ? 'Nexus' : 'Native terminal'}</p>
      <p>{selected.effect}</p>
      {selected.state === 'native_only' && catalog.native_launch_version &&
        <p>Harness version at session start: {catalog.native_launch_version}</p>}
      {selected.reason && <p role="status">{selected.reason}</p>}
      {selected.state === 'supported' && <>
        {invalidArgument && <p>{needsMessage ? 'Add a plain message after the command.' : 'This command takes no arguments.'}</p>}
        <button type="button" className="btn btn-secondary" disabled={locked || invalidArgument || !controlsAvailable || checkingStatus}
          onClick={event => run(event.currentTarget)}>{label}</button>
      </>}
    </div>}
    {catalog && query && !selected && <p role="status" className="text-sm">
      This command is unavailable. Your draft is kept. Literal slash text is unavailable for this session.
    </p>}
    {showList && catalog && <ul className="max-h-52 space-y-1 overflow-auto text-sm">
      {catalog.items.filter(item => showAll || item.command_id.startsWith(query) ||
        item.label.toLowerCase().includes(query)).map(item =>
        <li key={item.command_id}>
          <button type="button" className="btn btn-secondary" disabled={locked || checkingStatus} onClick={() => {
            setShowAll(false);
            setNotice('');
            onSelect(item.command_id, item.arguments.includes('message'));
          }}>/{item.command_id} · {item.label}</button>
        </li>)}
    </ul>}
    {notice && <p role="status" className="text-sm">{notice}</p>}
    <button type="button" className="btn btn-secondary" disabled={locked || checkingStatus} onClick={() => {
      refreshCatalog(value => value + 1);
    }}>Refresh commands</button>
  </section>;
}
