import {useEffect, useRef, useState} from 'react';
import {Terminal} from '@xterm/xterm';
import {FitAddon} from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import {connectPiTerminal} from '../../piTerminalConnection';
import {piTerminalEdits, type PiEdit} from '../../piTerminalInput';
import {piPresentationApi, runtimeApi, type InteractionScope, type SessionInputReceipt} from '../../runtimeApi';
import {assertInteractionScope, receiptLabel} from '../../sessionConversation';
import {useAgentModalGuard} from '../AgentActionModal';

type TerminalView = 'connecting' | 'read' | 'write' | 'unavailable' | 'disconnected';
type Delivery = {intent: string; inputId: string};
const pendingDelivery = new Set<SessionInputReceipt['status']>(['QUEUED', 'DISPATCHING', 'PAUSED', 'DELIVERY_UNKNOWN']);

function deliveryMessage(status: SessionInputReceipt['status']) {
  if (status === 'QUEUED') return 'Message queued for the next turn.';
  if (status === 'ACCEPTED_NATIVE') return 'Message delivered to Pi.';
  return receiptLabel[status];
}

export function PiNativeTerminal({scope}: {scope: InteractionScope}) {
  const host = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<TerminalView>('connecting');
  const [status, setStatus] = useState('');
  const [delivery, setDelivery] = useState('');
  const [uncertain, setUncertain] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [draftEdited, setDraftEdited] = useState(false);
  const [confirmInterrupt, setConfirmInterrupt] = useState(false);
  useAgentModalGuard(draftEdited || confirmInterrupt);
  const receiptKey = `nexus:pi-pending:${JSON.stringify(scope)}`;
  const deliveryKey = `${receiptKey}:last-delivery`;
  const recover = useRef<() => void>(() => {});
  const decideInterrupt = useRef<(confirm: boolean) => void>(() => {});

  useEffect(() => {
    if (!draftEdited) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [draftEdited]);

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
    let deliveryTimer: number | undefined;
    let tracked: Delivery | null = null;
    let unknown: string | null = null;
    let interrupt: {id: string; intent: string} | null = null;
    let disposed = false;
    setDraftEdited(false);
    setConfirmInterrupt(false);
    setDelivery('');

    function disconnect() {
      attached = false;
      edits.length = 0;
      window.clearInterval(keepalive);
      window.clearTimeout(timeout);
      window.clearTimeout(deliveryTimer);
      terminal.options.disableStdin = true;
      connection?.socket.close();
      if (controller.signal.aborted) return;
      setView('disconnected');
      setDraftEdited(false);
      setConfirmInterrupt(false);
      if (pending?.key === 'enter') {
        setUncertain(true);
        setStatus('Message delivery is unconfirmed. Check delivery before sending again.');
      }
      if (pending?.key === 'interrupt_confirm') {
        setUncertain(true);
        setStatus('Interruption is unconfirmed. Check its status before trying again.');
      }
    }

    function watchDelivery(message: Delivery, initial?: SessionInputReceipt['status']) {
      tracked = message;
      window.clearTimeout(deliveryTimer);
      if (initial) setDelivery(deliveryMessage(initial));
      const poll = async () => {
        if (!attached || controller.signal.aborted || tracked !== message) return;
        let delay = 2000;
        try {
          const receipt = await piPresentationApi.receipt(scope, message.intent, controller.signal);
          if (!attached || controller.signal.aborted || tracked !== message) return;
          assertInteractionScope({...receipt.scope, session_owner_generation: receipt.session_owner_generation}, scope);
          if (receipt.input_id !== message.inputId) throw new Error('Message receipt changed.');
          setDelivery(deliveryMessage(receipt.status));
          if (!pendingDelivery.has(receipt.status)) return;
        } catch (error) {
          if (!attached || controller.signal.aborted || tracked !== message) return;
          setDelivery('Message status unavailable.');
          const status = (error as {status?: number}).status;
          if (status && status < 500) return;
          delay = 5000;
        }
        deliveryTimer = window.setTimeout(poll, delay);
      };
      void poll();
    }

    function rememberDelivery(message: Delivery, current?: SessionInputReceipt['status']) {
      try { sessionStorage.setItem(deliveryKey, JSON.stringify(message)); } catch { /* Acknowledgement remains visible here. */ }
      watchDelivery(message, current);
    }

    recover.current = () => {
      if (!unknown || pending && attached) return;
      const intent = unknown;
      if (intent.startsWith('interrupt:')) {
        void piPresentationApi.interruptReceipt(scope, intent.slice(10), controller.signal).then(receipt => {
          if (controller.signal.aborted || unknown !== intent ||
              Object.entries(receipt.scope).some(([key, value]) => scope[key as keyof InteractionScope] !== value)) return;
          const outcome = receipt.interrupt.target_status;
          if (outcome !== 'interrupted' && outcome !== 'finished') {
            setStatus('Interruption is still unconfirmed.');
            return;
          }
          clearReceipt();
          setStatus(outcome === 'interrupted' ? 'Work interrupted. The message queue is paused.' : 'The turn had already finished.');
        }).catch(() => { if (!controller.signal.aborted) setStatus('Interruption is still unconfirmed.'); });
        return;
      }
      void piPresentationApi.receipt(scope, intent, controller.signal).then(receipt => {
        if (controller.signal.aborted || unknown !== intent) return;
        if (receipt.session_owner_generation !== scope.session_owner_generation ||
            Object.entries(receipt.scope).some(([key, value]) => scope[key as keyof InteractionScope] !== value)) return;
        if (receipt.status === 'DELIVERY_UNKNOWN') {
          setStatus('Message delivery is still unconfirmed.');
          return;
        }
        clearReceipt();
        setStatus('');
        rememberDelivery({intent, inputId: receipt.input_id}, receipt.status);
      }).catch(() => {
        if (!controller.signal.aborted) setStatus('Message delivery is still unconfirmed.');
      });
    };

    try {
      unknown = sessionStorage.getItem(receiptKey);
      const last = JSON.parse(sessionStorage.getItem(deliveryKey) ?? 'null');
      if (last && typeof last.intent === 'string' && typeof last.inputId === 'string') tracked = last;
      setUncertain(Boolean(unknown));
      setStatus(unknown?.startsWith('interrupt:') ? 'Check whether the previous interruption took effect.' :
        unknown ? 'Check delivery of the previous message before sending again.' : '');
    } catch {
      setStatus('This browser cannot preserve a message receipt.');
    }

    function clearReceipt() {
      sessionStorage.removeItem(receiptKey);
      unknown = null;
      setUncertain(false);
      terminal.options.disableStdin = !attached || connection?.access !== 'write';
    }

    decideInterrupt.current = confirm => {
      if (!attached || !connection || !interrupt || pending) return;
      const {id, intent} = interrupt;
      if (confirm) {
        try { sessionStorage.setItem(receiptKey, `interrupt:${intent}`); }
        catch { setStatus('This browser cannot preserve an interruption receipt.'); return; }
        unknown = `interrupt:${intent}`;
      }
      interrupt = null;
      setConfirmInterrupt(false);
      const key = confirm ? 'interrupt_confirm' : 'interrupt_cancel';
      pending = {request: ++serial, key, intent};
      try {
        connection.socket.send(JSON.stringify({kind:key,request_id:serial,review_id:id}));
        timeout = window.setTimeout(disconnect, 10_000);
      } catch { disconnect(); }
    };

    function pump() {
      if (!attached || connection?.access !== 'write' || pending || unknown || interrupt || !edits.length) return;
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
      if (interrupt) {
        const key=event.key.toLowerCase();
        if (event.type==='keydown' && event.ctrlKey && (key==='y'||key==='n')) {
          event.preventDefault();
          decideInterrupt.current(key==='y');
        }
        return false;
      }
      if (event.type === 'keydown' && event.key === 'Enter' && event.shiftKey && !event.isComposing) {
        event.preventDefault();
        addEdits('\x1b[13;2u');
        return false;
      }
      return true;
    });
    function addEdits(data: string) {
      if (!attached || connection?.access !== 'write' || interrupt || unknown && pending?.key !== 'enter') return;
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
            if (!terminal.options.disableStdin) terminal.focus();
            if (tracked) watchDelivery(tracked);
            if (link.keepalive) keepalive = window.setInterval(() => {
              if (socket.readyState === WebSocket.OPEN) socket.send('{"kind":"keepalive"}');
            }, 5000);
          } else if (attached && frame.kind === 'key' && pending && frame.request_id === pending.request &&
              frame.key && typeof frame.key.limit_reached === 'boolean') {
            window.clearTimeout(timeout);
            if (pending.key === 'enter') {
              clearReceipt();
              if (!frame.key.limit_reached) {
                setDraftEdited(edits.some(edit => edit.key === 'insert' || edit.key === 'newline'));
              }
              if (frame.key.queued && typeof frame.key.queued.input_id === 'string') {
                setStatus('');
                rememberDelivery({intent: pending.intent, inputId: frame.key.queued.input_id}, frame.key.queued.status);
              }
              const command = frame.key.command;
              if (command?.name === 'help') setStatus('/status shows this session. /interrupt stops the current turn after confirmation.');
              if (command?.name === 'unavailable') setStatus('Command unavailable. Type /help for available commands.');
              if (command?.name === 'status') {
                void runtimeApi.sessionInteraction(scope,controller.signal).then(current=>{
                  if(controller.signal.aborted||Object.entries(current.scope).some(([key,value])=>scope[key as keyof InteractionScope]!==value))return;
                  const turn=current.next_turn.turn_state;
                  setStatus(turn==='busy'?'Working':turn==='idle'?'Ready for a message':'Current activity is unavailable.');
                }).catch(()=>{if(!controller.signal.aborted)setStatus('Current activity is unavailable.');});
              }
              if (command?.name === 'interrupt') {
                if (command.status === 'reviewed' && typeof command.review_id === 'string') {
                  interrupt = {id:command.review_id,intent:pending.intent};
                  edits.length = 0;
                  setDraftEdited(false);
                  setConfirmInterrupt(true);
                  setStatus('Interrupt the current turn? Ctrl+Y confirms. Ctrl+N cancels.');
                } else setStatus('There is no interruptible turn in this session.');
              }
            }
            if (frame.key.limit_reached) setStatus('The draft reached the Pi editor limit.');
            pending = null;
            pump();
          } else if (attached && pending && frame.request_id === pending.request && frame.kind === pending.key &&
              (pending.key === 'interrupt_confirm' || pending.key === 'interrupt_cancel')) {
            window.clearTimeout(timeout);
            const result = frame[frame.kind]?.status;
            pending = null;
            if (result === 'recorded' && unknown) {
              terminal.options.disableStdin = true;
              setUncertain(true);
              setStatus('Interruption requested. Checking the current turn.');
              recover.current();
            } else {
              clearReceipt();
              setStatus(result==='cancelled'?'Work continues.':'The turn changed. Interruption was not sent.');
            }
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

  const terminalStatus = status || (!delivery || view !== 'write' ? {connecting:'Connecting…',read:'View only',
    write:'Enter to send · /help for commands',unavailable:'Console unavailable',disconnected:'Disconnected'}[view] : '');
  return <div className="harness-console flex h-full min-h-0 flex-col bg-[#101419] text-white">
    <div className="min-h-0 flex-1 overflow-auto px-3 py-2" aria-label="Pi terminal">
      <div className="h-full" ref={host} data-modal-passive/>
    </div>
    <footer className="flex min-h-10 shrink-0 flex-wrap items-center gap-3 border-t border-white/10 px-3 py-2 text-xs text-white/80">
      {!!terminalStatus&&<span role="status">{terminalStatus}</span>}
      {!!delivery&&<span role="status">{delivery}</span>}
      {confirmInterrupt&&<><button className="underline" type="button" onClick={()=>decideInterrupt.current(true)}>Interrupt turn</button>
        <button className="underline" type="button" onClick={()=>decideInterrupt.current(false)}>Keep running</button></>}
      {uncertain && <button className="underline" type="button" onClick={() => recover.current()}>Check status</button>}
      {(view === 'disconnected' || view === 'unavailable') && <button className="underline" type="button" onClick={() => {setView('connecting'); setAttempt(previous => previous + 1);}}>Reconnect</button>}
    </footer>
  </div>;
}
