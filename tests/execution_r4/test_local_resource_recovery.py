import asyncio
from contextlib import contextmanager
import os
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient
from nexus_connector_core import OperationKey, SessionKey
from nexus_connector_core.journal import SQLiteJournal
from nexus_connector_core.native.process import spawn_owned_process, snapshot_owned_process_birth

from test_embedded_dispatch import connected_local, admit, wait_receipt, qualified_contract
from test_local_realization import local_setup
from test_embedded_inventory import app_for


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows durable container recovery')
@pytest.mark.parametrize('legacy', [False, True])
def test_restart_recovers_containers_or_requires_scoped_operator_attestation(tmp_path, monkeypatch, legacy):
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, None) as setup:
        setup, binding, native = connected_local.__wrapped__(setup)
        deps, app, client, headers, *_ = setup
        opened = admit(setup, binding, 'retained-open', 'runtime.start', new_session=True)
        wait_receipt(setup, opened)
        owner = app.state.embedded_dispatch_owner
        channel = owner.channel
        session_id = opened['scope']['session_id']
        journal_path = owner.host._journal_path(channel.executor_id, session_id)
    # Model the crash window after process stop but before durable slot release.
    with sqlite3.connect(tmp_path / 'home/core-runtime/owned-slots.db') as db:
        db.execute('UPDATE owned_slot_reservations SET released=0')
    if not legacy:
        process = spawn_owned_process([sys.executable, '-c', 'import time; time.sleep(60)'],
            cwd=os.getcwd(), env=dict(os.environ), text=True)
        try:
            evidence = snapshot_owned_process_birth(process)
        finally:
            process.kill(); process.wait(timeout=5)
        async def record():
            journal = SQLiteJournal(journal_path)
            try:
                key = OperationKey(channel.server_id, channel.executor_id, opened['operation_id'])
                expected = await journal.record_process_birth(key, session_id, evidence)
                assert await journal.get_process_birth(SessionKey(channel.server_id, channel.executor_id, session_id)) == expected
            finally:
                await journal.aclose()
        asyncio.run(record())
    deps, app = app_for(tmp_path / 'home')
    with TestClient(app) as client:
        owner = app.state.embedded_dispatch_owner
        prefix = '/api/v1/runtime-management/runtime/recovery'
        if legacy:
            assert owner.pump is None
            assert client.post('/v1/runtime/recovery/retry', headers=headers['subject']).status_code == 403
            assert client.post(prefix + '/retry').status_code == 401
            response = client.post(prefix + '/retry', headers=headers['operator'], json={})
            assert response.status_code == 200, response.text
            assert response.json()['state'] == 'RECOVERING'
            plan_response = client.get(prefix + '/plan', headers=headers['operator'])
            assert plan_response.status_code == 200, plan_response.text
            plan = plan_response.json()
            assert plan['sessions'] == [{'session_id': session_id, 'opening_operation_id': opened['operation_id'], 'agent_id': 'subject'}]
            assert client.post(prefix + '/confirm-stopped', headers=headers['operator'], json={'plan': plan}).status_code == 422
            confirmation = 'PREVIOUS_RUNTIME_PROCESSES_STOPPED'
            stale = dict(plan, generation=plan['generation'] - 1)
            assert client.post(prefix + '/confirm-stopped', headers=headers['operator'],
                json={'plan': stale, 'confirmation': confirmation}).status_code == 409
            response = client.post(prefix + '/confirm-stopped', headers=headers['operator'],
                json={'plan': plan, 'confirmation': confirmation})
            assert response.status_code == 200, response.text
            assert response.json()['state'] == 'READY'
        assert owner.pump is not None
        pump = owner.pump
        response = client.post('/v1/runtime/recovery/retry', headers=headers['operator'])
        assert response.status_code == 200 and response.json()['state'] == 'READY'
        assert owner.pump is pump
        assert native.opens == 1
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions WHERE session_id=?', (session_id,)).fetchone()[0] == 'CLOSED'
            code = 'RECOVERY_OPERATOR_CONFIRMED_STOPPED' if legacy else 'RECOVERY_CONTAINER_STOPPED'
            assert uow.connection.execute('SELECT COUNT(*) FROM runtime_recovery_events WHERE code=?', (code,)).fetchone()[0] == 1
            assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 1
