import {useEffect, useRef, useState} from 'react';
import {runtimeApi, type InteractionScope, type SessionInputReceipt, type SessionSteerAvailability} from '../runtimeApi';
import {assertSteerPreview, steerReceiptOutcome, steerStorageKey, type SteerReference, type SteerSource} from '../sessionSteer';

export function SessionSteerControl({scope, available, source, pending, draftRetained, onCloseReview, onPending, onSubmitted,
  onAccessLost, onQueueChanged}: {
  scope: InteractionScope;
  available: boolean;
  source: SteerSource | null;
  pending: SteerReference | null;
  draftRetained: boolean;
  onCloseReview: () => void;
  onPending: (reference: SteerReference | null) => void;
  onSubmitted: (reference: SteerReference, receipt: SessionInputReceipt) => void;
  onAccessLost: () => void;
  onQueueChanged: () => void;
}) {
  const key = steerStorageKey(scope);
  const [preview, setPreview] = useState<{source: SteerSource; availability: SessionSteerAvailability} | null>(null);
  const [reviewError, setReviewError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const request = useRef<AbortController | null>(null);
  const currentPending = useRef(pending);
  const cancel = useRef<HTMLButtonElement>(null);
  const callbacks = useRef({onPending, onSubmitted, onAccessLost, onQueueChanged, draftRetained});
  callbacks.current = {onPending, onSubmitted, onAccessLost, onQueueChanged, draftRetained};
  currentPending.current = pending;

  useEffect(() => () => request.current?.abort(), []);

  useEffect(() => {
    if (!source) return;
    setReviewError('');
    setPreview(null);
    setNotice('');
    cancel.current?.focus();
    const controller = new AbortController();
    const inputId = source.kind === 'queue' ? source.inputId : null;
    void runtimeApi.sessionSteerTarget(scope, inputId, controller.signal).then(availability => {
      if (controller.signal.aborted) return;
      assertSteerPreview(availability, scope, source);
      setPreview({source, availability});
    }).catch(error => {
      if (controller.signal.aborted) return;
      if (error.status === 401) callbacks.current.onAccessLost();
      else setReviewError('This message or current turn could not be reviewed. The message was kept.');
    });
    return () => controller.abort();
  }, [source]);

  function finish() {
    window.sessionStorage.removeItem(key);
    currentPending.current = null;
    callbacks.current.onPending(null);
  }

  function acceptReceipt(reference: SteerReference, receipt: SessionInputReceipt) {
    switch (steerReceiptOutcome(receipt, scope, reference)) {
      case 'accepted':
      case 'submitted':
        callbacks.current.onSubmitted(reference, receipt);
        finish();
        callbacks.current.onQueueChanged();
        setNotice(receipt.status === 'ACCEPTED_NATIVE' ? 'Reorientation was accepted by the harness.'
          : 'Reorientation sent to the current turn. Harness acceptance is unconfirmed.');
        break;
      case 'refused':
        finish();
        callbacks.current.onQueueChanged();
        setNotice(reference.kind === 'draft' && callbacks.current.draftRetained
          ? 'The reorientation was refused before sending. Your draft is available.'
          : 'The reorientation was refused before sending.');
        break;
      case 'original-changed':
        finish();
        callbacks.current.onQueueChanged();
        setNotice('The original queue entry changed before reorientation could be confirmed.');
        break;
      case 'dispatching':
        setNotice('Reorientation requested. Waiting for dispatch.');
        break;
      default:
        setNotice('Reorientation is unconfirmed. Check the original receipt before taking another action.');
    }
  }

  async function check(reference: SteerReference, background = false) {
    if (request.current || currentPending.current !== reference) return;
    const controller = new AbortController();
    request.current = controller;
    if (!background) setBusy(true);
    try {
      const receipt = reference.kind === 'draft'
        ? await runtimeApi.sessionInputReceipt(scope, reference.intent, controller.signal)
        : await runtimeApi.sessionInputReceiptById(scope, reference.inputId, controller.signal);
      if (!controller.signal.aborted && currentPending.current === reference) acceptReceipt(reference, receipt);
    } catch (error) {
      if (controller.signal.aborted) return;
      const status = (error as {status?: number})?.status;
      if (status === 401) callbacks.current.onAccessLost();
      else setNotice('Reorientation is unconfirmed. Check the original receipt before taking another action.');
    } finally {
      if (!controller.signal.aborted) {
        request.current = null;
        if (!background) setBusy(false);
      }
    }
  }

  useEffect(() => {
    if (!pending) return;
    void check(pending, true);
    const timer = window.setInterval(() => void check(pending, true), 2500);
    return () => window.clearInterval(timer);
  }, [pending]);

  async function confirm() {
    const reviewed = preview?.source === source ? preview?.availability : null;
    if (!available || !source || !reviewed?.control || pending || request.current) return;
    if (source.kind === 'queue' && !reviewed.queued_input) return;
    const reference: SteerReference = source.kind === 'draft'
      ? {kind: 'draft', intent: 'ui_steer_' + crypto.randomUUID()} : {kind: 'queue', inputId: source.inputId};
    try {
      window.sessionStorage.setItem(key, JSON.stringify(reference));
    } catch {
      setReviewError('The recovery reference could not be saved. The request is still a draft.');
      return;
    }
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    currentPending.current = reference;
    callbacks.current.onPending(reference);
    onCloseReview();
    try {
      const receipt = source.kind === 'draft' && reference.kind === 'draft'
        ? await runtimeApi.steerSessionInput(scope, reviewed.control, reference.intent, source.text, controller.signal,
          source.catalogRevision)
        : await runtimeApi.promoteSessionInput(scope, reviewed.control, reviewed.queued_input!, controller.signal);
      if (!controller.signal.aborted) {
        acceptReceipt(reference, receipt);
        callbacks.current.onQueueChanged();
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      const status = (error as {status?: number})?.status;
      if (status === 401) callbacks.current.onAccessLost();
      else if ([400, 403, 404, 409, 422, 429].includes(status ?? 0)) {
        finish();
        callbacks.current.onQueueChanged();
        const reason = status === 409
          ? (source.kind === 'draft' && source.catalogRevision ? 'The commands, turn or queue changed. Refresh commands and review again.'
            : 'The turn or queue changed.')
          : 'The reorientation was refused.';
        setNotice(reason + (source.kind === 'draft' ? ' Your draft is available.' : ' Refresh the queue to review its state.'));
      } else {
        setNotice('Reorientation is unconfirmed. Check the original receipt before taking another action.');
      }
    } finally {
      if (!controller.signal.aborted) {
        request.current = null;
        setBusy(false);
      }
    }
  }

  if (!source && !pending && !notice) return null;
  const reviewed = preview?.source === source ? preview?.availability : null;
  return <section aria-label="Turn reorientation" className="space-y-2">
    {source && <div className="space-y-2 rounded-md border p-2">
      {reviewError ? <p role="alert" className="text-sm">{reviewError}</p> :
        !reviewed ? <p role="status" className="text-sm">Checking the current turn…</p> :
        !reviewed.control ? <p role="status" className="text-sm">The current turn is unavailable for reorientation.</p> :
        <>
          {reviewed.queued_input && <p className="text-sm whitespace-pre-wrap break-words">
            {reviewed.queued_input.text_preview}{reviewed.queued_input.truncated ? '…' : ''}
          </p>}
          <p className="text-sm">{source.kind === 'draft' ? 'Send this draft to the current turn.' :
            'Move this message out of the queue and send it to the current turn.'}</p>
        </>}
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn btn-primary" disabled={busy || !available || !reviewed?.control || !!reviewError}
          onClick={() => void confirm()}>Confirm reorientation</button>
        <button ref={cancel} type="button" className="btn btn-secondary" onClick={onCloseReview}>Cancel review</button>
      </div>
    </div>}
    {notice && <p role="status" className="text-sm">{notice}</p>}
    {pending && <button type="button" className="btn btn-secondary" disabled={busy}
      onClick={() => void check(pending)}>Check reorientation receipt</button>}
  </section>;
}
