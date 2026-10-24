"""Decide whether a new binary takes over an approved installation ref.

The consent record is the anchor. Under the `follow` policy the hub relabels
exactly one newer successor to the approved ref. Every other case is held.
Each decision writes one append-only row to execution_installation_succession.
"""
import asyncio
import json
import logging
import re
import sys
from dataclasses import asdict, replace
from pathlib import Path

from nexus_connector_core import CoreError, __version__ as CORE_VERSION
from nexus_connector_core.availability import effective_installation_ref
from nexus_connector_core.discovery import selected_fingerprint
from nexus_connector_core.protocol import canonical_json

from ..errors import ErrorCode, OktoNexusError

log = logging.getLogger(__name__)

POLICIES = ('review', 'follow')
# Rules 1-5 decide which binary is the successor. An operator accept cannot
# override them: the relabel on the next tick would never apply.
TRUST_RULE_REASONS = frozenset({'architecture_mismatch', 'untrusted', 'launch_script_mismatch',
                                'other_parent', 'ambiguous_successors'})
_VERSION = re.compile(r'\d+(?:\.\d+)*')
_COLUMNS = ('server_id', 'executor_id', 'adapter_id', 'stable_ref', 'decision', 'reason', 'policy',
            'policy_source', 'decided_by', 'from_executable', 'to_executable', 'from_version',
            'to_version', 'from_build_identity', 'to_build_identity', 'from_fingerprint',
            'to_fingerprint', 'to_natural_ref', 'decided_at')


def parse_version(value):
    """Return a tuple of integers, or None when the text is not a dotted number."""
    text = value.strip() if isinstance(value, str) else ''
    if not _VERSION.fullmatch(text):
        return None
    return tuple(int(part) for part in text.split('.'))


def record_succession(conn, row):
    """Insert one audit row. Return the row dict when it is new, else None."""
    values = tuple(row.get(name) for name in _COLUMNS)
    cursor = conn.execute(
        'INSERT OR IGNORE INTO execution_installation_succession (' + ','.join(_COLUMNS) + ') '
        'VALUES (' + ','.join('?' * len(_COLUMNS)) + ')', values)
    return dict(row, id=cursor.lastrowid) if cursor.rowcount else None


def latest_accepted(conn, server_id, executor_id, stable_ref):
    return conn.execute(
        'SELECT * FROM execution_installation_succession WHERE server_id=? AND executor_id=? '
        "AND stable_ref=? AND decision='accepted' ORDER BY id DESC LIMIT 1",
        (server_id, executor_id, stable_ref)).fetchone()


def _read_bindings(conn, key):
    rows = conn.execute(
        'SELECT b.candidate_ref,b.endpoint_id,e.agent_id,e.adapter_id,e.runtime_update_policy,'
        'w.workspace_id,l.local_record_json FROM execution_bindings b '
        'JOIN agent_endpoints e USING(endpoint_id) JOIN agents a ON a.agent_id=e.agent_id '
        'JOIN execution_local_realizations l ON l.server_id=b.server_id '
        'AND l.executor_id=b.executor_id AND l.realization_ref=b.realization_ref '
        'JOIN execution_workspace_bindings w ON w.server_id=b.server_id '
        'AND w.executor_id=b.executor_id AND w.workspace_binding_id=b.workspace_binding_id '
        "WHERE b.server_id=? AND b.executor_id=? AND e.enabled=1 AND a.is_active=1 "
        "AND e.activation_state='approved' ORDER BY b.binding_id",
        (key.server_id, key.executor_id)).fetchall()
    groups = {}
    for row in rows:
        groups.setdefault((row['adapter_id'], row['candidate_ref']), []).append(dict(row))
    return groups


def effective_policy(bindings, hub_policy):
    """Most restrictive wins: one `review` binding blocks the whole ref."""
    resolved = [(b['runtime_update_policy'] or hub_policy, b['runtime_update_policy'] is not None)
                for b in bindings]
    if any(policy != 'follow' for policy, _ in resolved):
        decisive = [own for policy, own in resolved if policy != 'follow']
        return 'review', 'endpoint' if any(decisive) else 'hub'
    return 'follow', 'endpoint' if any(own for _, own in resolved) else 'hub'


def _rule_failure(candidate, record):
    """Return the first failed adoption rule (1-4) for one candidate, or None."""
    consented = record['candidate']
    if candidate.adapter_id != consented['adapter_id'] or candidate.architecture != consented.get('architecture'):
        return 'architecture_mismatch'
    if candidate.trust != 'selected':
        return 'untrusted'
    if candidate.launch_script != consented.get('launch_script'):
        return 'launch_script_mismatch'
    path = Path(candidate.executable)
    if not path.is_file() or path.parent != Path(consented['executable']).parent:
        return 'other_parent'
    return None


def _probe(candidate):
    from . import execution_local_observations as observations
    return asyncio.run(observations.probe_version(replace(candidate, trust='selected')))


def _from_build(record, last):
    """Return the 'from' build: the last accepted row when one exists, else the consent record."""
    if last is not None:
        return dict(executable=last['to_executable'], version=last['to_version'],
                    build_identity=last['to_build_identity'], fingerprint=last['to_fingerprint'])
    consented = record['candidate']
    return dict(executable=consented['executable'], version=consented.get('version'),
                build_identity=consented.get('build_identity'), fingerprint=consented.get('fingerprint'))


def _row(key, adapter, stable, decision, reason, policy, source, by, origin, candidate, version, now):
    return dict(server_id=key.server_id, executor_id=key.executor_id, adapter_id=adapter,
                stable_ref=stable, decision=decision, reason=reason, policy=policy, policy_source=source,
                decided_by=by, from_executable=origin['executable'], to_executable=candidate.executable,
                from_version=origin['version'], to_version=version,
                from_build_identity=origin['build_identity'],
                to_build_identity=candidate.build_identity or candidate.fingerprint,
                from_fingerprint=origin['fingerprint'], to_fingerprint=candidate.fingerprint,
                to_natural_ref=effective_installation_ref(candidate), decided_at=now)


def apply_update_policy(deps, key, candidates, notify=None):
    """Return the candidates with at most one successor relabeled per approved ref.

    Runs in a worker thread. `notify` receives each new audit row after commit.
    """
    candidates = tuple(candidates)
    hub_policy = getattr(getattr(deps, 'config', None), 'runtime_update_policy', 'review')
    factory = deps.connection_factory
    with factory.unit_of_work(write=False) as uow:
        groups = _read_bindings(uow.connection, key)
    if not groups:
        return candidates
    approved_refs = {ref for _, ref in groups}
    present = {effective_installation_ref(c) for c in candidates}
    result, fresh_rows = list(candidates), []
    for (adapter, stable), bindings in groups.items():
        if stable in present:
            continue
        record = json.loads(bindings[0]['local_record_json'])
        pool = [c for c in candidates if c.adapter_id == adapter
                and effective_installation_ref(c) not in approved_refs]
        failures = [(c, _rule_failure(c, record)) for c in pool]
        passing = [c for c, why in failures if why is None]
        if len(passing) == 1:
            chosen, why = passing[0], None
        elif len(passing) > 1:
            chosen, why = min(passing, key=lambda c: c.executable), 'ambiguous_successors'
        elif len(pool) == 1:
            chosen, why = failures[0]
        else:
            continue
        policy, source = effective_policy(bindings, hub_policy)
        with factory.unit_of_work(write=False) as uow:
            last = latest_accepted(uow.connection, key.server_id, key.executor_id, stable)
        if last is not None and last['to_build_identity'] == (chosen.build_identity or chosen.fingerprint) and why is None:
            result[result.index(chosen)] = replace(chosen, installation_ref=stable)
            continue
        origin = _from_build(record, last if last is not None and last['to_version'] else None)
        base_version = origin['version']
        version, decision, reason = None, 'held', why
        if why is None and policy != 'follow':
            reason = 'policy_review'
        elif why is None:
            try:
                observed = _probe(chosen)
                version = observed.version
                if (type(version) is not str or not 1 <= len(version) <= 160
                        or selected_fingerprint(chosen) != chosen.fingerprint):
                    raise ValueError('probe result')
            except (CoreError, OktoNexusError, OSError, ValueError):
                version, reason = None, 'probe_failed'
            else:
                new, old = parse_version(version), parse_version(base_version)
                if new is None or old is None:
                    reason = 'version_unparseable'
                elif new == old:
                    reason = 'same_version_new_bytes'
                elif new < old:
                    reason = 'downgrade'
                else:
                    decision, reason = 'accepted', 'newer_version'
        now = deps.clock.now_iso()
        row = _row(key, adapter, stable, decision, reason, policy, source, 'hub', origin,
                   chosen, version, now)
        with factory.unit_of_work() as uow:
            if decision == 'accepted':
                relabeled = replace(chosen, installation_ref=stable)
                uow.connection.execute(
                    'INSERT INTO execution_local_observations VALUES (?,?,?,?,?,?,?,?,?) '
                    'ON CONFLICT(server_id,executor_id,candidate_ref) DO UPDATE SET '
                    'core_version=excluded.core_version,platform=excluded.platform,source_json=excluded.source_json,'
                    'version=excluded.version,actor_agent_id=excluded.actor_agent_id,observed_at=excluded.observed_at',
                    (key.server_id, key.executor_id, stable, CORE_VERSION, sys.platform,
                     canonical_json(asdict(relabeled)).decode(), version, bindings[0]['agent_id'], now))
                result[result.index(chosen)] = relabeled
            new_row = record_succession(uow.connection, row)
        if new_row is not None:
            new_row['workspace_ids'] = sorted({b['workspace_id'] for b in bindings})
            fresh_rows.append(new_row)
            log.warning('Runtime installation update: decision=%s reason=%s from=%s to=%s policy=%s',
                        decision, reason, base_version, version, policy)
    for row in fresh_rows:
        if notify is not None:
            notify(row)
    return tuple(result)


def probe_held_successor(conn, succession_id, candidates):
    """Return the probed version of the build behind a held row, or None.

    The probe is bounded and needs no database write. It returns None when the
    inventory has no matching candidate or the probe fails. The row then keeps
    to_version NULL, as before.
    """
    held = conn.execute('SELECT * FROM execution_installation_succession WHERE id=?',
                        (succession_id,)).fetchone()
    if held is None or held['decision'] != 'held' or held['reason'] in TRUST_RULE_REASONS:
        return None
    match = [c for c in candidates if c.adapter_id == held['adapter_id']
             and c.executable == held['to_executable'] and c.fingerprint == held['to_fingerprint']]
    if not match:
        return None
    try:
        version = _probe(match[0]).version
        if (type(version) is not str or not 1 <= len(version) <= 160
                or selected_fingerprint(match[0]) != match[0].fingerprint):
            return None
    except (CoreError, OktoNexusError, OSError, ValueError):
        return None
    return version


def accept_succession(conn, succession_id, actor, version=None):
    """Operator action: accept a held successor. The relabel follows on the next tick.

    `version` is the probed version of the successor. It fills to_version, so the
    next held row takes its "from" build from this accepted row.
    """
    held = conn.execute('SELECT * FROM execution_installation_succession WHERE id=?',
                        (succession_id,)).fetchone()
    if held is None or held['decision'] != 'held':
        raise OktoNexusError(ErrorCode.NOT_FOUND,
                             'No held installation update with this id.', {})
    if held['reason'] in TRUST_RULE_REASONS:
        raise OktoNexusError(ErrorCode.CONFLICT,
                             'This update failed a successor trust rule (' + held['reason'] + '). Rebind the agent instead.', {})
    row = {name: held[name] for name in _COLUMNS}
    row.update(decision='accepted', reason='operator_accepted', decided_by=actor)
    if version is not None:
        row['to_version'] = version
    row['decided_at'] = conn.execute("SELECT strftime('%Y-%m-%dT%H:%M:%fZ','now')").fetchone()[0]
    new_row = record_succession(conn, row)
    if new_row is not None:
        log.warning('Runtime installation update: decision=%s reason=%s from=%s to=%s policy=%s',
                    'accepted', 'operator_accepted', row['from_version'], row['to_version'], row['policy'])
    return new_row or dict(row, id=None)
