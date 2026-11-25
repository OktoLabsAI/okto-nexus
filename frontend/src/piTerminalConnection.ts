import {ApiError} from './api';
import {piPresentationApi, type InteractionScope, type PiPresentation, type PiPresentationReview,
  type PresentationAccess} from './runtimeApi';

const protocols: Record<PiPresentation, string> = {
  pi: 'nexus.presenter.pi.v1', pi_remote: 'nexus.presenter.pi-remote.v1',
};
const browserProtocol = 'nexus.presenter.browser.v1';
const scopeKeys = ['server_id', 'executor_id', 'binding_id', 'workspace_id', 'workspace_binding_id', 'agent_id', 'session_id'] as const;

async function availableReview(scope: InteractionScope, presentation: PiPresentation, access: PresentationAccess,
  signal: AbortSignal): Promise<PiPresentationReview | null> {
  let review: PiPresentationReview;
  try {
    review = await piPresentationApi.review(scope, presentation, access, signal);
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) return null;
    throw error;
  }
  const strategy = presentation === 'pi' ? 'pi_local' : 'pi_remote';
  if (review.version !== 1 || review.attach_strategy !== `${strategy}_${access}` || !review.capability_revision ||
      review.expected_session_generation !== scope.session_owner_generation ||
      scopeKeys.some(key => review.scope?.[key] !== scope[key])) throw new Error('Terminal review changed scope.');
  if (access === 'write' && (!Number.isSafeInteger(review.writer_epoch) || typeof review.writer_occupied !== 'boolean' ||
      !review.input_capability_revision)) throw new Error('Terminal writing could not be verified.');
  return review;
}

/** Acquire only a vacant writer. A lost reply never triggers a second prepare. */
export async function connectPiTerminal(scope: InteractionScope, columns: number, rows: number, signal: AbortSignal) {
  const origin = new URL(window.location.href);
  const local = ['127.0.0.1', 'localhost', '[::1]'].includes(origin.hostname);
  const candidates: PiPresentation[] = [];
  if (local) candidates.push('pi');
  if (local || origin.protocol === 'https:') candidates.push('pi_remote');
  for (const presentation of candidates) {
    const reader = await availableReview(scope, presentation, 'read', signal);
    if (!reader) continue;
    const writer = await availableReview(scope, presentation, 'write', signal);
    const write = writer !== null && !writer.writer_occupied;
    const access: PresentationAccess = write ? 'write' : 'read';
    const review = write ? writer : reader;
    const offer = await piPresentationApi.prepare(scope, presentation, access, review, crypto.randomUUID(), signal);
    signal.throwIfAborted();
    if (offer.version !== 1 || !offer.attachment_id || !offer.ticket) throw new Error('Terminal attachment was not prepared.');
    const socket = new WebSocket(piPresentationApi.url(offer.attachment_id, origin), [protocols[presentation], browserProtocol]);
    socket.binaryType = 'arraybuffer';
    socket.onopen = () => {
      if (signal.aborted || socket.protocol !== protocols[presentation]) {
        socket.close();
        return;
      }
      socket.send(JSON.stringify({kind: 'hello', version: 1, ticket: offer.ticket, scope: review.scope,
        expected_session_generation: scope.session_owner_generation, columns, rows, editor: write}));
    };
    return {socket, access, attachmentId: offer.attachment_id, keepalive: offer.pi_keepalive === true,
      inputRevision: writer?.input_capability_revision};
  }
  return null;
}
