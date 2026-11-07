import type { CanonicalObservation, ExternalObservation } from '../src/observationTypes';

declare const legacy: Omit<ExternalObservation, 'canonical_observation'>;
const oldServer: ExternalObservation = legacy;
const cleared: ExternalObservation = { ...oldServer, canonical_session_ref: null, canonical_observation: null };
declare const correlated: CanonicalObservation;
const unknownReceipt: CanonicalObservation = { ...correlated, last_received_receipt: {
  status: 'unknown', reason: 'receipt_provenance_unavailable',
} };
const verifiedReceipt: CanonicalObservation = { ...correlated, last_received_receipt: {
  status: 'verified', operation_id: 'operation', action: 'runtime.send', stage: 'SUCCEEDED',
  receipt_revision: 1, received_at: '2030-01-01T00:00:00Z', provenance: 'core_committed',
} };
// @ts-expect-error External activity cannot declare a verified canonical receipt.
const externalProof: CanonicalObservation['last_received_receipt'] = { ...verifiedReceipt.last_received_receipt, status: 'verified', provenance: 'external_report' };
// @ts-expect-error A process-birth comparison is not task success evidence.
const taskProof: CanonicalObservation['provenance']['native_birth_provenance'] = 'task_succeeded';
void [cleared, unknownReceipt, verifiedReceipt, externalProof, taskProof];
