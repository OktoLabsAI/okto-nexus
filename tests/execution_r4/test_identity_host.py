"""Runtime identity ownership survives uncertain sessions and concurrent opens."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from okto_nexus.application.execution_identity_owner import require_identity_host
from okto_nexus.errors import OktoNexusError


@pytest.fixture
def database(tmp_path):
    path = tmp_path / 'owners.db'
    with sqlite3.connect(path) as conn:
        conn.executescript('''
            CREATE TABLE agent_endpoints(endpoint_id TEXT PRIMARY KEY, agent_id TEXT);
            CREATE TABLE execution_bindings(server_id TEXT,executor_id TEXT,binding_id TEXT,endpoint_id TEXT);
            CREATE TABLE execution_sessions(server_id TEXT,executor_id TEXT,binding_id TEXT,lifecycle_state TEXT,lease_state TEXT);
            INSERT INTO agent_endpoints VALUES ('ep','agent');
            INSERT INTO execution_bindings VALUES ('server','local','local-binding','ep');
            INSERT INTO execution_bindings VALUES ('server','remote','remote-binding','ep');
        ''')
    return path


@pytest.mark.parametrize('state', ['OPEN_PENDING', 'READY', 'RECONCILIATION_REQUIRED', 'CLOSED', 'FAILED'])
def test_owner_is_retained_until_terminal(database, state):
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('INSERT INTO execution_sessions VALUES (?,?,?,?,?)',
                     ('server', 'local', 'local-binding', state, 'ACTIVE'))
        require_identity_host(conn, server_id='server', agent_id='agent', executor_id='local')
        require_identity_host(conn, server_id='server', agent_id='another', executor_id='remote')
        if state in ('CLOSED', 'FAILED'):
            require_identity_host(conn, server_id='server', agent_id='agent', executor_id='remote')
        else:
            with pytest.raises(OktoNexusError) as caught:
                require_identity_host(conn, server_id='server', agent_id='agent', executor_id='remote')
            assert caught.value.details['reason'] == 'AGENT_RUNTIME_HOST_CONFLICT'


def test_simultaneous_hosts_cannot_both_claim_identity(database):
    gate = Barrier(2)
    def claim(host):
        with sqlite3.connect(database, isolation_level=None) as conn:
            conn.row_factory = sqlite3.Row
            gate.wait()
            conn.execute('BEGIN IMMEDIATE')
            try:
                require_identity_host(conn, server_id='server', agent_id='agent', executor_id=host)
                conn.execute('INSERT INTO execution_sessions VALUES (?,?,?,?,?)',
                             ('server', host, host+'-binding', 'OPEN_PENDING', 'ACTIVE'))
                conn.commit()
                return 'accepted'
            except OktoNexusError:
                conn.rollback()
                return 'rejected'
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(claim, ['local', 'remote'])) == ['accepted', 'rejected']
    with sqlite3.connect(database) as conn:
        assert conn.execute('SELECT count(*) FROM execution_sessions').fetchone()[0] == 1


def test_revoked_session_no_longer_owns_routing_identity(database):
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("INSERT INTO execution_sessions VALUES ('server','local','local-binding','READY','REVOKED')")
        require_identity_host(conn, server_id='server', agent_id='agent', executor_id='remote')
        assert conn.execute('SELECT lifecycle_state FROM execution_sessions').fetchone()[0] == 'READY'
