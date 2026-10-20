"""T22: one logical candidate across two separately running remote executors."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import fields
import json
import os
from pathlib import Path
import site
import socket
import sys

import pytest
import uvicorn
from nexus_connector_core import InstallationCandidate
from nexus_connector_core.discovery import fingerprint

from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from okto_nexus.adapters.outbound.execution.core_inventory import local_inventory_snapshot
from okto_nexus.application.handoff_runtime_scheduler import HandoffScheduleLease
from okto_nexus.application.execution_inventory_freshness import inventory_is_fresh
from okto_nexus.application.execution_inventory_revalidation import accepts_binding
from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_candidates
from okto_nexus.domain.base import iso_plus
from test_binding_operator import onboarding, prepare_operator
from test_runtime_policy_defaults import save


def bind(client, headers, proposal, name):
    _, apply = prepare_operator(client, headers, proposal)
    apply['client_intent_id'] = name + '-apply'
    response = client.post('/v1/connections/bindings:apply', headers=headers['operator'], json=apply)
    assert response.status_code == 200, response.text
    return response.json()


def second_remote(onboarding, tmp_path, workspace_id):
    from okto_nexus_connector.services.launch_configuration import stage_launch_configuration
    from okto_nexus_connector.services.realization_service import (
        stage_local_realization, publication_body, acknowledge_local_realization)
    from okto_nexus_connector.storage.state_store import StateStore
    from okto_nexus_connector.transport.https_client import R4Realization
    _, client, headers, _ = onboarding
    response = client.post('/v1/connections/executors:register', headers=headers['subject'], json=dict(
        client_intent_id='register-second', connector_id='connector-second', label='Remote host', control_capabilities=[]))
    assert response.status_code == 201, response.text
    registered = response.json()
    executor = registered['executor_id']
    ticket = {'Authorization': 'Bearer ' + registered['bootstrap_ticket']['ticket']}
    binary = tmp_path / 'second-codex.exe'
    binary.write_bytes(b'Synthetic separate remote installation')
    candidate = InstallationCandidate('codex_app_server', str(binary), fingerprint(binary), 'explicit', 'selected')
    snapshot = local_inventory_snapshot([candidate], server_id=registered['server_id'], executor_id=executor,
                                        producer_instance_id='second-peer', publication_sequence=1)
    response = client.put(f'/v1/runtime/executors/{executor}/inventory', headers=ticket, json=snapshot)
    assert response.status_code == 200, response.text
    store = StateStore(tmp_path / 'second-state.json')
    config = stage_launch_configuration(store, server_id=registered['server_id'], executor_id=executor,
        agent_id='subject', local_consent_id='second-consent', adapter_id=candidate.adapter_id,
        profile_revision=1, secret_bindings={'OPENAI_API_KEY': 'vault:provider-demo'})
    workspace_root = tmp_path / 'second-workspace'
    workspace_root.mkdir()
    local = stage_local_realization(store, server_id=registered['server_id'], executor_id=executor,
        agent_id='subject', client_intent_id='second-realization', candidates=[candidate],
        adapter_id=candidate.adapter_id, candidate_ref=snapshot['evidence'][0]['candidate_ref'],
        inventory_revision=snapshot['inventory_revision'], workspace_root=workspace_root,
        workspace_id=workspace_id, workspace_label='Same logical workspace',
        configuration_digest=config.configuration_digest, local_consent_id='second-consent')
    response = client.post(f'/v1/runtime/executors/{executor}/realizations', headers=ticket, json=publication_body(local))
    assert response.status_code == 201, response.text
    realization = response.json()
    acknowledge_local_realization(store, record=local, published=R4Realization(**{
        field.name: realization[field.name] for field in fields(R4Realization)}))
    binding = bind(client, headers, dict(client_intent_id='second-prepare', agent_id_hint='subject',
        executor_id=executor, adapter_id=candidate.adapter_id, candidate_ref=snapshot['evidence'][0]['candidate_ref'],
        inventory_revision=snapshot['inventory_revision'], realization_ref=realization['realization_ref'],
        workspace_id=workspace_id, alias='second'), 'second')
    return binding, store, binary, workspace_root, 'connector-second', 'register-second'


@asynccontextmanager
async def running_pair(onboarding, records, tmp_path, *, managed_native=False):
    import nexus_connector_core
    import okto_nexus_connector
    from okto_nexus_connector.services.execution_selection import acknowledge_execution_binding
    from okto_nexus_connector.transport.https_client import R4BindingView
    from okto_nexus_connector.storage.state_store import StateStore
    from okto_nexus_connector.platform.paths import state_dir, state_file
    deps, client, headers, _ = onboarding
    registry = deps.runtime_availability
    registry.enabled = True
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    server = uvicorn.Server(uvicorn.Config(client.app, lifespan='off', log_level='error'))
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    children, logs, configs = [], [], []

    async def spawn(index, config, *, suffix=''):
        log = (tmp_path / f'selection-{index}{suffix}.stderr').open('wb')
        logs.append(log)
        # A Windows venv executable can be a redirector with a different PID
        # from the Python worker. Use the real interpreter so a crash cut
        # terminates the process that owns the Core journal and control link.
        child = await asyncio.create_subprocess_exec(getattr(sys, '_base_executable', sys.executable), '-I', '-u',
            str(Path(__file__).with_name('capacity_connector_process.py')),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=log,
            creationflags=0x08000000 if os.name == 'nt' else 0)
        if index == len(children):
            children.append(child)
        else:
            children[index] = child
        child.stdin.write((json.dumps(config) + '\n').encode())
        await child.stdin.drain()
        return child

    async def command(index, name):
        if name == 'kill':
            child = children[index]
            if child.returncode is None:
                child.kill()  # Only the child created by this disposable test.
                await asyncio.wait_for(child.wait(), 15)
            return dict(pid=child.pid, returncode=child.returncode)
        if name == 'restart':
            previous = children[index]
            if previous.returncode is None:
                previous.kill()  # Only the child created by this disposable test.
                await asyncio.wait_for(previous.wait(), 15)
            child = await spawn(index, configs[index], suffix='-restart')
            return dict(previous_pid=previous.pid, pid=child.pid)
        child = children[index]
        child.stdin.write((json.dumps({'command': name}) + '\n').encode())
        await child.stdin.drain()
        line = await asyncio.wait_for(child.stdout.readline(), 120)
        assert line, ('Connector child exited: ' +
            (tmp_path / f'selection-{index}.stderr').read_text(errors='replace')[-2500:])
        return json.loads(line)

    try:
        async with asyncio.timeout(5):
            while not server.started:
                if serving.done():
                    await serving
                await asyncio.sleep(.01)
        _, revisions, _ = current_agent_revisions(deps.connection_factory, agent_id='subject')
        for index, (binding, store, binary, workspace_root, connector_id, intent) in enumerate(records):
            binding.update(configuration_revision=revisions.configuration, authorization_revision=revisions.authorization)
            acknowledge_execution_binding(store, binding=R4BindingView(**binding))
            root = state_dir(tmp_path / ('selection-daemon-' + str(index)))
            state = store.load()
            state.preferences['vault.fallback_file.approved'] = True
            StateStore(state_file(root)).save(state)
            config = dict(root=str(root), base_url=f'http://127.0.0.1:{sock.getsockname()[1]}',
                server_id=binding['server_id'], executor_id=binding['executor_id'],
                connector_id=connector_id, register_intent=intent,
                credential_epoch=revisions.credential_epoch, agent_key=headers['subject']['Authorization'].removeprefix('Bearer '),
                binary=str(binary), workspace_root=str(workspace_root),
                real_native_child=managed_native,
                source_roots=[str(Path(module.__file__).resolve().parents[1])
                    for module in (nexus_connector_core, okto_nexus_connector)] + site.getsitepackages() + [site.getusersitepackages()])
            configs.append(config)
            await spawn(index, config)
        async with asyncio.timeout(180):
            while True:
                states = [await command(i, 'status') for i in range(len(records))]
                hosts = [registry.current_host(row[0]['server_id'], row[0]['executor_id']) for row in records]
                fresh = client.app.state.inventory_fresh_publications
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    accepted = []
                    for binding, *_ in records:
                        current = uow.connection.execute(
                            'SELECT c.publication_sequence,c.inventory_revision,s.observation_age_ms,'
                            's.canonical_projection FROM execution_inventory_current c '
                            'JOIN execution_inventory_snapshots s ON s.server_id=c.server_id '
                            'AND s.executor_id=c.executor_id AND s.publication_sequence=c.publication_sequence '
                            'WHERE c.server_id=? AND c.executor_id=?',
                            (binding['server_id'], binding['executor_id'])).fetchone()
                        marker = fresh.get((binding['server_id'], binding['executor_id']))
                        selected = uow.connection.execute(
                            'SELECT b.*,ep.adapter_id,e.control_state FROM execution_bindings b '
                            'JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id '
                            'JOIN execution_executors e ON e.server_id=b.server_id AND e.executor_id=b.executor_id '
                            'WHERE b.server_id=? AND b.binding_id=?',
                            (binding['server_id'], binding['binding_id'])).fetchone()
                        accepted.append(current is not None and marker is not None
                                        and selected is not None
                                        and selected['control_state'] == 'CONTROL_READY'
                                        and marker[0] == current['publication_sequence']
                                        and inventory_is_fresh(current, marker, selected['adapter_id'])
                                        and accepts_binding(uow.connection, selected, current['inventory_revision'],
                                                            binding['server_id'], binding['executor_id']))
                if all(state['ready'] and state['pid'] == children[index].pid
                       and host and row[0]['binding_id'] in host.observations and accepted[index]
                       for index, (state, host, row) in enumerate(zip(states, hosts, records))):
                    assert len({os.getpid(), *(state['pid'] for state in states)}) == len(records) + 1
                    break
                await asyncio.sleep(.1)
        yield command
    finally:
        cleanup_errors = []
        for index, child in enumerate(children):
            if child.returncode is None:
                try:
                    result = await command(index, 'stop')
                    while 'pending' not in result:
                        line = await asyncio.wait_for(child.stdout.readline(), 30)
                        assert line, 'Connector child exited before shutdown result'
                        result = json.loads(line)
                    assert result['pending'] == 0, result
                    assert await asyncio.wait_for(child.wait(), 15) == 0
                except (Exception, asyncio.CancelledError) as error:
                    cleanup_errors.append(error)
                finally:
                    if child.returncode is None:
                        child.kill()
                        await child.wait()
        server.should_exit = True
        try:
            await asyncio.wait_for(serving, 15)
        finally:
            sock.close()
            for log in logs:
                log.close()
        if cleanup_errors:
            raise cleanup_errors[0]


@pytest.mark.parametrize('onboarding', ['connector-configured'], indirect=True)
@pytest.mark.parametrize('mode', ['priority', 'group', 'ambiguous', 'busy_affinity', 'unresolved_affinity', 'revoked', 'unknown_native_reply', 'unknown_reconnect', 'unknown_host_restart'])
def test_one_candidate_selects_authorized_unambiguous_executor_without_busy_fallback(onboarding, tmp_path, monkeypatch, mode):
    if mode == 'unknown_host_restart' and os.name != 'nt':
        pytest.skip('M6 Windows Job host restart qualification')
    from okto_nexus_connector.storage.state_store import StateStore
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    unknown = mode in {'unknown_native_reply', 'unknown_reconnect', 'unknown_host_restart'}
    if mode in {'unknown_reconnect', 'unknown_host_restart'}:
        from functools import partial
        from okto_nexus.adapters.inbound.http import executor_link
        # The production disconnect path preserves a granted lease until its
        # deadline. Shorten the granted duration, not the cleanup guarantee.
        monkeypatch.setattr(executor_link, 'ExecutionLeaseService',
            partial(executor_link.ExecutionLeaseService, max_duration_ms=15000))
    deps, client, headers, proposal = onboarding
    first = bind(client, headers, proposal, 'first')
    records = [(first, StateStore(tmp_path / 'connector-state.json'), tmp_path / 'remote-only' / 'codex.exe',
                tmp_path / 'remote-workspace', 'connector', 'register')]
    records.append(second_remote(onboarding, tmp_path, first['workspace_id']))
    second = records[1][0]
    assert first['executor_id'] != second['executor_id']
    assert save((deps, client.app, client, headers), agent='subject', session_policy='shared', broadcast_handoff_auto_claim=True).status_code == 200
    with deps.connection_factory.unit_of_work() as uow:
        # Current onboarding replaces the previous remote machine. T22 also
        # requires safe discovery for a restored/historical catalog containing
        # two approved executors. Seed that catalog shape explicitly, then use
        # real grants, scope checks, live owners and capacity for both hosts.
        # This does not change the product's machine-replacement policy.
        uow.connection.execute("UPDATE agent_endpoints SET enabled=1,activation_state='approved' WHERE endpoint_id=?",
                               (first['endpoint_id'],))
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none',consumption='exclusive',priority=1,selection_group=?",
                               ('approved-equivalents' if mode == 'group' else None,))
        if mode in {'priority', 'busy_affinity', 'unresolved_affinity'} or unknown:
            uow.connection.execute('UPDATE agent_endpoints SET priority=10 WHERE endpoint_id=?', (second['endpoint_id'],))
    grants = []
    for binding in (first, second):
        for actions in (['execute_work'], ['open', 'send', 'close']):
            response = client.post('/api/v1/harness/grants', headers=headers['operator'], json=dict(
                actor_agent_id='subject', endpoint_id=binding['endpoint_id'], actions=actions, max_executions=10,
                expires_at=iso_plus(deps.clock.now_iso(), 600)))
            assert response.status_code == 200, response.text
            if actions == ['execute_work']:
                grants.append(response.json()['data']['grant_id'])
    if mode == 'revoked':
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE runtime_execution_grants SET revoked_at=? WHERE grant_id=?', (deps.clock.now_iso(), grants[0]))
    client.headers['host'] = '127.0.0.1:8000'

    async def wait(operation, stage):
        async with asyncio.timeout(25):
            while True:
                response = client.get('/v1/runtime/operations/' + operation, headers=headers['subject'])
                assert response.status_code == 200, response.text
                view = response.json()
                if view['executor_stage'] == stage:
                    return
                if stage != 'OUTCOME_UNKNOWN':
                    assert view['error'] is None, view
                else:
                    # An unknown native reply may close the transport before
                    # receipt recovery. This is uncertainty, never no-effect.
                    assert view['error'] is None or view['error']['possible_effect'] is True, view
                await asyncio.sleep(.05)

    async def admit(intent, **kwargs):
        response = client.post('/v1/runtime/intents:resolve', headers=headers['subject'], json=dict(
            client_intent_id='selection-' + intent, intent=intent, binding_id=first['binding_id'],
            workspace_binding_id=first['workspace_binding_id'], **kwargs))
        assert response.status_code == 200 and response.json()['can_submit'], response.text
        resolved = response.json()
        response = client.post('/v1/runtime/operations', headers=headers['subject'], json={
            key: resolved[key] for key in ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')})
        assert response.status_code == 202, response.text
        await wait(resolved['operation_id'], 'SUCCEEDED' if intent == 'runtime.close' else 'SUBMITTED')
        return resolved

    async def run():
        # A reconnect must recover the same durable native launch on every OS.
        async with running_pair(onboarding, records, tmp_path,
                                managed_native=mode in {
                                    'unknown_reconnect', 'unknown_host_restart'}) as command:
            if unknown:
                await command(1, 'lose_next_send')
            if mode in {'busy_affinity', 'unresolved_affinity'}:
                opened = await admit('runtime.start', new_session=True)
                if mode == 'busy_affinity':
                    await admit('turn.submit', session_id=opened['session_id'], text='Existing shared affinity is occupied')
                else:
                    with deps.connection_factory.unit_of_work() as uow:
                        uow.connection.execute("UPDATE execution_sessions SET lease_state='NONE' WHERE session_id=?", (opened['session_id'],))
            made = tool(client, headers['other']['Authorization'].removeprefix('Bearer '), 'handoff_create',
                dict(workspace_id=first['workspace_id'], from_agent_id='other', visibility='eligible',
                     target={'strategy': 'broadcast'}, payload='Single logical candidate'))
            assert made['ok'], made
            hid = made['data']['handoff_id']
            discovery = build_handoff_runtime_candidates(deps)
            page = discovery.prepare_page(HandoffScheduleLease(hid, first['workspace_id'], 0, 'pair', 0, 0, ''), limit=4)
            if mode in {'ambiguous', 'unresolved_affinity'}:
                assert page.attempt_ids == ()
                assert page.reason == ('AMBIGUOUS_BINDING' if mode == 'ambiguous' else 'RECOVERING')
            else:
                assert len(page.attempt_ids) == 1, page
                attempts = build_handoff_runtime_attempts(deps)
                selected = attempts.get(page.attempt_ids[0])
                expected = (first if mode == 'busy_affinity' else
                            min((first, second), key=lambda row: row['endpoint_id']) if mode == 'group' else second)
                assert selected.principal.endpoint_id == expected['endpoint_id']
                held = await attempts.reserve(selected.request.attempt_id)
                if mode == 'busy_affinity':
                    assert held.state == 'NOT_AVAILABLE' and held.reason in {'BUSY_AFFINITY', 'EARLIER_WORK_PENDING'}
                    assert not (await attempts.release(selected.request.attempt_id)).active
                else:
                    assert held.state == 'RESERVED', held
                    committed = attempts.claim(held.request.attempt_id)
                    admitted = await build_capacity_admission(deps).consume(committed.operation_id)
                    await wait(admitted.consumption.turn_operation_id,
                               'OUTCOME_UNKNOWN' if unknown else 'SUBMITTED')
            if unknown:
                # The child records a native send before losing its response.
                # Receipt uncertainty must preserve the winner even if another
                # authorized executor is idle and later becomes preferred.
                before = await command(1, 'status')
                assert before['ready'], 'Publishing a durable unknown fact must not collapse the connection'
                registry = deps.runtime_availability
                old_host = registry.current_host(second['server_id'], second['executor_id'])
                if mode == 'unknown_host_restart':
                    import time
                    from datetime import datetime
                    from okto_nexus.adapters.outbound.process_liveness import process_exited
                    assert before['opens'] == before['sends'] == 1
                    child_pid, = before['native_child_pids']
                    from okto_nexus_connector.platform.paths import state_dir
                    daemon_root = state_dir(tmp_path / 'selection-daemon-1')
                    import sqlite3
                    with sqlite3.connect(
                            f'file:{daemon_root / "owned-slots.db"}?mode=ro', uri=True) as ledger:
                        assert ledger.execute(
                            'SELECT released FROM owned_slot_reservations WHERE session_id=?',
                            (held.request.scope.session_id,),
                        ).fetchone()[0] == 0
                    await command(1, 'kill')
                    async with asyncio.timeout(5):
                        while process_exited(child_pid) is not True:
                            await asyncio.sleep(.05)
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        deadline = uow.connection.execute(
                            'SELECT valid_until_server FROM execution_leases '
                            'WHERE session_id=? ORDER BY lease_serial DESC LIMIT 1',
                            (held.request.scope.session_id,),
                        ).fetchone()[0]
                    await asyncio.sleep(max(0, datetime.fromisoformat(deadline).timestamp() - time.time() + .2))
                    await command(1, 'restart')
                else:
                    after = await command(1, 'disconnect')
                    assert not after['ready']
                # While the failed host drains/reconciles, the other executor
                # is live. Its availability still grants no right to replay.
                # Full reconnect/generation qualification belongs to T29.
                assert (await command(0, 'status'))['ready']
                if mode in {'unknown_reconnect', 'unknown_host_restart'}:
                    async with asyncio.timeout(60):
                        while True:
                            after = await command(1, 'status')
                            new_host = registry.current_host(second['server_id'], second['executor_id'])
                            if (after['ready'] and after['generation'] > before['generation']
                                    and new_host is not None and second['binding_id'] in new_host.observations):
                                break
                            await asyncio.sleep(.05)
                    assert new_host is not old_host and new_host.boot_id != old_host.boot_id
                    snapshot = dict(new_host.observations)
                    assert not registry.observe(old_host, binding_id=second['binding_id'], boot_id=old_host.boot_id,
                        revision=10**9, reason='AVAILABLE', valid_for_ms=60000)
                    from nexus_connector_core import CoreError
                    with pytest.raises(CoreError, match='STALE_OBSERVATION'):
                        registry.register(old_host.channel, old_host.port)
                    with pytest.raises(CoreError, match='STALE_OBSERVATION'):
                        await registry.consume_capacity(held.request, held.reservation.reservation_id, admitted.consumption)
                    registry.unregister(old_host)
                    assert registry.current_host(second['server_id'], second['executor_id']) is new_host
                    assert new_host.observations == snapshot
                    if mode == 'unknown_host_restart':
                        assert after['opens'] == after['sends'] == 0
                        with sqlite3.connect(
                                f'file:{daemon_root / "executor-journal.db"}?mode=ro', uri=True) as journal:
                            launch = journal.execute(
                                'SELECT spawn_claimed,producer_fenced,stop_proof '
                                'FROM process_launches WHERE session_id=?',
                                (held.request.scope.session_id,),
                            ).fetchone()
                        assert launch == (1, 1, 'CONTAINER_STOPPED')
                        with sqlite3.connect(
                                f'file:{daemon_root / "owned-slots.db"}?mode=ro', uri=True) as ledger:
                            assert ledger.execute(
                                'SELECT released FROM owned_slot_reservations WHERE session_id=?',
                                (held.request.scope.session_id,),
                            ).fetchone()[0] == 1
                        with deps.connection_factory.unit_of_work(write=False) as uow:
                            assert uow.connection.execute(
                                'SELECT attempt_no FROM execution_dispatch_outbox WHERE operation_id=?',
                                (admitted.consumption.turn_operation_id,),
                            ).fetchone()[0] == 1
                with deps.connection_factory.unit_of_work() as uow:
                    uow.connection.execute('UPDATE agent_endpoints SET priority=20 WHERE endpoint_id=?', (first['endpoint_id'],))
                for generation in (0, 1):
                    restarted = build_handoff_runtime_candidates(deps)
                    page = restarted.prepare_page(HandoffScheduleLease(
                        hid, first['workspace_id'], generation, 'after-unknown', 0, 0, ''), limit=4)
                    assert page.settled and not page.attempt_ids
                assert attempts.claim(selected.request.attempt_id).operation_id == committed.operation_id
                assert (await build_capacity_admission(deps).consume(committed.operation_id)).consumption == admitted.consumption
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    assert uow.connection.execute('SELECT count(*) FROM execution_capacity_compensations').fetchone()[0] == 0
                    receipt = uow.connection.execute('SELECT stage,possible_effect FROM execution_receipts WHERE operation_id=? '
                        "AND stage='OUTCOME_UNKNOWN'", (admitted.consumption.turn_operation_id,)).fetchone()
                    assert receipt[:] == ('OUTCOME_UNKNOWN', 1)
            states = [await command(i, 'status') for i in range(2)]
            successful = mode in {'priority', 'group', 'revoked'} or unknown
            assert sum(s['opens'] for s in states) == int(
                (successful or mode in {'busy_affinity', 'unresolved_affinity'})
                and mode != 'unknown_host_restart')
            assert sum(s['sends'] for s in states) == int(
                (successful or mode == 'busy_affinity')
                and mode != 'unknown_host_restart')
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT COUNT(*) FROM handoff_runtime_attempts').fetchone()[0] <= 1
                assert uow.connection.execute('SELECT COUNT(*) FROM runtime_handoff_bindings').fetchone()[0] == int(successful)
                assert uow.connection.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == (
                    ('CLAIMED', 1) if successful else ('OPEN', 0))
    asyncio.run(run())
