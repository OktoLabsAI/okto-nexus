import {useEffect, useRef, useState} from 'react';
import {Terminal} from '@xterm/xterm';
import {FitAddon} from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import {connectPiTerminal} from '../../piTerminalConnection';
import {piTerminalEdits, type PiEdit} from '../../piTerminalInput';
import {piPresentationApi, type InteractionScope} from '../../runtimeApi';
import {useAgentModalGuard} from '../AgentActionModal';

type TerminalView = 'connecting' | 'read' | 'write' | 'unavailable' | 'disconnected';

export function PiNativeTerminal({scope}: {scope: InteractionScope}) {
  const host = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<TerminalView>('connecting');
  const [status, setStatus] = useState('');
  const [uncertain, setUncertain] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [draftEdited, setDraftEdited] = useState(false);
  useAgentModalGuard(draftEdited);
  const receiptKey = `nexus:pi-pending:${JSON.stringify(scope)}`;
  const recover = useRef<() => void>(() => {});

  useEffect(() => {
    const controller = new AbortController();
    const terminal = new Terminal({disableStdin: true, screenReaderMode: true, cursorBlink: true, fontSize: 13,
      scrollback: 2000, theme: {background: '#101419', foreground: '#f2f4f5'}});
    const fit = new FitAddon();
    terminal.loadAddon(fit);
    terminal.open(host.current!);
    // The harness output may contain untrusted content. Suppress clipboard and clickable hyperlinks.
    terminal.parser.registerOscHandler(52, () => true);
    terminal.parser.registerOscHandler(8, () => true);
    const size = fit.proposeDimensions();
    terminal.resize(Math.min(300, Math.max(24, size?.cols ?? 80)), Math.min(120, Math.max(8, size?.rows ?? 24)));
    const edits: PiEdit[] = [];
    let pending: {request: number; key: string; intent: string} | null = null;
    let serial = 0, attached = false, proved = false;
    let connection: Awaited<ReturnType<typeof connectPiTerminal>> = null;
    let keepalive: number | undefined;
    let timeout: number | undefined;
    let unknown: string | null = null;
    let disposed = false;
    setDraftEdited(false);

    function disconnect() {
      attached = false;
      edits.length = 0;
      window.clearInterval(keepalive);
      window.clearTimeout(timeout);
      terminal.options.disableStdin = true;
      connection?.socket.close();
      if (controller.signal.aborted) return;
      setView('disconnected');
      setDraftEdited(false);
      if (pending?.key === 'enter') {
        setUncertain(true);
        setStatus('Message delivery is unconfirmed. Check delivery before sending again.');
      }
    }

    recover.current = () => {
      if (!unknown || pending && attached) return;
      const intent = unknown;
      void piPresentationApi.receipt(scope, intent, controller.signal).then(receipt => {
        if (controller.signal.aborted || unknown !== intent) return;
        if (receipt.session_owner_generation !== scope.session_owner_generation ||
            Object.entries(receipt.scope).some(([key, value]) => scope[key as keyof InteractionScope] !== value)) return;
        if (receipt.status === 'DELIVERY_UNKNOWN') {
          setStatus('Message delivery is still unconfirmed.');
          return;
        }
        sessionStorage.removeItem(receiptKey);
        unknown = null;
        setUncertain(false);
        terminal.options.disableStdin = !attached || connection?.access !== 'write';
        setStatus(receipt.status === 'QUEUED' ? 'Message queued for the next turn.' : `Message receipt recovered (${receipt.status.toLowerCase().replaceAll('_', ' ')}).`);
      }).catch(() => {
        if (!controller.signal.aborted) setStatus('Message delivery is still unconfirmed.');
      });
    };

    try {
      unknown = sessionStorage.getItem(receiptKey);
      setUncertain(Boolean(unknown));
      setStatus(unknown ? 'Check delivery of the previous message before sending again.' : '');
    } catch {
      setStatus('This browser cannot preserve a message receipt.');
    }

    function pump() {
      if (!attached || connection?.access !== 'write' || pending || unknown || !edits.length) return;
      const edit = edits.shift()!;
      const intent = crypto.randomUUID();
      if (edit.key === 'enter') {
        try {
          sessionStorage.setItem(receiptKey, intent);
        } catch {
          edits.length = 0;
          setStatus('This browser cannot preserve a message receipt. The message was not sent.');
          return;
        }
        unknown = intent;
      }
      pending = {request: ++serial, key: edit.key, intent};
      try {
        connection.socket.send(JSON.stringify({kind: 'key', request_id: serial, client_intent_id: intent,
          capability_revision: connection.inputRevision, ...edit}));
        timeout = window.setTimeout(disconnect, 10_000);
      } catch {
        disconnect();
      }
    }

    terminal.attachCustomKeyEventHandler(event => {
      if (event.key === 'Tab' || (event.key === 'Enter' && event.isComposing)) return false;
      if (event.type === 'keydown' && event.key === 'Enter' && event.shiftKey && !event.isComposing) {
        event.preventDefault();
        addEdits('\x1b[13;2u');
        return false;
      }
      return true;
    });
    function addEdits(data: string) {
      if (!attached || connection?.access !== 'write' || unknown && pending?.key !== 'enter') return;
      const batch = piTerminalEdits(data);
      if (!batch || edits.length + batch.length > 64) {
        setStatus('The terminal could not accept all of that input.');
        return;
      }
      if (batch.some(edit => edit.key === 'insert' || edit.key === 'newline')) setDraftEdited(true);
      edits.push(...batch);
      pump();
    }
    terminal.onData(addEdits);

    void connectPiTerminal(scope, terminal.cols, terminal.rows, controller.signal).then(link => {
      if (controller.signal.aborted) { link?.socket.close(); return; }
      if (!link) { setView('unavailable'); return; }
      connection = link;
      const {socket} = link;
      timeout = window.setTimeout(disconnect, 15_000);
      socket.onclose = disconnect;
      socket.onmessage = event => {
        if (controller.signal.aborted) return;
        if (event.data instanceof ArrayBuffer) {
          if (attached) terminal.write(new Uint8Array(event.data));
          return;
        }
        try {
          const frame = JSON.parse(event.data);
          if (frame.kind === 'challenge' && !proved && typeof frame.challenge === 'string') {
            proved = true;
            socket.send(JSON.stringify({kind: 'prove', challenge: frame.challenge}));
          } else if (frame.kind === 'attached' && proved && !attached && frame.attachment_id === link.attachmentId && frame.access === link.access) {
            attached = true;
            window.clearTimeout(timeout);
            terminal.options.disableStdin = link.access !== 'write' || Boolean(unknown);
            terminal.write('\x1b[?2004h');
            setView(link.access);
            if (link.keepalive) keepalive = window.setInterval(() => {
              if (socket.readyState === WebSocket.OPEN) socket.send('{"kind":"keepalive"}');
            }, 5000);
          } else if (attached && frame.kind === 'key' && pending && frame.request_id === pending.request &&
              frame.key && typeof frame.key.limit_reached === 'boolean') {
            window.clearTimeout(timeout);
            if (pending.key === 'enter') {
              sessionStorage.removeItem(receiptKey);
              unknown = null;
              setUncertain(false);
              if (!frame.key.limit_reached) {
                setDraftEdited(edits.some(edit => edit.key === 'insert' || edit.key === 'newline'));
              }
              if (frame.key.queued) setStatus('Message queued for the next turn.');
            }
            if (frame.key.limit_reached) setStatus('The draft reached the Pi editor limit.');
            pending = null;
            pump();
          } else disconnect();
        } catch {
          disconnect();
        }
      };
    }).catch(() => { if (!controller.signal.aborted) setView('unavailable'); });

    const cleanup = () => {
      if (disposed) return;
      disposed = true;
      controller.abort();
      disconnect();
      terminal.dispose();
    };
    const revoke = () => { cleanup(); setView('unavailable'); setStatus('Sign in to open the terminal.'); };
    window.addEventListener('nexus-auth-expired', revoke);
    window.addEventListener('nexus-operator-logout', revoke);
    return () => {
      cleanup();
      window.removeEventListener('nexus-auth-expired', revoke);
      window.removeEventListener('nexus-operator-logout', revoke);
    };
  }, [receiptKey, attempt]);

  return <div className="space-y-2">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="text-sm font-semibold">Pi terminal</h3>
      <span className="text-xs text-muted-foreground" role="status">{{connecting: 'Connecting…', read: 'Connected · View only',
        write: 'Connected', unavailable: 'Terminal unavailable', disconnected: 'Disconnected'}[view]}</span>
    </div>
    <div className="overflow-auto rounded-lg bg-[#101419] p-2" aria-label="Pi terminal" style={{height: 'clamp(14rem, 51vh, 38rem)'}}>
      <div className="h-full" ref={host}/>
    </div>
    {view === 'write' && !uncertain && <p className="text-xs text-muted-foreground">Enter sends a message. Shift+Enter adds a line.</p>}
    {status && <p className="text-sm" role="status">{status}</p>}
    {uncertain && <button type="button" onClick={() => recover.current()}>Check delivery</button>}
    {(view === 'disconnected' || view === 'unavailable') && <button type="button" onClick={() => {setView('connecting'); setAttempt(previous => previous + 1);}}>Reconnect terminal</button>}
  </div>;
}
