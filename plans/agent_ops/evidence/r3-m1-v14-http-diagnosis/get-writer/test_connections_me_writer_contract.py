"""Small SQL/HTTP characterization; no bootstrap workers, services or provider."""
import json
import sqlite3
import sys
import threading
from types import SimpleNamespace

import pytest

sys.path.insert(0, 'D:/Projetos/Techridy/okto_labs_okto_nexus/src')
from fastapi import FastAPI
from fastapi.testclient import TestClient
from okto_nexus.config import NexusConfig
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from okto_nexus.adapters.inbound.http import connections_v1


@pytest.fixture
def owner(tmp_path, monkeypatch):
    home = tmp_path / 'own-home'
    home.mkdir()
    config = NexusConfig(home_dir=home)
    factory = ConnectionFactory(config)
    db = factory.get_connection()
    db.executescript('''
        CREATE TABLE execution_installation(singleton INTEGER,server_id TEXT);
        INSERT INTO execution_installation VALUES(1,'own-server');
        CREATE TABLE agents(agent_id TEXT,permissions TEXT,comm_scope TEXT,is_active INTEGER,
            metadata TEXT,capabilities TEXT,api_key_hash TEXT);
        CREATE TABLE agent_connection_methods(agent_id TEXT,method TEXT);
        CREATE TABLE agent_endpoints(agent_id TEXT,endpoint_id TEXT,profile_id TEXT);
        CREATE TABLE runtime_profiles(profile_id TEXT);
        CREATE TABLE execution_agent_revisions(server_id TEXT,agent_id TEXT,authorization_revision INTEGER,
            configuration_revision INTEGER,credential_epoch INTEGER,authorization_digest TEXT,
            configuration_digest TEXT,credential_digest TEXT);
    ''')
    for name in ('reader', 'writer'):
        db.execute("INSERT INTO agents VALUES(?,NULL,'workspace',1,'{}','[]','fake-hash')", (name,))
    db.close()
    app = FastAPI()
    app.state.deps = SimpleNamespace(connection_factory=factory)
    app.include_router(connections_v1.build_router(), prefix='/v1')
    monkeypatch.setattr(connections_v1, 'get_authenticated_agent', lambda: SimpleNamespace(agent_id='writer'))
    with TestClient(app) as client:
        yield SimpleNamespace(factory=factory, config=config, client=client)
    factory.close()


def change(owner, value, agent=None):
    with owner.factory.unit_of_work() as uow:
        sql = 'UPDATE agents SET metadata=?' + (' WHERE agent_id=?' if agent else '')
        uow.connection.execute(sql, (json.dumps({'display_name': value}), agent) if agent else (json.dumps({'display_name': value}),))


def test_get_me_waits_on_actual_external_sqlite_writer(owner, monkeypatch):
    attempting_writer, returned = threading.Event(), threading.Event()
    original_open = owner.factory._open_connection
    def traced_connection(*args, **kwargs):
        db = original_open(*args, **kwargs)
        db.set_trace_callback(lambda sql: attempting_writer.set() if sql == 'BEGIN IMMEDIATE' else None)
        return db
    monkeypatch.setattr(owner.factory, '_open_connection', traced_connection)
    first = owner.client.get('/v1/connections/me')
    assert first.status_code == 200 and first.json()['revisions']['configuration'] == 1
    attempting_writer.clear()
    external = sqlite3.connect(owner.config.db_path, isolation_level=None)
    external.execute('BEGIN IMMEDIATE')
    external.execute("UPDATE agents SET metadata=? WHERE agent_id='writer'", (json.dumps({'display_name': 'B'}),))
    result = {}
    def get():
        try:
            result['response'] = owner.client.get('/v1/connections/me')
        except BaseException as exc:
            result['error'] = exc
        finally:
            returned.set()
    thread = threading.Thread(target=get)
    thread.start()
    try:
        assert attempting_writer.wait(2), 'GET did not reach its real BEGIN IMMEDIATE'
        assert not returned.wait(.15), 'GET unexpectedly completed before the external writer released'
        # This snapshot remains available while the writer is held, confirming
        # the contention is not a blanket inability to read the own WAL DB.
        _, revision, projection = current_agent_revisions(owner.factory, agent_id='writer', persist=False)
        assert revision.configuration == 1 and projection['metadata'] == {}
    finally:
        external.commit()
        external.close()
        thread.join(3)
    assert returned.is_set() and 'error' not in result
    response = result['response']
    assert response.status_code == 200
    assert response.json()['display_name'] == 'B' and response.json()['revisions']['configuration'] == 2


def test_readonly_projection_collapses_successive_changes_without_persisting(owner):
    for agent in ('reader', 'writer'):
        assert current_agent_revisions(owner.factory, agent_id=agent)[1].configuration == 1
    observed = []
    for name in ('B', 'C'):
        change(owner, name)
        readonly = current_agent_revisions(owner.factory, agent_id='reader', persist=False)[1].configuration
        response = owner.client.get('/v1/connections/me')
        assert response.status_code == 200
        observed.append((readonly, response.json()['revisions']['configuration']))
    assert observed == [(2, 2), (2, 3)]


def test_no_baseline_readonly_projection_keeps_revision_one(owner):
    assert current_agent_revisions(owner.factory, agent_id='writer', persist=False)[1].configuration == 1
    change(owner, 'B', 'writer')
    assert current_agent_revisions(owner.factory, agent_id='writer', persist=False)[1].configuration == 1
    first = owner.client.get('/v1/connections/me')
    assert first.json()['revisions']['configuration'] == 1
    change(owner, 'C', 'writer')
    assert owner.client.get('/v1/connections/me').json()['revisions']['configuration'] == 2
