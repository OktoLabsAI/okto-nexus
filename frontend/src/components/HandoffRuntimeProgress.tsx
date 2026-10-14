import type { HandoffRuntimeProgress as Progress } from '../api';

const labels: Record<string, string> = {
  WAITING_EXECUTOR:'Waiting for an available executor', CLAIMED:'Claimed', RUNNING:'Executing',
  DISPATCHED:'Sent to runtime', WAITING_INPUT:'Waiting for input',
  AWAITING_EXPLICIT_CLAIM:'Available for an explicit claim',
  AWAITING_DECISION:'Waiting for handoff decision', AWAITING_VERIFICATION:'Waiting for verification',
  NEEDS_RECONCILIATION:'Execution outcome requires reconciliation', EXECUTION_FAILED:'Execution failed',
  COMPLETED:'Completed', REJECTED:'Rejected', CANCELLED:'Cancelled', UNKNOWN:'Execution state unknown',
};

export function HandoffRuntimeProgress({value, details=false}: {value: Progress; details?: boolean}) {
  return <div className="text-xs space-y-1" aria-label="Broadcast handoff progress">
    <p>{labels[value.state] || labels.UNKNOWN}{value.claimed_by ? ` · ${value.claimed_by}` : ''}</p>
    {value.reason && <p className="text-surface-500 break-words">{value.reason.replaceAll('_',' ').toLowerCase()}</p>}
    {details && <>
      <p className="text-surface-500">{value.origin === 'missing' ? 'No verified source session. Source-session isolation uses the per-sender fallback.' : `Verified ${value.origin} source session.`}</p>
      {value.winner_channel && <p>Claim channel: {value.winner_channel === 'runtime' ? 'Managed runtime' : 'Explicit claim'}</p>}
      {value.claim_latency_ms !== null && <p>Created to runtime claim: {(value.claim_latency_ms/1000).toFixed(2)} s</p>}
      {value.execution_delay_ms !== null && <p>Claim to execution: {(value.execution_delay_ms/1000).toFixed(2)} s</p>}
      {value.state === 'AWAITING_DECISION' && <p>The native turn finished. An authenticated handoff decision is still required.</p>}
    </>}
  </div>;
}
