import type { ExternalObservation } from '../observationTypes';

const time = (value: string) => Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString() : 'Not recorded';

/** These facts describe a fenced association and received evidence, never a live process. */
export function CanonicalObservationFacts({ item, currentView }: {
  item: ExternalObservation; currentView: boolean;
}) {
  if (!currentView) return <p className="text-surface-500">Canonical correlation must be refreshed with this snapshot.</p>;
  const ref = item.canonical_session_ref, facts = item.canonical_observation;
  if (!ref || !facts || facts.precedence !== 'canonical_core_facts' ||
      facts.provenance?.external_binding_provenance !== 'operator_attested_external_binding' ||
      facts.provenance?.native_birth_provenance !== 'machine_checked_native_birth')
    return <p className="text-surface-500">No current canonical session correlation is available in this snapshot.</p>;
  const receipt = facts.last_received_receipt;
  return <section aria-label="Canonical session facts" className="rounded border border-accent-300 dark:border-accent-700 p-3 space-y-2" data-testid="canonical-observation-facts">
    <h4 className="font-semibold">Canonical session facts</h4>
    <p>These Core facts take precedence over the external activity signal below.</p>
    <dl className="grid gap-2 sm:grid-cols-2">
      <div><dt className="text-surface-500">Recorded session lifecycle</dt><dd className="font-mono break-all">{facts.session_lifecycle_state}</dd></div>
      <div><dt className="text-surface-500">Session</dt><dd className="font-mono break-all">{ref.session_id}</dd></div>
      <div><dt className="text-surface-500">Server</dt><dd className="font-mono break-all">{ref.server_id}</dd></div>
      <div><dt className="text-surface-500">Executor</dt><dd className="font-mono break-all">{ref.executor_id}</dd></div>
      <div><dt className="text-surface-500">Opening operation</dt><dd className="font-mono break-all">{ref.open_operation_id}</dd></div>
      <div><dt className="text-surface-500">Session generation · stream</dt><dd className="font-mono break-all">{ref.session_owner_generation} · {ref.stream_epoch}</dd></div>
    </dl>
    <p>Association revision {facts.correlation_revision} · Verified at {time(facts.verified_at)}</p>
    <p>External binding attested by the operator. Native process birth checked by the machine.</p>
    <section aria-label="Last receipt received" className="space-y-1 border-t border-surface-200 dark:border-surface-700 pt-2">
      <h5 className="font-semibold">Last receipt received</h5>
      {receipt?.status === 'verified' && receipt.provenance === 'core_committed' ? <>
        <dl className="grid gap-2 sm:grid-cols-2">
          <div><dt className="text-surface-500">Receipt stage</dt><dd className="font-mono break-all">{receipt.stage}</dd></div>
          <div><dt className="text-surface-500">Operation</dt><dd className="font-mono break-all">{receipt.operation_id}</dd></div>
          <div><dt className="text-surface-500">Action</dt><dd className="font-mono whitespace-pre-wrap break-all">{receipt.action}</dd></div>
          <div><dt className="text-surface-500">Receipt revision · received at</dt><dd>{receipt.receipt_revision} · {time(receipt.received_at)}</dd></div>
        </dl>
        <p>Provenance: committed Core receipt.</p>
      </> : <p>{receipt === null ? 'No receipt received in this snapshot.' : 'Receipt unknown: committed Core provenance is unavailable.'}</p>}
      <p>A received receipt records an operation event; it does not establish the current execution state.</p>
    </section>
    <p>Matching association fences do not establish continuing process liveness, idle activity, presence or available capacity.</p>
  </section>;
}
