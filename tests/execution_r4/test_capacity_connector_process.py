"""T39: actual Server/Connector transport and journals in separate processes.

Source-tuple qualification with synthetic native peers, not a real-provider
or independent-machine claim. The Connector never opens the Server database.
"""
import asyncio
import json
import os
from pathlib import Path
import socket
import site
import sys

import pytest
import uvicorn

from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from okto_nexus.application.execution_inventory_freshness import inventory_is_fresh
from okto_nexus.application.execution_inventory_revalidation import accepts_binding
from okto_nexus.application.handoff_runtime_scheduler import HandoffScheduleLease
from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_candidates
from okto_nexus.domain.base import iso_plus
from test_binding_operator import onboarding, prepare_delegated, decide_binding
from test_runtime_policy_defaults import save


@pytest.mark.parametrize('onboarding', ['connector-configured'], indirect=True)
@pytest.mark.parametrize('restart_mode,receipt_fault,stop_during_open', [
    ('graceful', False, False), ('abrupt', False, False),
    ('abrupt', True, False), ('graceful', False, True)])
def test_capacity_survives_lost_reply_reconnect_and_connector_process_restart(
        onboarding, tmp_path, monkeypatch, restart_mode, receipt_fault,
        stop_during_open):
    import nexus_connector_core
    import okto_nexus_connector
    from okto_nexus_connector.services.execution_selection import acknowledge_execution_binding
    from okto_nexus_connector.storage.state_store import StateStore
    from okto_nexus_connector.transport.https_client import R4BindingView
    from okto_nexus_connector.platform.paths import state_dir, state_file
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool

    deps, client, headers, prepare = onboarding
    _, apply, approval = prepare_delegated(client, headers, prepare)
    assert decide_binding(client, headers, approval).status_code == 200
    response = client.post('/v1/connections/bindings:apply', headers=headers['subject'], json=apply)
    assert response.status_code == 200, response.text
    binding = response.json()
    setup = (deps, client.app, client, headers)
    assert save(setup, agent='subject', broadcast_handoff_auto_claim=True,
                session_policy='per_sender_session').status_code == 200
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none',consumption='exclusive' WHERE endpoint_id=?",
                               (binding['endpoint_id'],))
    for actions in (['execute_work'], ['open', 'send', 'steer', 'interrupt', 'close']):
        response = client.post('/api/v1/harness/grants', headers=headers['operator'], json=dict(
            actor_agent_id='subject', endpoint_id=binding['endpoint_id'], actions=actions,
            max_executions=10, expires_at=iso_plus(deps.clock.now_iso(), 600)))
        assert response.status_code == 200, response.text
    _, revisions, _ = current_agent_revisions(deps.connection_factory, agent_id='subject')
    binding.update(configuration_revision=revisions.configuration, authorization_revision=revisions.authorization)
    original = StateStore(tmp_path / 'connector-state.json')
    acknowledge_execution_binding(original, binding=R4BindingView(**binding))
    root = state_dir(tmp_path / 'isolated-connector')
    state = original.load()
    state.preferences['vault.fallback_file.approved'] = True
    StateStore(state_file(root)).save(state)
    registry = deps.runtime_availability
    registry.enabled = True
    client.headers['host'] = '127.0.0.1:8000'

    def new_candidate():
        origin = tool(client, headers['other']['Authorization'].removeprefix('Bearer '), 'session_open',
            dict(workspace_id=binding['workspace_id'], agent_id='other'))
        assert origin['ok'], origin
        made = tool(client, headers['other']['Authorization'].removeprefix('Bearer '), 'handoff_create',
            dict(workspace_id=binding['workspace_id'], from_agent_id='other', visibility='eligible',
                 target={'strategy': 'broadcast'}, payload='Cross-process reserved work',
                 **{key: origin['data'][key] for key in ('session_id', 'session_secret')}))
        assert made['ok'], made
        hid = made['data']['handoff_id']
        page = build_handoff_runtime_candidates(deps).prepare_page(
            HandoffScheduleLease(hid, binding['workspace_id'], 0, 'process-campaign', 0, 0, ''), limit=4)
        assert len(page.attempt_ids) == 1, page
        return hid, page.attempt_ids[0]

    async def run():
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        sock.listen()
        server = uvicorn.Server(uvicorn.Config(client.app, lifespan='off', log_level='error'))
        serving = asyncio.create_task(server.serve(sockets=[sock]))
        process = None
        log = (tmp_path / 'connector-process.stderr').open('wb')
        config = dict(root=str(root), base_url=f'http://127.0.0.1:{sock.getsockname()[1]}',
            server_id=binding['server_id'], executor_id=binding['executor_id'],
            credential_epoch=revisions.credential_epoch,
            agent_key=headers['subject']['Authorization'].removeprefix('Bearer '),
            binary=str(tmp_path / 'remote-only' / 'codex.exe'), workspace_root=str(tmp_path / 'remote-workspace'),
            source_roots=[str(Path(module.__file__).resolve().parents[1])
                          for module in (nexus_connector_core, okto_nexus_connector)]
                         + site.getsitepackages() + [site.getusersitepackages()])

        async def command(name):
            process.stdin.write((json.dumps({'command': name}) + '\n').encode())
            await process.stdin.drain()
            line = await asyncio.wait_for(process.stdout.readline(), 35)
            assert line, 'Connector worker exited; inspect connector-process.stderr'
            return json.loads(line)

        async def finish_process():
            # Drain/close all pipe transports before asyncio.run closes its
            # Proactor loop on Windows, including a cancelled stdout read.
            await asyncio.wait_for(process.communicate(), 15)
            return process.returncode

        async def start():
            nonlocal process
            process = await asyncio.create_subprocess_exec(sys.executable, '-I', '-u',
                str(Path(__file__).with_name('capacity_connector_process.py')),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=log,
                creationflags=0x08000000 if os.name == 'nt' else 0)
            process.stdin.write((json.dumps(config) + '\n').encode())
            await process.stdin.drain()
            await ready()

        async def ready(after_generation=0):
            last = {}
            try:
                async with asyncio.timeout(35):
                    while True:
                        state = await command('status')
                        host = registry.current_host(binding['server_id'], binding['executor_id'])
                        fresh = client.app.state.inventory_fresh_publications.get(
                            (binding['server_id'], binding['executor_id']))
                        with deps.connection_factory.unit_of_work(write=False) as uow:
                            conn = uow.connection
                            inventory = conn.execute(
                                'SELECT c.publication_sequence,c.inventory_revision,s.observation_age_ms,'
                                's.canonical_projection FROM execution_inventory_current c '
                                'JOIN execution_inventory_snapshots s ON s.server_id=c.server_id '
                                'AND s.executor_id=c.executor_id AND s.publication_sequence=c.publication_sequence '
                                'WHERE c.server_id=? AND c.executor_id=?',
                                (binding['server_id'], binding['executor_id'])).fetchone()
                            selected = conn.execute(
                                'SELECT b.inventory_revision,b.candidate_ref,ep.adapter_id '
                                'FROM execution_bindings b JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id '
                                'WHERE b.server_id=? AND b.binding_id=?',
                                (binding['server_id'], binding['binding_id'])).fetchone()
                            binding_ready = (inventory is not None and fresh is not None and selected is not None
                                and fresh[0] == inventory['publication_sequence']
                                and inventory_is_fresh(inventory, fresh, selected['adapter_id'])
                                and accepts_binding(conn, selected, inventory['inventory_revision'],
                                                    binding['server_id'], binding['executor_id']))
                            last = dict(connector_ready=state['ready'],
                                generation=state['generation'], host_generation=(host.channel.connection_generation
                                    if host else None), observed=(binding['binding_id'] in host.observations
                                    if host else False), publication=(inventory['publication_sequence'] if inventory else None),
                                fresh=(fresh[0] if fresh else None), selected=selected is not None,
                                binding_ready=binding_ready)
                        if (state['ready'] and state['generation'] > after_generation and host
                                and host.channel.connection_generation == state['generation']
                                and binding['binding_id'] in host.observations and binding_ready):
                            assert state['pid'] != os.getpid()
                            return state
                        await asyncio.sleep(.1)
            except TimeoutError:
                pytest.fail(f'Connector capacity readiness timeout: {last}')

        async def wait_turn(operation_id, stage, *, allow_uncertain=False):
            async with asyncio.timeout(35 if allow_uncertain else 25):
                while True:
                    response = client.get('/v1/runtime/operations/' + operation_id, headers=headers['subject'])
                    assert response.status_code == 200, response.text
                    view = response.json()
                    if view['executor_stage'] == stage:
                        return view
                    assert view['error'] is None or (allow_uncertain and
                        view['error']['code'] == 'DISPATCH_CONNECTION_LOST' and
                        view['error']['possible_effect']), view
                    await asyncio.sleep(.05)

        async def reserve_fresh(attempt_id):
            # Publication and binding revalidation can advance between the
            # readiness snapshot and an assessment. Only a pre-reservation
            # stale observation is retryable; keep uncertain writes visible.
            async with asyncio.timeout(30):
                while True:
                    try:
                        return await attempts.reserve(attempt_id)
                    except nexus_connector_core.CoreError as error:
                        if error.code != 'STALE_OBSERVATION':
                            raise
                        await asyncio.sleep(.05)

        try:
            async with asyncio.timeout(5):
                while not server.started:
                    if serving.done():
                        await serving
                    await asyncio.sleep(.01)
            await start()
            attempts = build_handoff_runtime_attempts(deps)
            _, aid = new_candidate()
            # Lose the Server application result after the real remote ledger
            # committed. Recovery must query the same identity over the link.
            class LostReply:
                def __getattr__(self, name):
                    return getattr(registry, name)
                async def try_reserve_capacity(self, request):
                    await registry.try_reserve_capacity(request)
                    raise ConnectionError('Synthetic lost reserve response')
            attempts.capacity = LostReply()
            with pytest.raises(ConnectionError, match='lost reserve'):
                await reserve_fresh(aid)
            original_request = attempts.get(aid).request
            attempts.capacity = registry
            held = await reserve_fresh(aid)
            assert held.state == 'RESERVED' and held.request == original_request
            assert (await command('status'))['opens'] == 0
            _, other = new_candidate()
            denied = await reserve_fresh(other)
            assert denied.state == 'NOT_AVAILABLE' and denied.reason == 'HOST_FULL'
            assert not (await attempts.release(other)).active
            generation = (await command('status'))['generation']
            await command('disconnect')
            await ready(generation)
            historical = await registry.get_capacity_reservation(original_request)
            assert historical.request == original_request
            assert not (await attempts.release(aid)).active
            assert (await command('status'))['opens'] == 0

            # Persist another unused ticket, terminate this process, and load
            # its original record from a new process with a different boot.
            _, restart_id = new_candidate()
            before = await reserve_fresh(restart_id)
            assert before.state == 'RESERVED'
            old_pid = process.pid
            if restart_mode == 'graceful':
                assert (await command('stop'))['pending'] == 0
                assert await finish_process() == 0
            else:
                # Only this disposable child is terminated; no provider has
                # started. Its journal/slot ledger must survive the process.
                process.kill()
                assert await finish_process() != 0
            await start()
            assert process.pid != old_pid
            assert registry.current_host(binding['server_id'], binding['executor_id']).boot_id != before.request.scope.boot_id
            recovered = await registry.get_capacity_reservation(before.request)
            assert recovered.request == before.request and recovered.reservation_id == before.reservation.reservation_id
            assert not (await attempts.release(restart_id)).active

            _, work_id = new_candidate()
            assert (await reserve_fresh(work_id)).state == 'RESERVED'
            if stop_during_open:
                assert (await command('hold_open'))['opening'] == 0
            committed = attempts.claim(work_id)
            admitted = await build_capacity_admission(deps).consume(committed.operation_id)
            if stop_during_open:
                async with asyncio.timeout(15):
                    while (opening_state := await command('status'))['opening'] != 1:
                        await asyncio.sleep(.05)
                assert opening_state['opens'] == 0
                assert (await command('begin_stop'))['stop_pending']
                await asyncio.sleep(.2)
                held = await command('status')
                assert held['stop_pending'] and held['opens'] == 0
                assert (await command('release_open'))['stop_pending']
                assert (await asyncio.wait_for(command('finish_stop'), 60))['pending'] == 0
                assert await finish_process() == 0
                assert process.returncode == 0
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    assert uow.connection.execute(
                        'SELECT COUNT(*) FROM execution_dispatch_outbox WHERE operation_id=? AND attempt_no>1',
                        (admitted.consumption.turn_operation_id,)).fetchone()[0] == 0
                return
            await wait_turn(admitted.consumption.turn_operation_id, 'SUBMITTED')
            state = await command('status')
            assert (state['opens'], state['sends'], state['stopped']) == (1, 1, 0), state
            _, waiting = new_candidate()
            unavailable = await reserve_fresh(waiting)
            assert unavailable.state == 'NOT_AVAILABLE' and unavailable.reason in {'BUSY_AFFINITY', 'HOST_FULL', 'EARLIER_WORK_PENDING'}
            await attempts.release(waiting)
            response = client.post('/v1/runtime/intents:resolve', headers=headers['subject'], json=dict(
                client_intent_id='process-campaign-close', intent='runtime.close',
                binding_id=binding['binding_id'], workspace_binding_id=binding['workspace_binding_id'],
                session_id=committed.request.scope.session_id))
            assert response.status_code == 200, response.text
            resolved = response.json()
            assert resolved['can_submit'], resolved
            if receipt_fault:
                prior_generation = (await command('status'))['generation']
                assert (await command('cut_next_receipt'))['receipt_cuts'] == 0
            response = client.post('/v1/runtime/operations', headers=headers['subject'], json={
                key: resolved[key] for key in ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')})
            assert response.status_code == 202, response.text
            await wait_turn(resolved['operation_id'], 'SUCCEEDED',
                            allow_uncertain=receipt_fault)
            state = await command('status')
            assert state['receipt_cuts'] == int(receipt_fault), state
            assert state['opens'] == 1 and state['stopped'] == 1, state
            if receipt_fault:
                state = await ready(prior_generation)
                assert state['ready'] and state['error'] is None, state
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    assert uow.connection.execute(
                        'SELECT COUNT(*) FROM execution_receipts WHERE operation_id=?',
                        (resolved['operation_id'],)).fetchone()[0] == 1
                    assert uow.connection.execute(
                        'SELECT COUNT(*) FROM execution_dispatch_outbox WHERE attempt_no<>1').fetchone()[0] == 0
                assert (await command('stop'))['pending'] == 0
                assert await finish_process() == 0
                return
            async with asyncio.timeout(15):
                while True:
                    released = await registry.release_capacity(committed.request, committed.reservation.reservation_id, 'CANCELLED')
                    if released.state == 'RELEASED':
                        break
                    assert released.state == 'RELEASE_PENDING'
                    await asyncio.sleep(.05)
            _, available_again = new_candidate()
            fresh = await reserve_fresh(available_again)
            assert fresh.state == 'RESERVED', fresh
            assert not (await attempts.release(available_again)).active
            assert (await command('status'))['opens'] == 1
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT COUNT(*) FROM runtime_handoff_bindings').fetchone()[0] == 1
                assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1
            assert (await command('stop'))['pending'] == 0
            assert await finish_process() == 0
        finally:
            if process is not None and process.returncode is None:
                try:
                    await command('stop')
                    await finish_process()
                except (Exception, asyncio.CancelledError):
                    if process.returncode is None:
                        process.kill()
                        await finish_process()
            server.should_exit = True
            await asyncio.wait_for(serving, 15)
            sock.close()
            log.close()
    asyncio.run(run())
