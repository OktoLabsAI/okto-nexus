import json
import re
import tempfile
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.testclient import TestClient
from okto_nexus.adapters.inbound.http import app as http_app
from okto_nexus.bootstrap.dependencies import bootstrap

with tempfile.TemporaryDirectory(prefix='nexus-openapi-053-') as root:
    deps = bootstrap({}, ['--home', str(Path(root) / 'home')])
    broken = http_app.build_app(deps)
    report = {'module': http_app.__file__, 'diagnostic_only': True}
    try:
        broken.openapi()
    except Exception as error:
        report['before'] = {'type': type(error).__name__, 'message': str(error)}
    else:
        raise AssertionError('Expected the installed schema generation failure')
    # In-process diagnostic of a module-level import; never changes the installed
    # wheel or source checkout used by the live immutable regression campaign.
    http_app.FileResponse = FileResponse
    fixed = http_app.build_app(deps)
    schema = fixed.openapi()
    report['after'] = {'schema_paths': len(schema['paths']), 'openapi': schema['openapi']}
    contract = Path('D:/Projetos/Techridy/okto_labs_okto_nexus/plans/02_CONTRATOS_HTTP_NXL_E_ESTADOS.md').read_text(encoding='utf-8')
    required = re.findall(r'(GET|POST|PUT|DELETE) `(/v1/[^`]+)`', contract)
    normalize = lambda path: re.sub(r'\{[^}]+\}', '{}', path)
    report['route_audit'] = {
        'document': 'plans/02_CONTRATOS_HTTP_NXL_E_ESTADOS.md',
        'required_count': len(required),
        'absent_from_openapi': [
            {'method': method, 'path': path}
            for method, path in required
            if not any(normalize(path) == normalize(actual) and method.lower() in operations
                       for actual, operations in schema['paths'].items())
        ],
        'limit': 'Schema absence requires source/runtime confirmation; a route may deliberately be excluded from OpenAPI.'
    }
    with TestClient(fixed, client=('127.0.0.1', 50000), base_url='http://127.0.0.1') as client:
        response = client.get('/api/v1/openapi.json')
        assert response.status_code == 200, response.text
        report['after']['http_status'] = response.status_code
        assert client.get('/').status_code == 200
    output = Path('D:/Projetos/Techridy/okto_labs_okto_nexus/plans/r4_execution/evidence/openapi-053-diagnostic.json')
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
