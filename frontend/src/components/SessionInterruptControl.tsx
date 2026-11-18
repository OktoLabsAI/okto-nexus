import {useEffect, useRef, useState} from 'react';
import {runtimeApi, type InteractionScope, type RuntimeOperation, type SessionInterruptReceipt, type SessionInterruptTarget} from '../runtimeApi';
import {assertInteractionScope} from '../sessionConversation';
import {canDismissInterrupt, interruptStatus, interruptStorageKey} from '../sessionInterrupt';

export function SessionInterruptControl({scope, canReview, onAccessLost, onQueueChanged}: {
  scope: InteractionScope;
  canReview: boolean;
  onAccessLost: () => void;
  onQueueChanged: () => void;
}) {
  const key = interruptStorageKey(scope);
  const [intent, setIntent] = useState(() => typeof window === 'undefined' ? null : window.sessionStorage.getItem(key));
  const [review, setReview] = useState<SessionInterruptTarget | null>(null);
  const [receipt, setReceipt] = useState<SessionInterruptReceipt | null>(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const request = useRef<AbortController | null>(null);
  const controlButton = useRef<HTMLButtonElement>(null);
  const keepRunning = useRef<HTMLButtonElement>(null);
  const observedPause = useRef<boolean | null>(null);
  const onLost = useRef(onAccessLost);
  const onQueue = useRef(onQueueChanged);
  onLost.current = onAccessLost;
  onQueue.current = onQueueChanged;

  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => {
    if (review) keepRunning.current?.focus();
  }, [review]);

  function assertControl(operation: RuntimeOperation) {
    assertInteractionScope({...operation.scope, session_owner_generation: operation.scope.session_owner_generation!}, scope);
    if (operation.action !== 'turn.interrupt' || !operation.operation_id) throw new Error('Invalid interrupt receipt.');
  }

  function removeIntent() {
    window.sessionStorage.removeItem(key);
    setIntent(null);
    setReceipt(null);
  }

  async function run(action: 'review' | 'confirm' | 'receipt', background = false) {
    if (request.current || (action !== 'receipt' && (!canReview || intent))
        || (action === 'receipt' && !intent) || (action === 'confirm' && !review)) return;
    const controller = new AbortController();
    request.current = controller;
    if (!background) {
      setNotice('');
      setBusy(true);
    }
    try {
      if (action === 'review') {
        const availability = await runtimeApi.sessionInterruptTarget(scope, controller.signal);
        if (controller.signal.aborted) return;
        assertInteractionScope({...availability.scope, session_owner_generation: availability.session_owner_generation}, scope);
        setReview(availability.control);
        if (!availability.control) setNotice('There is no confirmed turn to interrupt.');
      } else if (action === 'confirm' && review) {
        const originalIntent = 'stop_' + crypto.randomUUID();
        window.sessionStorage.setItem(key, originalIntent);
        setIntent(originalIntent);
        setReview(null);
        const operation = await runtimeApi.interruptSessionTurn(scope, review, originalIntent, controller.signal);
        if (controller.signal.aborted) return;
        assertControl(operation);
        setNotice('Interrupt requested. Checking its receipt…');
        onQueue.current();
      } else if (intent) {
        const next = await runtimeApi.sessionInterruptReceipt(scope, intent, controller.signal);
        if (controller.signal.aborted) return;
        assertControl(next);
        if (!next.interrupt || !Number.isSafeInteger(next.interrupt.pending_count) || next.interrupt.pending_count < 0) {
          throw new Error('Invalid interrupt outcome.');
        }
        setReceipt(next);
        setNotice('');
        if (observedPause.current !== next.interrupt.queue_paused) {
          observedPause.current = next.interrupt.queue_paused;
          onQueue.current();
        }
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      const status = (error as {status?: number})?.status;
      if (status === 401 || (status === 403 && action === 'receipt')) {
        onLost.current();
      } else if (action === 'confirm' && [400, 403, 409, 422, 429].includes(status ?? 0)) {
        removeIntent();
        setNotice(status === 409 ? 'The turn or its queue changed. Review the current turn before interrupting.'
          : 'The interrupt request was refused.');
      } else if (action !== 'review') {
        setNotice('The interrupt could not be confirmed. Check its original receipt.');
      } else {
        setNotice('The current turn could not be checked.');
      }
    } finally {
      if (!controller.signal.aborted) {
        request.current = null;
        if (!background) setBusy(false);
      }
    }
  }

  useEffect(() => {
    if (!intent) return;
    const read = () => void run('receipt', true);
    read();
    const timer = window.setInterval(read, 2500);
    return () => window.clearInterval(timer);
  }, [intent]);

  if (!canReview && !intent) return null;
  return <section aria-label="Turn interruption" className="space-y-2">
    {!intent && !review && <button ref={controlButton} type="button" className="btn btn-secondary"
      disabled={busy} onClick={() => void run('review')}>Interrupt turn</button>}
    {review && <div className="space-y-2 rounded-md border p-2">
      <p className="text-sm">Interrupt this turn and pause pending sends. You can resume the queue separately.</p>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn btn-primary" disabled={busy || !canReview}
          onClick={() => void run('confirm')}>Confirm interrupt</button>
        <button ref={keepRunning} type="button" className="btn btn-secondary" onClick={() => {
          setReview(null);
          window.requestAnimationFrame(() => controlButton.current?.focus());
        }}>Keep turn running</button>
      </div>
    </div>}
    <div role="status" className="text-sm">
      {intent && receipt && <p>{interruptStatus(receipt)}</p>}
      {intent && receipt?.interrupt.queue_paused && <p>
        {receipt.interrupt.pending_count === 1 ? '1 pending message' : `${receipt.interrupt.pending_count} pending messages`} · Queue paused.
      </p>}
      {notice && <p>{notice}</p>}
    </div>
    {intent && <div className="flex flex-wrap gap-2">
      <button type="button" className="btn btn-secondary" disabled={busy}
        onClick={() => void run('receipt')}>Check interrupt receipt</button>
      {canDismissInterrupt(receipt) && <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => {
        request.current?.abort();
        request.current = null;
        observedPause.current = null;
        removeIntent();
        setNotice('');
        window.requestAnimationFrame(() => controlButton.current?.focus());
      }}>Dismiss interrupt status</button>}
    </div>}
  </section>;
}
