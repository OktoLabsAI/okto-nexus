import {useEffect, useRef, useState} from 'react';
import {runtimeApi, type InteractionScope, type SessionInputQueueItem, type SessionInputQueuePage, type SessionInputReceipt} from '../runtimeApi';
import {assertInteractionScope, receiptLabel} from '../sessionConversation';

function assertReceiptScope(receipt: SessionInputReceipt, scope: InteractionScope) {
  assertInteractionScope({...receipt.scope, session_owner_generation: receipt.session_owner_generation}, scope);
}

export function SessionInputQueue({scope, onAccessLost, onCancelled}: {
  scope: InteractionScope;
  onAccessLost: () => void;
  onCancelled: (receipt: SessionInputReceipt) => void;
}) {
  const [page, setPage] = useState<SessionInputQueuePage | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [confirmResume, setConfirmResume] = useState(false);
  const request = useRef<AbortController | null>(null);
  const summary = useRef<HTMLElement>(null);
  const keepPaused = useRef<HTMLButtonElement>(null);

  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => {
    if (confirmResume) keepPaused.current?.focus();
  }, [confirmResume]);

  async function readPage(cursor: string | null, signal: AbortSignal) {
    const result = await runtimeApi.sessionInputQueue(scope, cursor, signal);
    assertInteractionScope({...result.scope, session_owner_generation: result.session_owner_generation}, scope);
    let sequence = cursor ? page?.items.at(-1)?.enqueue_sequence ?? 0 : 0;
    if (!Number.isSafeInteger(result.queue_revision) || result.items.length > 50) {
      throw new Error('The queue page could not be verified.');
    }
    for (const item of result.items) {
      assertReceiptScope(item, scope);
      if (item.queue_revision !== result.queue_revision || !Number.isSafeInteger(item.enqueue_sequence) ||
          item.enqueue_sequence <= sequence || !Number.isSafeInteger(item.input_revision)) {
        throw new Error('The queue page could not be verified.');
      }
      sequence = item.enqueue_sequence;
    }
    return result;
  }

  function showError(error: unknown, action: 'read' | 'remove' | 'pause-change') {
    const status = (error as {status?: number})?.status;
    if (status === 401 || (status === 403 && action === 'read')) {
      setPage(null);
      onAccessLost();
      return;
    }
    setPage(null);
    if (action !== 'read') summary.current?.focus();
    if (action === 'pause-change') {
      setNotice(status === 403 ? 'This queue change was refused. Refresh to review the current queue.'
        : 'The queue change could not be confirmed. Refresh to review its current state.');
    } else if (action === 'remove') {
      setNotice(status === 409 ? 'The queue changed. Refresh it before removing an entry.'
        : 'Removal could not be confirmed. Refresh the queue to check its current state.');
    } else {
      setNotice('The message queue could not be refreshed.');
    }
  }

  async function run({cursor = null, remove, paused}: {cursor?: string | null; remove?: SessionInputQueueItem; paused?: boolean} = {}) {
    if (request.current) return;
    const capability = page?.cancel_capability_revision;
    if (remove && (!capability || !remove.can_cancel)) return;
    if (paused !== undefined && (!page?.pause_capability_revision || page.paused === paused)) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setConfirmResume(false);
    setNotice('');
    let confirmed = '';
    try {
      if (remove && capability) {
        const receipt = await runtimeApi.cancelSessionInput(scope, remove, capability, controller.signal);
        if (controller.signal.aborted) return;
        assertReceiptScope(receipt, scope);
        if (receipt.input_id !== remove.input_id || receipt.status !== 'CANCELLED') {
          throw new Error('The removal could not be verified.');
        }
        confirmed = 'Message removed from the queue.';
        onCancelled(receipt);
      } else if (page && paused !== undefined) {
        const receipt = await runtimeApi.changeSessionQueuePause(scope, page, paused, controller.signal);
        if (controller.signal.aborted) return;
        assertInteractionScope({...receipt.scope, session_owner_generation: receipt.session_owner_generation}, scope);
        if (receipt.paused !== paused || receipt.queue_revision !== page.queue_revision + 1) {
          throw new Error('The queue change could not be verified.');
        }
        confirmed = paused ? 'Message queue paused.' : 'Message queue resumed.';
      }
      if (confirmed) {
        setPage(null);
        setNotice(confirmed);
        summary.current?.focus();
      }
      const next = await readPage(cursor, controller.signal);
      if (controller.signal.aborted) return;
      if (cursor && next.queue_revision !== page?.queue_revision) {
        const current = await readPage(null, controller.signal);
        if (controller.signal.aborted) return;
        setPage(current);
        setNotice('The queue changed. Showing the current first page.');
      } else {
        setPage(cursor && page ? {...next, items: [...page.items, ...next.items]} : next);
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        showError(error, confirmed ? 'read' : remove ? 'remove' : paused !== undefined ? 'pause-change' : 'read');
        if (confirmed) setNotice(confirmed + ' Refresh to see the current queue.');
      }
    } finally {
      if (!controller.signal.aborted) {
        request.current = null;
        setBusy(false);
      }
    }
  }

  return <details className="rounded-lg border p-2" onToggle={event => {
    if (event.currentTarget.open) void run();
  }}>
    <summary ref={summary} className="cursor-pointer text-sm font-medium">View message queue</summary>
    <div className="mt-2 space-y-2" aria-busy={busy}>
      {page?.paused && <p className="text-sm">Queue paused. Pending messages will wait for an explicit resume.</p>}
      {page?.paused && !page.pause_capability_revision &&
        <p className="text-xs text-surface-500">Resume is unavailable until this session can send again and any interrupt is settled.</p>}
      {page && (!page.items.length ? <p className="text-sm">No pending messages.</p> :
        <ol className="space-y-1 text-sm" aria-label="Pending messages">
          {page.items.map((item, position) => <li key={item.input_id} className="flex flex-wrap items-center gap-2">
            <span>Entry {position + 1} · {receiptLabel[item.status]}</span>
            {item.can_cancel && page.cancel_capability_revision && <button type="button" className="btn btn-secondary"
              aria-label={`Remove entry ${position + 1} from the queue`} disabled={busy}
              onClick={() => void run({remove: item})}>Remove</button>}
          </li>)}
        </ol>)}
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => void run()}>Refresh queue</button>
        {page?.pause_capability_revision && !confirmResume && (page.paused
          ? <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => setConfirmResume(true)}>Resume queue</button>
          : <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => void run({paused: true})}>Pause queue</button>)}
        {page?.next_cursor && <button type="button" className="btn btn-secondary" disabled={busy}
          onClick={() => void run({cursor: page.next_cursor})}>Load more entries</button>}
      </div>
      {confirmResume && <div className="space-y-2 rounded-md border p-2">
        <p className="text-sm">Pending messages can start sending at the next available turn.</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn btn-primary" onClick={() => void run({paused: false})}>Resume sending</button>
          <button ref={keepPaused} type="button" className="btn btn-secondary" onClick={() => {
            setConfirmResume(false);
            summary.current?.focus();
          }}>Keep paused</button>
        </div>
      </div>}
    </div>
    <p className="text-sm" role="status">{notice || (busy ? 'Checking the queue…' : '')}</p>
  </details>;
}
