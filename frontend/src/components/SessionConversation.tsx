import {useEffect, useId, useLayoutEffect, useRef, useState} from 'react';
import {runtimeApi, type InteractionScope, type SessionInputReceipt, type SessionInteraction} from '../runtimeApi';
import {applyConversationUpdates, assertConversationPage, assertInteractionScope, interactionKey,
  receiptLabel, type ConversationMessage} from '../sessionConversation';
import {OperatorSignIn} from './OperatorSignIn';

interface Draft {
  text: string;
  uncertain: string | null;
  latest: {intent: string; receipt: SessionInputReceipt} | null;
}

const emptyDraft: Draft = {text: '', uncertain: null, latest: null};
const drafts = new Map<string, Draft>();

export function clearConversationDrafts() {
  drafts.clear();
}

interface History {
  messages: Map<string, ConversationMessage>;
  epoch: string | null;
  after: number;
  ready: boolean;
  more: boolean;
  gap: boolean;
  incomplete: boolean;
}

function emptyHistory(epoch: string | null = null): History {
  return {messages: new Map(), epoch, after: 0, ready: false, more: false, gap: false, incomplete: false};
}

function errorStatus(error: unknown) {
  return (error as {status?: number})?.status;
}

export function SessionConversation({scope, active, onAccessLost}: {
  scope: InteractionScope;
  active: boolean;
  onAccessLost: () => void;
}) {
  const key = interactionKey(scope);
  const editorId = useId();
  const [draft, setDraft] = useState(() => drafts.get(key) ?? emptyDraft);
  const [history, setHistory] = useState<History>(() => emptyHistory());
  const [interaction, setInteraction] = useState<SessionInteraction | null>(null);
  const [reading, setReading] = useState('');
  const [messageError, setMessageError] = useState('');
  const [busy, setBusy] = useState(false);
  const [newMessages, setNewMessages] = useState(false);
  const view = useRef(history);
  const lastInteraction = useRef<SessionInteraction | null>(null);
  const polling = useRef<() => void>(() => {});
  const mutation = useRef<AbortController | null>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const revoke = useRef(onAccessLost);
  revoke.current = onAccessLost;

  function save(value: Draft) {
    drafts.set(key, value);
    setDraft(value);
  }

  function installReceipt(intent: string, receipt: SessionInputReceipt) {
    assertInteractionScope({...receipt.scope, session_owner_generation: receipt.session_owner_generation}, scope);
    const prior = drafts.get(key) ?? emptyDraft;
    if (prior.uncertain === intent) save({text: '', uncertain: null, latest: {intent, receipt}});
    else if (prior.latest?.intent === intent && receipt.input_revision >= prior.latest.receipt.input_revision &&
             receipt.input_id === prior.latest.receipt.input_id) save({...prior, latest: {intent, receipt}});
  }

  function loseAccess() {
    mutation.current?.abort();
    clearConversationDrafts();
    window.dispatchEvent(new Event('nexus-auth-expired'));
    revoke.current();
  }

  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    let inFlight = false;
    const signal = controller.signal;

    const poll = async (includeNext: boolean) => {
      if (inFlight || signal.aborted) return;
      inFlight = true;
      window.clearTimeout(timer);
      try {
        const next = await runtimeApi.sessionInteraction(scope, signal);
        if (signal.aborted) return;
        assertInteractionScope(next.scope, scope);
        if (lastInteraction.current?.next_turn.human_login_required === false && next.next_turn.human_login_required) {
          controller.abort();
          loseAccess();
          return;
        }
        lastInteraction.current = next;
        setInteraction(next);
        const current = view.current.epoch === next.stream_epoch ? view.current : emptyHistory(next.stream_epoch);
        if (includeNext || !current.ready || !current.more) {
          const page = await runtimeApi.sessionConversation(scope, current.after, current.epoch, signal);
          if (signal.aborted) return;
          assertConversationPage(page, scope, current.after, current.epoch);
          view.current = {messages: applyConversationUpdates(current.messages, page.updates), epoch: page.stream_epoch,
            after: page.next_after_sequence, ready: true, more: page.has_more, gap: page.gap_pending,
            incomplete: !page.history_complete};
          if (current.ready && !following.current && page.updates.length && !includeNext) setNewMessages(true);
          setHistory(view.current);
        }
        const latest = drafts.get(key)?.latest;
        if (latest && ['QUEUED', 'DISPATCHING', 'DELIVERY_UNKNOWN', 'PAUSED'].includes(latest.receipt.status) &&
            !next.next_turn.human_login_required && !mutation.current) {
          try {
            const receipt = await runtimeApi.sessionInputReceipt(scope, latest.intent, signal);
            if (!signal.aborted) installReceipt(latest.intent, receipt);
          } catch (error) {
            if (errorStatus(error) !== 404) throw error;
          }
        }
        if (!signal.aborted) setReading('');
      } catch (error) {
        if (signal.aborted) return;
        if (errorStatus(error) === 404) {
          controller.abort();
          mutation.current?.abort();
          setInteraction(null);
          view.current = emptyHistory();
          setHistory(view.current);
          setReading('The exact session is unavailable. Reopen its context.');
          return;
        }
        if ([401, 403].includes(errorStatus(error) ?? 0)) {
          controller.abort();
          loseAccess();
          return;
        }
        setInteraction(null);
        setReading('Conversation could not be refreshed. Try again.');
      } finally {
        inFlight = false;
        if (!signal.aborted && active) timer = window.setTimeout(() => void poll(false), 2000);
      }
    };
    polling.current = () => void poll(true);
    void poll(false);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
      mutation.current?.abort();
      mutation.current = null;
    };
  }, [key, active]);

  useLayoutEffect(() => {
    if (scroll.current && following.current) scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [history]);

  const capability = interaction?.next_turn;
  const canSend = active && !!capability?.supported && !capability.human_login_required;
  const firstCharacter = draft.text.trimStart()[0];
  const command = firstCharacter === '/' || firstCharacter === '!';
  const tooLong = new TextEncoder().encode(draft.text).length > 64 * 1024;

  async function send(recover: boolean) {
    if (mutation.current || recover && !draft.uncertain) return;
    if (!recover && (!canSend || !draft.text.trim() || draft.uncertain || command || tooLong)) return;
    const intent = recover ? draft.uncertain! : 'ui_' + crypto.randomUUID();
    const controller = new AbortController();
    mutation.current = controller;
    setBusy(true);
    setMessageError('');
    if (!recover) save({...draft, uncertain: intent});
    try {
      const receipt = recover
        ? await runtimeApi.sessionInputReceipt(scope, intent, controller.signal)
        : await runtimeApi.enqueueSessionInput(scope, intent, draft.text, capability!.capability_revision!, controller.signal);
      if (!controller.signal.aborted) installReceipt(intent, receipt);
    } catch (error) {
      if (controller.signal.aborted) return;
      const status = errorStatus(error);
      if (status === 401) {
        loseAccess();
      } else if (!recover && [400, 403, 409, 422, 429].includes(status ?? 0)) {
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

  return <section aria-label="Session conversation" className="space-y-3 min-w-0">
    <div ref={scroll} className="max-h-80 overflow-y-auto rounded-lg border p-3" tabIndex={0}
      role="region" aria-label="Conversation messages" data-modal-passive
      onScroll={event => {
        const el = event.currentTarget;
        following.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
        if (following.current) setNewMessages(false);
      }}>
      {history.messages.size ? <ol className="space-y-3 m-0">
        {[...history.messages].map(([id, item]) => <li key={id}
          className={item.role === 'user' ? 'rounded-md bg-surface-100 p-2 dark:bg-surface-800' : 'p-2'}>
          <strong className="text-xs">{item.role === 'user' ? 'User' : 'Assistant'}</strong>
          {item.text && <p className="whitespace-pre-wrap break-words text-sm">{item.text}</p>}
          {item.truncated && <p className="text-xs text-surface-500">Part of this message is unavailable.</p>}
        </li>)}
      </ol> : <p className="text-sm text-surface-500">{history.ready ? 'No conversation messages in this page.' : 'Loading conversation…'}</p>}
    </div>
    {history.gap && <p className="text-xs" role="status">Some messages are still being recovered.</p>}
    {history.incomplete && <p className="text-xs text-surface-500">Earlier native history may be unavailable.</p>}
    {history.more && <button className="btn btn-secondary" type="button" onClick={() => polling.current()}>Load more messages</button>}
    {newMessages && <button className="btn btn-secondary" type="button" onClick={() => {
      following.current = true;
      if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
      setNewMessages(false);
    }}>New messages</button>}
    {reading && <p className="text-sm" role="status">{reading} <button type="button" className="btn btn-secondary"
      onClick={() => polling.current()}>Retry</button></p>}
    {capability?.supported && capability.human_login_required && <OperatorSignIn />}
    {!canSend && capability && !capability.supported &&
      <p className="text-xs text-surface-500">Sending is unavailable for this session.</p>}
    {(canSend || !!draft.text || !!draft.uncertain) && <form className="space-y-2" onSubmit={event => {
      event.preventDefault();
      void send(false);
    }}>
      <label htmlFor={editorId} className="block text-sm font-medium">Message for this session</label>
      <textarea id={editorId} value={draft.text} rows={3} readOnly={!!draft.uncertain} data-modal-passive
        className="block w-full rounded-md border bg-transparent p-2 text-sm" aria-describedby={editorId + '-hint'}
        onChange={event => {save({...draft, text: event.target.value});setMessageError('');}}
        onKeyDown={event => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
            event.preventDefault();
            void send(false);
          }
        }}/>
      <p id={editorId + '-hint'} className="text-xs text-surface-500">Enter sends. Shift+Enter adds a line.</p>
      {command && <p role="status" className="text-xs">Commands are unavailable in this message input.</p>}
      {tooLong && <p role="status" className="text-xs">The message is longer than 64 KiB.</p>}
      <div className="flex flex-wrap gap-2">
        <button type="submit" className="btn btn-primary"
          disabled={!canSend || busy || !!draft.uncertain || !draft.text.trim() || command || tooLong}>Send for next turn</button>
        {draft.uncertain && <button type="button" disabled={busy} className="btn btn-secondary"
          onClick={() => void send(true)}>Check message receipt</button>}
      </div>
    </form>}
    {(draft.latest || draft.uncertain) && <p role="status" className="text-sm">
      {draft.uncertain ? (busy ? 'Checking message…' : 'Waiting for confirmation of this message.') :
        receiptLabel[draft.latest!.receipt.status]}</p>}
    {messageError && <p role="alert" className="text-sm">{messageError}</p>}
  </section>;
}
