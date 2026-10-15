"""Version checks for selected installations; observations never grant runtime authority."""
import asyncio
import json
from dataclasses import asdict, replace
import os
from pathlib import Path
import sys
import tempfile
import time

from nexus_connector_core import CoreError, __version__ as CORE_VERSION, resolve_installation
from nexus_connector_core.discovery import selected_fingerprint
from nexus_connector_core.protocol import canonical_json

from ..adapters.outbound.execution.core_inventory import resolve_local_installation_selection
from ..errors import ErrorCode, OktoNexusError
from .execution_local_realizations import _authority


def _error(message, code=ErrorCode.CONFLICT):
    return OktoNexusError(code, message, {})


def apply_local_observations(factory, key, candidates):
    with factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute(
            'SELECT source_json,version FROM execution_local_observations '
            'WHERE server_id=? AND executor_id=? AND platform=?',
            (key.server_id, key.executor_id, sys.platform)).fetchall()
    # A version observation describes exact harness bytes, not a Core release.
    # Reuse only an identical full source; current Core still qualifies it.
    observations = {row['source_json']: row['version'] for row in rows}
    return tuple(replace(candidate, trust='selected', version=observations[canonical_json(asdict(candidate)).decode()])
                 if canonical_json(asdict(candidate)).decode() in observations else candidate
                 for candidate in candidates)


def _authorize(owner, access, context, request, *, uow, identity_reobserved=False):
    if owner._stop.is_set():
        raise _error('The local executor is shutting down.')
    guard = _authority(uow, owner=owner, access=access, context=context,
                       subject=request['agent_id'], adapter_id=request['adapter_id'], check_execution_policy=False)
    current = uow.connection.execute(
        'SELECT publication_sequence,inventory_revision FROM execution_inventory_current '
        'WHERE server_id=? AND executor_id=?', (owner.key.server_id, owner.key.executor_id)).fetchone()
    fresh = owner.fresh.get((owner.key.server_id, owner.key.executor_id))
    if (current is None or fresh is None or fresh[0] != current['publication_sequence']
            or current['inventory_revision'] != request['inventory_revision']
            or (not identity_reobserved and
                (time.monotonic() - fresh[1]) * 1000 + (fresh[2] if len(fresh) > 2 else 0) >= 120000)):
        raise _error('Refresh the local inventory and select the installation again.')
    return guard


async def probe_version(selected):
    from nexus_connector_core.discovery import probe_selected_claude, probe_selected_codex, probe_selected_pi
    probe = {'codex_app_server': probe_selected_codex, 'claude_stream': probe_selected_claude,
             'pi_rpc': probe_selected_pi}.get(selected.adapter_id)
    if probe is None:
        raise _error('This harness does not support a local version check.')
    essentials = {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'PATH', 'TEMP', 'TMP', 'LANG', 'LC_ALL', 'TERM'}
    env = {key: value for key, value in os.environ.items() if key.upper() in essentials}
    # No workspace, provider home or credentials are supplied to the process.
    with tempfile.TemporaryDirectory(prefix='nexus-version-check-') as directory:
        return await probe(selected, cwd=Path(directory), env=env)


async def refresh_approved_installations(owner, candidates):
    """Restore missing observations at locations selected by an active binding."""
    from .execution_inventory_revalidation import same_installation_location
    def approved():
        with owner.deps.connection_factory.unit_of_work(write=False) as uow:
            return [dict(row) for row in uow.connection.execute(
                'SELECT b.candidate_ref,e.agent_id,l.local_record_json FROM execution_bindings b '
                'JOIN agent_endpoints e USING(endpoint_id) JOIN agents a ON a.agent_id=e.agent_id '
                'JOIN execution_local_realizations l ON l.server_id=b.server_id '
                'AND l.executor_id=b.executor_id AND l.realization_ref=b.realization_ref '
                "WHERE b.server_id=? AND b.executor_id=? AND e.enabled=1 AND a.is_active=1 "
                "AND e.activation_state='approved'", (owner.key.server_id, owner.key.executor_id))]
    records = await asyncio.to_thread(approved)
    observed_candidates = await asyncio.to_thread(apply_local_observations,
        owner.deps.connection_factory, owner.key, candidates)
    semaphore = asyncio.Semaphore(4)
    async def refresh(source, existing):
        if existing.trust == 'selected' and existing.version:
            return
        selected = next((r for r in records if same_installation_location(
            json.loads(r['local_record_json'])['candidate'], asdict(source))), None)
        if selected is None:
            return
        async with semaphore:
            try:
                observed = await probe_version(replace(source, trust='selected'))
                if (type(observed.version) is not str or not 1 <= len(observed.version) <= 160
                        or replace(observed, trust=source.trust, version=source.version) != source
                        or await asyncio.to_thread(selected_fingerprint, source) != source.fingerprint
                        or owner._stop.is_set()):
                    return
                if selected not in await asyncio.to_thread(approved):
                    return
                def save():
                    with owner.deps.connection_factory.unit_of_work() as uow:
                        uow.connection.execute('INSERT INTO execution_local_observations VALUES (?,?,?,?,?,?,?,?,?) '
                            'ON CONFLICT(server_id,executor_id,candidate_ref) DO UPDATE SET '
                            'core_version=excluded.core_version,platform=excluded.platform,source_json=excluded.source_json,'
                            'version=excluded.version,actor_agent_id=excluded.actor_agent_id,observed_at=excluded.observed_at',
                            (owner.key.server_id, owner.key.executor_id, selected['candidate_ref'], CORE_VERSION,
                             sys.platform, canonical_json(asdict(source)).decode(), observed.version,
                             selected['agent_id'], owner.deps.clock.now_iso()))
                await asyncio.to_thread(save)
            except (CoreError, OktoNexusError, OSError, ValueError):
                # A technical probe failure remains visible; other installations
                # still publish and retain their independent readiness.
                return
    await asyncio.gather(*(refresh(source, existing) for source, existing in zip(candidates, observed_candidates)))


async def observe_local_installation(owner, *, access, context, request):
    """Called only by the owner-held task, under the inventory publication lock."""
    factory = owner.deps.connection_factory
    if request.get('approved') is not True:
        raise _error('Explicit operator consent is required for a version check.', ErrorCode.VALIDATION_ERROR)
    def authorize():
        with factory.unit_of_work(write=False) as uow:
            return _authorize(owner, access, context, request, uow=uow)
    guard = await asyncio.to_thread(authorize)
    try:
        resolve_local_installation_selection(owner.candidates,
            adapter_id=request['adapter_id'], candidate_ref=request['candidate_ref'],
            expected_inventory_revision=request['inventory_revision'])
        source = resolve_installation(owner.raw_candidates, request['adapter_id'], request['candidate_ref'])
        if await asyncio.to_thread(selected_fingerprint, source) != source.fingerprint:
            raise _error('The selected local installation changed.')
        # Selection is an explicit local operator decision, scoped to these
        # exact bytes. Core performs containment and pre/post-probe identity checks.
        if guard != await asyncio.to_thread(authorize) or owner._stop.is_set():
            raise _error('Operator authority changed before the version check.')
        observed = await probe_version(replace(source, trust='selected'))
        if (type(observed.version) is not str or not 1 <= len(observed.version) <= 160 or
                replace(observed, trust=source.trust, version=source.version) != source):
            raise _error('The selected installation version could not be verified.')
        raw = await owner.discover_candidates()
        if resolve_installation(raw, request['adapter_id'], request['candidate_ref']) != source:
            raise _error('The local installation changed during the version check.')
    except CoreError as error:
        raise _error('The local version check was refused: ' + error.code + '.') from None
    except (OSError, ValueError):
        raise _error('The local installation is unavailable or changed.') from None
    def commit():
        with factory.unit_of_work() as uow:
            # The full discovery above revalidated the exact source identity
            # under the publication lock. Its duration must not expire its own
            # result. Keep checking ownership, authority and revision; this
            # records a version observation, never execution authorization.
            if guard != _authorize(owner, access, context, request, uow=uow, identity_reobserved=True):
                raise _error('Operator authority changed during the version check.')
            conn = uow.connection
            count = conn.execute('SELECT COUNT(*) FROM execution_local_observations WHERE server_id=? AND executor_id=?',
                                 (owner.key.server_id, owner.key.executor_id)).fetchone()[0]
            exists = conn.execute('SELECT 1 FROM execution_local_observations WHERE server_id=? AND executor_id=? AND candidate_ref=?',
                                  (owner.key.server_id, owner.key.executor_id, request['candidate_ref'])).fetchone()
            if count >= 64 and not exists:
                raise _error('The local installation observation limit has been reached.')
            conn.execute('INSERT INTO execution_local_observations VALUES (?,?,?,?,?,?,?,?,?) '
                'ON CONFLICT(server_id,executor_id,candidate_ref) DO UPDATE SET '
                'core_version=excluded.core_version,platform=excluded.platform,source_json=excluded.source_json,'
                'version=excluded.version,actor_agent_id=excluded.actor_agent_id,observed_at=excluded.observed_at',
                (owner.key.server_id, owner.key.executor_id, request['candidate_ref'], CORE_VERSION, sys.platform,
                 canonical_json(asdict(source)).decode(), observed.version, context.actor_agent_id, access.clock.now_iso()))
            access.authorize(context, uow=uow, audit=True, represented_agent_id=request['agent_id'])
    await asyncio.to_thread(commit)
    # Publication failure does not erase the durable observation. Passive
    # refresh/restart can publish it without running --version again.
    await owner._refresh()
    return dict(executor_id=owner.key.executor_id, candidate_ref=request['candidate_ref'],
                version=observed.version, runtime_authorized=False, publication_pending=False)
