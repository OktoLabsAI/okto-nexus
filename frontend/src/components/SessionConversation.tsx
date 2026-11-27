import {useEffect, useId, useLayoutEffect, useRef, useState} from 'react';
import {presenterReceipts, runtimeApi, type InteractionScope, type SessionConversationPosition, type SessionInputReceipt,
  type SessionInteraction} from '../runtimeApi';
import {applyConversationUpdates, assertConversationPage, assertConversationPosition, assertInteractionScope, clearInputIntents,
  inputIntentStorageKey, interactionKey, liveTurnAnnouncement, readInputIntent, receiptLabel, type ConversationMessage} from '../sessionConversation';
import {OperatorSignIn} from './OperatorSignIn';
import {useAgentModalGuard} from './AgentActionModal';
import {SessionCommandPicker} from './SessionCommandPicker';
import {SessionInputQueue} from './SessionInputQueue';
import {SessionInterruptControl} from './SessionInterruptControl';
import {SessionSteerControl} from './SessionSteerControl';
import {clearInterruptIntents} from '../sessionInterrupt';
import {claudeSteerLabel, clearSteerReferences, readSteerReference, steerBoundaryLabel, steerStorageKey,
  type SteerReference, type SteerSource} from '../sessionSteer';

interface Draft {
  text: string;
  uncertain: string | null;
  latest: {intent: string; receipt: SessionInputReceipt} | null;
}

const emptyDraft: Draft = {text: '', uncertain: null, latest: null};
const drafts = new Map<string, Draft>();
const formerPiIntentPrefix = 'nexus:pi-pending:';

export function clearConversationDrafts() {
  drafts.clear();
  if (typeof window !== 'undefined') {
    try {
      clearInputIntents(window.sessionStorage);
      clearInterruptIntents(window.sessionStorage);
      clearSteerReferences(window.sessionStorage);
      for (let i = sessionStorage.length - 1; i >= 0; i--) {
        const key = sessionStorage.key(i);
        if (key?.startsWith(formerPiIntentPrefix)) sessionStorage.removeItem(key);
      }
    } catch {
      // Browser storage may be disabled. Revocation still clears in-memory state.
    }
  }
}

interface History {
  messages: Map<string, ConversationMessage>;
  epoch: string | null;
  after: number;
  ready: boolean;
  more: boolean;
  gap: boolean;
  missingHistory: boolean;
  incomplete: boolean;
  announceAfter: number;
  committed: number;
}

function emptyHistory(epoch: string | null = null): History {
  return {messages: new Map(), epoch, after: 0, ready: false, more: false, gap: false,
    missingHistory: false, incomplete: false, announceAfter: 0, committed: 0};
}

function errorStatus(error: unknown) {
  return (error as {status?: number})?.status;
}

function ConsoleDraftGuard({dirty, busy}: {dirty: boolean; busy: boolean}) {
  useAgentModalGuard(dirty, busy);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {event.preventDefault(); event.returnValue = '';};
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  return null;
}

export function SessionConversation({scope, active, visible, composerOnly=false, guardDraft=false, onAccessLost}: {
  scope: InteractionScope;
  active: boolean;
  visible: boolean;
  composerOnly?: boolean;
  guardDraft?: boolean;
  onAccessLost: () => void;
}) {
  const key = interactionKey(scope);
  const intentKey = inputIntentStorageKey(scope);
  const lastReceiptKey = `${intentKey}:latest`;
  const formerPiKey = formerPiIntentPrefix + JSON.stringify(scope);
  const editorId = useId();
  const [draft, setDraft] = useState(currentDraft);
  const [formerPiIntent, setFormerPiIntent] = useState<string | null>(() => {
    if (!composerOnly || typeof window === 'undefined') return null;
    try { return sessionStorage.getItem(formerPiKey); } catch { return null; }
  });
  const [formerPiNotice, setFormerPiNotice] = useState('');
  const [history, setHistory] = useState<History>(() => emptyHistory());
  const [interaction, setInteraction] = useState<SessionInteraction | null>(null);
  const [reading, setReading] = useState('');
  const [messageError, setMessageError] = useState('');
  const [busy, setBusy] = useState(false);
  const [newMessages, setNewMessages] = useState(false);
  const [pagedUpdates, setPagedUpdates] = useState(false);
  const [turnAnnouncement, setTurnAnnouncement] = useState<ReturnType<typeof liveTurnAnnouncement>>(null);
  const [queueRefresh, setQueueRefresh] = useState(0);
  const [steerSource, setSteerSource] = useState<SteerSource | null>(null);
  const [interruptCommand, setInterruptCommand] = useState<{revision: string} | null>(null);
  const [steerPending, setSteerPending] = useState<SteerReference | null>(() =>
    typeof window === 'undefined' ? null : readSteerReference(window.sessionStorage, steerStorageKey(scope)));
  const steerTrigger = useRef<HTMLButtonElement | null>(null);
  const editorCommand = useRef<HTMLButtonElement>(null);
  const editorCompletion = useRef<HTMLButtonElement>(null);
  const editor = useRef<HTMLTextAreaElement>(null);
  const view = useRef(history);
  const lastInteraction = useRef<SessionInteraction | null>(null);
  const polling = useRef<() => void>(() => {});
  const mutation = useRef<AbortController | null>(null);
  const recoverOnOpen = useRef(!!draft.uncertain);
  const scroll = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const readingOffset = useRef(0);
  const revoke = useRef(onAccessLost);
  revoke.current = onAccessLost;

  function currentDraft() {
    const inMemory = drafts.get(key);
    if (inMemory || typeof window === 'undefined') return inMemory ?? emptyDraft;
    try {
      const intent = readInputIntent(window.sessionStorage, intentKey);
      return intent ? {...emptyDraft, uncertain: intent} : emptyDraft;
    } catch {
      return emptyDraft;
    }
  }

  function clearReceiptReference(intent: string) {
    try {
      if (readInputIntent(window.sessionStorage, intentKey) === intent) window.sessionStorage.removeItem(intentKey);
    } catch {
      // The durable server-side receipt remains available if storage access changes.
    }
  }

  function save(value: Draft) {
    drafts.set(key, value);
    setDraft(value);
  }

  function installReceipt(intent: string, receipt: SessionInputReceipt) {
    assertInteractionScope({...receipt.scope, session_owner_generation: receipt.session_owner_generation}, scope);
    const prior = currentDraft();
    if (prior.uncertain === intent) {
      if (composerOnly) {
        try { sessionStorage.setItem(lastReceiptKey, intent); } catch { /* The durable receipt can still be read. */ }
      }
      clearReceiptReference(intent);
      save({text: '', uncertain: null, latest: {intent, receipt}});
    } else if (prior.latest?.intent === intent && receipt.input_revision >= prior.latest.receipt.input_revision &&
             receipt.input_id === prior.latest.receipt.input_id) save({...prior, latest: {intent, receipt}});
  }

  function loseAccess() {
    mutation.current?.abort();
    clearConversationDrafts();
    window.dispatchEvent(new Event('nexus-auth-expired'));
    revoke.current();
  }

  const showConversation = visible && !composerOnly;
  useEffect(() => {
    if (!showConversation) setTurnAnnouncement(null);
    setPagedUpdates(false);
    const controller = new AbortController();
    let timer: number | undefined;
    let inFlight = false;
    let requestedPage = false;
    let position: SessionConversationPosition | null = null;
    let stream: EventSource | null = null;
    const signal = controller.signal;

    function positionAdvanced(current: History) {
      return position !== null && (position.stream_epoch !== current.epoch ||
        position.committed_contiguous > current.after || position.gap_pending !== current.gap);
    }

    function updatePagedNotice(current: History) {
      const streamedThrough = position && position.stream_epoch === current.epoch ? position.committed_contiguous : 0;
      // The initial snapshot may already have unread history. Only signal
      // activity newer than that snapshot and the pages subsequently loaded.
      setPagedUpdates(active && current.more && !current.missingHistory &&
        Math.max(current.committed, streamedThrough) > current.announceAfter);
    }

    function schedule(delay: number) {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const includeNext = requestedPage;
        requestedPage = false;
        void poll(includeNext);
      }, delay);
    }

    function unavailable() {
      controller.abort();
      stream?.close();
      mutation.current?.abort();
      setInteraction(null);
      view.current = emptyHistory();
      setHistory(view.current);
      setTurnAnnouncement(null);
      setPagedUpdates(false);
      setReading('The exact session is unavailable. Reopen its context.');
    }

    const poll = async (includeNext: boolean) => {
      if (signal.aborted) return;
      if (inFlight) {
        requestedPage ||= includeNext;
        return;
      }
      inFlight = true;
      window.clearTimeout(timer);
      try {
        const next = await runtimeApi.sessionInteraction(scope, signal);
        if (signal.aborted) return;
        assertInteractionScope(next.scope, scope);
        if (lastInteraction.current?.next_turn.human_login_required === false && next.next_turn.human_login_required) {
          controller.abort();
          stream?.close();
          loseAccess();
          return;
        }
        lastInteraction.current = next;
        setInteraction(next);
        const current = view.current.epoch === next.stream_epoch ? view.current : emptyHistory(next.stream_epoch);
        if (showConversation && (includeNext || !current.ready ||
            (!current.more && !current.missingHistory && (!position || positionAdvanced(current))))) {
          const page = await runtimeApi.sessionConversation(scope, current.after, current.epoch, signal);
          if (signal.aborted) return;
          assertConversationPage(page, scope, current.after, current.epoch);
          setTurnAnnouncement(previous => current.ready
            ? liveTurnAnnouncement(page, current.announceAfter, previous?.text) ?? previous
            : null);
          view.current = {messages: page.updates.length ? applyConversationUpdates(current.messages, page.updates) : current.messages,
            epoch: page.stream_epoch,
            after: page.next_after_sequence, ready: true, more: page.has_more, gap: page.gap_pending,
            missingHistory: page.history_gap != null, incomplete: !page.history_complete,
            committed: Math.max(current.committed, page.committed_contiguous),
            announceAfter: current.ready ? Math.max(current.announceAfter, page.next_after_sequence) : page.committed_contiguous};
          if (current.ready && !following.current && page.updates.length && !includeNext) setNewMessages(true);
          setHistory(view.current);
          updatePagedNotice(view.current);
        }
        const draftBeforeRead = currentDraft();
        const latest = draftBeforeRead.latest;
        let intent: string | null = null;
        if (!next.next_turn.human_login_required && !mutation.current && !draftBeforeRead.uncertain) {
          if (latest && !latest.receipt.steer_submitted &&
              ['QUEUED', 'DISPATCHING', 'DELIVERY_UNKNOWN', 'PAUSED'].includes(latest.receipt.status)) intent = latest.intent;
          if (!latest && composerOnly) {
            try { intent = readInputIntent(sessionStorage, lastReceiptKey); } catch { /* Restore is optional. */ }
          }
        }
        if (intent) {
          try {
            const receipt = await runtimeApi.sessionInputReceipt(scope, intent, signal);
            if (!signal.aborted && latest) installReceipt(intent, receipt);
            if (!signal.aborted && !latest && !mutation.current) {
              assertInteractionScope({...receipt.scope, session_owner_generation: receipt.session_owner_generation}, scope);
              const currentDraftState = currentDraft();
              if (!currentDraftState.latest && !currentDraftState.uncertain) save({...currentDraftState, latest: {intent, receipt}});
            }
          } catch (error) {
            if (errorStatus(error) !== 404) throw error;
          }
        }
        if (!signal.aborted) setReading('');
      } catch (error) {
        if (signal.aborted) return;
        if (errorStatus(error) === 404) {
          unavailable();
          return;
        }
        if ([401, 403].includes(errorStatus(error) ?? 0)) {
          controller.abort();
          stream?.close();
          loseAccess();
          return;
        }
        setInteraction(null);
        setReading(composerOnly ? 'Session controls could not be refreshed.' : 'Conversation could not be refreshed. Try again.');
      } finally {
        inFlight = false;
        if (!signal.aborted && (active || requestedPage)) schedule(requestedPage ? 0 : 2000);
      }
    };

    if (active && showConversation && typeof EventSource === 'function') {
      stream = new EventSource(runtimeApi.sessionConversationStream(scope));
      stream.addEventListener('conversation-position', event => {
        if (signal.aborted) return;
        try {
          const next: SessionConversationPosition = JSON.parse((event as MessageEvent<string>).data);
          assertConversationPosition(next, scope);
          position = next;
        } catch {
          position = null;
          stream?.close();
          return;
        }
        updatePagedNotice(view.current);
        if (!inFlight && !view.current.more && positionAdvanced(view.current)) schedule(150);
      });
      stream.addEventListener('conversation-unavailable', event => {
        if (signal.aborted) return;
        position = null;
        stream?.close();
        try {
          const value = JSON.parse((event as MessageEvent<string>).data);
          if (value.version === 1 && value.reason === 'authorization_lost') {
            controller.abort();
            loseAccess();
            return;
          }
          if (value.version === 1 && value.reason === 'scope_changed') {
            unavailable();
            return;
          }
        } catch {
          // Resume bounded snapshot reads when the stream is unavailable.
        }
        if (!inFlight) schedule(0);
      });
      stream.onerror = () => {position = null;};
    }

    polling.current = () => void poll(true);
    void poll(false);
    return () => {
      controller.abort();
      stream?.close();
      window.clearTimeout(timer);
    };
  }, [key, active, showConversation, composerOnly]);

  useEffect(() => () => {
    mutation.current?.abort();
    mutation.current = null;
  }, [key]);

  useLayoutEffect(() => {
    if (visible && scroll.current) {
      scroll.current.scrollTop = following.current ? scroll.current.scrollHeight : readingOffset.current;
    }
  }, [history, visible]);

  const capability = interaction?.next_turn;
  const admissionsPaused = capability?.admissions_paused === true;
  const canSend = active && !formerPiIntent && !!capability?.supported && !capability.human_login_required && !admissionsPaused;
  const sendLabel = capability?.turn_state === 'busy' ? 'Add to next turn'
    : capability?.turn_state === 'idle' ? 'Send' : 'Send for next turn';
  const firstCharacter = draft.text.trimStart()[0];
  const command = firstCharacter === '/' || firstCharacter === '!';
  const slashCommand = firstCharacter === '/' && capability?.human_login_required === false;
  const tooLong = new TextEncoder().encode(draft.text).length > 64 * 1024;
  const steerAvailable = active && interaction?.steer_review_supported === true && !capability?.human_login_required;
  const canReviewSteer = steerAvailable && !steerSource && !steerPending && !draft.uncertain && !formerPiIntent && !busy;
  const canReviewDraftSteer = canReviewSteer && !admissionsPaused;
  const draftHeld = steerSource?.kind === 'draft' || steerPending?.kind === 'draft';
  const canReviewInterrupt = active && !formerPiIntent && interaction?.interrupt_review_supported === true;

  function reviewSteer(source: SteerSource, trigger: HTMLButtonElement) {
    if (!canReviewSteer || (source.kind === 'draft' && admissionsPaused) || mutation.current) return;
    steerTrigger.current = trigger;
    setSteerSource(source);
  }

  function closeSteerReview() {
    setSteerSource(null);
    window.requestAnimationFrame(() => {
      if (steerTrigger.current?.isConnected && !steerTrigger.current.disabled) steerTrigger.current.focus();
      else editor.current?.focus();
      steerTrigger.current = null;
    });
  }

  function completeSteer(reference: SteerReference, receipt: SessionInputReceipt) {
    const prior = drafts.get(key) ?? emptyDraft;
    if (composerOnly && reference.kind === 'queue' && prior.latest?.receipt.input_id === receipt.input_id) {
      try { sessionStorage.removeItem(lastReceiptKey); } catch { /* The queued receipt remains on the server. */ }
    }
    if (reference.kind === 'draft') save({...prior, text: '', latest: composerOnly ? prior.latest : null});
    else if (prior.latest?.receipt.input_id === receipt.input_id) save({...prior, latest: null});
  }

  async function send(recover: boolean, selected?: {message: string; revision: string; literal?: boolean}) {
    if (mutation.current || recover && (!draft.uncertain || capability?.human_login_required !== false)) return;
    if (!recover && (!canSend || draftHeld || draft.uncertain || (!selected && (!draft.text.trim() || command || tooLong)))) return;
    const intent = recover ? draft.uncertain! : 'ui_' + crypto.randomUUID();
    if (!recover) {
      try {
        window.sessionStorage.setItem(intentKey, intent);
      } catch {
        setMessageError('The receipt reference could not be saved. Your message is still a draft.');
        return;
      }
    }
    const controller = new AbortController();
    mutation.current = controller;
    setBusy(true);
    setMessageError('');
    if (!recover) save({...draft, uncertain: intent});
    try {
      const receipt = recover
        ? await runtimeApi.sessionInputReceipt(scope, intent, controller.signal)
        : await runtimeApi.enqueueSessionInput(scope, intent, selected?.message ?? draft.text,
          capability!.capability_revision!, controller.signal, selected?.revision, selected?.literal);
      if (!controller.signal.aborted) installReceipt(intent, receipt);
    } catch (error) {
      if (controller.signal.aborted) return;
      const status = errorStatus(error);
      if (status === 401) {
        loseAccess();
      } else if (!recover && [400, 403, 409, 422, 429].includes(status ?? 0)) {
        clearReceiptReference(intent);
        save({...draft, uncertain: null});
        setMessageError(error instanceof Error ? error.message : 'The message was refused.');
      } else {
        setMessageError(recover && status === 404
          ? 'The server has no receipt yet. Check again before sending anything else.'
          : 'Sending could not be confirmed. Check the receipt for this message.');
      }
    } finally {
      if (!controller.signal.aborted) {
        mutation.current = null;
        setBusy(false);
      }
    }
  }

  async function recoverFormerPiIntent() {
    if (!formerPiIntent || mutation.current || capability?.human_login_required !== false) return;
    const controller = new AbortController();
    mutation.current = controller;
    setBusy(true);
    setFormerPiNotice('');
    try {
      let status: string;
      if (formerPiIntent.startsWith('interrupt:')) {
        const receipt = await presenterReceipts.interruptReceipt(scope, formerPiIntent.slice(10), controller.signal);
        assertInteractionScope({...receipt.scope, session_owner_generation: receipt.scope.session_owner_generation ?? scope.session_owner_generation}, scope);
        const outcome = receipt.interrupt.target_status;
        if (outcome !== 'interrupted' && outcome !== 'finished') throw new Error('Interruption remains unconfirmed.');
        status = outcome === 'interrupted' ? 'Work interrupted. The message queue is paused.' : 'The turn had already finished.';
      } else {
        const receipt = await presenterReceipts.receipt(scope, formerPiIntent, controller.signal);
        assertInteractionScope({...receipt.scope, session_owner_generation: receipt.session_owner_generation}, scope);
        if (receipt.status === 'DELIVERY_UNKNOWN') throw new Error('Delivery remains unconfirmed.');
        status = receiptLabel[receipt.status];
      }
      if (!controller.signal.aborted) {
        sessionStorage.removeItem(formerPiKey);
        setFormerPiIntent(null);
        setFormerPiNotice(status);
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      if (errorStatus(error) === 401) loseAccess();
      else setFormerPiNotice('The previous action is still unconfirmed. Check its receipt again before sending.');
    } finally {
      if (!controller.signal.aborted) {
        mutation.current = null;
        setBusy(false);
      }
    }
  }

  useEffect(() => {
    if (!visible || !recoverOnOpen.current || capability?.human_login_required !== false) return;
    recoverOnOpen.current = false;
    void send(true);
  }, [capability?.human_login_required, visible]);

  const transcript = !composerOnly && <>
    <div ref={scroll} className="max-h-80 overflow-y-auto rounded-lg border p-3" tabIndex={0}
      role="region" aria-label="Conversation messages" data-modal-passive
      onScroll={event => {
        if (!visible) return;
        const el = event.currentTarget;
        readingOffset.current = el.scrollTop;
        following.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
        if (following.current) setNewMessages(false);
      }}>
      {history.messages.size ? <ol className="space-y-3 m-0">
        {[...history.messages].map(([id, item]) => <li key={id}
          className={item.role === 'user' ? 'rounded-md bg-surface-100 p-2 dark:bg-surface-800' : 'p-2'}>
          <strong className="text-xs">{item.incoming ? 'Incoming message' : item.role === 'user' ? 'User' : item.subagent ? 'Subagent' : 'Assistant'}</strong>
          {item.text && <p className="whitespace-pre-wrap break-words text-sm">{item.text}</p>}
          {item.truncated && <p className="text-xs text-surface-500">Part of this message is unavailable.</p>}
        </li>)}
      </ol> : !history.missingHistory &&
        <p className="text-sm text-surface-500">{history.ready ? 'No conversation messages in this page.' : 'Loading conversation…'}</p>}
    </div>
    {history.missingHistory ? <p className="text-xs" role="status">Part of this conversation history is unavailable.</p>
      : history.gap && <p className="text-xs" role="status">Some messages are still being recovered.</p>}
    {history.incomplete && !history.missingHistory &&
      <p className="text-xs text-surface-500">Earlier native history may be unavailable.</p>}
    <p className={pagedUpdates ? 'text-xs text-surface-500' : 'sr-only'} role="status">
      {pagedUpdates ? 'New activity is available.' : newMessages ? 'New messages available.' : ''}
    </p>
    {history.more && <button className="btn btn-secondary" type="button" onClick={() => polling.current()}>Load more messages</button>}
    <p className="sr-only" role="status" aria-atomic="true">
      {visible && turnAnnouncement && <span key={turnAnnouncement.sequence}>{turnAnnouncement.text}</span>}
    </p>
    {newMessages && <button className="btn btn-secondary" type="button" onClick={() => {
      following.current = true;
      if (scroll.current) {
        scroll.current.scrollTop = scroll.current.scrollHeight;
        scroll.current.focus({preventScroll: true});
      }
      setNewMessages(false);
    }}>New messages</button>}
  </>;

  const sendDraft = () => {
    if (composerOnly && slashCommand) editorCommand.current?.click();
    else void send(false);
  };
  const form = (composerOnly && active || canSend || !!draft.text || !!draft.uncertain) && <form className="space-y-2" onSubmit={event => {
      event.preventDefault();
      sendDraft();
    }}>
      <label htmlFor={editorId} className={composerOnly ? 'sr-only' : 'block text-sm font-medium'}>Message for this session</label>
      <textarea ref={editor} id={editorId} value={draft.text} rows={composerOnly ? 2 : 3}
        readOnly={!!draft.uncertain || draftHeld || !!formerPiIntent || composerOnly && (!active || capability?.human_login_required !== false)} data-modal-passive
        placeholder={composerOnly ? 'Write a message or type / for commands' : undefined}
        className={`block w-full rounded-md border bg-transparent p-2 text-sm ${composerOnly ? 'resize-none' : 'resize-y'}`} aria-describedby={editorId + '-hint'}
        onChange={event => {save({...draft, text: event.target.value});setMessageError('');setFormerPiNotice('');}}
        onKeyDown={event => {
          if (composerOnly && slashCommand && event.key === 'Tab' && !event.shiftKey &&
              editorCompletion.current && !editorCompletion.current.disabled) {
            event.preventDefault();
            editorCompletion.current.click();
          }
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
            event.preventDefault();
            sendDraft();
          }
        }}/>
      <p id={editorId + '-hint'} className="text-xs text-surface-500">Enter sends. Shift+Enter adds a line.</p>
      {command && !slashCommand && <p role="status" className="text-xs">
        {firstCharacter === '!' ? 'Shell commands are unavailable. Your draft is kept.' : 'Sign in to view session commands.'}
      </p>}
      {tooLong && !slashCommand && <p role="status" className="text-xs">The message is longer than 64 KiB.</p>}
      <div className="flex flex-wrap gap-2">
        <button type="submit" className="btn btn-primary"
          disabled={!canSend || busy || draftHeld || !!draft.uncertain || !draft.text.trim() || command || tooLong}>{sendLabel}</button>
        {steerAvailable && <button type="button" className="btn btn-secondary"
          disabled={!canReviewDraftSteer || !draft.text.trim() || command || tooLong}
          onClick={event => reviewSteer({kind: 'draft', text: draft.text}, event.currentTarget)}>Reorient current turn</button>}
        {draft.uncertain && <button type="button" disabled={busy || capability?.human_login_required !== false} className="btn btn-secondary"
          onClick={() => void send(true)}>Check message receipt</button>}
      </div>
    </form>;
  const feedback = <>
    {reading && <p className="text-sm" role="status">{reading} <button type="button" className="btn btn-secondary"
      onClick={() => polling.current()}>Retry</button></p>}
    {capability?.supported && capability.human_login_required && <OperatorSignIn />}
    {!canSend && capability && !capability.supported &&
      <p className="text-xs text-surface-500">Sending is unavailable for this session.</p>}
    {capability?.supported && admissionsPaused && <p className="text-xs text-surface-500" role="status">
      New session messages are paused. Accepted messages can still finish.
    </p>}
  </>;
  const controls = <>
    {formerPiIntent && <button type="button" className="btn btn-secondary" disabled={busy || capability?.human_login_required !== false}
      onClick={() => void recoverFormerPiIntent()}>Check previous console action</button>}
    {formerPiNotice && <p role="status" className="text-sm">{formerPiNotice}</p>}
    {slashCommand && <SessionCommandPicker scope={scope} draft={draft.text}
      consoleView={composerOnly} editorAction={composerOnly ? editorCommand : undefined}
      editorCompletion={composerOnly ? editorCompletion : undefined}
      locked={busy || !!draft.uncertain || !!formerPiIntent || draftHeld} canSend={canSend} canSteer={canReviewDraftSteer}
      canInterrupt={canReviewInterrupt} onSelect={(id, needsMessage) => {
        save({...draft, text: '/' + id + (needsMessage ? ' ' : '')});
        setMessageError('');
        editor.current?.focus();
      }} onSend={(message, revision) => void send(false, {message, revision})}
      onSendLiteral={revision => void send(false, {message: draft.text, revision, literal: true})}
      onSteer={(text, catalogRevision, trigger) => reviewSteer({kind: 'draft', text, catalogRevision}, trigger)}
      onInterrupt={revision => setInterruptCommand({revision})} onAccessLost={loseAccess}/>}
    {(draft.latest || draft.uncertain) && <p role="status" className="text-sm">
      {draft.uncertain ? (busy ? 'Checking message…' : 'Waiting for confirmation of this message.') :
        claudeSteerLabel(draft.latest!.receipt.steer_compound, draft.latest!.receipt.status === 'ACCEPTED_NATIVE') ??
          steerBoundaryLabel(draft.latest!.receipt.steer_boundary) ??
          (draft.latest!.receipt.steer_submitted ? 'Reorientation sent. Harness acceptance is unconfirmed.' :
            receiptLabel[draft.latest!.receipt.status])}</p>}
    {messageError && <p role="alert" className="text-sm">{messageError}</p>}
    {capability?.human_login_required === false && <>
      <SessionSteerControl scope={scope} available={steerAvailable} source={steerSource} pending={steerPending}
        draftRetained={!!draft.text}
        onCloseReview={closeSteerReview} onPending={setSteerPending} onSubmitted={completeSteer}
        onAccessLost={loseAccess} onQueueChanged={() => setQueueRefresh(value => value + 1)}/>
      {active && <SessionInputQueue scope={scope} onAccessLost={loseAccess} refreshKey={queueRefresh}
        pendingSteerInput={steerPending?.kind === 'queue' ? steerPending.inputId : null}
        onReviewPromotion={steerAvailable ? (inputId, trigger) => reviewSteer({kind: 'queue', inputId}, trigger) : undefined}
        canReviewPromotion={canReviewSteer}
        onCancelled={receipt => {
          const latest = drafts.get(key)?.latest;
          if (latest?.receipt.input_id === receipt.input_id) installReceipt(latest.intent, receipt);
        }}/>}
      <SessionInterruptControl scope={scope} canReview={canReviewInterrupt} commandReview={interruptCommand}
        onAccessLost={loseAccess} onQueueChanged={() => setQueueRefresh(value => value + 1)}/>
    </>}
  </>;
  return <section aria-label={composerOnly ? 'Session input' : 'Session conversation'}
    className={composerOnly ? 'shrink-0 space-y-2 border-t px-4 py-3' : 'space-y-3 min-w-0'}>
    {(composerOnly || guardDraft) && <ConsoleDraftGuard dirty={!!draft.text && !draft.uncertain} busy={busy}/>}
    {composerOnly ? <>
      <div className="max-h-[25dvh] space-y-2 overflow-y-auto overscroll-contain">{feedback}{controls}</div>
      {form}
    </> : <>{transcript}{feedback}{form}{controls}</>}
  </section>;
}
