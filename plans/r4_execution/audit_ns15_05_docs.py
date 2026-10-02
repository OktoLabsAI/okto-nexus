"""Check documented commands/routes against the imported installed Server.

This is supporting documentation evidence, not complete TR4-15-05 acceptance:
resources, dashboard and TN-38/39/40 still require their own scenario evidence.
Run with an installed campaign interpreter using -I.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

import okto_nexus


def main():
    root = Path(__file__).resolve().parents[2]
    package = Path(okto_nexus.__file__).resolve().parent
    assert not package.is_relative_to(root), 'Use an installed interpreter with -I'
    guide = root / 'docs/harness-integrations/r4-operations.md'
    text = guide.read_text(encoding='utf-8')
    commands = re.findall(r'^okto-nexus (.+--help)$', text, re.M)
    assert len(commands) == 7, commands
    results = []
    for command in commands:
        argv = [sys.executable, '-I', '-m',
                'okto_nexus.adapters.inbound.cli.main', *shlex.split(command)]
        result = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8')
        assert result.returncode == 0, (argv, result.stdout, result.stderr)
        assert 'usage:' in result.stdout.lower(), (argv, result.stdout)
        results.append({'argv': argv, 'returncode': result.returncode,
                        'help_sha256': hashlib.sha256(result.stdout.encode()).hexdigest()})
    routes = set()
    route_sources = {}
    for name in ('connections_v1.py', 'runtime_v1.py'):
        source = package / 'adapters/inbound/http' / name
        route_sources[name] = hashlib.sha256(source.read_bytes()).hexdigest()
        for node in ast.walk(ast.parse(source.read_text(encoding='utf-8'))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {'get', 'post', 'put', 'patch', 'delete'}
                    and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                routes.add((node.func.attr.upper(), '/v1' + node.args[0].value))
    documented = sorted(set(re.findall(r'`(GET|POST|PUT|PATCH|DELETE) (/v1/[^`]+)`', text)))
    assert len(documented) >= 13
    assert set(documented) <= routes, set(documented) - routes
    links = re.findall(r'\]\(([^)#]+)(?:#[^)]*)?\)', text)
    assert all((guide.parent / link).is_file() for link in links)
    from nexus_connector_core import catalog
    catalog_source = Path(catalog.__file__).read_text(encoding='utf-8')
    for adapter in ('codex_app_server', 'pi_rpc', 'claude_stream', 'claude_attach'):
        assert f'`{adapter}`' in text and f'"{adapter}"' in catalog_source
    report = {'scope': 'NS15.05 supporting docs audit; NOT full scenario acceptance',
              'package_path': str(package), 'guide_sha256': hashlib.sha256(guide.read_bytes()).hexdigest(),
              'commands': results, 'routes': documented, 'route_source_sha256': route_sources,
              'links_checked': len(links), 'status': 'PASSED',
              'remaining': ['resource/dashboard review', 'TN-38', 'TN-39', 'TN-40',
                            'final artifact and release acceptance']}
    output = root / 'plans/r4_execution/evidence/ns15-05-docs.json'
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
