"""Provider startup errors stay private through actual serve projections."""
import json
import time

import pytest

import runtime_serve_shutdown_fixture as fixture
from test_canonical_owner_process import rows
from test_pr34_remediation import tool


SECRET = 'fixture-opaque-backend-credential-43816'


@pytest.mark.parametrize('boundary', ['construct', 'start'])
@pytest.mark.parametrize('surface', ['rest', 'mcp'])
def test_native_start_failure_keeps_secret_out_of_public_history(tmp_path, monkeypatch, boundary, surface):
    injected = '''    from nexus_connector_core.native import runtime_bridge
    async def environment(prepared):
        return {"FIXTURE_BACKEND_KEY": SECRET}
    def construct(**options):
        value=options["env"]["FIXTURE_BACKEND_KEY"]
        assert value==SECRET
        Path(marker+".boundary").write_text(BOUNDARY,encoding="utf-8")
        if BOUNDARY=="construct":
            raise RuntimeError("Fixture constructor diagnostic "+value)
        connector=PiRpcConnector(command=[sys._base_executable,"-u",peer,marker],cwd=options["cwd"],env=options["env"])
        def fail(**kwargs):
            raise RuntimeError("Fixture handshake diagnostic "+value)
        connector.start=fail
        return connector
    runtime_bridge.qualified_build=lambda *a,**k:True
    runtime_bridge.load_adapter=lambda _:construct
    self.fixture_native_factory=runtime_bridge.CopiedAdapterFactory(environment)
'''.replace('SECRET', repr(SECRET)).replace('BOUNDARY', repr(boundary))
    launcher = fixture.LAUNCHER.replace('    self.fixture_native_factory=Factory()\n', injected)
    assert launcher != fixture.LAUNCHER
    monkeypatch.setattr(fixture, 'LAUNCHER', launcher)
    server = fixture.ServeFixture(tmp_path)
    try:
        server.open(start_native=False)
        body = dict(agent_id='shutdown-fixture', kind='pi', endpoint_id=server.binding['endpoint_id'],
                    project_root=str(server.project), idempotency_key='startup-secret')
        if surface == 'rest':
            response = server.client.post('/api/v1/harness/sessions',
                headers={'Authorization': 'Bearer ' + server.subject}, json=body)
            assert response.status_code == 200, response.text
            opened = response.json()
        else:
            opened = tool(server.client, server.subject, 'harness_open', body)
        assert opened['ok'], opened
        deadline = time.monotonic() + 10
        while not rows(server, "SELECT 1 FROM execution_agent_recovery WHERE agent_id='shutdown-fixture' AND state='RECOVERING' AND error_code='RuntimeError'"):
            assert server.process.poll() is None
            assert time.monotonic() < deadline, server.log_path.read_text(encoding='utf-8')
            time.sleep(.02)
        response = server.client.get('/v1/runtime/operations/' + opened['data']['operation_id'],
            headers={'Authorization': 'Bearer ' + server.subject})
        assert response.status_code == 200, response.text
        failed = response.json()
        # A generic adapter exception is not proof of a safe failed opening.
        # Observe the retained uncertainty instead of inventing a terminal fact.
        assert failed['possible_effect'] and not failed['retry_safe']
        assert server.marker.with_name(server.marker.name + '.boundary').read_text(encoding='utf-8') == boundary
        assert not server.marker.exists()  # neither injected boundary spawns a peer
        assert SECRET not in json.dumps(opened) + json.dumps(failed)
        for table in ('execution_receipts', 'execution_event_ingress', 'runtime_recovery_events'):
            assert SECRET not in json.dumps(rows(server, 'SELECT * FROM ' + table))
        sid = opened['data']['scope']['session_id']
        for route in (f'/v1/runtime/sessions/{sid}/events', f'/api/v1/harness/sessions/{sid}/events'):
            response = server.client.get(route, headers={'Authorization': 'Bearer ' + server.subject})
            assert response.status_code == 200, response.text
            assert SECRET not in response.text
        assert not rows(server, "SELECT 1 FROM execution_sessions WHERE lifecycle_state='READY'")
        assert SECRET not in server.log_path.read_text(encoding='utf-8')
    finally:
        # Generic exceptions cannot prove absence of effects to Core. Keep
        # its uncertainty classification; end only this disposable process.
        server.close()
