"""Revalidate selected installations without changing approved scopes or sessions."""
import json
import logging

log = logging.getLogger(__name__)


def same_installation_location(approved, current):
    """Consent selects an installation location, not an immutable release."""
    changing = {'version', 'fingerprint', 'build_identity', 'trust', 'source'}
    return ({k: v for k, v in approved.items() if k not in changing}
            == {k: v for k, v in current.items() if k not in changing})


def compatible_selection(baseline, current):
    if baseline is None or current is None:
        return False
    # Format 3 adds independent observation coverage, not a new installation
    # identity or execution contract. Preserve retained format-2 consent while
    # still comparing every selected runtime/evidence field below.
    if baseline.get('format') == 2 and current.get('format') == 3:
        baseline = {**baseline, 'format': 3}
    if baseline == current:
        return True
    # Core may add an implementation for a previously unsupported control.
    # That does not replace the selected installation or change the contract
    # of an existing control. Current operation authorization still applies.
    old_runtime, new_runtime = baseline['runtime'], current['runtime']
    if ({k: v for k, v in old_runtime.items() if k != 'control_targeting'} !=
            {k: v for k, v in new_runtime.items() if k != 'control_targeting'}):
        return False
    new_controls = {control['action']: control for control in new_runtime['control_targeting']}
    if any(control['supported'] and new_controls.get(control['action']) != control
           for control in old_runtime['control_targeting']):
        return False
    # Discovery provenance is not installation identity or execution authority.
    # The same selected executable can be found through PATH or a trusted root.
    baseline = {**baseline, 'runtime': new_runtime,
                'evidence': {k: v for k, v in baseline['evidence'].items() if k != 'source'}}
    current = {**current,
               'evidence': {k: v for k, v in current['evidence'].items() if k != 'source'}}
    if baseline == current:
        return True
    # Candidate identity, platform, adapter contract and explicit selection
    # remain fixed. Version/build changes alone do not revoke that selection.
    changing = {'version', 'build_identity', 'content_fingerprint', 'qualification',
                'qualified_control_actions'}
    def stable(value):
        return {**value, 'evidence': {k: v for k, v in value['evidence'].items() if k not in changing}}
    return (current['evidence']['state'] in {'READY_FOR_RUNTIME', baseline['evidence']['state']}
            and current['evidence']['trust'] == 'selected'
            and bool(current['evidence']['version'])
            and current['evidence']['version'] != baseline['evidence']['version']
            and stable(baseline) == stable(current))


def accepts_binding(conn, binding, current_revision, server_id, executor_id):
    return inventory_accepted(conn, server_id=server_id, executor_id=executor_id,
        approved_revision=binding['inventory_revision'], candidate_ref=binding['candidate_ref'],
        current_revision=current_revision)


def selection(snapshot, adapter, candidate):
    """Ignore producer/Core version and unrelated installations, never selected evidence."""
    evidence = [x for x in snapshot['evidence']
                if x['adapter_id'] == adapter and x['candidate_ref'] == candidate]
    catalog = [x for x in snapshot['catalog']['runtimes'] if x['adapter_id'] == adapter]
    if len(evidence) != 1 or len(catalog) != 1:
        return None
    # Display labels are not execution authority. Everything else is compared.
    runtime = {k: v for k, v in catalog[0].items() if k != 'display_name'}
    return dict(format=snapshot['snapshot_format_version'],
                catalog_format=snapshot['catalog']['format_version'],
                availability_format=snapshot['availability']['format_version'],
                runtime=runtime, evidence=evidence[0])


def inventory_accepted(conn, *, server_id, executor_id, approved_revision, candidate_ref, current_revision):
    if approved_revision == current_revision:
        return True
    return conn.execute(
        'SELECT 1 FROM execution_inventory_revalidation WHERE server_id=? AND executor_id=? '
        'AND approved_revision=? AND candidate_ref=? AND current_revision=? AND compatible=1 '
        "AND reason NOT IN ('observation_pending','observation_failed')",
        (server_id, executor_id, approved_revision, candidate_ref, current_revision)).fetchone() is not None


def binding_consent_preserved(conn, binding, current_revision, server_id, executor_id):
    """Read-only consent projection; deferred observation grants no execution."""
    if accepts_binding(conn, binding, current_revision, server_id, executor_id):
        return True
    return conn.execute(
        'SELECT 1 FROM execution_inventory_revalidation WHERE server_id=? AND executor_id=? '
        'AND approved_revision=? AND candidate_ref=? AND current_revision=? AND compatible=1 '
        "AND baseline_json IS NOT NULL AND reason IN ('observation_pending','observation_failed')",
        (server_id, executor_id, binding['inventory_revision'], binding['candidate_ref'], current_revision)
    ).fetchone() is not None


def revalidate_inventory(conn, snapshot):
    """Called only inside authenticated inventory publication; no provider I/O."""
    from nexus_connector_core import CoreError, InstallationCandidate, build_executor_inventory_snapshot
    from .execution_local_realizations import _digest

    server, executor, revision = (snapshot[k] for k in ('server_id', 'executor_id', 'inventory_revision'))
    bindings = conn.execute(
        'SELECT b.*,ep.adapter_id,r.configuration_digest,r.body_hash,l.local_record_json '
        'FROM execution_bindings b JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id '
        'JOIN execution_realizations r ON r.server_id=b.server_id AND r.executor_id=b.executor_id '
        'AND r.realization_ref=b.realization_ref LEFT JOIN execution_local_realizations l '
        'ON l.server_id=r.server_id AND l.executor_id=r.executor_id AND l.realization_ref=r.realization_ref '
        'WHERE b.server_id=? AND b.executor_id=?', (server, executor)).fetchall()
    for binding in bindings:
        approved, candidate, adapter = (binding[k] for k in ('inventory_revision', 'candidate_ref', 'adapter_id'))
        key = (server, executor, approved, candidate)
        prior = conn.execute('SELECT * FROM execution_inventory_revalidation WHERE server_id=? '
            'AND executor_id=? AND approved_revision=? AND candidate_ref=?', key).fetchone()
        current = selection(snapshot, adapter, candidate)
        baseline = json.loads(prior['baseline_json']) if prior and prior['baseline_json'] else None
        if baseline is None:
            old = conn.execute('SELECT canonical_projection FROM execution_inventory_snapshots '
                'WHERE server_id=? AND executor_id=? AND inventory_revision=? '
                'ORDER BY publication_sequence DESC LIMIT 1', (server, executor, approved)).fetchone()
            if old:
                baseline = selection(json.loads(old[0]), adapter, candidate)
            elif binding['local_record_json']:
                # Legacy embedded bindings retain the exact consented candidate,
                # even when older global inventory snapshots were pruned.
                try:
                    record = json.loads(binding['local_record_json'])
                    if (_digest(record['configuration']) == binding['configuration_digest'] and
                            _digest(record['publication']) == binding['body_hash'] and
                            record['publication']['candidate_ref'] == candidate and
                            record['publication']['inventory_revision'] == approved):
                        retained = build_executor_inventory_snapshot(
                            (InstallationCandidate(**record['candidate']),), server_id=server,
                            executor_id=executor, producer_instance_id='retained-consent', publication_sequence=1)
                        baseline = selection(retained, adapter, candidate)
                except (CoreError, ValueError, TypeError, KeyError):
                    baseline = None
        compatible = compatible_selection(baseline, current)
        reason = ('installation_unchanged' if compatible and baseline == current else
                  'installation_updated' if compatible else 'installation_missing' if current is None
                  else 'approved_evidence_missing' if baseline is None else 'selected_installation_changed')
        observation = next((row for row in snapshot.get('observations', ()) if row['adapter_id'] == adapter), None)
        if observation and observation['state'] in ('PENDING', 'FAILED'):
            # Lack of completed evidence cannot revoke a prior selection, nor
            # repair one already found incompatible. Execution still requires
            # fresh completed evidence via inventory_accepted + freshness.
            compatible = baseline is not None and (bool(prior['compatible']) if prior else True)
            reason = 'observation_' + observation['state'].lower()
        conn.execute('INSERT INTO execution_inventory_revalidation VALUES (?,?,?,?,?,?,?,?,'
            "strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(server_id,executor_id,approved_revision,candidate_ref) "
            'DO UPDATE SET current_revision=excluded.current_revision,baseline_json=excluded.baseline_json,'
            'compatible=excluded.compatible,reason=excluded.reason,checked_at=excluded.checked_at',
            (*key, revision, json.dumps(baseline, sort_keys=True) if baseline else None, int(compatible), reason))
        if approved != revision and (prior is None or prior['current_revision'] != revision or
                                     prior['compatible'] != int(compatible)):
            log.info('Runtime inventory revalidation: binding=%s result=%s', binding['binding_id'], reason)


def revalidate_all_bindings(factory, *, context, access):
    """Operator action: accept the current installation for every binding that needs review.

    A binding is accepted only when its installation is present, selected and
    ready in the current inventory. The action records the current evidence as
    the new baseline. It does not change a binding, a grant or a session.
    """

    with factory.unit_of_work() as uow:
        access.authorize_maintenance(context, uow=uow)
        conn = uow.connection
        rows = conn.execute(
            'SELECT b.binding_id,b.endpoint_id,b.server_id,b.executor_id,b.inventory_revision,b.candidate_ref,'
            'ep.adapter_id,c.inventory_revision AS current_revision,s.canonical_projection '
            'FROM execution_bindings b JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id '
            'JOIN execution_executors e ON e.server_id=b.server_id AND e.executor_id=b.executor_id '
            'LEFT JOIN execution_inventory_current c ON c.server_id=b.server_id AND c.executor_id=b.executor_id '
            'LEFT JOIN execution_inventory_snapshots s ON s.server_id=c.server_id AND s.executor_id=c.executor_id '
            "AND s.publication_sequence=c.publication_sequence WHERE ep.activation_state='approved' "
            'AND e.revoked_at IS NULL ORDER BY b.binding_id').fetchall()
        results = []
        for row in rows:
            result = dict(binding_id=row['binding_id'], endpoint_id=row['endpoint_id'], adapter_id=row['adapter_id'])
            if row['current_revision'] is None:
                outcome = 'inventory_unavailable'
            elif accepts_binding(conn, row, row['current_revision'], row['server_id'], row['executor_id']):
                outcome = 'already_current'
            else:
                current = selection(json.loads(row['canonical_projection']), row['adapter_id'], row['candidate_ref'])
                evidence = (current or {}).get('evidence', {})
                if current is None:
                    outcome = 'installation_missing'
                elif evidence.get('state') != 'READY_FOR_RUNTIME' or evidence.get('trust') != 'selected':
                    outcome = 'installation_not_ready'
                else:
                    conn.execute('INSERT INTO execution_inventory_revalidation VALUES (?,?,?,?,?,?,1,?,'
                        "strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(server_id,executor_id,approved_revision,"
                        'candidate_ref) DO UPDATE SET current_revision=excluded.current_revision,'
                        'baseline_json=excluded.baseline_json,compatible=1,reason=excluded.reason,'
                        'checked_at=excluded.checked_at',
                        (row['server_id'], row['executor_id'], row['inventory_revision'], row['candidate_ref'],
                         row['current_revision'], json.dumps(current, sort_keys=True), 'operator_revalidated'))
                    outcome = 'revalidated'
            results.append({**result, 'outcome': outcome})
        counts = {name: sum(item['outcome'] == name for item in results)
                  for name in ('revalidated', 'already_current', 'installation_missing',
                               'installation_not_ready', 'inventory_unavailable')}
        log.info('Operator revalidated %d binding(s); %d need another action',
                 counts['revalidated'], len(results) - counts['revalidated'] - counts['already_current'])
        return dict(counts, bindings=results)
