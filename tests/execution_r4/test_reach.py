from fastapi.testclient import TestClient
from importlib import metadata

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.application.reach import MINIMUM_CLI_VERSION


def test_reach_is_public_without_runtime_activation(tmp_path):
    deps = bootstrap({}, ['--home', str(tmp_path / 'home')])
    client = TestClient(build_app(deps), client=('203.0.113.10', 1234))
    response = client.get('/v1/reach')
    assert response.status_code == 200, response.text
    assert response.json() == dict(service='okto-nexus',
        server_version=metadata.version('okto-nexus'),
        server_core_version=metadata.version('nexus-connector-core'),
        minimum_cli_version=MINIMUM_CLI_VERSION)
    assert response.headers['cache-control'] == 'no-store'
    assert client.get('/v1/runtime/sessions').status_code == 401


def test_reach_reports_missing_optional_core_honestly(monkeypatch):
    from okto_nexus.application.reach import reach_info
    def version(name):
        if name == 'nexus-connector-core': raise metadata.PackageNotFoundError(name)
        return '1.2.3'
    monkeypatch.setattr(metadata, 'version', version)
    assert reach_info()['server_core_version'] is None
    assert reach_info()['server_version'] == '1.2.3'
