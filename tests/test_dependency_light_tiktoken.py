"""Dependency-light invariant for the workspace-analytics tokenizer (T3).

The "size = TOKENS" feature pulls in tiktoken, a heavy dependency. It MUST stay
behind the serve-only tokenizer adapter, loaded lazily - importing the stdio
core never drags tiktoken in (BR6 / AC9), and the analytics path keeps it behind
the port (AC10 / hexagonal layering).

Scenario coverage (spec bf6e06dc):
* S10/AC9  - importing the core MCP server does NOT add 'tiktoken' to sys.modules
* S11/AC10 - the application analytics modules + the HTTP routes + the tokenizer
  module top-level never import tiktoken (it is lazy, inside the adapter methods)
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "okto_nexus"


def _top_level_imports(rel: str) -> set[str]:
    """Top-level (module-scope) imported root package names of a source file.

    Imports nested inside functions/methods are EXCLUDED - that is exactly the
    lazy-import seam we want to allow (tiktoken inside a method is fine).
    """
    tree = ast.parse((SRC / rel).read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in tree.body:  # module body only -> top-level statements
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_analytics_application_modules_never_import_tiktoken():
    for rel in (
        "application/workspace_analytics.py",
        "application/workspace_overview.py",
    ):
        assert "tiktoken" not in _top_level_imports(rel), rel


def test_http_routes_never_import_tiktoken():
    assert "tiktoken" not in _top_level_imports(
        "adapters/inbound/http/routes.py"
    )


def test_tokenizer_adapter_imports_tiktoken_lazily():
    # The adapter module top-level must NOT import tiktoken; the real import
    # lives inside TiktokenTokenizer._ensure_encoding / resolve_tokenizer.
    assert "tiktoken" not in _top_level_imports(
        "adapters/outbound/tokenizer/__init__.py"
    )
    source = (SRC / "adapters/outbound/tokenizer/__init__.py").read_text(
        encoding="utf-8"
    )
    assert "import tiktoken" in source  # it IS used, just lazily


def test_core_stdio_import_does_not_pull_tiktoken():
    """A fresh process importing the stdio core leaves tiktoken unloaded."""
    script = (
        "import sys; import okto_nexus.adapters.inbound.mcp.server as _s; "
        "print('tiktoken' in sys.modules)"
    )
    env = {**os.environ, "PYTHONPATH": str(SRC.parent)}
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "False"
