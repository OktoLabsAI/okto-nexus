"""Revalidate selected installations without changing approved scopes or sessions."""
import json
import logging

log = logging.getLogger(__name__)


def same_installation_location(approved, current):
    """Consent selects an installation location, not an immutable release."""
    changing = {'version', 'fingerprint', 'build_identity', 'trust'}
    return ({k: v for k, v in approved.items() if k not in changing}
            == {k: v for k, v in current.items() if k not in changing})


def compatible_selection(baseline, current):
    if baseline is None or current is None:
        return False
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
        'AND approved_revision=? AND candidate_ref=? AND current_revision=? AND compatible=1',
        (server_id, executor_id, approved_revision, candidate_ref, current_revision)).fetchone() is not None


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
        conn.execute('INSERT INTO execution_inventory_revalidation VALUES (?,?,?,?,?,?,?,?,'
            "strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(server_id,executor_id,approved_revision,candidate_ref) "
            'DO UPDATE SET current_revision=excluded.current_revision,baseline_json=excluded.baseline_json,'
            'compatible=excluded.compatible,reason=excluded.reason,checked_at=excluded.checked_at',
            (*key, revision, json.dumps(baseline, sort_keys=True) if baseline else None, int(compatible), reason))
        if approved != revision and (prior is None or prior['current_revision'] != revision or
                                     prior['compatible'] != int(compatible)):
            log.info('Runtime inventory revalidation: binding=%s result=%s', binding['binding_id'], reason)
