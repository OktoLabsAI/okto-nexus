"""Real router/UoW boundaries over a synthetic canonical isolated project."""
import hashlib
import subprocess

import pytest
from fastapi.testclient import TestClient

from tests.ui_simplification.test_fixtures import fixtures
from tests.ui_simplification.test_passive_effects import TABLES


def test_presentation_negotiation_is_explicit_rejects_ambiguity_and_does_not_mutate(tmp_path, monkeypatch):
    with fixtures.scenario(tmp_path / 'negotiation') as s:
        def snapshot():
            with s.factory.unit_of_work(write=False) as uow:
                data = {name: [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + name + ' ORDER BY rowid')]
                        for name in TABLES}
            return hashlib.sha256(repr(data).encode()).hexdigest()
        before = snapshot()
        monkeypatch.setattr(subprocess, 'Popen', lambda *a, **kw: pytest.fail('A Home read must not start or probe a process'))
        client = TestClient(s.app, headers={'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']})
        try:
            info = client.get('/api/v1/info')
            assert info.status_code == 200, info.text
            assert info.json()['data']['home_presentation_versions'] == [1, 2]
            legacy = client.get('/api/v1/home/harness-board')
            assert legacy.status_code == 200, legacy.text
            assert legacy.json()['data']['presentation_version'] == 1
            assert 'operational_summary' not in legacy.json()['data']
            current = client.get('/api/v1/home/harness-board', params={'presentation_version': 2})
            assert current.status_code == 200, current.text
            assert current.json()['data']['presentation_version'] == 2
            assert 'operational_summary' in current.json()['data']
            for query in ('presentation_version=0', 'presentation_version=3', 'presentation_version=true',
                          'presentation_version=02', 'presentation_version=', 'presentation_version=2&presentation_version=2'):
                response = client.get('/api/v1/home/harness-board?' + query)
                assert response.status_code == 422, (query, response.text)
            for path in ('overview', 'board'):
                assert client.get('/api/v1/home/' + path, params={'presentation_version': 2}).status_code == 422
            denied = client.get('/api/v1/home/harness-board', params={'presentation_version': 2},
                                headers={'Authorization': 'Bearer deliberately-invalid-key'})
            assert denied.status_code in (401, 403), denied.text
        finally:
            client.close()
        assert snapshot() == before
