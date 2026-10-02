"""The packaged dashboard must not break schema generation for the HTTP API."""

from importlib.resources import files

from fastapi.testclient import TestClient

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.bootstrap.dependencies import bootstrap


def test_dashboard_and_openapi_are_served_together(tmp_path):
    # Without the packaged index, build_app takes a different route branch and
    # cannot catch unresolved annotations on the actual FileResponse endpoint.
    assert files('okto_nexus').joinpath(
        'adapters/inbound/http/static/index.html').is_file()
    deps = bootstrap({}, ['--home', str(tmp_path / 'home'),
                          '--feature-harness-integrations', 'false',
                          '--embedding-mode', 'off'])
    app = build_app(deps)
    with TestClient(app, client=('127.0.0.1', 50000),
                    base_url='http://127.0.0.1',
                    raise_server_exceptions=False) as client:
        index = client.get('/')
        assert index.status_code == 200
        assert index.headers['content-type'].startswith('text/html')
        response = client.get('/api/v1/openapi.json')
        assert response.status_code == 200, response.text
        schema = response.json()
        assert schema['openapi'].startswith('3.')
        assert 'get' in schema['paths']['/v1/connections/protocol']
        assert 'post' in schema['paths']['/v1/runtime/operations']
        assert 'post' in schema['paths']['/v1/connections/bindings:prepare']
