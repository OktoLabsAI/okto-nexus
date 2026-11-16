"""The new service depends on a port; persistence is composed in bootstrap."""
import ast
import inspect
from pathlib import Path

import okto_nexus
from okto_nexus.application.home_entries import HomeEntriesService


def test_entries_inner_layers_have_no_persistence_or_transport_imports():
    root = Path(okto_nexus.__file__).resolve().parent
    for relative in ('domain/home_entries.py', 'domain/home_entry_pages.py',
                     'application/home_entries.py', 'application/home_ports.py'):
        path = root / relative
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            modules = ([a.name for a in node.names] if isinstance(node, ast.Import) else
                       [node.module or ''] if isinstance(node, ast.ImportFrom) else [])
            assert not [m for m in modules if set(m.split('.')) & {'adapters', 'sqlite3', 'mcp', 'fastapi'}], (relative, modules)
    parameter = inspect.signature(HomeEntriesService).parameters['queries']
    assert parameter.default is inspect.Parameter.empty
