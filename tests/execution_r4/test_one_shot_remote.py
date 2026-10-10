import asyncio
from pathlib import Path

import pytest
from nexus_connector_core import RuntimeEvent
from test_binding_operator import onboarding


async def run_one_shot(deps, client, headers, binding, native, execution, monkeypatch):
    from okto_nexus.application.one_shot_runtime import tick
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    client.headers['host'] = '127.0.0.1:8000'
    def rows(sql):
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return [dict(r) for r in uow.connection.execute(sql)]
    async def until(check):
        async with asyncio.timeout(20):
            while not check():
                assert execution.failure is None, repr(execution.failure)
                await asyncio.to_thread(tick, deps)
                await asyncio.sleep(.03)
    for number in range(2):
        reply = await asyncio.to_thread(tool, client, headers['operator']['Authorization'].removeprefix('Bearer '),
            'message_create', dict(workspace_id=binding['workspace_id'], from_agent_id='operator',
            target=dict(strategy='direct', agent_id='subject'), subject='Remote one shot', body=f'Call {number}'))
        assert reply['ok'], reply
    assert len(rows("SELECT * FROM one_shot_calls WHERE state='QUEUED'")) == 1
    sessions = []
    for number in range(2):
        await until(lambda: len(rows("SELECT * FROM one_shot_calls WHERE state='RUNNING'")) == 1
                    and len(native.native.sent) == 1)
        turn = rows("SELECT o.* FROM execution_operations o JOIN execution_domain_deliveries d "
            "USING(server_id,executor_id,operation_id) JOIN one_shot_calls c ON c.call_id=d.domain_operation_id "
            "WHERE o.action='turn.submit' AND c.state='RUNNING'")[0]
        sessions.append(turn['session_id'])
        peer = native.native
        await peer.queue.put(RuntimeEvent(binding['server_id'], binding['executor_id'], turn['session_id'],
            native.stream_epoch, 0, 'turn_state', 'fixture.result',
            dict(delivery_phase='terminal', delivery_outcome='success', output_text=f'Remote result {number}'),
            operation_id=turn['operation_id']))
        await until(lambda: len(rows("SELECT * FROM one_shot_calls WHERE state='SUCCEEDED'")) == number + 1
                    and peer.stopped)
    await until(lambda: not rows('SELECT * FROM one_shot_slots'))
    assert len(set(sessions)) == 2 and native.opens == 2
    assert len(rows("SELECT * FROM execution_sessions WHERE lifecycle_state='CLOSED' AND lease_state='CLOSED'")) == 2


@pytest.mark.parametrize('onboarding', ['connector-configured'], indirect=True)
def test_remote_connector_queues_disposes_and_opens_fresh_session(onboarding, tmp_path, monkeypatch):
    from test_remote_connection import test_owned_connector_reader_dispatches_five_actions_over_real_websocket
    test_owned_connector_reader_dispatches_five_actions_over_real_websocket(
        onboarding, tmp_path, monkeypatch, True, None, False, 0, None, domain_delivery=True, one_shot=True)


@pytest.mark.parametrize('onboarding', ['connector-configured'], indirect=True)
def test_remote_pool_ready_sessions_run_during_blocked_replenishment(onboarding, tmp_path, monkeypatch):
    import sys
    from test_remote_connection import test_owned_connector_reader_dispatches_five_actions_over_real_websocket

    async def scenario(deps, client, headers, binding, native, execution, monkeypatch):
        from okto_nexus.application.one_shot_runtime import tick
        from okto_nexus.application.one_shot_settings import read, save
        from test_pr34_remediation import tool
        client.headers['host'] = '127.0.0.1:8000'
        with deps.connection_factory.unit_of_work() as uow:
            current = read(uow.connection)
            save(uow.connection, expected_revision=current['revision'],
                 settings=current['settings'] | {'max_parallel': 6, 'warm_instances': 4})
        peers, scopes, blocked = {}, {}, []
        hold = False
        release = asyncio.Event()
        original = native.open

        async def opening(prepared, session_id, context, *, stream_epoch):
            if hold:
                blocked.append(session_id)
                await release.wait()
            peer = await original(prepared, session_id, context, stream_epoch=stream_epoch)
            peers[session_id] = peer
            scopes[session_id] = (context.server_id, context.executor_id, session_id, stream_epoch)
            return peer
        monkeypatch.setattr(native, 'open', opening)

        def rows(sql, args=()):
            with deps.connection_factory.unit_of_work(write=False) as uow:
                return [dict(r) for r in uow.connection.execute(sql, args)]

        async def until(check):
            async with asyncio.timeout(30):
                while not check():
                    assert execution.failure is None, repr(execution.failure)
                    await asyncio.to_thread(tick, deps)
                    await asyncio.sleep(.03)

        await until(lambda: len(rows("SELECT * FROM one_shot_slots WHERE state='WARM'")) == 4)
        original_sessions = set(peers)
        hold = True
        try:
            for number in range(4):
                reply = await asyncio.to_thread(tool, client, headers['operator']['Authorization'].removeprefix('Bearer '),
                    'message_create', dict(workspace_id=binding['workspace_id'], from_agent_id='operator',
                    target=dict(strategy='direct', agent_id='subject'), subject='Independent remote pool', body=f'Call {number}'))
                assert reply['ok'], reply
                if number < 2:
                    await until(lambda: len(blocked) >= number + 1)
            await until(lambda: sum(bool(peers[s].sent) for s in original_sessions) == 4)
            assert len(blocked) == 2 and not release.is_set()
            turns = rows("SELECT o.* FROM execution_operations o JOIN execution_domain_deliveries d "
                "USING(server_id,executor_id,operation_id) JOIN one_shot_calls c ON c.call_id=d.domain_operation_id "
                "WHERE o.action='turn.submit' AND c.state='RUNNING'")
            assert {t['session_id'] for t in turns} == original_sessions
            for turn in turns:
                await peers[turn['session_id']].queue.put(RuntimeEvent(*scopes[turn['session_id']], 0, 'turn_state', 'fixture.result',
                    dict(delivery_phase='terminal', delivery_outcome='success', output_text='Independent remote response'),
                    operation_id=turn['operation_id']))
            await until(lambda: len(rows("SELECT * FROM one_shot_calls WHERE state='SUCCEEDED'")) == 4)
            assert not release.is_set()
        finally:
            hold = False
            release.set()
        await until(lambda: len(rows("SELECT * FROM one_shot_slots WHERE state='WARM'")) == 4)
        assert all(peers[s].stopped for s in original_sessions)

    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    monkeypatch.setattr(sys.modules[__name__], 'run_one_shot', scenario)
    test_owned_connector_reader_dispatches_five_actions_over_real_websocket(
        onboarding, tmp_path, monkeypatch, True, None, False, 0, None, domain_delivery=True, one_shot=True)
